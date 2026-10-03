# Lets a tournament link (or a start.gg short link, or a bare slug) be used
# where an event link is expected: ParseTournamentInput works out what the
# text points to, and FetchTournamentEvents lists the tournament's events so
# one can be picked. Kept free of Qt so the set tournament dialog and the web
# server can share it.
import re
import requests
import orjson
from loguru import logger

from ..Helpers.TSHDirHelper import TSHResolve

STARTGG_GQL_URL = "https://www.start.gg/api/-/gql"
STARTGG_URL = "https://www.start.gg/"
STARTGG_HEADERS = {
    "client-version": "20",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
}
PARRY_URL = "https://parry.gg/"
REQUEST_TIMEOUT_SECS = 20
PARRY_TIMEOUT_SECS = 10

# Errors FetchTournamentEvents can raise, so callers can show their own text
ERROR_NOT_FOUND = "not_found"
ERROR_NO_EVENTS = "no_events"
ERROR_PARRY_KEY = "parrygg_api_key_missing"

# Event states, the same for every provider
STATE_UPCOMING = "upcoming"
STATE_ACTIVE = "active"
STATE_COMPLETED = "completed"

_STARTGG_EVENT = re.compile(r"(.*start\.gg/tournament/[^/?#]*/event[s]?/[^/?#]*)")
_STARTGG_ADMIN_EVENT = re.compile(r".*start\.gg/admin/tournament/[^/?#]+/brackets/[^/?#]+")
_STARTGG_TOURNAMENT = re.compile(r".*start\.gg/(?:admin/)?tournament/([^/?#]+)")
_STARTGG_SHORT = re.compile(r".*start\.gg/([^/?#]+)/?(?:[?#].*)?$")
_PARRY = re.compile(r".*parry\.gg/(.*)")
_BARE_SLUG = re.compile(r"^[A-Za-z0-9_-]+$")
_BARE_EVENT_PATH = re.compile(r"^tournament/[^/?#]+/event[s]?/[^/?#]+$")
_BARE_TOURNAMENT_PATH = re.compile(r"^tournament/([^/?#]+)/?$")

# parry.gg paths that aren't tournaments
_PARRY_RESERVED = {"profile", "_manage"}


class TournamentLookupError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def NormalizeEventURL(url):
    # Turns any supported event URL into the form the providers load
    if "start.gg" in url:
        matches = _STARTGG_EVENT.match(url)
        if matches:
            url = matches.group(0)
            # Some URLs in startgg have eventS but the API doesn't work with that format
            url = url.replace("/events/", "/event/")
    elif "parry.gg" in url:
        # Remove the "_manage" part of admin urls first
        url = url.replace("/_manage", "")
        matches = re.match("(.*parry.gg/[^/]*/[^/]*)", url)
        if matches:
            url = matches.group()
    return url


def ParseTournamentInput(text):
    """Works out what the pasted text points to.

    Returns one of:
      {"kind": "event", "url": ...} - load it straight away
      {"kind": "tournament", "provider": "startgg"|"parrygg"|None,
       "slug": ..., "short": bool} - pick one of its events first
      None - not something TSH can load
    A None provider is a bare slug, which could be on either site.
    """
    text = (text or "").strip()
    if not text:
        return None

    if "start.gg" in text:
        if _STARTGG_EVENT.match(text) or _STARTGG_ADMIN_EVENT.match(text):
            return {"kind": "event", "url": NormalizeEventURL(text)}
        matches = _STARTGG_TOURNAMENT.match(text)
        if matches:
            return {"kind": "tournament", "provider": "startgg", "slug": matches.group(1), "short": False}
        matches = _STARTGG_SHORT.match(text)
        if matches and matches.group(1) not in ("tournament", "admin"):
            return {"kind": "tournament", "provider": "startgg", "slug": matches.group(1), "short": True}
        return None

    if "parry.gg" in text:
        matches = _PARRY.match(text)
        path = matches.group(1).split("?")[0].split("#")[0] if matches else ""
        segments = [s for s in path.split("/") if s and s != "_manage"]
        if not segments or segments[0] in _PARRY_RESERVED:
            return None
        if len(segments) >= 2:
            return {"kind": "event", "url": NormalizeEventURL(text)}
        return {"kind": "tournament", "provider": "parrygg", "slug": segments[0], "short": False}

    # No site given: a bare slug or a start.gg path without the domain
    text = text.strip("/")
    if _BARE_EVENT_PATH.match(text):
        return {"kind": "event", "url": NormalizeEventURL(STARTGG_URL + text)}
    matches = _BARE_TOURNAMENT_PATH.match(text)
    if matches:
        return {"kind": "tournament", "provider": "startgg", "slug": matches.group(1), "short": False}
    if _BARE_SLUG.match(text):
        return {"kind": "tournament", "provider": None, "slug": text, "short": False}
    return None


def FetchTournamentEvents(parsed, parryApiKey=None):
    """Lists the events of a tournament ParseTournamentInput found.

    Returns {"provider", "tournamentName", "tournamentUrl", "events": [...]},
    each event being {"name", "url", "numEntrants", "game", "gameId",
    "startAt", "state", "location"}. Raises TournamentLookupError.
    """
    provider = parsed.get("provider")
    slug = parsed.get("slug")

    if provider == "startgg":
        result = _FetchStartGG(slug, short=parsed.get("short", False))
    elif provider == "parrygg":
        if not parryApiKey:
            raise TournamentLookupError(ERROR_PARRY_KEY, "A parry.gg API key is needed to load parry.gg tournaments")
        result = _FetchParryGG(slug, parryApiKey)
    else:
        # A bare slug: try start.gg first, then parry.gg if there's a key for it
        result = _FetchStartGG(slug, short=False)
        if result is None and parryApiKey:
            result = _FetchParryGG(slug, parryApiKey)

    if result is None:
        raise TournamentLookupError(ERROR_NOT_FOUND, f"Tournament '{slug}' was not found")
    if not result.get("events"):
        raise TournamentLookupError(ERROR_NO_EVENTS, f"Tournament '{result.get('tournamentName')}' has no events")
    return result


def _ReadQuery(name):
    with open(TSHResolve(f"src/TournamentDataProvider/StartGG{name}Query.txt"), "r") as f:
        return f.read()


def _StartGGShortLinkSlug(shortSlug):
    # A short link (start.gg/gx2) redirects to the tournament's page.
    # The API also takes some short slugs as a tournament slug, but not all
    # of them, and a short slug can be the real slug of another tournament.
    try:
        response = requests.get(
            STARTGG_URL + shortSlug,
            headers={"User-Agent": STARTGG_HEADERS["User-Agent"]},
            allow_redirects=False,
            timeout=REQUEST_TIMEOUT_SECS
        )
        location = response.headers.get("Location", "")
        matches = re.search(r"/tournament/([^/?#]+)", location)
        if response.is_redirect and matches:
            return matches.group(1)
    except requests.exceptions.RequestException as e:
        logger.error(f"start.gg short link {shortSlug}: {e.__class__.__name__}: {e}")
    return None


def _QueryStartGGTournament(slug):
    try:
        response = requests.post(
            STARTGG_GQL_URL,
            headers=STARTGG_HEADERS,
            json={
                "operationName": "TournamentEventsQuery",
                "variables": {"slug": slug},
                "query": _ReadQuery("TournamentEvents")
            },
            timeout=REQUEST_TIMEOUT_SECS
        )
        data = orjson.loads(response.text)
    except (requests.exceptions.RequestException, orjson.JSONDecodeError) as e:
        logger.error(f"start.gg TournamentEventsQuery: {e.__class__.__name__}: {e}")
        return None
    if isinstance(data, dict) and data.get("errors"):
        logger.warning(f"start.gg TournamentEventsQuery returned errors: {data.get('errors')}")
    return ((data or {}).get("data") or {}).get("tournament")


def _FetchStartGG(slug, short):
    tournament = None
    if short:
        realSlug = _StartGGShortLinkSlug(slug)
        if realSlug:
            tournament = _QueryStartGGTournament(realSlug)
    if tournament is None:
        tournament = _QueryStartGGTournament(slug)
    if tournament is None:
        return None
    return MapStartGGTournament(tournament)


_STARTGG_STATES = {
    "CREATED": STATE_UPCOMING,
    "ACTIVE": STATE_ACTIVE,
    "COMPLETED": STATE_COMPLETED,
}


def MapStartGGTournament(tournament):
    events = []
    for event in tournament.get("events") or []:
        videogame = event.get("videogame") or {}
        events.append({
            "name": event.get("name", ""),
            "url": NormalizeEventURL(STARTGG_URL + event.get("slug", "")),
            "numEntrants": event.get("numEntrants") or 0,
            "game": videogame.get("displayName") or videogame.get("name") or "",
            "gameId": videogame.get("id"),
            "startAt": event.get("startAt"),
            "state": _STARTGG_STATES.get(event.get("state"), STATE_UPCOMING),
            "location": "online" if event.get("isOnline") else "offline",
        })
    return {
        "provider": "startgg",
        "tournamentName": tournament.get("name", ""),
        "tournamentUrl": STARTGG_URL + (tournament.get("slug") or ""),
        "events": events,
    }


def _FetchParryGG(slug, apiKey):
    import grpc
    from parrygg.services.tournament_service_pb2_grpc import TournamentServiceStub
    from parrygg.services.tournament_service_pb2 import GetTournamentRequest

    try:
        with grpc.secure_channel("api.parry.gg:443", grpc.ssl_channel_credentials()) as channel:
            request = GetTournamentRequest()
            request.tournament_slug = slug
            response = TournamentServiceStub(channel).GetTournament(
                request, metadata=[("x-api-key", apiKey)], timeout=PARRY_TIMEOUT_SECS)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.UNAUTHENTICATED:
            raise TournamentLookupError(ERROR_PARRY_KEY, "Invalid parry.gg API key")
        if e.code() != grpc.StatusCode.NOT_FOUND:
            logger.error(f"ParryGG gRPC error: {e}")
        return None
    return MapParryGGTournament(response.tournament, slug)


def MapParryGGTournament(tournament, slug):
    from parrygg.models.event_pb2 import EventState, LocationType
    from parrygg.models.slug_pb2 import SlugType

    states = {
        EventState.EVENT_STATE_IN_PROGRESS: STATE_ACTIVE,
        EventState.EVENT_STATE_COMPLETED: STATE_COMPLETED,
    }
    locations = {
        LocationType.LOCATION_TYPE_ONLINE: "online",
        LocationType.LOCATION_TYPE_OFFLINE: "offline",
        LocationType.LOCATION_TYPE_HYBRID: "hybrid",
    }

    # Event URLs use the tournament's primary slug, like parry.gg's own links
    tournamentSlug = next(
        (s.slug for s in tournament.slugs if s.type == SlugType.SLUG_TYPE_PRIMARY), slug)

    events = []
    for event in tournament.events:
        events.append({
            "name": event.name,
            "url": PARRY_URL + tournamentSlug + "/" + event.slug,
            "numEntrants": event.entrant_count,
            "game": event.game.name,
            # The parry provider sets the game from this (see GetTournamentData)
            "gameId": event.game.slug or None,
            "startAt": event.start_date.seconds or None,
            "state": states.get(event.state, STATE_UPCOMING),
            "location": locations.get(event.location_type, ""),
        })
    return {
        "provider": "parrygg",
        "tournamentName": tournament.name,
        "tournamentUrl": PARRY_URL + tournamentSlug,
        "events": events,
    }
