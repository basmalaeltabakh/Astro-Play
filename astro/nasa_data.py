"""NASA DONKI (space weather) access for Outpost Command.

DONKI = NASA CCMC's Space Weather Database Of Notifications, Knowledge, Information.  Official API (OpenAPI 2.0):
https://ccmc.gsfc.nasa.gov/DONKI/api/  with server https://ccmc.gsfc.nasa.gov/DONKI-API  and paths /get/FLR, /get/CME,
/get/GST, /get/SEP (startDate / endDate as yyyy-MM-dd, at most a 60-day window).  The official spec declares no
authentication, so NO API key is read or sent.  This module
counts recent solar flares, coronal mass ejections, geomagnetic storms and solar energetic particle events and turns
those counts into ONE 0..1 "solar activity" number that the outpost simulation passes to ``outpost.roll_event``.
The simulation itself never imports this module and never touches the network.

HONEST DATA RULES
  * Every result carries a ``source`` label: "live" (fetched just now), "cached" (an earlier live fetch, with its
    date), "archived" (a bundled snapshot, with its date) or "default" (no NASA data at all).
  * Archived or cached data is never presented as live, and a "default" is never presented as NASA data.
  * The 0..1 number is a GAMEPLAY MAPPING of event counts (see ``outpost_config.DONKI``), not a scientific index and
    not a space-weather forecast.

``get_solar_activity`` never raises.  Live requests share one time budget (``DONKI["budget_s"]``): each request's timeout
is capped to what is left of it and the first failure ends the attempt, so a dead service costs at most one timeout.
Nothing secret is involved: requests carry only the two dates, and error messages never include the request URL.
"""
import datetime as dt
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config
from . import outpost_config as C
from .fileio import as_aware, atomic_write_text, local_date, local_now, local_text, parse_time

log = logging.getLogger("astro.nasa_data")

LIVE, CACHED, ARCHIVED, DEFAULT = "live", "cached", "archived", "default"
SOURCES = (LIVE, CACHED, ARCHIVED, DEFAULT)
COUNT_KEYS = ("flare_x", "flare_m", "flare_c", "flare_minor", "cme", "gst", "gst_strong", "sep")
_USER_AGENT = "AstroPlay/1.0 (educational game)"


class DonkiError(Exception):
    """A DONKI request failed. The message is short and never contains the request URL."""


@dataclass(frozen=True)
class SolarActivity:
    level: float                          # 0..1 game solar-activity value for ``roll_event``
    source: str                           # one of SOURCES
    as_of: Optional[str] = None           # LOCAL date the data was retrieved (live/cached) or snapshotted (archived)
    window: Optional[tuple] = None        # (start, end) ISO dates the counts cover
    counts: Dict[str, int] = field(default_factory=dict)
    retrieved_at: Optional[str] = None    # exact moment of that retrieval, ISO with UTC offset (NOT an event date)
    latest_event: Optional[str] = None    # the newest NASA event, with the time NASA gave it (UTC), never altered

    @property
    def is_live(self) -> bool:
        return self.source == LIVE

    @property
    def is_nasa_data(self) -> bool:
        return self.source != DEFAULT

    @property
    def source_key(self) -> str:
        return f"op_src_{self.source}"

    @property
    def level_key(self) -> str:
        lo, hi = C.DONKI["levels"]
        return "op_solar_low" if self.level < lo else "op_solar_medium" if self.level < hi else "op_solar_high"

    def describe(self, lang: Optional[str] = None) -> str:
        """Localized, honest one-line description of where this number came from."""
        from . import i18n
        return i18n.t(self.source_key, lang, date=self.as_of or "")

    def retrieved_text(self, tz: Optional[dt.tzinfo] = None) -> Optional[str]:
        """When this data was retrieved from NASA, in local time ('YYYY-MM-DD HH:MM'). Falls back to the date alone."""
        return local_text(self.retrieved_at, tz) or self.as_of

    @property
    def latest_event_date(self) -> Optional[str]:
        """Date (UTC, as NASA reported it) of the newest event in the window, or None if there were none."""
        return self.latest_event[:10] if self.latest_event else None


# ---------------------------------------------------------------------------------------------- fetching
_ID_FIELD = {"FLR": "flrID", "CME": "activityID", "GST": "gstID", "SEP": "sepID"}   # official DONKI event ids


def fetch_events(endpoint: str, start: dt.date, end: dt.date, session=None, timeout=None) -> List[dict]:
    """Return the list of DONKI events of one endpoint ('FLR', 'CME', 'GST' or 'SEP') for a date window.

    Raises DonkiError on any problem (HTTP error, rate limit, timeout, bad JSON)."""
    if endpoint not in C.DONKI["endpoints"]:
        raise ValueError(f"Unknown DONKI endpoint: {endpoint!r}")
    import requests
    session = session or requests
    try:
        r = session.get(f"{config.DONKI_BASE_URL}/{endpoint}",
                        params={"startDate": start.isoformat(), "endDate": end.isoformat()},
                        headers={"User-Agent": _USER_AGENT}, timeout=timeout or C.DONKI["timeout_s"])
    except requests.RequestException as e:                       # keep errors short: type only, never the URL
        raise DonkiError(f"{endpoint}: {type(e).__name__}") from None
    if r.status_code == 429:
        raise DonkiError(f"{endpoint}: rate limited")
    if r.status_code != 200:
        raise DonkiError(f"{endpoint}: HTTP {r.status_code}")
    body = (r.text or "").strip()
    if not body:                                                  # DONKI answers an empty body when nothing happened
        return []
    try:
        data = r.json()
    except ValueError:
        raise DonkiError(f"{endpoint}: not JSON") from None
    if not isinstance(data, list):
        raise DonkiError(f"{endpoint}: unexpected response shape")
    return [e for e in data if isinstance(e, dict)]


# ---------------------------------------------------------------------------------------------- counting
def _max_kp(event: dict) -> float:
    best = 0.0
    for k in event.get("allKpIndex") or []:
        try:
            best = max(best, float(k.get("kpIndex", 0)))
        except (TypeError, ValueError, AttributeError):
            continue
    return best


def _unique(endpoint: str, events: List[dict]) -> List[dict]:
    """Drop repeated event ids (one real event must never count twice). Entries without an id are all kept."""
    seen, out = set(), []
    for ev in events:
        eid = ev.get(_ID_FIELD[endpoint])
        if eid is not None:
            if eid in seen:
                continue
            seen.add(eid)
        out.append(ev)
    return out


def summarize(events: Dict[str, List[dict]]) -> Dict[str, int]:
    """Count events by kind. ``events`` maps endpoint code -> event list. Unreadable entries are skipped."""
    counts = {k: 0 for k in COUNT_KEYS}
    events = {ep: _unique(ep, events.get(ep, [])) for ep in _ID_FIELD}
    for ev in events.get("FLR", []):
        cls = str(ev.get("classType") or "").strip().upper()[:1]
        counts["flare_" + cls.lower() if cls in ("X", "M", "C") else "flare_minor"] += 1
    counts["cme"] = len(events.get("CME", []))
    for ev in events.get("GST", []):
        counts["gst"] += 1
        counts["gst_strong"] += _max_kp(ev) >= C.DONKI["gst_strong_kp"]
    counts["sep"] = len(events.get("SEP", []))
    return counts


def activity_level(counts: Dict[str, int]) -> float:
    """Game solar activity 0..1 from event counts (gameplay mapping defined in outpost_config.DONKI)."""
    pts = C.DONKI["points"]
    total = sum(max(0, int(counts.get(k, 0))) * pts[k] for k in pts)
    return max(0.0, min(1.0, total / C.DONKI["full_points"]))


# ---------------------------------------------------------------------------------------------- storage
def _read(path: Path) -> Optional[dict]:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(d, dict) or not isinstance(d.get("counts"), dict) or not d.get("fetched_at"):
            return None
        if parse_time(d["fetched_at"]) is None:
            return None
        return d
    except Exception:
        return None


def _write(path: Path, window, counts: Dict[str, int], now: dt.datetime, latest_event: Optional[str] = None):
    payload = {"fetched_at": as_aware(now).isoformat(timespec="seconds"), "window": [window[0], window[1]],
               "counts": {k: int(counts.get(k, 0)) for k in COUNT_KEYS}}
    if latest_event:
        payload["latest_event"] = latest_event
    atomic_write_text(path, json.dumps(payload, indent=2))          # an interrupted write cannot corrupt the old cache


_TIME_FIELDS = {"FLR": ("peakTime", "beginTime"), "CME": ("startTime",), "GST": ("startTime",), "SEP": ("eventTime",)}
_NASA_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def latest_event_time(events: Dict[str, List[dict]]) -> Optional[str]:
    """The newest event time among the given DONKI events, exactly as NASA wrote it (UTC). Only reads timestamps; an
    event without a valid time is ignored, and nothing is ever replaced by today's date. None if there is no event."""
    best = None
    for ep, items in (events or {}).items():
        for ev in items or []:
            for key in _TIME_FIELDS.get(ep, ()):
                value = ev.get(key) if isinstance(ev, dict) else None
                if isinstance(value, str) and _NASA_TIME.match(value) and (best is None or value > best):
                    best = value
    return best


def _from_record(rec: dict, source: str) -> SolarActivity:
    counts = {k: int(rec["counts"].get(k, 0)) for k in COUNT_KEYS}
    win = rec.get("window")
    when = parse_time(rec["fetched_at"])
    newest = rec.get("latest_event") if isinstance(rec.get("latest_event"), str) else None
    if newest is None and isinstance(rec.get("events"), dict):           # the bundled archive keeps the events themselves
        newest = latest_event_time(rec["events"])
    return SolarActivity(activity_level(counts), source, local_date(when).isoformat() if when else rec["fetched_at"][:10],
                         tuple(win) if isinstance(win, list) and len(win) == 2 else None, counts,
                         when.isoformat(timespec="seconds") if when else None, newest)


# ---------------------------------------------------------------------------------------------- public API
def _fetch_all(today: dt.date, session=None):
    """Fetch every DONKI endpoint for the configured window -> (start date, {endpoint: events}).
    All must succeed. Raises DonkiError if anything fails or the time budget runs out."""
    start = today - dt.timedelta(days=C.DONKI["window_days"])
    deadline = time.monotonic() + C.DONKI["budget_s"]
    events: Dict[str, List[dict]] = {}
    connect_s, read_s = C.DONKI["timeout_s"]
    for ep in C.DONKI["endpoints"]:
        left = deadline - time.monotonic()
        if left <= 0:
            raise DonkiError("time budget used up")
        events[ep] = fetch_events(ep, start, today, session, (min(connect_s, left), min(read_s, left)))
    return start, events


def fetch_live(today: Optional[dt.date] = None, session=None, now: Optional[dt.datetime] = None) -> SolarActivity:
    """Ask NASA for every DONKI endpoint. All must succeed (a partial answer would understate activity).
    Raises DonkiError if anything fails or the time budget runs out."""
    now = as_aware(now) if now else local_now()
    today = today or local_date(now)
    start, events = _fetch_all(today, session)
    counts = summarize(events)
    return SolarActivity(activity_level(counts), LIVE, local_date(now).isoformat(), (start.isoformat(), today.isoformat()),
                         counts, now.isoformat(timespec="seconds"), latest_event_time(events))


def get_solar_activity(today: Optional[dt.date] = None, session=None,
                       cache_path: Optional[Path] = None, archive_path: Optional[Path] = None,
                       allow_network: bool = True, now: Optional[dt.datetime] = None,
                       force: bool = False) -> SolarActivity:
    """Best available solar activity, always honestly labeled. NEVER raises.

    Order: fresh cache -> live NASA -> older cache -> bundled archive -> neutral default.
    ``force=True`` (the player pressed Refresh) skips the fresh-cache shortcut and always asks NASA first."""
    now = as_aware(now) if now else local_now()
    today = today or local_date(now)
    cache_path = Path(cache_path or config.DONKI_CACHE_PATH)
    archive_path = Path(archive_path or config.DONKI_ARCHIVE_PATH)
    try:
        cached = _read(cache_path)
        if cached:
            age = now - parse_time(cached["fetched_at"])
            if not force and dt.timedelta(0) <= age < dt.timedelta(hours=C.DONKI["cache_ttl_hours"]):
                return _from_record(cached, CACHED)
        if allow_network:
            try:
                live = fetch_live(today, session, now)
                try:
                    _write(cache_path, live.window, live.counts, now, live.latest_event)
                except OSError as e:
                    log.warning("Could not save the DONKI cache (%s).", type(e).__name__)
                return live
            except Exception as e:                               # DonkiError or anything unexpected: use saved data
                log.warning("DONKI unavailable (%s); using saved data.", e if isinstance(e, DonkiError)
                            else type(e).__name__)
        if cached:
            return _from_record(cached, CACHED)
        archived = _read(archive_path)
        if archived:
            return _from_record(archived, ARCHIVED)
    except Exception as e:                                       # a data problem must never stop the game
        log.warning("Solar activity lookup failed (%s); using the default.", type(e).__name__)
    return SolarActivity(C.SOLAR_ACTIVITY_DEFAULT, DEFAULT)


_KEEP = {"FLR": ("flrID", "classType", "beginTime", "peakTime", "endTime"),      # fields stored in the archive,
         "CME": ("activityID", "startTime"),                                        # copied verbatim from the API
         "GST": ("gstID", "startTime", "allKpIndex"),
         "SEP": ("sepID", "eventTime")}


def _project(endpoint: str, events: List[dict]) -> List[dict]:
    """Keep only the fields the game uses. Values are copied exactly as NASA returned them, never altered."""
    return [{k: ev[k] for k in _KEEP[endpoint] if k in ev} for ev in events]


def refresh_archive(path: Optional[Path] = None, today: Optional[dt.date] = None, session=None,
                    now: Optional[dt.datetime] = None) -> SolarActivity:
    """Fetch live DONKI data and store it as the bundled archive snapshot (used by scripts/fetch_donki_archive.py).

    The file keeps the real event values (a verbatim subset of fields), the dates covered, the retrieval time and the
    provenance, so the counts can be re-derived and checked.  Raises DonkiError if live data cannot be fetched:
    an archive is never made up."""
    now = as_aware(now) if now else local_now()
    today = today or local_date(now)
    start, events = _fetch_all(today, session)
    counts = summarize(events)
    window = (start.isoformat(), today.isoformat())
    payload = {
        "fetched_at": now.isoformat(timespec="seconds"), "window": list(window), "counts": counts,
        "provenance": {
            "source": "NASA CCMC DONKI (Space Weather Database Of Notifications, Knowledge, Information)",
            "documentation": "https://ccmc.gsfc.nasa.gov/DONKI/api/", "base_url": config.DONKI_BASE_URL,
            "authentication": "none", "date_format": "yyyy-MM-dd",
            "returned_by_endpoint": {ep: len(events[ep]) for ep in C.DONKI["endpoints"]},
            "note": "Event values are copied verbatim from the API responses (only the fields the game uses are kept). "
                    "counts are derived from these events with nasa_data.summarize(). Archived data is never live data.",
        },
        "events": {ep: _project(ep, events[ep]) for ep in C.DONKI["endpoints"]},
    }
    out = Path(path or config.DONKI_ARCHIVE_PATH)
    atomic_write_text(out, json.dumps(payload, indent=1, ensure_ascii=False))
    return SolarActivity(activity_level(counts), LIVE, local_date(now).isoformat(), window, counts,
                         now.isoformat(timespec="seconds"), latest_event_time(events))


def verify_archive(path: Optional[Path] = None) -> List[str]:
    """Check an archive file. Returns a list of problems (empty = consistent): the counts must equal the counts
    re-derived from the stored events, and the provenance and dates must be present."""
    rec = _read(Path(path or config.DONKI_ARCHIVE_PATH))
    if rec is None:
        return ["missing or unreadable"]
    problems = []
    events, prov = rec.get("events"), rec.get("provenance")
    if not isinstance(events, dict) or set(events) != set(C.DONKI["endpoints"]):
        return ["events missing or incomplete"]
    if summarize(events) != {k: int(rec["counts"].get(k, 0)) for k in COUNT_KEYS}:
        problems.append("counts do not match the stored events")
    if not isinstance(prov, dict) or not prov.get("source") or not prov.get("base_url"):
        problems.append("provenance missing")
    elif prov.get("returned_by_endpoint") != {ep: len(events[ep]) for ep in events}:
        problems.append("returned counts do not match the stored events")
    win = rec.get("window")
    if not (isinstance(win, list) and len(win) == 2):
        problems.append("date range missing")
    return problems
