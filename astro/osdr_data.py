"""NASA OSDR (Open Science Data Repository) study metadata for Outpost Command research cards.

Official API used: the OSDR Biological Data API, version 2.0.0 (https://visualization.osdr.nasa.gov/biodata/api/ , the
landing URL serves its OpenAPI document).  It needs no authentication.  Endpoints used:
  GET /v2/datasets/                   -> {accession: {"REST_URL": ...}} for every dataset
  GET /v2/dataset/{accession}/        -> {accession: {"REST_URL", "assays", "files", "metadata": {...}}}
  GET /v2/query/datasets/?format=json.records&<field path>=<value>   -> filtered rows (may repeat an accession)
The API has no server-side pagination, so paging here is client-side: studies are fetched ``page_size`` at a time.
File lists and data files are never requested (one study can have hundreds of files); only study-level METADATA is used.

HONEST DATA RULES
  * Verified fields are copied from the API (title and description verbatim, in English); nothing is invented.
  * A study is labeled "spaceflight", "ground" or "unknown" from its own metadata. Ground-based work is never presented
    as spaceflight, and a study whose metadata is unclear stays "unknown".
  * Research cards keep NASA's facts apart from the game: the gameplay note is written by us, labeled illustrative, and
    never contains findings or numeric safety thresholds.
  * No restricted data is exposed: records contain study-level descriptive metadata only (no file links, no samples,
    no personal names), and studies not yet publicly released are rejected.

The simulation never imports this module.  ``get_studies`` never raises and never blocks longer than ``OSDR["budget_s"]``.
"""
import datetime as dt
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from . import config
from . import outpost_config as C
from .fileio import as_aware, atomic_write_text, local_date, local_now, local_text, parse_time

log = logging.getLogger("astro.osdr")

LIVE, CACHED, OFFLINE, NONE = "live", "cached", "offline", "none"
SOURCES = (LIVE, CACHED, OFFLINE, NONE)
TOPICS = C.OSDR["topics"]
SETTINGS = ("spaceflight", "ground", "unknown")
ACCESSION = re.compile(r"^OSD-[0-9]{1,5}$")
STUDY_URL = "https://osdr.nasa.gov/bio/repo/data/studies/{accession}"
_USER_AGENT = "AstroPlay/1.0 (educational game)"

# the only keys a study record may contain (anything else, e.g. file links or sample data, is rejected)
RECORD_KEYS = ("accession", "title", "description", "description_truncated", "organism", "material", "mission",
               "project", "platform", "space_program", "managing_center", "assay_types", "setting", "release_date",
               "source_url", "api_url")


class OsdrError(Exception):
    """An OSDR request or record was unusable. Messages are short and never contain URLs.

    ``fatal`` marks a service-level failure (timeout, no connection, rate limit, server error): retrying other studies
    is pointless, so a batch stops. Study-level problems (unknown study, malformed record) are not fatal."""

    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


# ---------------------------------------------------------------------------------------------- small helpers
def _as_list(value) -> List[str]:
    """Normalize a metadata value that may be a string, a list, a number or empty into a list of clean strings."""
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    out = []
    for x in items:
        if isinstance(x, (dict, list, tuple)) or x is None or isinstance(x, bool):
            continue
        t = re.sub(r"\s+", " ", str(x)).strip()
        if t and t not in out:
            out.append(t)
    return out


def _text(value) -> Optional[str]:
    """First clean string of a metadata value, or None."""
    items = _as_list(value)
    return items[0] if items else None


def _trim(text: str, limit: int):
    """Cut a description at a sentence end near ``limit`` characters -> (text, was_cut)."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text, False
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return (cut[:end + 1] if end > limit // 3 else cut.rstrip() + "..."), True


def setting_of(project_types: List[str], platforms: List[str]) -> str:
    """'spaceflight' / 'ground' / 'unknown', judged only from the study's own project type and platform metadata."""
    kinds = " ".join(project_types).lower()
    if "ground" in kinds:
        return "ground"
    if "flight" in kinds:
        return "spaceflight"
    return "unknown"


def _release_date(value) -> Optional[dt.date]:
    try:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return dt.datetime.fromtimestamp(float(value), tz=dt.timezone.utc).date()
    except (OverflowError, OSError, ValueError):
        return None


def paginate(items: Iterable, page_size: int) -> Iterator[list]:
    """Yield successive pages of at most ``page_size`` items (client-side: the API returns everything at once)."""
    page_size = max(1, int(page_size))
    page: list = []
    for item in items:
        page.append(item)
        if len(page) == page_size:
            yield page
            page = []
    if page:
        yield page


def _unique(items: Iterable[str]) -> List[str]:
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ---------------------------------------------------------------------------------------------- requests
def _get_json(path: str, params: Optional[dict], session=None, timeout=None):
    import requests
    session = session or requests
    try:
        r = session.get(f"{config.OSDR_BASE_URL}{path}", params=params, headers={"User-Agent": _USER_AGENT},
                        timeout=timeout or C.OSDR["timeout_s"])
    except requests.RequestException as e:                       # keep errors short: type only, never the URL
        raise OsdrError(f"{type(e).__name__}", fatal=True) from None
    if r.status_code == 429:
        raise OsdrError("rate limited", fatal=True)
    if r.status_code != 200:
        raise OsdrError(f"HTTP {r.status_code}", fatal=r.status_code >= 500)
    try:
        return r.json()
    except ValueError:
        raise OsdrError("not JSON") from None


def list_accessions(session=None, timeout=None) -> List[str]:
    """Every dataset accession the API lists (validated, de-duplicated, in numeric order)."""
    data = _get_json("/v2/datasets/", None, session, timeout)
    if not isinstance(data, dict):
        raise OsdrError("unexpected response shape")
    ids = [k for k in data if isinstance(k, str) and ACCESSION.match(k)]
    return sorted(_unique(ids), key=lambda a: int(a.split("-")[1]))


def search(organism: Optional[str] = None, spaceflight: Optional[Iterable[str]] = None, radiation: bool = False,
           session=None, timeout=None) -> List[dict]:
    """Find candidate studies with the official query endpoint. Filters are exact metadata matches.

    organism: e.g. "lactuca sativa|raphanus sativus" ('|' means OR);  spaceflight: factor values such as
    ("Space Flight",);  radiation: only studies that have an ionizing-radiation factor.
    Returns one dict per accession ({"accession", plus the requested columns}), de-duplicated by accession."""
    f = C.OSDR["filters"]
    params: Dict[str, str] = {"format": "json.records"}
    if organism:
        params[f["organism"]] = organism
    if spaceflight:
        params[f["spaceflight"]] = "|".join(spaceflight)
    if radiation:
        params[f["radiation"]] = ""                                # bare field: adds the column, filters nothing...
    data = _get_json("/v2/query/datasets/", params, session, timeout)
    if not isinstance(data, list):
        raise OsdrError("unexpected response shape")
    merged: Dict[str, dict] = {}
    for row in data:
        acc = row.get("id.accession") if isinstance(row, dict) else None
        if not isinstance(acc, str) or not ACCESSION.match(acc):
            continue                                              # malformed row: skipped, not trusted
        entry = merged.setdefault(acc, {"accession": acc})
        for col, val in row.items():
            if col != "id.accession" and val not in (None, "") and col not in entry:
                entry[col] = val
    if radiation:                                                 # ... so keep only rows where the factor has a value
        merged = {a: e for a, e in merged.items() if e.get(f["radiation"])}
    return sorted(merged.values(), key=lambda e: int(e["accession"].split("-")[1]))


# ---------------------------------------------------------------------------------------------- normalizing
def normalize(accession: str, raw: Any, today: Optional[dt.date] = None) -> dict:
    """Turn one /v2/dataset/{accession}/ response into a validated study record, or raise OsdrError."""
    today = today or dt.date.today()
    if not isinstance(accession, str) or not ACCESSION.match(accession):
        raise OsdrError("invalid accession")
    if not isinstance(raw, dict) or not isinstance(raw.get(accession), dict):
        raise OsdrError("unexpected response shape")
    entry = raw[accession]
    meta = entry.get("metadata")
    if not isinstance(meta, dict):
        raise OsdrError("metadata missing")
    if _text(meta.get("accession")) not in (None, accession):
        raise OsdrError("accession mismatch")
    title = _text(meta.get("study title"))
    if not title:
        raise OsdrError("title missing")
    released = _release_date(meta.get("study public release date"))
    if released is None:
        raise OsdrError("release date missing")
    if released > today:
        raise OsdrError("not publicly released")                 # never expose unreleased / restricted studies
    desc, cut = _trim(_text(meta.get("study description")) or "", C.OSDR["description_chars"])
    mission = meta.get("mission") if isinstance(meta.get("mission"), dict) else {}
    project_types, platforms = _as_list(meta.get("project type")), _as_list(meta.get("experiment platform"))
    rest = entry.get("REST_URL")
    record = {
        "accession": accession, "title": title, "description": desc, "description_truncated": cut,
        "organism": _as_list(meta.get("organism")), "material": _as_list(meta.get("material type")),
        "mission": ({"name": _text(mission.get("name")), "start_date": _text(mission.get("start date")),
                     "end_date": _text(mission.get("end date"))} if _text(mission.get("name")) else None),
        "project": {"identifier": _text(meta.get("project identifier")), "title": _text(meta.get("project title")),
                    "type": _text(project_types)},
        "platform": platforms, "space_program": _as_list(meta.get("space program")),
        "managing_center": _text(meta.get("managing nasa center")),
        "assay_types": _as_list(meta.get("study assay measurement type")),
        "setting": setting_of(project_types, platforms), "release_date": released.isoformat(),
        "source_url": STUDY_URL.format(accession=accession),
        "api_url": rest if isinstance(rest, str) and rest.startswith("https://") else None,
    }
    problems = validate_record(record)
    if problems:
        raise OsdrError("invalid record: " + problems[0])
    return record


def validate_record(rec: Any) -> List[str]:
    """Problems with a study record (empty list = valid). Used for fresh, cached and offline records alike."""
    if not isinstance(rec, dict):
        return ["not an object"]
    problems = []
    extra = set(rec) - set(RECORD_KEYS)
    if extra:
        problems.append(f"unexpected fields: {sorted(extra)}")
    acc = rec.get("accession")
    if not isinstance(acc, str) or not ACCESSION.match(acc):
        problems.append("invalid accession")
        return problems
    if not isinstance(rec.get("title"), str) or not rec["title"].strip():
        problems.append("title missing")
    if rec.get("setting") not in SETTINGS:
        problems.append("invalid setting")
    for k in ("organism", "material", "platform", "space_program", "assay_types"):
        if not isinstance(rec.get(k), list) or not all(isinstance(x, str) for x in rec[k]):
            problems.append(f"{k} must be a list of strings")
    try:
        dt.date.fromisoformat(rec.get("release_date"))
    except (TypeError, ValueError):
        problems.append("release date invalid")
    if rec.get("source_url") != STUDY_URL.format(accession=acc):
        problems.append("source url is not the official study page")
    return problems


def fetch_study(accession: str, session=None, timeout=None, today: Optional[dt.date] = None) -> dict:
    """Retrieve and normalize one study's metadata. Raises OsdrError for any problem."""
    if not isinstance(accession, str) or not ACCESSION.match(accession):
        raise OsdrError("invalid accession")
    return normalize(accession, _get_json(f"/v2/dataset/{accession}/", None, session, timeout), today)


def fetch_studies(accessions: Iterable[str], session=None, today: Optional[dt.date] = None,
                  page_size: Optional[int] = None, max_studies: Optional[int] = None):
    """Fetch several studies page by page -> (records, errors).

    Duplicate accessions are fetched once; a bad STUDY (unknown or malformed) does not stop the others, but a SERVICE
    failure (timeout, no connection, rate limit, server error) ends the batch at once instead of waiting on every study;
    the shared time budget caps each request and ends the run when used up. Skipped studies are reported as errors."""
    accs = _unique(a for a in accessions if isinstance(a, str))[:max_studies or C.OSDR["max_studies"]]
    records: Dict[str, dict] = {}
    errors: Dict[str, str] = {}
    deadline = time.monotonic() + C.OSDR["budget_s"]
    connect_s, read_s = C.OSDR["timeout_s"]
    stopped = None
    for page in paginate(accs, page_size or C.OSDR["page_size"]):
        for acc in page:
            left = deadline - time.monotonic()
            if stopped:
                errors[acc] = stopped
                continue
            if left <= 0:
                errors[acc] = "time budget used up"
                continue
            try:
                records[acc] = fetch_study(acc, session, (min(connect_s, left), min(read_s, left)), today)
            except OsdrError as e:
                errors[acc] = str(e)
                if e.fatal:
                    stopped = "skipped: service unavailable"
    return [records[a] for a in accs if a in records], errors


# ---------------------------------------------------------------------------------------------- stored data
def _now_iso(now: dt.datetime) -> str:
    return as_aware(now).isoformat(timespec="seconds")


def _read_json(path: Path) -> Optional[dict]:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _entries_from(d: Optional[dict], key: str = "studies") -> List[dict]:
    """Valid {record, topic} entries of a cache or offline file (invalid entries are dropped, duplicates merged)."""
    out, seen = [], set()
    items = d.get(key) if isinstance(d, dict) else None
    if not isinstance(items, list):
        return out
    for item in items:
        rec = item.get("verified") if isinstance(item, dict) else None
        topic = (item.get("app") or {}).get("topic") if isinstance(item, dict) else None
        if validate_record(rec) or topic not in TOPICS or rec["accession"] in seen:
            continue
        seen.add(rec["accession"])
        out.append({"record": rec, "topic": topic, "retrieved": item.get("retrieved")})
    return out


def load_offline(path: Optional[Path] = None) -> Tuple[List[dict], Optional[str]]:
    """The curated offline dataset (needs no network) -> (entries, retrieval date). Empty if missing or unreadable."""
    d = _read_json(Path(path or config.OSDR_STUDIES_PATH))
    return _entries_from(d), (d or {}).get("retrieved") if isinstance((d or {}).get("retrieved"), str) else None


def verify_offline(path: Optional[Path] = None) -> List[str]:
    """Check the curated offline dataset. Returns problems (empty = consistent)."""
    d = _read_json(Path(path or config.OSDR_STUDIES_PATH))
    if d is None:
        return ["missing or unreadable"]
    problems = []
    prov = d.get("provenance")
    if not isinstance(prov, dict) or not prov.get("source") or not prov.get("base_url") or \
            not prov.get("verified_vs_app_text"):
        problems.append("provenance missing")
    try:
        dt.date.fromisoformat(d.get("retrieved"))
    except (TypeError, ValueError):
        problems.append("retrieval date missing")
    studies = d.get("studies")
    if not isinstance(studies, list) or not studies:
        return problems + ["no studies"]
    ids = []
    for i, item in enumerate(studies):
        rec = item.get("verified") if isinstance(item, dict) else None
        bad = validate_record(rec)
        if bad:
            problems.append(f"study #{i}: {bad[0]}")
            continue
        ids.append(rec["accession"])
        app = item.get("app")
        if not isinstance(app, dict) or app.get("topic") not in TOPICS or not isinstance(app.get("why_selected"), str):
            problems.append(f"{rec['accession']}: app notes missing")
        if rec["setting"] not in SETTINGS:
            problems.append(f"{rec['accession']}: setting invalid")
        try:
            dt.date.fromisoformat(item.get("retrieved"))
        except (TypeError, ValueError):
            problems.append(f"{rec['accession']}: retrieval date missing")
    if len(ids) != len(set(ids)):
        problems.append("duplicate accession")
    return problems


def _read_cache(path: Path) -> Tuple[List[dict], Optional[dt.datetime]]:
    d = _read_json(path)
    try:
        when = parse_time(d["fetched_at"]) if d else None
    except (KeyError, TypeError):
        when = None
    return (_entries_from(d), when) if when else ([], None)


def _write_cache(path: Path, entries: List[dict], now: dt.datetime) -> None:
    payload = {"fetched_at": _now_iso(now), "studies": [
        {"verified": e["record"], "app": {"topic": e["topic"]}, "retrieved": local_date(now).isoformat()} for e in entries]}
    atomic_write_text(path, json.dumps(payload, indent=1, ensure_ascii=False))   # an interrupted write cannot corrupt the cache


# ---------------------------------------------------------------------------------------------- public API
_FRESHNESS = {OFFLINE: 0, CACHED: 1, LIVE: 2}              # a set is only as fresh as its least fresh study


@dataclass(frozen=True)
class StudySet:
    entries: List[dict]                    # [{"record", "topic", "retrieved", "source"}] one per study
    source: str                            # LIVE only if EVERY study is live; otherwise the least fresh source present
    as_of: Optional[str] = None            # retrieval date of the least fresh study
    errors: Dict[str, str] = field(default_factory=dict)
    retrieved_at: Optional[str] = None     # exact moment (ISO with UTC offset) of the least fresh live/cached retrieval
                                           # (None for the bundled offline set, which only has a date)

    @property
    def is_live(self) -> bool:
        return self.source == LIVE

    def retrieved_text(self, tz: Optional[dt.tzinfo] = None) -> Optional[str]:
        """When the studies were retrieved from NASA, local time ('YYYY-MM-DD HH:MM'); the date alone for the offline set."""
        return local_text(self.retrieved_at, tz) or self.as_of

    @property
    def status_key(self) -> str:
        return f"op_osdr_src_{self.source}"

    @property
    def empty(self) -> bool:
        return not self.entries

    def describe(self, lang: Optional[str] = None) -> str:
        from . import i18n
        return i18n.t(self.status_key, lang, date=self.as_of or "")

    def cards(self) -> List["ResearchCard"]:
        return [build_card(e["record"], e["topic"], e["source"]) for e in self.entries]


def _tag(entries: List[dict], source: str, fallback_date: Optional[str]) -> List[dict]:
    return [{"record": e["record"], "topic": e["topic"], "source": source,
             "retrieved": e.get("retrieved") or fallback_date} for e in entries]


def _combine(parts: List[dict], errors: Dict[str, str], times: Optional[Dict[str, str]] = None) -> StudySet:
    if not parts:
        return StudySet([], NONE, None, errors)
    weakest = min(parts, key=lambda e: _FRESHNESS[e["source"]])
    return StudySet(parts, weakest["source"], min(e["retrieved"] or "" for e in parts
                                                 if e["source"] == weakest["source"]) or None, errors,
                    (times or {}).get(weakest["source"]))


def get_studies(session=None, today: Optional[dt.date] = None, cache_path: Optional[Path] = None,
                offline_path: Optional[Path] = None, allow_network: bool = True,
                now: Optional[dt.datetime] = None, force: bool = False) -> StudySet:
    """Study metadata for the curated topics, always honestly labeled. NEVER raises.

    The curated offline dataset says WHICH studies (accession + topic). For each study the best available copy wins:
    live NASA data > saved cache > curated offline record. Each entry keeps its own source label, and the set is
    labeled with its least fresh source, so offline or saved records are never presented as live.
    ``force=True`` (the player pressed Refresh) skips the fresh-cache shortcut and always asks NASA first."""
    now = as_aware(now) if now else local_now()
    today = today or local_date(now)
    cache_path = Path(cache_path or config.OSDR_CACHE_PATH)
    errors: Dict[str, str] = {}
    try:
        curated, offline_date = load_offline(offline_path)
        wanted = {e["record"]["accession"]: e["topic"] for e in curated}
        cached, when = _read_cache(cache_path)
        cached = [e for e in cached if not wanted or e["record"]["accession"] in wanted]
        cache_date = local_date(when).isoformat() if when else None
        times = {CACHED: when.isoformat(timespec="seconds")} if when else {}
        have = {e["record"]["accession"] for e in cached}
        if (not force and cached and when and dt.timedelta(0) <= now - when < dt.timedelta(days=C.OSDR["cache_ttl_days"])
                and have >= set(wanted)):
            return _combine(_tag(cached, CACHED, cache_date), errors, times)
        live: List[dict] = []
        if allow_network and wanted:
            try:
                records, errors = fetch_studies(list(wanted), session, today)
                live = [{"record": r, "topic": wanted[r["accession"]]} for r in records]
                if live and len(live) == len(wanted):               # the cache is always a complete live snapshot
                    try:
                        _write_cache(cache_path, live, now)
                    except OSError as e:
                        log.warning("Could not save the OSDR cache (%s).", type(e).__name__)
            except Exception as e:
                log.warning("NASA OSDR unavailable (%s); using saved data.", e if isinstance(e, OsdrError)
                            else type(e).__name__)
        parts = _tag(live, LIVE, local_date(now).isoformat())
        times[LIVE] = now.isoformat(timespec="seconds")
        taken = {e["record"]["accession"] for e in parts}
        parts += _tag([e for e in cached if e["record"]["accession"] not in taken], CACHED, cache_date)
        taken |= {e["record"]["accession"] for e in parts}
        parts += _tag([e for e in curated if e["record"]["accession"] not in taken], OFFLINE, offline_date)
        return _combine(parts, errors, times)
    except Exception as e:                                       # a data problem must never stop the game
        log.warning("Research lookup failed (%s).", type(e).__name__)
        return StudySet([], NONE, None, errors)


# ---------------------------------------------------------------------------------------------- research cards
@dataclass(frozen=True)
class ResearchCard:
    """What the UI will show. NASA facts and our gameplay note are separate fields on purpose."""
    accession: str
    topic: str
    setting: str                      # spaceflight | ground | unknown (from the study's own metadata)
    title: str                        # NASA's official title, verbatim (English)
    organism: Tuple[str, ...]
    material: Tuple[str, ...]
    mission: Optional[str]
    platform: Tuple[str, ...]
    assay_types: Tuple[str, ...]
    source_url: str
    data_source: str                  # live | cached | offline: where this record came from
    description: str = ""             # NASA's description, verbatim (English), possibly shortened at a sentence end

    @property
    def topic_key(self) -> str:
        return f"op_osdr_topic_{self.topic}"

    @property
    def setting_key(self) -> str:
        return f"op_osdr_setting_{self.setting}"

    @property
    def summary_key(self) -> str:
        return f"op_osdr_summary_{self.setting}"

    @property
    def gameplay_key(self) -> str:
        return f"op_osdr_game_{self.topic}"

    def render(self, lang: Optional[str] = None) -> Dict[str, str]:
        """Localized card text. 'official_*' fields are NASA's English words; everything else is our labelled text."""
        from . import i18n
        organism = ", ".join(self.organism) if self.organism else i18n.t("op_osdr_unknown_organism", lang)
        return {
            "accession": self.accession, "official_title": self.title, "official_description": self.description,
            "topic": i18n.t(self.topic_key, lang), "setting": i18n.t(self.setting_key, lang),
            "summary": i18n.t(self.summary_key, lang, organism=organism),        # app-written, from verified fields only
            "organism": organism, "mission": self.mission or "", "platform": ", ".join(self.platform),
            "gameplay_note": i18n.t(self.gameplay_key, lang),                    # app-written, labelled illustrative
            "disclaimer": i18n.t("op_osdr_disclaimer", lang), "source_url": self.source_url,
            "source_label": i18n.t("op_osdr_source", lang),
            "data_status": i18n.t(f"op_osdr_card_{self.data_source}", lang),
        }


def build_card(record: dict, topic: str, data_source: str) -> ResearchCard:
    """Make a research card from a validated record. Raises OsdrError for an invalid record or topic."""
    problems = validate_record(record)
    if problems:
        raise OsdrError("invalid record: " + problems[0])
    if topic not in TOPICS:
        raise OsdrError("unknown topic")
    m = record.get("mission")
    return ResearchCard(
        accession=record["accession"], topic=topic, setting=record["setting"], title=record["title"],
        organism=tuple(record["organism"]), material=tuple(record["material"]),
        mission=(m or {}).get("name") if isinstance(m, dict) else None, platform=tuple(record["platform"]),
        assay_types=tuple(record["assay_types"]), source_url=record["source_url"], data_source=data_source,
        description=record.get("description") or "")
