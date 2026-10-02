# Checks that StateManager.NarrowChangedKeys() makes DeepDiff produce exactly
# the same diff as the original changed keys, on random states and changes.
# The narrowing mirrors some DeepDiff internals, so run this after updating
# deepdiff. Run from the repository root: python test/test_state_narrowing.py
import copy
import os
import random
import sys
import types

sys.path.insert(0, os.path.abspath("."))
# Import only the modules needed, not the whole application
package = types.ModuleType("src")
package.__path__ = [os.path.abspath("src")]
sys.modules["src"] = package

from deepdiff import DeepDiff, Delta
from src.StateManager import StateManager
from src.Helpers.TSHDictHelper import deep_get, deep_set, deep_unset, deep_clone

KEYS = ["a", "b", "c", "1", "2", "x y", "q'uote", 'dq"', "back\\slash", "ü"]
SCALARS = [None, 0, 1, 1.0, True, False, "s", "t", "", 2.5, float("nan"),
           -0.0, 0.0, (1, 2), [1, 2], {1: "int"}, {"1": "int"}]


def RandomValue(depth=0):
    r = random.random()
    if depth < 3 and r < 0.35:
        return {random.choice(KEYS): RandomValue(depth + 1) for _ in range(random.randint(0, 4))}
    if r < 0.45:
        return [RandomValue(depth + 1) for _ in range(random.randint(0, 3))] if depth < 3 else 1
    return random.choice(SCALARS)


def Diff(old, new, include_paths):
    try:
        return DeepDiff(old, new, exclude_types=[type(None)], include_paths=include_paths,
                        verbose_level=2, threshold_to_diff_deeper=StateManager.DIFF_DEEPER_THRESHOLD)
    except Exception as e:
        return type(e).__name__


def Comparable(diff):
    if isinstance(diff, str):
        return diff
    view = {}
    for kind, items in diff.items():
        if hasattr(items, "items"):
            view[kind] = {p: repr(v) for p, v in items.items()}
        else:
            view[kind] = sorted(map(str, items))
    try:
        rows = sorted(repr(sorted(r.items())) for r in Delta(diff).to_flat_dicts()) if diff else []
    except Exception as e:
        rows = type(e).__name__
    return view, rows


def Mutate(state):
    paths = []
    for _ in range(random.randint(0, 7)):
        path = [random.choice(["score", "game", "x", "new"])] + \
            [random.choice(KEYS[:6]) for _ in range(random.randint(0, 3))]
        key = ".".join(path)
        try:
            current = deep_get(state, key)
            r = random.random()
            if r < 0.35 and isinstance(current, dict) and current:
                # Same dict with a few changes, like most Set() calls
                value = copy.deepcopy(current)
                for _ in range(random.randint(0, 3)):
                    k = random.choice(list(value.keys()) + KEYS)
                    m = random.random()
                    if m < 0.5:
                        value[k] = RandomValue(2)
                    elif m < 0.7:
                        value.pop(k, None)
                deep_set(state, key, value)
            elif r < 0.5:
                deep_set(state, key, copy.deepcopy(current))
            elif r < 0.85:
                deep_set(state, key, RandomValue(1))
            else:
                deep_unset(state, key)
        except Exception:
            continue
        paths.append(tuple(key.split(".")))
    # Changes made without Set() are only found when no keys are given
    if not paths and random.random() < 0.5 and isinstance(state.get("score"), dict):
        state["score"]["zz"] = RandomValue()
    return paths


def main(iterations=20000, seed=0):
    random.seed(seed)
    mismatches = 0
    for _ in range(iterations):
        base = {"score": RandomValue(), "game": RandomValue(), "x": RandomValue()}
        old = deep_clone(base) if random.random() < 0.5 else copy.deepcopy(base)
        new = copy.deepcopy(base)
        paths = Mutate(new)

        keys = list(set("root" + "".join(f"['{k}']" for k in p) for p in paths))
        expected = Diff(old, new, keys)

        StateManager.lastSavedState = old
        StateManager.state = new
        narrowed = StateManager.NarrowChangedKeys(paths)
        actual = Diff(old, new, narrowed) if narrowed is None or narrowed else {}

        if Comparable(expected) != Comparable(actual):
            mismatches += 1
            if mismatches <= 5:
                print("Mismatch\n  keys:", keys, "\n  narrowed:", narrowed,
                      "\n  expected:", Comparable(expected), "\n  actual:", Comparable(actual))

    print(f"{iterations} iterations, {mismatches} mismatches")
    return mismatches == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
