# Checks Bracket.FromGraph, which builds the bracket widget's bracket from the
# provider's real sets and the links between them (start.gg slot prereqs).
# Run from the repository root: python test/test_bracket_graph.py
import os
import sys
import types

sys.path.insert(0, os.path.abspath("."))
# Import only the modules needed, not the whole application
package = types.ModuleType("src")
package.__path__ = [os.path.abspath("src")]
sys.modules["src"] = package

localeHelper = types.ModuleType("src.Helpers.TSHLocaleHelper")


class TSHLocaleHelper:
    matchNames = {
        "winners_round": "Winners Round {0}",
        "losers_round": "Losers Round {0}",
    }


localeHelper.TSHLocaleHelper = TSHLocaleHelper
helpers = types.ModuleType("src.Helpers")
helpers.__path__ = [os.path.abspath("src/Helpers")]
sys.modules["src.Helpers"] = helpers
sys.modules["src.Helpers.TSHLocaleHelper"] = localeHelper

from src.TSHBracket import Bracket, BracketSet

BYE = BracketSet.BYE
PENDING = BracketSet.PENDING


def Seed(player):
    return {"prereqType": "seed", "prereqId": f"seed{player}", "player": player}


def Winner(setId):
    return {"prereqType": "set", "prereqId": setId, "placement": 1}


def Loser(setId):
    return {"prereqType": "set", "prereqId": setId, "placement": 2}


def Set(id, round, identifier, slots, score=(None, None), finished=False, name=None, winnerSlot=None):
    return {"id": id, "round": round, "identifier": identifier, "name": name,
            "slots": slots, "score": list(score), "finished": finished,
            "winnerSlot": winnerSlot}


def Find(bracket, roundKey, index):
    return bracket.rounds[str(roundKey)][index]


def DoubleElim4(a1=Seed(1), a2=Seed(4)):
    # start.gg puts both grand final sets in the same round. The ids are in
    # a different order than the bracket on purpose.
    return {"sets": [
        Set("90", 1, "B", [Seed(2), Seed(3)], (0, 2), True, "Winners Semi-Final"),
        Set("95", 1, "A", [a1, a2], (2, 0), True, "Winners Semi-Final"),
        Set("80", 2, "C", [Winner("95"), Winner("90")], (2, 1), True, "Winners Final"),
        Set("70", -1, "D", [Loser("95"), Loser("90")], (0, 2), True, "Losers Semi-Final"),
        Set("60", -2, "E", [Loser("80"), Winner("70")], (0, 2), True, "Losers Final"),
        Set("50", 3, "F", [Winner("80"), Winner("60")], name="Grand Final"),
        Set("51", 3, "G", [Winner("50"), Loser("50")], name="Grand Final Reset"),
    ]}


def TestDoubleElimination():
    bracket = Bracket.FromGraph(DoubleElim4(), 4)

    assert bracket.isGraph
    # Winners first then losers, each in play order; the reset gets its own round
    assert list(bracket.rounds.keys()) == ["1", "2", "3", "4", "-1", "-2"], bracket.rounds.keys()
    assert [len(r) for r in bracket.rounds.values()] == [2, 1, 1, 1, 1, 1]

    # Ordered by where they lead, not by id or identifier order
    assert Find(bracket, 1, 0).playerIds == [1, 4]
    assert Find(bracket, 1, 1).playerIds == [2, 3]

    assert Find(bracket, 2, 0).playerIds == [1, 3]
    assert Find(bracket, -1, 0).playerIds == [4, 2]
    assert Find(bracket, -2, 0).playerIds == [3, 2]
    assert Find(bracket, 3, 0).playerIds == [1, 2]
    assert Find(bracket, 4, 0).playerIds == [PENDING, PENDING]

    gf = Find(bracket, 3, 0)
    reset = Find(bracket, 4, 0)
    assert gf.winNext is reset and gf.winNextSlot == 0
    assert gf.loseNext is reset and gf.loseNextSlot == 1
    assert Find(bracket, -2, 0).winNext is gf and Find(bracket, -2, 0).winNextSlot == 1
    assert Find(bracket, 1, 1).loseNext is Find(bracket, -1, 0)
    assert Find(bracket, 1, 1).loseNextSlot == 1
    assert Find(bracket, 4, 0).winNext is None

    assert bracket.GetRoundName("3") == "Grand Final"
    assert bracket.GetRoundName("4") == "Grand Final Reset"
    assert bracket.GetRoundName("-2") == "Losers Final"
    assert bracket.winnersOnlyProgressions

    # Editing a score in the widget moves players along
    gf.score = [1, 3]
    gf.finished = True
    bracket.UpdateBracket()
    assert reset.playerIds == [2, 1]


def TestByes():
    bracket = Bracket.FromGraph(
        DoubleElim4(a2={"prereqType": "bye", "prereqId": None}), 3)

    assert Find(bracket, 1, 0).playerIds == [1, BYE]
    # The bye's "loser" goes to losers, which makes that set a bye too
    assert Find(bracket, -1, 0).playerIds == [BYE, 2]
    assert Find(bracket, -2, 0).playerIds == [3, 2]
    assert Find(bracket, 2, 0).playerIds == [1, 3]


def TestSingleEliminationAndWinnerWithoutScore():
    graph = {"sets": [
        Set("1", 1, "A", [Seed(1), Seed(4)], (None, None), True, winnerSlot=1),
        Set("2", 1, "B", [Seed(2), Seed(3)], (3, 1), True),
        Set("3", 2, "D", [Loser("1"), Loser("2")], name="3rd Place Match"),
        Set("4", 2, "C", [Winner("1"), Winner("2")], name="Final"),
    ]}
    bracket = Bracket.FromGraph(graph, 4)

    assert list(bracket.rounds.keys()) == ["1", "2"]
    # Same round: ordered by identifier
    final, thirdPlace = bracket.rounds["2"]
    assert final.playerIds == [4, 2]
    assert thirdPlace.playerIds == [1, 3]
    assert bracket.GetRoundName("2") == "Final"
    assert bracket.GetRoundName("1") == "Winners Round 1"


def TestMissingSetsAndLosersSeeds():
    graph = {"sets": [
        # Winner/loser of sets in another phase group or left out of the query
        Set("1", 1, "A", [Winner("missing"), Seed(1)]),
        Set("2", -1, "B", [Loser("missing"), Seed(2)]),
    ]}
    bracket = Bracket.FromGraph(graph, 2)

    assert Find(bracket, 1, 0).playerIds == [PENDING, 1]
    assert Find(bracket, -1, 0).playerIds == [BYE, 2]
    # Players are seeded straight into losers
    assert not bracket.winnersOnlyProgressions


def TestInvalidGraphs():
    for graph in [
        {"sets": []},
        {"sets": [Set("1", 0, "A", [Seed(1), Seed(2)])]},
        {"sets": [
            Set("1", 1, "A", [Winner("2"), Seed(1)]),
            Set("2", 1, "B", [Winner("1"), Seed(2)]),
        ]},
    ]:
        try:
            Bracket.FromGraph(graph, 2)
        except ValueError:
            continue
        raise AssertionError(f"Expected {graph} to be rejected")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("Test")]
    for test in tests:
        test()
        print(f"{test.__name__}: OK")
