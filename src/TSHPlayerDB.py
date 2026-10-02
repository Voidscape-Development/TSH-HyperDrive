from multiprocessing import Lock
import os
import json
import orjson
from qtpy.QtGui import *
from qtpy.QtWidgets import *
from qtpy.QtCore import *
import csv
import traceback
from loguru import logger


from .Helpers.TSHDictHelper import deep_clone
from .Helpers.TSHQtHelper import gui_thread_sync
from .TSHGameAssetManager import TSHGameAssetManager
from .SettingsManager import SettingsManager

class TSHPlayerDBSignals(QObject):
    db_updated = Signal()


class TSHPlayerDB:
    signals = TSHPlayerDBSignals()
    database = {}
    model: QStandardItemModel = None
    webServer = None
    modelLock = Lock()
    # Character icons used by the model, built on demand. Reset when a game
    # is loaded, which replaces TSHGameAssetManager's stockIcons.
    iconCache = {}
    iconCacheSource = None
    fieldnames = ["prefix", "gamerTag", "name", "twitter",
                "country_code", "state_code", "mains", "pronoun", "custom_textbox", "controller"] # Used for filtering what we save locally

    @staticmethod
    def LoadDB():
        try:
            json_db_exists = True
            if os.path.exists("./user_data/local_players.json") == False:
                json_db_exists = False
                with open('./user_data/local_players.json', 'wt', encoding='utf-8') as outfile:
                    outfile.write(json.dumps([]))

            if (not json_db_exists) and os.path.exists("./user_data/local_players.csv"):
                logger.info("Importing from the previous version of the player database")
                with open('./user_data/local_players.csv', 'r', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile, quotechar='\'')
                    for player in reader:
                        tag = player.get(
                            "prefix")+" "+player.get("gamerTag") if player.get("prefix") else player.get("gamerTag")
                        if tag not in TSHPlayerDB.database:
                            TSHPlayerDB.database[tag] = player
                            logger.info(f"Import player {tag} from old database")
                            try:
                                player["mains"] = json.loads(
                                    player.get("mains", "{}"))
                            except:
                                player["mains"] = {}
                                logger.error(f"No mains found for: {tag}")

            json_db_exists = True

            if os.path.exists("./user_data/local_players.csv"):
                try:
                    os.remove("./user_data/local_players.csv")
                except Exception as e:
                    logger.error(traceback.format_exc())

            with open('./user_data/local_players.json', 'rb') as jsonfile:
                player_list = orjson.loads(jsonfile.read())
                for player in player_list:
                    tag = player.get("prefix")+" "+player.get("gamerTag") if player.get("prefix") else player.get("gamerTag")
                    if tag not in TSHPlayerDB.database:
                        TSHPlayerDB.database[tag] = player

                        try:
                            player["mains"] = player.get("mains", "{}")
                        except:
                            player["mains"] = {}
                            logger.error(f"No mains found for: {tag}")
            
            TSHPlayerDB.SaveDB()
            TSHPlayerDB.SetupModel()
            
        except Exception as e:
            logger.error(traceback.format_exc())

    @staticmethod
    def AddPlayers(players, overwrite=False):
        logger.info(f"Adding players to DB: {len(players)}")
        for player in players:
            if player is not None:
                tag = player.get(
                    "prefix")+" "+player.get("gamerTag") if player.get("prefix") else player.get("gamerTag")

                if not overwrite:
                    if tag not in TSHPlayerDB.database:
                        incomingMains = player.get("mains", {})
                        for game in incomingMains:
                            for main in incomingMains[game]:
                                if len(main) == 1:
                                    main.append(0)
                        TSHPlayerDB.database[tag] = player
                    else:
                        dbMains = deep_clone(
                            TSHPlayerDB.database[tag].get("mains", {})
                        )
                        if isinstance(dbMains, str):
                            dbMains = json.loads(dbMains)
                        incomingMains = player.get("mains", {})

                        newMains = []
                        for game in incomingMains:
                            for main in incomingMains[game]:
                                if len(main) == 1:
                                    found = next(
                                        (m for m in dbMains.get(game, []) if m[0] == main[0]), None)
                                    if found:
                                        main.append(found[1])
                                    else:
                                        main.append(0)
                                newMains.append(main)
                            dbMains[game] = newMains

                        if SettingsManager.Get("general.disable_overwrite", False):
                            TSHPlayerDB.database[tag] = player | TSHPlayerDB.database[tag]
                        else:
                            TSHPlayerDB.database[tag].update(player)
                        TSHPlayerDB.database[tag]["mains"] = dbMains
                else:
                    if TSHPlayerDB.database.get(tag) is not None and player.get("mains") is not None:
                        try:
                            mains = TSHPlayerDB.database[tag].get("mains", {})
                            mains.update(player.get("mains", {}))
                            player["mains"] = mains
                        except:
                            logger.error(traceback.format_exc())
                    TSHPlayerDB.database[tag] = player

        TSHPlayerDB.SaveDB()
        TSHPlayerDB.SetupModel()

    @staticmethod
    def DeletePlayer(tag):
        if tag in TSHPlayerDB.database:
            del TSHPlayerDB.database[tag]

        TSHPlayerDB.SaveDB()
        TSHPlayerDB.SetupModel()

    @staticmethod
    def GetPlayer(tag):
        """Returns a copy of the player saved under tag (prefix + gamerTag), or None."""
        player = TSHPlayerDB.database.get(tag)
        return deep_clone(player) if player is not None else None

    @staticmethod
    def GetPlayerFromTag(tag):
        for player_db in TSHPlayerDB.database.values():
            if tag.lower() == player_db.get("gamerTag").lower():
                return player_db
        return None

    @staticmethod
    @gui_thread_sync
    def SetupModel():
        with TSHPlayerDB.modelLock:
            TSHPlayerDB.model = QStandardItemModel()

            cancelIcon = QIcon(QPixmap.fromImage(QImage("./assets/icons/cancel.svg").scaledToWidth(
                32, Qt.TransformationMode.SmoothTransformation)))

            stockIcons = TSHGameAssetManager.instance.stockIcons
            if TSHPlayerDB.iconCacheSource is not stockIcons:
                TSHPlayerDB.iconCache = {}
                TSHPlayerDB.iconCacheSource = stockIcons

            def GetCharIcon(char, skin):
                # Only the icons players actually use get decoded and scaled
                key = (char, skin)
                icon = TSHPlayerDB.iconCache.get(key)
                if icon is None:
                    # Misses aren't cached: stockIcons is filled in after
                    # being assigned, so a missing entry may appear later
                    path = stockIcons.get(char, {}).get(skin)
                    if path:
                        icon = QIcon(QPixmap.fromImage(
                            QImage(path).scaledToWidth(
                                32, Qt.TransformationMode.SmoothTransformation)))
                        TSHPlayerDB.iconCache[key] = icon
                return icon

            for player in TSHPlayerDB.database.values():
                if player is not None:
                    try:
                        tag = player.get(
                            "prefix")+" "+player.get("gamerTag") if player.get("prefix") else player.get("gamerTag")

                        item = QStandardItem(tag)
                        item.setIcon(cancelIcon)

                        if player.get("mains") and type(player.get("mains")) == dict:
                            if TSHGameAssetManager.instance.selectedGame.get("codename") in player.get("mains", {}).keys():
                                playerMains = player.get(
                                    "mains")[TSHGameAssetManager.instance.selectedGame.get("codename")]

                                if playerMains is not None and len(playerMains) > 0:
                                    # Must be a list of size 2 [character, skin]
                                    playerMains = [main for main in playerMains if isinstance(
                                        main, list) and (len(main) == 2) or (len(main) == 3)]

                                    # If the skin is invalid, default to 0
                                    for main in playerMains:
                                        while len(main) < 3:
                                            main.append("")
                                        skin = 0
                                        try:
                                            skin = int(main[1])
                                        except:
                                            logger.error(
                                                f'Local DB error: Player {player.get("gamerTag")} has an invalid skin for character {main[0]}')
                                            logger.error(traceback.format_exc())
                                        main[1] = skin

                                        # If no variant, set to none
                                        if len(main) >=3:
                                            variant = main[2]
                                        else:
                                            variant = ""
                                        main[2] = variant
                                        

                                    if playerMains[0][0] in TSHGameAssetManager.instance.characters.keys():
                                        character = playerMains[0]

                                        icon = GetCharIcon(
                                            character[0], int(character[1]))
                                        if icon is not None:
                                            item.setIcon(icon)

                        item.setData(player, Qt.ItemDataRole.UserRole)

                        TSHPlayerDB.model.appendRow(item)
                    except:
                        logger.error(
                            f'Error loading player from local DB: {player.get("gamerTag")}')
                        logger.error(traceback.format_exc())

            TSHPlayerDB.signals.db_updated.emit()

    @staticmethod
    def SaveDB():
        try:
            # One copy of the whole DB, taken in a single call so another
            # thread changing it can't break the loop below
            players = deep_clone(list(TSHPlayerDB.database.values()))

            player_list = [
                {k: v for k, v in player.items() if k in TSHPlayerDB.fieldnames}
                for player in players if player is not None
            ]

            with open('./user_data/local_players.json', 'wb') as outfile:
                outfile.write(orjson.dumps(
                    player_list, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS))
        except Exception as e:
            logger.error(traceback.format_exc())


TSHGameAssetManager.instance.signals.onLoad.connect(TSHPlayerDB.SetupModel)
