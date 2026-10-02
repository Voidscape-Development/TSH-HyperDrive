import math
from .Helpers.TSHLocaleHelper import TSHLocaleHelper
from loguru import logger
import traceback


class BracketSet():
    BYE = -1
    PENDING = -2

    def __init__(self, bracket: "Bracket", pos) -> None:
        self.bracket: Bracket = bracket
        self.playerIds = [BracketSet.BYE, BracketSet.BYE]
        self.score = [0, 0]
        self.winNext: "BracketSet" = None
        self.winNextSlot: int = 0
        self.loseNext: "BracketSet" = None
        self.loseNextSlot: int = 0
        self.pos = pos
        self.finished = False
        # Only used by brackets built with Bracket.FromGraph:
        # slots filled by a seed/bye instead of another set's result
        self.fixedIds = [None, None]
        # Winner reported by the provider, for sets without a decisive score
        self.winnerSlot = None

# Bracket always has a power of 2 number of players
# if there are less than that, we round up and add
# 'bye's as the lower seeded players


def next_power_of_2(x):
    return 1 if x == 0 else 2**math.ceil(math.log2(x))

# Seeding order logic


def seeding(numPlayers):
    rounds = math.log(numPlayers)/math.log(2)-1
    pls = [1, 2]
    for i in range(int(rounds)):
        pls = nextLayer(pls)
    return pls

# Checks if a number is power of 2


def is_power_of_two(n):
    return (n != 0) and (n & (n-1) == 0)


def nextLayer(pls):
    out = []
    length = len(pls)*2+1

    for d in pls:
        out.append(d)
        out.append(length-d)
    return out


def _IdentifierKey(identifier):
    # start.gg identifiers go A, B, ..., Z, AA, AB, ...
    identifier = str(identifier or "")
    return (len(identifier), identifier)


class Bracket():
    # Built from a provider's real set graph (see FromGraph) instead of
    # synthesized as a standard power of 2 double elimination bracket
    isGraph = False

    def __init__(self, playerNumber, progressionsIn, seedMap=None, winnersOnlyProgressions=False, customSeeding=False, progressionsOut=0) -> None:
        self.originalPlayerNumber = playerNumber
        self.playerNumber = next_power_of_2(playerNumber)

        self.progressionsIn = progressionsIn
        self.progressionsOut = progressionsOut

        if seedMap:
            if len(seedMap) < self.playerNumber:
                for i in range(len(seedMap)+1, self.playerNumber+1):
                    seedMap.append(-1)
            seeds = seedMap
        else:
            seeds = seeding(self.playerNumber)

        self.seedMap = seeds

        self.winnersOnlyProgressions = winnersOnlyProgressions

        self.customSeeding = customSeeding

        if progressionsIn > 0 and -1 in self.seedMap:
            self.winnersOnlyProgressions = True

        self.rounds = {}

        for i in range(len(seeds)):
            if seeds[i] > self.originalPlayerNumber:
                seeds[i] = -1

        # Create winners
        self.rounds["1"] = []
        for i in range(self.playerNumber):
            if i % 2 == 0:
                _set = BracketSet(self, [1, len(self.rounds["1"])])
                _set.playerIds[0] = seeds[i]
                _set.playerIds[1] = seeds[i+1]
                self.rounds["1"].append(_set)

        # Create losers
        self.rounds["-1"] = []
        self.rounds["-2"] = []
        for i in range(int(self.playerNumber/2)):
            self.rounds["-1"].append(BracketSet(self,
                                     [-1, int(len(self.rounds["-1"])/2)]))
            self.rounds["-2"].append(BracketSet(self,
                                     [-1, int(len(self.rounds["-2"])/2)]))

        # Fill with -1
        for round in ["-1", "-2"]:
            for _set in self.rounds[round]:
                _set.score = [-1, -1]
                _set.finished = True

        # Expand winners
        subBracket = []
        i = self.playerNumber/2

        while i > 1:
            i = math.floor(i/2)
            round = [BracketSet(self, [2+len(subBracket), i])
                     for i in range(int(i))]
            subBracket.append(round)
        subBracket.append([BracketSet(self, [2+len(subBracket), 0])])
        subBracket.append([BracketSet(self, [2+len(subBracket), 0])])

        for r, round in enumerate(subBracket):
            self.rounds[str(2+r)] = round

        # Expand losers
        subBracket = []
        i = self.playerNumber/2

        while i > 1:
            i = math.floor(i/2)
            for j in range(2):
                round = [BracketSet(self, [-1-len(subBracket), i])
                         for i in range(math.floor(i))]
                subBracket.append(round)

        for r, round in enumerate(subBracket):
            self.rounds[str(-3-r)] = round

        # Connect sets
        for k, round in self.rounds.items():
            roundNum = int(k)

            if roundNum > 0:
                for j, _set in enumerate(round):
                    try:
                        _set.winNext = self.rounds[str(
                            roundNum+1)][math.floor(j/2)]
                        targetIdW = j % 2
                        if int(k) < 0 and abs(int(k)) % 2 == 1:
                            targetIdW = 1
                        _set.winNextSlot = targetIdW
                    except KeyError as e:
                        logger.warning(f"Bracket KeyError: {e}")
                    except:
                        logger.error(traceback.format_exc())
                    try:
                        if abs(roundNum) % 4 == 0:
                            _set.loseNext = self.rounds[str(-int(2*(roundNum)))][(int(len(round)/2)+j) % len(round)]
                        elif abs(roundNum) % 4 == 1:
                            _set.loseNext = self.rounds[str(-int(2*(roundNum)))][j]
                        elif abs(roundNum) % 4 == 2:
                            _set.loseNext = self.rounds[str(-int(2*(roundNum)))][(-1-j) % len(round)]
                        elif abs(roundNum) % 4 == 3:
                            _set.loseNext = self.rounds[str(-int(2*(roundNum)))][(int(len(round)/2)-1-j) % len(round)]

                        targetIdL = 0

                        if roundNum == 1:
                            targetIdL = j % 2

                        _set.loseNextSlot = targetIdL
                    except KeyError as e:
                        logger.warning(f"Bracket KeyError: {e}")
                    except:
                        logger.error(traceback.format_exc())
            else:
                for j, _set in enumerate(round):
                    try:
                        if abs(roundNum) % 2 == 0:
                            _set.winNext = self.rounds[str(
                                roundNum-1)][math.floor(j/2)]
                        else:
                            _set.winNext = self.rounds[str(roundNum-1)][j]
                        targetIdW = j % 2
                        if int(k) < 0 and abs(int(k)) % 2 == 1:
                            targetIdW = 1
                        _set.winNextSlot = targetIdW
                    except KeyError as e:
                        logger.warning(f"Bracket KeyError: {e}")
                    except Exception as e:
                        logger.error(e)

        # Connect losers to winners for grand finals
        lastLosers = min([int(r) for r in self.rounds.keys()])
        gfsRound = max([int(r) for r in self.rounds.keys()]) - 1
        self.rounds[str(lastLosers)][0].winNext = self.rounds[str(gfsRound)][0]

        # Connect grand finals to reset
        gfsResetRound = max([int(r) for r in self.rounds.keys()])
        gfsRound = gfsResetRound - 1
        self.rounds[str(gfsRound)][0].winNext = self.rounds[str(
            gfsResetRound)][0]
        self.rounds[str(gfsRound)][0].loseNext = self.rounds[str(
            gfsResetRound)][0]

    @classmethod
    def FromGraph(cls, graph, playerNumber):
        """
        Builds the bracket from the provider's own sets and the links between
        them, so its shape, losers drops, byes and round names match the
        provider exactly instead of being guessed.

        graph = {"sets": [{
            "id": str, "round": int (> 0 winners, < 0 losers),
            "identifier": str, "name": str (round name),
            "score": [int|None, int|None], "finished": bool,
            "winnerSlot": 0|1|None,
            "slots": [{
                "prereqType": "seed"|"set"|"bye"|...,
                "prereqId": str|None, "placement": 1 (winner)|2 (loser)|None,
                "player": 1-based entrant index|None
            }, ...]
        }, ...]}
        """
        sets = {}
        for s in (graph or {}).get("sets") or []:
            sets.setdefault(str(s.get("id")), s)

        if not sets:
            raise ValueError("Bracket graph has no sets")

        side = {}
        depth = {}
        for id, s in sets.items():
            round = int(s.get("round") or 0)
            if round == 0:
                raise ValueError(f"Set {id} has no round")
            side[id] = 1 if round > 0 else -1
            depth[id] = abs(round)

        def SetPrereqs(s):
            for slotIndex, slot in enumerate((s.get("slots") or [])[:2]):
                prereqId = slot.get("prereqId")
                if slot.get("prereqType") == "set" and prereqId is not None and str(prereqId) in sets:
                    yield slotIndex, str(prereqId), slot.get("placement") or 1

        # Sets must come after the sets that feed them on the same side. The
        # only case where the provider's round numbers don't already do that
        # is the grand final reset, which start.gg puts in the grand final's
        # round.
        for _ in range(len(sets) + 1):
            changed = False
            for id, s in sets.items():
                for _slot, prereqId, _placement in SetPrereqs(s):
                    if side[prereqId] == side[id] and depth[prereqId] >= depth[id]:
                        depth[id] = depth[prereqId] + 1
                        changed = True
            if not changed:
                break
        else:
            raise ValueError("Bracket graph has a cycle")

        # Renumber rounds so each side goes 1, 2, 3... with no gaps
        roundOf = {}
        for sign in (1, -1):
            depths = sorted({depth[id] for id in sets if side[id] == sign})
            remap = {d: i + 1 for i, d in enumerate(depths)}
            for id in sets:
                if side[id] == sign:
                    roundOf[id] = sign * remap[depth[id]]

        columns = {}
        for id in sets:
            columns.setdefault(roundOf[id], []).append(id)

        # Order each round top to bottom by walking back from the last round
        # of each side: the sets feeding a set go where that set is.
        order = {}
        for sign in (1, -1):
            keys = sorted([k for k in columns if k * sign > 0], key=abs)
            if not keys:
                continue

            def ByIdentifier(ids):
                return sorted(ids, key=lambda id: (_IdentifierKey(sets[id].get("identifier")), id))

            order[keys[-1]] = ByIdentifier(columns[keys[-1]])

            for k in reversed(keys[:-1]):
                ordered = []
                seen = set()
                for consumerId in order[keys[keys.index(k) + 1]]:
                    for _slot, prereqId, _placement in SetPrereqs(sets[consumerId]):
                        if roundOf[prereqId] == k and prereqId not in seen:
                            seen.add(prereqId)
                            ordered.append(prereqId)
                ordered.extend(ByIdentifier(
                    [id for id in columns[k] if id not in seen]))
                order[k] = ordered

        bracket = cls.__new__(cls)
        bracket.isGraph = True
        bracket.originalPlayerNumber = playerNumber
        bracket.playerNumber = next_power_of_2(max(playerNumber, 1))
        bracket.progressionsIn = 0
        bracket.progressionsOut = 0
        bracket.seedMap = None
        bracket.customSeeding = False
        bracket.roundNames = {}
        bracket.rounds = {}

        bracketSets = {}
        roundKeys = sorted([k for k in order if k > 0]) + \
            sorted([k for k in order if k < 0], reverse=True)

        for k in roundKeys:
            bracket.rounds[str(k)] = []
            for j, id in enumerate(order[k]):
                s = sets[id]
                _set = BracketSet(bracket, [k, j])
                score = list(s.get("score") or [None, None])[:2]
                score += [None] * (2 - len(score))
                _set.score = [v if v is not None else 0 for v in score]
                _set.finished = bool(s.get("finished"))
                _set.winnerSlot = s.get("winnerSlot")
                bracket.rounds[str(k)].append(_set)
                bracketSets[id] = _set

                if str(k) not in bracket.roundNames and s.get("name"):
                    bracket.roundNames[str(k)] = s.get("name")

        # Entrants coming into the losers side means players progress into
        # this bracket into both winners and losers
        bracket.winnersOnlyProgressions = True

        for id, s in sets.items():
            _set = bracketSets[id]
            slots = (s.get("slots") or [])[:2]
            for slotIndex in range(2):
                slot = slots[slotIndex] if slotIndex < len(slots) else {}
                prereqId = slot.get("prereqId")
                prereqType = slot.get("prereqType")

                if prereqType == "set" and prereqId is not None and str(prereqId) in bracketSets:
                    source = bracketSets[str(prereqId)]
                    if (slot.get("placement") or 1) == 2:
                        source.loseNext = _set
                        source.loseNextSlot = slotIndex
                    else:
                        source.winNext = _set
                        source.winNextSlot = slotIndex
                    _set.playerIds[slotIndex] = BracketSet.PENDING
                    continue

                player = slot.get("player")
                if player:
                    _set.fixedIds[slotIndex] = int(player)
                    if roundOf[id] < 0:
                        bracket.winnersOnlyProgressions = False
                elif prereqType == "set" and (slot.get("placement") or 1) != 2:
                    # Winner of a set we don't have: still to be decided
                    _set.fixedIds[slotIndex] = BracketSet.PENDING
                else:
                    _set.fixedIds[slotIndex] = BracketSet.BYE
                _set.playerIds[slotIndex] = _set.fixedIds[slotIndex]

        # Order to resolve results in: every set after the sets feeding it
        incoming = {_set: 0 for _set in bracketSets.values()}
        for _set in bracketSets.values():
            for nxt in (_set.winNext, _set.loseNext):
                if nxt is not None:
                    incoming[nxt] += 1

        ready = [_set for _set in bracketSets.values()
                 if incoming[_set] == 0]
        bracket.graphOrder = []
        while ready:
            _set = ready.pop()
            bracket.graphOrder.append(_set)
            for nxt in (_set.winNext, _set.loseNext):
                if nxt is not None:
                    incoming[nxt] -= 1
                    if incoming[nxt] == 0:
                        ready.append(nxt)

        if len(bracket.graphOrder) != len(bracketSets):
            raise ValueError("Bracket graph has a cycle")

        bracket.UpdateBracket()

        return bracket

    def _UpdateGraphBracket(self):
        for _set in self.graphOrder:
            for slot in range(2):
                if _set.fixedIds[slot] is not None:
                    _set.playerIds[slot] = _set.fixedIds[slot]
                else:
                    _set.playerIds[slot] = BracketSet.PENDING

        for _set in self.graphOrder:
            p1, p2 = _set.playerIds

            if p1 == BracketSet.BYE and p2 == BracketSet.BYE:
                won, lost = BracketSet.BYE, BracketSet.BYE
            elif p2 == BracketSet.BYE:
                won, lost = p1, BracketSet.BYE
            elif p1 == BracketSet.BYE:
                won, lost = p2, BracketSet.BYE
            elif p1 == BracketSet.PENDING or p2 == BracketSet.PENDING or not _set.finished:
                won, lost = BracketSet.PENDING, BracketSet.PENDING
            else:
                winner = None
                if _set.score[0] != _set.score[1]:
                    winner = 0 if _set.score[0] > _set.score[1] else 1
                elif _set.winnerSlot in (0, 1):
                    # e.g. reported without a score
                    winner = _set.winnerSlot

                if winner is None:
                    won, lost = BracketSet.PENDING, BracketSet.PENDING
                else:
                    won, lost = _set.playerIds[winner], _set.playerIds[1 - winner]

            if _set.winNext:
                _set.winNext.playerIds[_set.winNextSlot] = won
            if _set.loseNext:
                _set.loseNext.playerIds[_set.loseNextSlot] = lost

    def IsBye(self, playerId):
        if playerId == -1 or playerId > self.originalPlayerNumber:
            return True
        return False

    def UpdateBracket(self):
        if self.isGraph:
            self._UpdateGraphBracket()
            return

        for roundKey, round in sorted(self.rounds.items(), key=lambda x: (int(x[0]) < 0, abs(int(x[0])))):
            for j, _set in enumerate(round):
                targetIdW = j % 2
                targetIdL = 0
                if int(roundKey) < 0 and abs(int(roundKey)) % 2 == 1:
                    targetIdW = 1

                lastLosers = min([int(r) for r in self.rounds.keys()])
                if roundKey == str(lastLosers):
                    targetIdW = 1

                gfsRound = max([int(r) for r in self.rounds.keys()]) - 1
                if roundKey == str(gfsRound):
                    targetIdW = 0
                    targetIdL = 1

                # When we have progressions in, force first (hidden) sets to double DQs
                # If we have a non-power of 2 number of progressions, we do it for 2 rounds
                if self.progressionsIn > 0 and not self.winnersOnlyProgressions:
                    if int(roundKey) == 1:
                        _set.score = [-1, -1]
                        _set.finished = True

                    if int(roundKey) == 2 and not is_power_of_two(self.progressionsIn) and not self.customSeeding:
                        _set.score = [-1, -1]
                        _set.finished = True

                if _set.winNext:
                    # Both slots are bye OR slot 2 is bye, auto win for p1
                    if (self.IsBye(_set.playerIds[0]) and self.IsBye(_set.playerIds[1])) or \
                            (not self.IsBye(_set.playerIds[0]) and self.IsBye(_set.playerIds[1])):
                        won = 0
                        lost = 1
                        _set.winNext.playerIds[targetIdW] = _set.playerIds[won]
                        if _set.loseNext:
                            _set.loseNext.playerIds[targetIdL] = _set.playerIds[lost]
                    # Slot 1 is bye, auto win
                    elif self.IsBye(_set.playerIds[0]) and not self.IsBye(_set.playerIds[1]):
                        won = 1
                        lost = 0
                        _set.winNext.playerIds[targetIdW] = _set.playerIds[won]
                        if _set.loseNext:
                            _set.loseNext.playerIds[targetIdL] = _set.playerIds[lost]
                    # -1,-1 draw; advance higher seed
                    elif _set.score[0] == -1 and _set.score[1] == -1:
                        # Advance higher seed
                        won = 0 if _set.playerIds[0] < _set.playerIds[1] else 1
                        lost = 0 if won == 1 else 1
                        _set.winNext.playerIds[targetIdW] = _set.playerIds[won]
                        if _set.loseNext:
                            _set.loseNext.playerIds[targetIdL] = _set.playerIds[lost]
                    # Set not finished, pass pending state
                    elif not _set.finished:
                        _set.winNext.playerIds[targetIdW] = -2
                        if _set.loseNext:
                            _set.loseNext.playerIds[targetIdL] = -2
                    # Real match results
                    else:
                        # P1 wins
                        if _set.score[0] > _set.score[1]:
                            _set.winNext.playerIds[targetIdW] = _set.playerIds[0]
                            if _set.loseNext:
                                _set.loseNext.playerIds[targetIdL] = _set.playerIds[1]
                        # P2 wins
                        elif _set.score[0] < _set.score[1]:
                            _set.winNext.playerIds[targetIdW] = _set.playerIds[1]
                            if _set.loseNext:
                                _set.loseNext.playerIds[targetIdL] = _set.playerIds[0]
                        # Draw
                        else:
                            _set.winNext.playerIds[targetIdW] = -2
                            if _set.loseNext:
                                _set.loseNext.playerIds[targetIdL] = -2

        # Clear scores when no players in set
        # for k, round in sorted(self.rounds.items(), key=lambda x: (int(x[0]) < 0, abs(int(x[0])))):
        #     for j, _set in enumerate(round):
        #         if _set.playerIds[0] == -2 or _set.playerIds[1] == -2:
        #             _set.score[0] = 0
        #             _set.score[1] = 0

    # Get round names
    def GetRoundName(self, round: str, winnersCutout=[0, 0], losersCutout=[0, 0]):
        roundNumber = int(round)

        if self.isGraph:
            name = self.roundNames.get(str(roundNumber))
            if name:
                return name
            if roundNumber > 0:
                return TSHLocaleHelper.matchNames.get("winners_round").format(roundNumber)
            return TSHLocaleHelper.matchNames.get("losers_round").format(abs(roundNumber))

        gfsRound = max([int(r) for r in self.rounds.keys()]) - 1
        lastLosers = min([int(r) for r in self.rounds.keys()])

        if self.progressionsOut <= 0:
            if roundNumber > 0:
                if roundNumber == gfsRound:
                    return TSHLocaleHelper.matchNames.get("grand_final")
                if roundNumber == gfsRound + 1:
                    return TSHLocaleHelper.matchNames.get("grand_final_reset")
                if roundNumber == gfsRound - 1:
                    return TSHLocaleHelper.matchNames.get("winners_final")
                if roundNumber == gfsRound - 2:
                    return TSHLocaleHelper.matchNames.get("winners_semi_final")
                if roundNumber == gfsRound - 3:
                    return TSHLocaleHelper.matchNames.get("winners_quarter_final")
            else:
                if roundNumber == lastLosers:
                    return TSHLocaleHelper.matchNames.get("losers_final")
                if roundNumber == lastLosers + 1:
                    return TSHLocaleHelper.matchNames.get("losers_semi_final")
                if roundNumber == lastLosers + 2:
                    return TSHLocaleHelper.matchNames.get("losers_quarter_final")
                if roundNumber == lastLosers + 3:
                    return TSHLocaleHelper.matchNames.get("losers_top8")

        if roundNumber > 0:
            roundNumber -= winnersCutout[0]
            return TSHLocaleHelper.matchNames.get("winners_round").format(abs(roundNumber))
        if roundNumber < 0:
            roundNumber += losersCutout[0]
            return TSHLocaleHelper.matchNames.get("losers_round").format(abs(roundNumber))

    @staticmethod
    def GetTopN(round_number: int, bracket_size: int):
        print("Input:", round_number, bracket_size)

        if round_number >= 0:
            return bracket_size // (2 ** (round_number-1))
        else:
            return math.ceil(bracket_size / (2 ** (abs(round_number-1)/2)))
