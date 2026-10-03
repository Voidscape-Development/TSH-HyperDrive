# Checks TournamentEventLookup, which lets the set tournament dialog and the
# web server take a tournament link, short link or slug and list its events.
# Run from the repository root: python test/test_tournament_event_lookup.py
import os
import sys
import types

sys.path.insert(0, os.path.abspath("."))
# Import only the modules needed, not the whole application
for name, path in [
    ("src", "src"),
    ("src.Helpers", "src/Helpers"),
    ("src.TournamentDataProvider", "src/TournamentDataProvider"),
]:
    package = types.ModuleType(name)
    package.__path__ = [os.path.abspath(path)]
    sys.modules[name] = package

import src.TournamentDataProvider.TournamentEventLookup as lookup
from src.TournamentDataProvider.TournamentEventLookup import (
    ParseTournamentInput, NormalizeEventURL, FetchTournamentEvents,
    MapStartGGTournament, TournamentLookupError,
    ERROR_NOT_FOUND, ERROR_NO_EVENTS, ERROR_PARRY_KEY,
)


def Event(url):
    return {"kind": "event", "url": url}


def Tournament(provider, slug, short=False):
    return {"kind": "tournament", "provider": provider, "slug": slug, "short": short}


def TestEventLinks():
    for text, expected in [
        ("https://www.start.gg/tournament/genesis-x2/event/melee-singles",
         "https://www.start.gg/tournament/genesis-x2/event/melee-singles"),
        ("https://www.start.gg/tournament/genesis-x2/events/melee-singles/overview",
         "https://www.start.gg/tournament/genesis-x2/event/melee-singles"),
        ("https://www.start.gg/admin/tournament/genesis-x2/brackets/1229469",
         "https://www.start.gg/admin/tournament/genesis-x2/brackets/1229469"),
        ("tournament/genesis-x2/event/melee-singles",
         "https://www.start.gg/tournament/genesis-x2/event/melee-singles"),
        ("https://parry.gg/my-tourney/my-event",
         "https://parry.gg/my-tourney/my-event"),
        ("https://parry.gg/my-tourney/_manage/my-event/main/bracket",
         "https://parry.gg/my-tourney/my-event"),
    ]:
        assert ParseTournamentInput(text) == Event(expected), text


def TestTournamentLinks():
    for text, expected in [
        ("https://www.start.gg/tournament/genesis-x2", Tournament("startgg", "genesis-x2")),
        ("https://www.start.gg/tournament/genesis-x2/details", Tournament("startgg", "genesis-x2")),
        ("start.gg/tournament/genesis-x2/events?filter=1", Tournament("startgg", "genesis-x2")),
        ("https://www.start.gg/admin/tournament/genesis-x2/dashboard", Tournament("startgg", "genesis-x2")),
        ("https://start.gg/gx2", Tournament("startgg", "gx2", short=True)),
        ("start.gg/gx2/", Tournament("startgg", "gx2", short=True)),
        ("tournament/genesis-x2", Tournament("startgg", "genesis-x2")),
        ("https://parry.gg/my-tourney", Tournament("parrygg", "my-tourney")),
        ("  gx2  ", Tournament(None, "gx2")),
    ]:
        assert ParseTournamentInput(text) == expected, text


def TestInvalidInput():
    for text in ["", "   ", None, "https://parry.gg/profile/someone",
                 "https://www.start.gg/user/abc123", "not a slug", "https://example.com/x"]:
        assert ParseTournamentInput(text) is None, text


def TestNormalizeKeepsOtherURLs():
    url = "https://www.start.gg/admin/tournament/x/brackets/1"
    assert NormalizeEventURL(url) == url


def TestMapStartGG():
    result = MapStartGGTournament({
        "name": "Genesis X2",
        "slug": "tournament/genesis-x2",
        "events": [{
            "name": "Melee Singles",
            "slug": "tournament/genesis-x2/event/melee-singles",
            "numEntrants": 1000,
            "startAt": 1739561400,
            "state": "ACTIVE",
            "isOnline": False,
            "videogame": {"id": 1, "name": "Super Smash Bros. Melee", "displayName": "Melee"},
        }, {
            "name": "Side event",
            "slug": "tournament/genesis-x2/event/side-event",
            "numEntrants": None,
            "state": "CREATED",
            "isOnline": True,
            "videogame": None,
        }],
    })
    assert result["provider"] == "startgg"
    assert result["tournamentUrl"] == "https://www.start.gg/tournament/genesis-x2"
    melee, side = result["events"]
    assert melee == {
        "name": "Melee Singles",
        "url": "https://www.start.gg/tournament/genesis-x2/event/melee-singles",
        "numEntrants": 1000,
        "game": "Melee",
        "gameId": 1,
        "startAt": 1739561400,
        "state": "active",
        "location": "offline",
    }
    assert side["numEntrants"] == 0 and side["game"] == "" and side["gameId"] is None
    assert side["state"] == "upcoming" and side["location"] == "online"


def TestMapParryGG():
    try:
        from parrygg.models.tournament_pb2 import Tournament as ParryTournament
        from parrygg.models.event_pb2 import EventState, LocationType
        from parrygg.models.slug_pb2 import SlugType
    except ImportError:
        print("TestMapParryGG: parrygg not installed, skipped")
        return
    tournament = ParryTournament(name="My Tourney")
    tournament.slugs.add(slug="custom", type=SlugType.SLUG_TYPE_CUSTOM)
    tournament.slugs.add(slug="my-tourney", type=SlugType.SLUG_TYPE_PRIMARY)
    event = tournament.events.add(
        name="Singles", slug="singles", entrant_count=32,
        state=EventState.EVENT_STATE_COMPLETED,
        location_type=LocationType.LOCATION_TYPE_HYBRID)
    event.game.name = "Rivals 2"
    event.game.slug = "rivals-2"
    event.start_date.seconds = 1739561400
    result = lookup.MapParryGGTournament(tournament, "custom")
    assert result["tournamentUrl"] == "https://parry.gg/my-tourney"
    assert result["events"] == [{
        "name": "Singles",
        "url": "https://parry.gg/my-tourney/singles",
        "numEntrants": 32,
        "game": "Rivals 2",
        "gameId": "rivals-2",
        "startAt": 1739561400,
        "state": "completed",
        "location": "hybrid",
    }]


def WithFakeProviders(startgg=None, parrygg=None, shortLinks=None):
    calls = []

    def fakeStartGG(slug):
        calls.append(("startgg", slug))
        return (startgg or {}).get(slug)

    def fakeShortLink(slug):
        calls.append(("short", slug))
        return (shortLinks or {}).get(slug)

    def fakeParryGG(slug, key):
        calls.append(("parrygg", slug))
        return (parrygg or {}).get(slug)

    lookup._QueryStartGGTournament = fakeStartGG
    lookup._StartGGShortLinkSlug = fakeShortLink
    lookup._FetchParryGG = fakeParryGG
    return calls


def StartGGTournament(name):
    return {"name": name, "slug": "tournament/" + name, "events": [
        {"name": "Singles", "slug": f"tournament/{name}/event/singles"}]}


def ParryResult(name):
    return {"provider": "parrygg", "tournamentName": name, "tournamentUrl": "",
            "events": [{"name": "Singles"}]}


def ExpectError(code, parsed, key=None):
    try:
        FetchTournamentEvents(parsed, key)
    except TournamentLookupError as e:
        assert e.code == code, e.code
        return
    raise AssertionError(f"Expected {code}")


def TestShortLinkPrefersRedirect():
    # "genesis" is the real slug of another tournament, so the redirect wins
    calls = WithFakeProviders(
        startgg={"genesis": StartGGTournament("genesis"), "genesis-9": StartGGTournament("genesis-9")},
        shortLinks={"genesis": "genesis-9"})
    result = FetchTournamentEvents(Tournament("startgg", "genesis", short=True))
    assert result["tournamentName"] == "genesis-9"
    assert calls == [("short", "genesis"), ("startgg", "genesis-9")]


def TestShortLinkFallsBackToAPI():
    calls = WithFakeProviders(startgg={"tbh11": StartGGTournament("the-big-house-11")})
    result = FetchTournamentEvents(Tournament("startgg", "tbh11", short=True))
    assert result["tournamentName"] == "the-big-house-11"
    assert calls == [("short", "tbh11"), ("startgg", "tbh11")]


def TestBareSlugTriesStartGGThenParry():
    calls = WithFakeProviders(parrygg={"my-tourney": ParryResult("Parry one")})
    result = FetchTournamentEvents(Tournament(None, "my-tourney"), "key")
    assert result["tournamentName"] == "Parry one"
    assert calls == [("startgg", "my-tourney"), ("parrygg", "my-tourney")]

    # Without a parry.gg key only start.gg is tried
    calls = WithFakeProviders(parrygg={"my-tourney": ParryResult("Parry one")})
    ExpectError(ERROR_NOT_FOUND, Tournament(None, "my-tourney"))
    assert calls == [("startgg", "my-tourney")]

    calls = WithFakeProviders(startgg={"my-tourney": StartGGTournament("my-tourney")})
    assert FetchTournamentEvents(Tournament(None, "my-tourney"), "key")["provider"] == "startgg"
    assert calls == [("startgg", "my-tourney")]


def TestErrors():
    WithFakeProviders()
    ExpectError(ERROR_PARRY_KEY, Tournament("parrygg", "my-tourney"))
    ExpectError(ERROR_NOT_FOUND, Tournament("parrygg", "my-tourney"), "key")
    ExpectError(ERROR_NOT_FOUND, Tournament("startgg", "nope"))
    WithFakeProviders(startgg={"empty": {"name": "Empty", "slug": "tournament/empty", "events": None}})
    ExpectError(ERROR_NO_EVENTS, Tournament("startgg", "empty"))


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("Test")]
    for test in tests:
        test()
        print(f"{test.__name__}: OK")
