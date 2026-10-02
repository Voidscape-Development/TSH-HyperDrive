import contextlib
import os

import orjson
import traceback

from deepdiff.helper import DELTA_VIEW
from qtpy.QtCore import QObject, Signal, Slot, QTimer, QCoreApplication, QThread
from deepdiff import DeepDiff, Delta, extract
import shutil
import threading
import requests
from PIL import Image
import time
from loguru import logger
from .Helpers.TSHDictHelper import deep_get, deep_set, deep_unset, deep_clone
from .SettingsManager import SettingsManager

class StateManagerSignals(QObject):
    state_big_change = Signal()
    state_updated = Signal(dict)


class StateManagerSaveScheduler(QObject):
    """Coalesces the saves requested by Set()/Unset() into one save.

    Lives on the GUI thread; request can be emitted from any thread.
    """
    request = Signal()

    def __init__(self):
        super().__init__()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(StateManager.SAVE_DEBOUNCE_MS)
        self.timer.timeout.connect(StateManager.FlushPendingSave)
        self.request.connect(self.Start)

    @Slot()
    def Start(self):
        # Not restarted while active, so a stream of changes can't postpone
        # the save indefinitely.
        if not self.timer.isActive():
            self.timer.start()


class StateManager:
    lastSavedState = {}
    state = {}
    saveBlocked = 0
    signals = StateManagerSignals()
    changedKeys = []
    # Same changes as changedKeys, as tuples of keys, used to update
    # lastSavedState without cloning the whole state
    changedPaths = []
    deltaIndex = 0
    load_error: "str | None" = None

    lock = threading.RLock()
    loop = None

    # Set()/Unset() don't save right away: changes made within this window are
    # exported together in a single save.
    SAVE_DEBOUNCE_MS = 40
    savePending = False
    saveScheduler: "StateManagerSaveScheduler | None" = None

    # Timestamp of the last 0 -> 1 transition of saveBlocked, used by the
    # watchdog to detect a BlockSaving() that never got its ReleaseSaving().
    saveBlockedSince = None

    # If saving stays blocked for longer than this (seconds) while there are
    # pending changes, we assume a block was leaked and force a save.
    DEFAULT_BLOCK_WATCHDOG_SECONDS = 30

    # State paths whose subtrees are excluded from the out/ file export.
    # Use this for large lookup tables that are only useful as JSON (e.g. game.stages).
    EXPORT_EXCLUDED_PREFIXES = (
        "root['game']['stages']",
    )

    @contextlib.contextmanager
    def SaveBlock(watchdog=True):
        StateManager.BlockSaving(watchdog=watchdog)
        try:
            yield
        finally:
            StateManager.ReleaseSaving()

    def BlockSaving(watchdog=True):
        # watchdog=False marks a block that is expected to be long lived (app
        # startup), so the stuck-block watchdog doesn't fire on it.
        with StateManager.lock:
            StateManager.saveBlocked += 1
            if StateManager.saveBlocked == 1:
                StateManager.saveBlockedSince = time.time() if watchdog else None
            if SettingsManager.Get("general.statemanager_logging", False):
                logger.debug("Initial Block - Current Blocking Status: " + str(StateManager.saveBlocked))

    def ReleaseSaving():
        with StateManager.lock:
            StateManager.saveBlocked -= 1
            if SettingsManager.Get("general.statemanager_logging", False):
                logger.debug("Release Block - Current Blocking Status: " + str(StateManager.saveBlocked))

            # More releases than blocks would leave the counter negative, which
            # silently disables every future export just like a leaked block.
            if StateManager.saveBlocked < 0:
                logger.error(
                    "StateManager save block counter went negative "
                    f"({StateManager.saveBlocked}); there is a ReleaseSaving() "
                    "without a matching BlockSaving(). Resetting to 0.")
                StateManager.saveBlocked = 0

            if StateManager.saveBlocked == 0:
                StateManager.saveBlockedSince = None
                StateManager.SaveState()

    def ResetSaveBlock(reason: str):
        """Force saving back to an unblocked state and export immediately.

        Used to recover from an unbalanced BlockSaving() (usually an exception
        thrown between BlockSaving() and ReleaseSaving()), which would
        otherwise stop every export until the application is restarted.
        """
        with StateManager.lock:
            if StateManager.saveBlocked == 0:
                return
            logger.error(
                f"StateManager saving was stuck blocked ({StateManager.saveBlocked}): "
                f"{reason}. Forcing a save.")
            StateManager.saveBlocked = 0
            StateManager.saveBlockedSince = None
            StateManager.SaveState()

    def CheckSaveBlockWatchdog():
        """Recover the export if saving has been blocked for too long."""
        blockedSince = StateManager.saveBlockedSince

        if StateManager.saveBlocked <= 0 or blockedSince is None:
            return

        timeout = SettingsManager.Get(
            "general.statemanager_block_timeout",
            StateManager.DEFAULT_BLOCK_WATCHDOG_SECONDS)

        if timeout <= 0:
            return

        blockedFor = time.time() - blockedSince

        if blockedFor > timeout:
            StateManager.ResetSaveBlock(
                f"saving has been blocked for {blockedFor:.1f}s, which points to a "
                "BlockSaving() without a matching ReleaseSaving()")

    def SaveState():
        if StateManager.saveBlocked != 0:
            return

        with StateManager.lock:
            StateManager.savePending = False
            try:
                StateManager.DoSaveState()
            except Exception as e:
                # An export failure must never escape into a caller that is
                # holding a save block: it would skip that caller's
                # ReleaseSaving() and disable every future export.
                logger.error(traceback.format_exc())

    def RequestSave():
        """Schedule a save shortly, merging it with any other changes made until then."""
        with StateManager.lock:
            StateManager.savePending = True

            if StateManager.saveScheduler is None:
                app = QCoreApplication.instance()
                if app is None:
                    # No event loop to run the timer on, save right away
                    StateManager.SaveState()
                    return
                scheduler = StateManagerSaveScheduler()
                scheduler.moveToThread(app.thread())
                StateManager.saveScheduler = scheduler

            if QThread.currentThread() == StateManager.saveScheduler.thread():
                StateManager.saveScheduler.Start()
            else:
                StateManager.saveScheduler.request.emit()

    def FlushPendingSave():
        """Save now if there are changes waiting for a scheduled save."""
        with StateManager.lock:
            if StateManager.savePending:
                StateManager.SaveState()

    def DoSaveState():
        def EncodeFallback(value):
            # Without this a single value orjson can't handle would stop
            # program_state.json from ever being written again.
            logger.warning(
                f"State contains a {type(value).__name__} value which isn't JSON "
                "serializable; exporting it as text")
            return str(value)

        def ExportAll(ref_diff, changedPaths):
            try:
                StateManager.state.update({"timestamp": time.time()})
                try:
                    encoded = orjson.dumps(
                        StateManager.state, default=EncodeFallback,
                        option=orjson.OPT_NON_STR_KEYS)

                    # Write to a temp file then atomically replace, so a concurrent
                    # reader never sees a truncated file. On Windows the replace can
                    # fail if the browser has the destination open; fall back to a
                    # direct write in that case.
                    tmp_path = "./out/program_state.json.tmp"
                    with open(tmp_path, 'wb') as file:
                        file.write(encoded)
                    try:
                        os.replace(tmp_path, "./out/program_state.json")
                    except PermissionError:
                        os.remove(tmp_path)
                        with open("./out/program_state.json", 'wb') as file:
                            file.write(encoded)
                finally:
                    StateManager.state.pop("timestamp", None)

                if not SettingsManager.Get("general.disable_export", False):
                    StateManager.ExportText(
                        StateManager.lastSavedState, ref_diff)
                StateManager.UpdateLastSavedState(changedPaths)
            except Exception as e:
                logger.error(traceback.format_exc())

        # logger.debug(StateManager.changedKeys)

        changedKeys = list(set(StateManager.changedKeys))
        changedPaths = StateManager.changedPaths

        # Cleared up front: a change we cannot diff must not be retried on every
        # subsequent save, or a single bad key would stall the export for good.
        StateManager.changedKeys = []
        StateManager.changedPaths = []

        try:
            diff = DeepDiff(
                StateManager.lastSavedState,
                StateManager.state,
                exclude_types=[type(None)],
                include_paths=changedKeys,
                verbose_level=2, # Necessary to see values of added items.
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            diff = None

        if diff is not None:
            try:
                delta = Delta(diff).to_flat_dicts()
                # logger.debug(f"State diff length: {diff_count}")
                if len(delta) > 100:
                    StateManager.deltaIndex += 1
                    StateManager.signals.state_big_change.emit()
                elif len(delta) > 0:
                    StateManager.deltaIndex += 1
                    StateManager.signals.state_updated.emit({
                        'delta_index': StateManager.deltaIndex,
                        'delta': delta
                    })
            except TypeError:
                logger.warning(f"Couldn't serialize diff. Changed Keys: {changedKeys}")
            except Exception as e:
                logger.error(traceback.format_exc())
                # Overlays can still resync from the full state.
                StateManager.deltaIndex += 1
                StateManager.signals.state_big_change.emit()

        # When the diff couldn't be computed we still export, so that
        # program_state.json keeps tracking the live state.
        if diff is None or len(diff) > 0:
            # Without a diff (or without changed keys, which makes DeepDiff
            # compare everything) we can't tell what changed, so resync
            # lastSavedState completely.
            ExportAll(
                diff if diff is not None else {},
                changedPaths if diff is not None and changedKeys else None)

    def UpdateLastSavedState(changedPaths):
        """Copy the changed paths of the state into lastSavedState.

        Much cheaper than cloning the whole state on every save. With
        changedPaths=None the whole state is cloned.
        """
        if changedPaths is not None:
            try:
                # Parents first, so a child copied later isn't overwritten
                for path in sorted(set(changedPaths), key=len):
                    src = StateManager.state
                    exists = True
                    for k in path:
                        if isinstance(src, dict) and k in src:
                            src = src[k]
                        else:
                            exists = False
                            break

                    dst = StateManager.lastSavedState
                    for k in path[:-1]:
                        if k not in dst:
                            if not exists:
                                break
                            dst[k] = {}
                        dst = dst[k]
                        if not isinstance(dst, dict):
                            raise TypeError(f"Can't update lastSavedState at {path}")
                    else:
                        if exists:
                            dst[path[-1]] = deep_clone(src)
                        else:
                            dst.pop(path[-1], None)
                return
            except Exception:
                logger.warning(traceback.format_exc())

        StateManager.lastSavedState = deep_clone(StateManager.state)

    def LoadState():
        StateManager.load_error = None
        try:
            with open("./out/program_state.json", 'rb') as file:
                StateManager.state = orjson.loads(file.read())
                # Only changed paths are copied to lastSavedState from now on,
                # so it must start out matching the loaded state
                StateManager.lastSavedState = deep_clone(StateManager.state)
                StateManager.signals.state_big_change.emit()
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error(traceback.format_exc())
            StateManager.load_error = f"./out/program_state.json\n\n{e}"
            StateManager.state = {}
            StateManager.signals.state_big_change.emit()
            StateManager.SaveState()

    def Set(key: str, value):
        # import inspect
        # func = inspect.currentframe().f_back.f_code
        # fname = os.path.split(func.co_filename)[1]
        # logger.debug(f"{func.co_name}({fname}:{func.co_firstlineno}) Setting {key} to {value}")
        with StateManager.lock:
            # StateManager.lastSavedState = deep_clone(StateManager.state)

            deep_set(StateManager.state, key, value)

            final_key = "root"
            for k in key.split("."):
                final_key += f"['{k}']"

            StateManager.changedKeys.append(final_key)
            StateManager.changedPaths.append(tuple(key.split(".")))

            if StateManager.saveBlocked == 0:
                StateManager.RequestSave()
            else:
                StateManager.CheckSaveBlockWatchdog()

    def Unset(key: str):
        # import inspect
        # func = inspect.currentframe().f_back.f_code
        # fname = os.path.split(func.co_filename)[1]
        # logger.debug(f"{func.co_name}({fname}:{func.co_firstlineno}) Deleting {key}")

        with StateManager.lock:
            # StateManager.lastSavedState = deep_clone(StateManager.state)
            deep_unset(StateManager.state, key)

            final_key = "root"
            for k in key.split("."):
                final_key += f"['{k}']"
            StateManager.changedKeys.append(final_key)
            StateManager.changedPaths.append(tuple(key.split(".")))

            if StateManager.saveBlocked == 0:
                StateManager.RequestSave()
            else:
                StateManager.CheckSaveBlockWatchdog()

    def Get(key: str, default=None):
        return deep_get(StateManager.state, key, default)

    def ExportText(oldState, diff):
        # logger.info("ExportState")
        # logger.info(diff)

        mergedDiffs = list(diff.get("values_changed", {}).items())
        mergedDiffs.extend(list(diff.get("type_changes", {}).items()))

        # logger.info(mergedDiffs)

        for changeKey, change in mergedDiffs:
            if any(changeKey.startswith(p) for p in StateManager.EXPORT_EXCLUDED_PREFIXES):
                continue

            # Remove "root[" from start and separate keys
            filename = "/".join(changeKey[5:].replace(
                "'", "").replace("]", "").replace("/", "_").split("["))

            # logger.info(filename)

            if change.get("new_type") == type(None):
                StateManager.RemoveFilesDict(
                    filename, extract(oldState, changeKey))
            else:
                StateManager.CreateFilesDict(
                    filename, change.get("new_value"))

        removedKeys = diff.get("dictionary_item_removed", {})

        for key in removedKeys:
            if any(key.startswith(p) for p in StateManager.EXPORT_EXCLUDED_PREFIXES):
                continue

            item = extract(oldState, key)

            # Remove "root[" from start and separate keys
            filename = "/".join(key[5:].replace(
                "'", "").replace("]", "").replace("/", "_").split("["))

            # logger.info("Removed:", filename, item)

            StateManager.RemoveFilesDict(filename, item)

        addedKeys = diff.get("dictionary_item_added", {})

        for key in addedKeys:
            if any(key.startswith(p) for p in StateManager.EXPORT_EXCLUDED_PREFIXES):
                continue

            try:
                item = extract(StateManager.state, key)

                # Remove "root[" from start and separate keys
                path = "/".join(key[5:].replace(
                    "'", "").replace("]", "").replace("/", "_").split("["))

                # logger.info("Added:", path, item)
                # logger.info("Added:", path, item)

                StateManager.CreateFilesDict(path, item)
            except Exception as e:
                logger.error(traceback.format_exc())

    def CreateFilesDict(path, di):
        parts = [p for p in path.split("/") if p]
        state_key = "root" + "".join(f"['{p}']" for p in parts)
        if any(state_key.startswith(p) for p in StateManager.EXPORT_EXCLUDED_PREFIXES):
            return

        pathdirs = "/".join(path.split("/")[0:-1])

        if not os.path.isdir("./out/"+pathdirs):
            os.makedirs("./out/"+pathdirs)

        if type(di) == dict:
            for k, i in di.items():
                StateManager.CreateFilesDict(
                    path+"/"+str(k).replace("/", "_"), i)
        else:
            # logger.info("try to add: ", path)
            if type(di) == str and di.startswith("./"):
                if os.path.exists(f"./out/{path}" + "." + di.rsplit(".", 1)[-1]):
                    try:
                        os.remove(f"./out/{path}" + "." +
                                  di.rsplit(".", 1)[-1])
                    except Exception as e:
                        logger.error(traceback.format_exc())
                if os.path.exists(di):
                    try:
                        shutil.copyfile(
                            os.path.abspath(di),
                            f"./out/{path}" + "." + di.rsplit(".", 1)[-1])
                    except Exception as e:
                        logger.error(traceback.format_exc())
            elif type(di) == str and di.startswith("http") and (di.endswith(".png") or di.endswith(".jpg")):
                try:
                    if os.path.exists(f"./out/{path}" + "." + di.rsplit(".", 1)[-1]):
                        try:
                            os.remove(f"./out/{path}" +
                                      "." + di.rsplit(".", 1)[-1])
                        except Exception as e:
                            logger.error(traceback.format_exc())

                    def downloadImage(url, dlpath):
                        try:
                            r = requests.get(url, stream=True, timeout=15)
                            if r.status_code == 200:
                                with open(dlpath, 'wb') as f:
                                    r.raw.decode_content = True
                                    shutil.copyfileobj(r.raw, f)
                                    f.flush()
                            if url.endswith(".jpg"):
                                original = Image.open(dlpath)
                                original.save(dlpath.rsplit(
                                    ".", 1)[0]+".png", format="png")
                                os.remove(dlpath)
                        except Exception as e:
                            logger.error(traceback.format_exc())

                    # Not waited on: the save runs on the caller's thread
                    # (usually the GUI), which must not hang on the network.
                    t = threading.Thread(
                        target=downloadImage,
                        args=[
                            di,
                            f"./out/{path}" + "." + di.rsplit(".", 1)[-1]
                        ],
                        daemon=True
                    )
                    t.start()
                except Exception as e:
                    logger.error(traceback.format_exc())
            else:
                with open(f"./out/{path}.txt", 'w', encoding='utf-8') as file:
                    file.write(str(di))

    def RemoveFilesDict(path, di):
        parts = [p for p in path.split("/") if p]
        state_key = "root" + "".join(f"['{p}']" for p in parts)
        if any(state_key.startswith(p) for p in StateManager.EXPORT_EXCLUDED_PREFIXES):
            return

        pathdirs = "/".join(path.split("/")[0:-1])

        if type(di) == dict:
            for k, i in di.items():
                StateManager.RemoveFilesDict(
                    path+"/"+str(k).replace("/", "_"), i)
        else:
            if type(di) == str and (di.startswith("./") or di.startswith("http")):
                try:
                    removeFile = f"./out/{path}" + \
                        "." + di.rsplit(".", 1)[-1]
                    # logger.info("try to remove: ", removeFile)
                    if os.path.exists(removeFile):
                        os.remove(removeFile)
                except:
                    logger.error(traceback.format_exc())
            else:
                try:
                    removeFile = f"./out/{path}.txt"
                    # logger.info("try to remove: ", removeFile)
                    if os.path.exists(removeFile):
                        os.remove(removeFile)
                except:
                    logger.error(traceback.format_exc())

        try:
            # logger.info("Remove path", f"./out/{path}")
            if os.path.exists(f"./out/{path}"):
                shutil.rmtree(f"./out/{path}")
        except:
            logger.error(traceback.format_exc())


if not os.path.exists("./out"):
    os.makedirs("./out/")

if not os.path.isfile("./out/program_state.json"):
    StateManager.SaveState()

StateManager.LoadState()
