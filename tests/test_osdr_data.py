"""NASA OSDR integration tests. No test touches the network (HTTP is replaced by a fake session).

Evidence used besides fakes:
  * tests/fixtures/osdr_openapi.json  : server, authentication and paths copied from the OFFICIAL OSDR Biological Data API
    OpenAPI document (https://visualization.osdr.nasa.gov/biodata/api/, version 2.0.0).
  * tests/fixtures/osdr_recorded.json : REAL responses recorded from that API (trimmed list, real query rows, whole study
    responses). The small dictionaries written inline below are synthetic and only exercise edge cases."""
import ast
import copy
import datetime as dt
import json
import logging
import re
from pathlib import Path

import pytest
import requests

from astro import config, i18n
from astro import osdr_data as O
from astro import outpost_config as C

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "tests" / "fixtures" / "osdr_openapi.json").read_text(encoding="utf-8"))
REAL = json.loads((ROOT / "tests" / "fixtures" / "osdr_recorded.json").read_text(encoding="utf-8"))
TODAY = dt.date(2026, 11, 9)
NOW = dt.datetime(2026, 11, 9, 12, 0, 0)
DAY = dt.timedelta(days=1)


class Resp:
    def __init__(self, status=200, data=None, text=None):
        self.status_code = status
        self.text = text if text is not None else json.dumps(data)

    def json(self):
        return json.loads(self.text)


class FakeSession:
    """Routes by URL path. ``routes`` maps a path (e.g. '/v2/dataset/OSD-1/') to a Resp, an Exception or raw data."""

    def __init__(self, routes=None, default=None):
        self.routes, self.default, self.calls = routes or {}, default, []

    def get(self, url, params=None, headers=None, timeout=None):
        path = url[len(config.OSDR_BASE_URL):]
        self.calls.append({"url": url, "path": path, "params": params, "headers": headers, "timeout": timeout})
        out = self.routes.get(path, self.default)
        if isinstance(out, Exception):
            raise out
        if isinstance(out, Resp):
            return out
        if out is None:
            return Resp(404, text='{"code": 404}')
        return Resp(200, out)


def recorded_routes():
    return {f"/v2/dataset/{acc}/": raw for acc, raw in REAL["datasets"].items()}


ACCS = sorted(REAL["datasets"], key=lambda a: int(a.split("-")[1]))


def real_session():
    return FakeSession(recorded_routes())


def down(exc=None):
    return FakeSession(default=exc or Resp(503, text="upstream connect error"))


def raw_of(acc):
    return copy.deepcopy(REAL["datasets"][acc])


def meta_of(raw):
    return raw[next(iter(raw))]["metadata"]


# ---- a tiny curated dataset built from the real recorded studies (used by the fallback-chain tests)
TOPIC_CYCLE = ("plants", "radiation", "microgravity", "health", "microbes")


def write_offline(path, accs=None, retrieved="2026-10-01"):
    accs = accs or ACCS
    studies = [{"verified": O.normalize(a, raw_of(a), TODAY),
                "app": {"topic": TOPIC_CYCLE[i % 5], "why_selected": "test"}, "retrieved": retrieved}
               for i, a in enumerate(accs)]
    path.write_text(json.dumps({"dataset": "t", "retrieved": retrieved, "studies": studies, "provenance": {
        "source": "s", "base_url": "u", "verified_vs_app_text": "v"}}), encoding="utf-8")
    return path


def get(tmp_path, session, offline=True, now=NOW, **kw):
    off = write_offline(tmp_path / "off.json") if offline else tmp_path / "missing.json"
    return O.get_studies(session, TODAY, tmp_path / "cache.json", off, now=now, **kw)


# ======================================================================= official contract
def test_official_spec_server_authentication_and_paths():
    assert SPEC["servers"] == ["https://visualization.osdr.nasa.gov/biodata/api"]
    assert SPEC["version"] == "2.0.0" and SPEC["security"] is None and SPEC["securitySchemes"] is None
    for p in ("/v2/datasets/", "/v2/dataset/{accessionId}/", "/v2/query/datasets/"):
        assert p in SPEC["paths"]
    assert config.OSDR_BASE_URL == SPEC["servers"][0] or "ASTRO_OSDR_URL" in __import__("os").environ


def test_we_only_use_endpoints_the_official_spec_defines():
    used = {"/v2/datasets/", "/v2/dataset/{accessionId}/", "/v2/query/datasets/"}
    assert used <= set(SPEC["paths"])
    src = (ROOT / "astro" / "osdr_data.py").read_text(encoding="utf-8")
    assert "/files/" not in re.sub(r'"""(?:.|\n)*?"""', "", src.split("class OsdrError")[1])       # never lists files


def test_recorded_real_responses_have_the_documented_shape():
    assert REAL["_recorded"] and REAL["_source"].startswith("https://visualization.osdr.nasa.gov/biodata/api")
    assert all(O.ACCESSION.match(a) for a in REAL["datasets_list"])
    assert all("REST_URL" in v for v in REAL["datasets_list"].values())
    for acc, raw in REAL["datasets"].items():
        entry = raw[acc]
        assert set(entry) == {"REST_URL", "assays", "files", "metadata"}
        assert isinstance(entry["metadata"], dict) and entry["metadata"]["study title"]


# ======================================================================= request construction
def test_list_request():
    s = FakeSession({"/v2/datasets/": REAL["datasets_list"]})
    ids = O.list_accessions(s)
    c = s.calls[0]
    assert c["url"] == f"{config.OSDR_BASE_URL}/v2/datasets/" and c["params"] is None
    assert c["timeout"] == C.OSDR["timeout_s"]
    assert set(c["headers"]) == {"User-Agent"} and "@" not in c["headers"]["User-Agent"]
    assert ids == sorted(REAL["datasets_list"], key=lambda a: int(a.split("-")[1]))


def test_search_request_uses_the_official_canonical_field_paths():
    s = FakeSession({"/v2/query/datasets/": []})
    O.search(organism="lactuca sativa|raphanus sativus", spaceflight=("Space Flight",), session=s)
    c = s.calls[0]
    f = C.OSDR["filters"]
    assert c["path"] == "/v2/query/datasets/"
    assert c["params"] == {"format": "json.records", f["organism"]: "lactuca sativa|raphanus sativus",
                           f["spaceflight"]: "Space Flight"}
    assert f["organism"] == "study.characteristics.organism" and f["spaceflight"] == "study.factor value.spaceflight"
    s = FakeSession({"/v2/query/datasets/": []})
    O.search(radiation=True, session=s)
    assert s.calls[0]["params"] == {"format": "json.records", f["radiation"]: ""}          # bare field = column only
    s = FakeSession({"/v2/query/datasets/": []})
    O.search(spaceflight=C.OSDR["spaceflight_values"], session=s)
    assert s.calls[0]["params"][f["spaceflight"]] == "Space Flight|in-flight|pre-flight|post-flight"   # '|' means OR


def test_study_request_and_no_credentials(monkeypatch):
    acc = ACCS[0]
    for name in ("NASA_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.setenv(name, "SECRET-TEST-VALUE")
    s = real_session()
    O.fetch_study(acc, s, today=TODAY)
    c = s.calls[0]
    assert c["url"] == f"{config.OSDR_BASE_URL}/v2/dataset/{acc}/" and c["params"] is None
    assert "SECRET-TEST-VALUE" not in json.dumps(c, default=str)


@pytest.mark.parametrize("bad", ["", "osd-1", "OSD-", "OSD-1/../x", "OSD-123456", "GLDS-1", None, 5, ["OSD-1"]])
def test_invalid_accessions_never_reach_the_network(bad):
    s = FakeSession()
    with pytest.raises(O.OsdrError):
        O.fetch_study(bad, s, today=TODAY)
    assert s.calls == []


# ======================================================================= searching
def test_successful_search_returns_one_entry_per_accession():
    rows = [{"id.accession": "OSD-48", "study.characteristics.organism": "Mus musculus"},
            {"id.accession": "OSD-3", "study.characteristics.organism": "Mus musculus"}]
    out = O.search(organism="mus musculus", session=FakeSession({"/v2/query/datasets/": rows}))
    assert [e["accession"] for e in out] == ["OSD-3", "OSD-48"]                      # numeric order
    assert out[0]["study.characteristics.organism"] == "Mus musculus"


def test_search_deduplicates_repeated_rows_keeping_every_requested_value():
    real_rows = REAL["query_rows"]
    accs = [r["id.accession"] for r in real_rows]
    assert len(accs) > len(set(accs)), "the real API repeats an accession once per characteristic value"
    out = O.search(organism="x", session=FakeSession({"/v2/query/datasets/": real_rows}))
    assert [e["accession"] for e in out] == sorted(set(accs), key=lambda a: int(a.split("-")[1]))
    assert len({e["accession"] for e in out}) == len(out)


def test_empty_search_results():
    for body in ([], Resp(200, text="[]")):
        assert O.search(organism="nothing", session=FakeSession({"/v2/query/datasets/": body})) == []


def test_radiation_search_keeps_only_studies_with_a_radiation_factor_value():
    f = C.OSDR["filters"]["radiation"]
    rows = [{"id.accession": "OSD-5", f: "Gamma ray 17 Gy"}, {"id.accession": "OSD-6", f: None},
            {"id.accession": "OSD-7", f: ""}]
    out = O.search(radiation=True, session=FakeSession({"/v2/query/datasets/": rows}))
    assert [e["accession"] for e in out] == ["OSD-5"]


def test_malformed_search_rows_are_skipped_not_trusted():
    rows = [{"id.accession": "OSD-1"}, {"id.accession": "bogus"}, {"id.accession": None}, {"x": 1}, "junk", 5, None,
            {"id.accession": "OSD-2"}]
    out = O.search(session=FakeSession({"/v2/query/datasets/": rows}))
    assert [e["accession"] for e in out] == ["OSD-1", "OSD-2"]


def test_search_and_list_reject_the_wrong_shape():
    with pytest.raises(O.OsdrError, match="shape"):
        O.search(session=FakeSession({"/v2/query/datasets/": {"a": 1}}))
    with pytest.raises(O.OsdrError, match="shape"):
        O.list_accessions(FakeSession({"/v2/datasets/": [1, 2]}))


def test_list_accessions_validates_and_orders():
    data = {"OSD-10": {}, "OSD-2": {}, "nonsense": {}, "OSD-": {}, "OSD-1": {}}
    assert O.list_accessions(FakeSession({"/v2/datasets/": data})) == ["OSD-1", "OSD-2", "OSD-10"]


# ======================================================================= metadata retrieval and normalizing
@pytest.mark.parametrize("acc", ACCS)
def test_real_studies_normalize_to_the_exact_record_format(acc):
    rec = O.normalize(acc, raw_of(acc), TODAY)
    assert tuple(rec) == O.RECORD_KEYS and O.validate_record(rec) == []
    meta = meta_of(raw_of(acc))
    assert rec["title"] == re.sub(r"\s+", " ", meta["study title"]).strip()              # official title, verbatim
    assert rec["source_url"] == f"https://osdr.nasa.gov/bio/repo/data/studies/{acc}"
    assert rec["api_url"] == f"{config.OSDR_BASE_URL}/v2/dataset/{acc}/"
    assert rec["setting"] in O.SETTINGS and dt.date.fromisoformat(rec["release_date"]) <= TODAY
    assert rec["organism"] == O._as_list(meta.get("organism"))
    assert len(rec["description"]) <= C.OSDR["description_chars"] + 3


def test_description_is_verbatim_or_cut_at_a_sentence_and_flagged():
    for acc in ACCS:
        raw = meta_of(raw_of(acc)).get("study description") or ""
        rec = O.normalize(acc, raw_of(acc), TODAY)
        full = re.sub(r"\s+", " ", str(raw)).strip()
        if rec["description_truncated"]:
            assert full.startswith(rec["description"].rstrip(".")) or full.startswith(rec["description"])
            assert len(full) > C.OSDR["description_chars"]
        else:
            assert rec["description"] == full


def test_fetch_study_retrieves_and_normalizes_through_the_session():
    acc = ACCS[0]
    rec = O.fetch_study(acc, real_session(), today=TODAY)
    assert rec == O.normalize(acc, raw_of(acc), TODAY)


def test_setting_is_judged_only_from_the_studys_own_metadata():
    cases = [(["Spaceflight Study"], "spaceflight"), (["Flight Study"], "spaceflight"), (["Spaceflight"], "spaceflight"),
             (["spaceflight study"], "spaceflight"), (["Ground Study"], "ground"), (["GROUND STUDY"], "ground"),
             ([], "unknown"), (["Something else"], "unknown"), (["Ground Study", "Spaceflight Study"], "ground")]
    for types, want in cases:
        assert O.setting_of(types, []) == want, types
    assert O.setting_of([], ["International Space Station (ISS)"]) == "unknown"       # a platform alone proves nothing


def test_real_ground_and_flight_studies_are_labeled_correctly():
    seen = {O.normalize(a, raw_of(a), TODAY)["setting"] for a in ACCS}
    assert {"spaceflight", "ground"} <= seen, "the recorded fixtures must include both kinds"
    for a in ACCS:
        project_type = (O._text(meta_of(raw_of(a)).get("project type")) or "").lower()
        rec = O.normalize(a, raw_of(a), TODAY)
        assert (rec["setting"] == "ground") == ("ground" in project_type)


# ======================================================================= missing and malformed fields
def _with(acc, **changes):
    raw = raw_of(acc)
    meta = raw[acc]["metadata"]
    for k, v in changes.items():
        if v is KeyError:
            meta.pop(k, None)
        else:
            meta[k] = v
    return raw


def test_missing_optional_fields_become_safe_empty_values():
    acc = ACCS[0]
    raw = _with(acc, **{k: KeyError for k in ("organism", "material type", "mission", "experiment platform",
                                              "space program", "managing nasa center", "study assay measurement type",
                                              "project type", "project title", "project identifier",
                                              "study description")})
    rec = O.normalize(acc, raw, TODAY)
    assert rec["organism"] == rec["material"] == rec["platform"] == rec["space_program"] == rec["assay_types"] == []
    assert rec["mission"] is None and rec["managing_center"] is None and rec["description"] == ""
    assert rec["setting"] == "unknown" and rec["project"] == {"identifier": None, "title": None, "type": None}
    assert O.validate_record(rec) == []


@pytest.mark.parametrize("field", ["study title"])
def test_a_study_without_a_usable_title_is_rejected(field):
    acc = ACCS[0]
    for bad in (KeyError, "", "   ", None, [], ["", None]):
        with pytest.raises(O.OsdrError, match="title"):
            O.normalize(acc, _with(acc, **{field: bad}), TODAY)


@pytest.mark.parametrize("value", ["A", ["A", "B"], ["", None, "A"], 5, {"a": 1}, True, [[1]]])
def test_list_or_string_fields_are_normalized_without_errors(value):
    acc = ACCS[0]
    rec = O.normalize(acc, _with(acc, organism=value, **{"material type": value, "experiment platform": value}), TODAY)
    assert all(isinstance(x, str) for x in rec["organism"] + rec["material"] + rec["platform"])


def test_list_valued_real_fields_are_handled():
    kinds = {type(meta_of(raw_of(a)).get(k)).__name__ for a in ACCS for k in ("organism", "material type",
                                                                              "experiment platform", "project type")}
    assert "str" in kinds
    for a in ACCS:
        rec = O.normalize(a, raw_of(a), TODAY)
        assert all(isinstance(x, str) and x == x.strip() and "  " not in x for x in rec["organism"] + rec["platform"])


@pytest.mark.parametrize("raw", [None, [], "x", 5, {}, {"OSD-9": None}, {"OSD-9": []}, {"OSD-9": {}},
                                 {"OSD-9": {"metadata": None}}, {"OSD-9": {"metadata": []}},
                                 {"OSD-8": {"metadata": {"study title": "x"}}}])
def test_malformed_responses_are_rejected(raw):
    with pytest.raises(O.OsdrError):
        O.normalize("OSD-9", raw, TODAY)


def test_accession_mismatch_inside_the_metadata_is_rejected():
    acc = ACCS[0]
    with pytest.raises(O.OsdrError, match="mismatch"):
        O.normalize(acc, _with(acc, accession="OSD-99999"), TODAY)


def test_bad_release_dates_are_rejected():
    acc = ACCS[0]
    for bad in (KeyError, None, "yesterday", "", [], True, float("inf"), 10 ** 30):
        with pytest.raises(O.OsdrError, match="release"):
            O.normalize(acc, _with(acc, **{"study public release date": bad}), TODAY)


def test_unreleased_studies_are_never_exposed():
    acc = ACCS[0]
    tomorrow = int(dt.datetime.combine(TODAY + DAY, dt.time(12), tzinfo=dt.timezone.utc).timestamp())
    with pytest.raises(O.OsdrError, match="not publicly released"):
        O.normalize(acc, _with(acc, **{"study public release date": tomorrow}), TODAY)
    today_ts = int(dt.datetime.combine(TODAY, dt.time(1), tzinfo=dt.timezone.utc).timestamp())
    assert O.normalize(acc, _with(acc, **{"study public release date": today_ts}), TODAY)["release_date"] == "2026-11-09"


def test_invalid_records_are_flagged():
    rec = O.normalize(ACCS[0], raw_of(ACCS[0]), TODAY)
    for change, fragment in [({"accession": "x"}, "invalid accession"), ({"title": ""}, "title missing"),
                             ({"setting": "moon"}, "invalid setting"), ({"organism": "Mus"}, "list of strings"),
                             ({"release_date": "soon"}, "release date"), ({"source_url": "https://evil"}, "source url"),
                             ({"files": ["a.fastq"]}, "unexpected fields")]:
        assert any(fragment in p for p in O.validate_record({**rec, **change})), change
    assert O.validate_record("nope") == ["not an object"]


# ======================================================================= pagination and duplicates
def test_pagination_splits_into_pages():
    assert list(O.paginate(range(7), 3)) == [[0, 1, 2], [3, 4, 5], [6]]
    assert list(O.paginate([], 3)) == [] and list(O.paginate([1], 5)) == [[1]]
    assert list(O.paginate(range(4), 0)) == [[0], [1], [2], [3]]                      # a bad page size is clamped
    assert list(O.paginate((x for x in "abcd"), 2)) == [["a", "b"], ["c", "d"]]       # works on generators


def test_fetching_goes_page_by_page_in_order_and_respects_the_limit():
    s = real_session()
    recs, errs = O.fetch_studies(ACCS, s, TODAY, page_size=2)
    assert [c["path"] for c in s.calls] == [f"/v2/dataset/{a}/" for a in ACCS] and errs == {}
    assert [r["accession"] for r in recs] == ACCS
    s = real_session()
    recs, _ = O.fetch_studies(ACCS, s, TODAY, page_size=1, max_studies=2)
    assert len(s.calls) == 2 and len(recs) == 2


def test_duplicate_accessions_are_fetched_once_and_returned_once():
    s = real_session()
    recs, errs = O.fetch_studies([ACCS[0], ACCS[1], ACCS[0], ACCS[1], ACCS[0]], s, TODAY)
    assert len(s.calls) == 2 and [r["accession"] for r in recs] == [ACCS[0], ACCS[1]] and errs == {}


def test_one_bad_study_does_not_stop_the_others():
    routes = recorded_routes()
    routes[f"/v2/dataset/{ACCS[1]}/"] = Resp(404, text="nope")                       # unknown study: a study-level problem
    routes["/v2/dataset/OSD-77777/"] = {"OSD-77777": {"metadata": {"study title": ""}}}
    recs, errs = O.fetch_studies([ACCS[0], ACCS[1], "OSD-77777", ACCS[2]], FakeSession(routes), TODAY)
    assert [r["accession"] for r in recs] == [ACCS[0], ACCS[2]]
    assert errs == {ACCS[1]: "HTTP 404", "OSD-77777": "title missing"}


@pytest.mark.parametrize("failure", [requests.Timeout("t"), requests.ConnectionError("c"), Resp(503, text="x"),
                                     Resp(500, text="x"), Resp(429, text="slow")])
def test_a_service_failure_ends_the_batch_at_once_instead_of_waiting_on_every_study(failure):
    s = down(failure)
    recs, errs = O.fetch_studies(ACCS, s, TODAY)
    assert recs == [] and len(s.calls) == 1                                           # one attempt, not one per study
    assert set(errs) == set(ACCS) and list(errs.values()).count("skipped: service unavailable") == len(ACCS) - 1


def test_a_service_failure_midway_keeps_the_studies_already_fetched():
    routes = recorded_routes()
    routes[f"/v2/dataset/{ACCS[2]}/"] = requests.Timeout("t")
    s = FakeSession(routes)
    recs, errs = O.fetch_studies(ACCS, s, TODAY)
    assert [r["accession"] for r in recs] == ACCS[:2] and len(s.calls) == 3
    assert errs[ACCS[2]] == "Timeout" and all(errs[a] == "skipped: service unavailable" for a in ACCS[3:])


def test_the_error_class_marks_service_failures_as_fatal_and_study_problems_as_not():
    for resp, fatal in ((Resp(503, text="x"), True), (Resp(429, text="x"), True), (Resp(404, text="x"), False),
                        (Resp(200, text="<html>"), False), (requests.Timeout("t"), True)):
        with pytest.raises(O.OsdrError) as e:
            O.fetch_study("OSD-1", FakeSession({"/v2/dataset/OSD-1/": resp}), today=TODAY)
        assert e.value.fatal is fatal


def test_with_nasa_down_the_whole_lookup_costs_one_attempt_not_one_per_study(tmp_path):
    s = down()
    r = get(tmp_path, s)
    assert len(s.calls) == 1 and r.source == O.OFFLINE and len(r.entries) == len(ACCS)


# ======================================================================= timeouts and HTTP errors
@pytest.mark.parametrize("resp,fragment", [(Resp(429, text="slow"), "rate limited"), (Resp(503, text="x"), "HTTP 503"),
                                           (Resp(404, text="x"), "HTTP 404"), (Resp(500, text="x"), "HTTP 500"),
                                           (Resp(200, text="<html>"), "not JSON")])
def test_bad_http_responses_raise_osdr_error(resp, fragment):
    with pytest.raises(O.OsdrError, match=fragment):
        O.fetch_study("OSD-1", FakeSession({"/v2/dataset/OSD-1/": resp}), today=TODAY)


@pytest.mark.parametrize("exc", [requests.Timeout("timed out"), requests.ConnectionError("https://example.invalid/x?k=1")])
def test_network_errors_become_short_errors_without_the_url(exc):
    with pytest.raises(O.OsdrError) as e:
        O.fetch_study("OSD-1", FakeSession({"/v2/dataset/OSD-1/": exc}), today=TODAY)
    assert "http" not in str(e.value) and e.value.__cause__ is None and e.value.__suppress_context__


def test_time_budget_caps_each_request_and_ends_the_run(monkeypatch):
    s = real_session()
    O.fetch_studies(ACCS, s, TODAY)
    connect, read = C.OSDR["timeout_s"]
    assert all(c["timeout"][0] <= connect and c["timeout"][1] <= read for c in s.calls)
    monkeypatch.setitem(C.OSDR, "budget_s", 2)
    s = real_session()
    O.fetch_studies(ACCS, s, TODAY)
    assert all(c["timeout"][0] <= 2 and c["timeout"][1] <= 2 for c in s.calls)
    clock = iter([0.0, 0.0, 5.0, 99.0, 99.0, 99.0, 99.0, 99.0])
    monkeypatch.setattr(O.time, "monotonic", lambda: next(clock))
    monkeypatch.setitem(C.OSDR, "budget_s", 40)
    s = real_session()
    recs, errs = O.fetch_studies(ACCS[:4], s, TODAY)
    assert len(recs) == 2 and set(errs.values()) == {"time budget used up"} and len(errs) == 2


# ======================================================================= cache, fallback chain, honest labels
def test_live_data_is_labeled_live_and_a_complete_snapshot_is_cached(tmp_path):
    r = get(tmp_path, real_session())
    assert r.source == O.LIVE and r.is_live and r.as_of == "2026-11-09" and not r.errors
    assert all(e["source"] == O.LIVE for e in r.entries) and len(r.entries) == len(ACCS)
    saved = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
    assert set(saved) == {"fetched_at", "studies"} and len(saved["studies"]) == len(ACCS)
    assert all(O.validate_record(s["verified"]) == [] for s in saved["studies"])


def test_a_fresh_cache_is_reused_without_asking_nasa_and_is_not_called_live(tmp_path):
    get(tmp_path, real_session())
    s = real_session()
    r = get(tmp_path, s, now=NOW + dt.timedelta(days=C.OSDR["cache_ttl_days"]) - DAY)
    assert s.calls == [] and r.source == O.CACHED and not r.is_live and r.as_of == "2026-11-09"
    assert all(e["source"] == O.CACHED for e in r.entries)


def test_a_stale_cache_triggers_a_new_live_fetch(tmp_path):
    get(tmp_path, real_session())
    s = real_session()
    r = get(tmp_path, s, now=NOW + dt.timedelta(days=C.OSDR["cache_ttl_days"] + 1))
    assert len(s.calls) == len(ACCS) and r.source == O.LIVE


def test_when_nasa_is_down_the_cache_is_used_and_labeled_cached(tmp_path):
    get(tmp_path, real_session())
    r = get(tmp_path, down(), now=NOW + dt.timedelta(days=30))
    assert r.source == O.CACHED and not r.is_live and r.as_of == "2026-11-09" and len(r.entries) == len(ACCS)


def test_when_nasa_is_down_and_there_is_no_cache_the_offline_dataset_is_used(tmp_path):
    r = get(tmp_path, down())
    assert r.source == O.OFFLINE and not r.is_live and r.as_of == "2026-10-01"
    assert all(e["source"] == O.OFFLINE for e in r.entries) and len(r.entries) == len(ACCS)
    assert "Not live" in r.describe("en") and "2026-10-01" in r.describe("en") and "Live" not in r.describe("en")[:5]


def test_with_nothing_anywhere_the_result_is_empty_and_honest(tmp_path):
    r = get(tmp_path, down(), offline=False)
    assert r.source == O.NONE and r.empty and r.entries == [] and r.cards() == []
    assert r.describe("en") == i18n.t("op_osdr_src_none", "en")


def test_a_partial_live_fetch_never_makes_offline_records_look_live(tmp_path):
    routes = recorded_routes()
    routes[f"/v2/dataset/{ACCS[0]}/"] = Resp(404, text="x")                           # one study is unavailable
    r = get(tmp_path, FakeSession(routes))
    sources = {e["record"]["accession"]: e["source"] for e in r.entries}
    assert sources[ACCS[0]] == O.OFFLINE and all(sources[a] == O.LIVE for a in ACCS[1:])
    assert r.source == O.OFFLINE and not r.is_live and ACCS[0] in r.errors              # the set is as fresh as its weakest
    assert not (tmp_path / "cache.json").exists()                                      # only complete snapshots are cached
    assert {c.data_source for c in r.cards()} == {O.OFFLINE, O.LIVE}


def test_cache_and_offline_fill_in_for_each_other(tmp_path):
    get(tmp_path, real_session())                                                      # a complete cache
    routes = recorded_routes()
    routes[f"/v2/dataset/{ACCS[1]}/"] = Resp(404, text="x")                           # one study is unavailable
    r = get(tmp_path, FakeSession(routes), now=NOW + dt.timedelta(days=30))
    sources = {e["record"]["accession"]: e["source"] for e in r.entries}
    assert sources[ACCS[1]] == O.CACHED and sources[ACCS[0]] == O.LIVE and r.source == O.CACHED


def test_offline_mode_never_touches_the_network(tmp_path):
    s = real_session()
    r = get(tmp_path, s, allow_network=False)
    assert r.source == O.OFFLINE and s.calls == []


def test_offline_dataset_loads_with_the_network_broken(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(requests.Session, "get", boom)
    off = write_offline(tmp_path / "off.json")
    entries, date = O.load_offline(off)
    assert len(entries) == len(ACCS) and date == "2026-10-01"
    assert O.get_studies(None, TODAY, tmp_path / "c.json", off, allow_network=False, now=NOW).source == O.OFFLINE


@pytest.mark.parametrize("junk", ["", "not json", "[]", "{}", '{"fetched_at": "x", "studies": 5}',
                                  '{"fetched_at": "2026-11-09T00:00:00", "studies": [1, "a", null, {}]}', "\x00"])
def test_corrupt_cache_and_offline_files_are_ignored(tmp_path, junk):
    (tmp_path / "cache.json").write_text(junk, encoding="utf-8")
    (tmp_path / "off.json").write_text(junk, encoding="utf-8")
    r = O.get_studies(down(), TODAY, tmp_path / "cache.json", tmp_path / "off.json", now=NOW)
    assert r.source == O.NONE and r.empty
    assert O.verify_offline(tmp_path / "off.json") != []


def test_invalid_entries_in_a_cache_are_dropped_and_the_rest_kept(tmp_path):
    off = write_offline(tmp_path / "off.json")
    get(tmp_path, real_session())
    d = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
    d["studies"][0]["verified"]["files"] = ["secret.fastq"]                           # smuggled extra field
    d["studies"][1]["app"]["topic"] = "astrology"                                      # unknown topic
    (tmp_path / "cache.json").write_text(json.dumps(d), encoding="utf-8")
    r = O.get_studies(down(), TODAY, tmp_path / "cache.json", off, now=NOW + dt.timedelta(days=1))
    sources = {e["record"]["accession"]: e["source"] for e in r.entries}
    assert sources[ACCS[0]] == O.OFFLINE and sources[ACCS[1]] == O.OFFLINE            # replaced from the offline data
    assert all(sources[a] == O.CACHED for a in ACCS[2:])


def test_get_studies_never_raises(tmp_path):
    for session in (down(), down(requests.Timeout("t")), down(RuntimeError("boom")), down(ValueError("odd")),
                    down(KeyError("k")), None):
        r = O.get_studies(session, TODAY, tmp_path / "c.json", tmp_path / "missing.json", now=NOW)
        assert r.source in O.SOURCES
    (tmp_path / "blocked").mkdir()                                                    # unwritable cache location
    r = O.get_studies(real_session(), TODAY, tmp_path / "blocked", write_offline(tmp_path / "o2.json"), now=NOW)
    assert r.source == O.LIVE


def test_future_dated_cache_is_not_trusted_as_fresh(tmp_path):
    get(tmp_path, real_session(), now=NOW + dt.timedelta(days=5))
    s = real_session()
    assert get(tmp_path, s).source == O.LIVE and len(s.calls) == len(ACCS)


# ======================================================================= research cards: facts vs gameplay
def entry_cards(tmp_path):
    return get(tmp_path, down()).cards()


def test_cards_keep_nasa_facts_and_the_game_note_in_separate_fields(tmp_path):
    for card in entry_cards(tmp_path):
        rec = O.normalize(card.accession, raw_of(card.accession), TODAY)
        r = card.render("en")
        assert r["official_title"] == rec["title"] == card.title                       # NASA's words, untouched
        assert r["official_description"] == rec["description"]
        assert r["gameplay_note"] != r["summary"] != r["official_title"]
        assert r["gameplay_note"].startswith("Educational idea:")                      # labelled as educational
        assert card.source_url.startswith("https://osdr.nasa.gov/bio/repo/data/studies/OSD-")


def test_gameplay_notes_contain_no_numbers_findings_or_thresholds():
    for topic in O.TOPICS:
        for lang in ("en", "ar"):
            text = i18n.t(f"op_osdr_game_{topic}", lang)
            assert not re.search(r"[0-9٠-٩]", text), (topic, lang)         # no thresholds or doses
            phrases = {"en": ("not taken from", "numbers from this study"),
                       "ar": ("ليست مأخوذة", "لا تستخدم أرقامًا")}[lang]            # each note disclaims the study's numbers
            assert any(p in text for p in phrases), (topic, lang)
        en = i18n.t(f"op_osdr_game_{topic}", "en").lower()
        for banned in ("proves", "shows that", "causes", "safe level", "threshold", "will happen", "found that"):
            assert banned not in en, (topic, banned)


def test_summaries_come_only_from_verified_fields_and_never_claim_spaceflight_for_ground_work(tmp_path):
    for card in entry_cards(tmp_path):
        s = card.render("en")["summary"]
        if card.setting == "ground":
            assert "on Earth" in s and "not in space" in s and "spaceflight study" not in s
        elif card.setting == "spaceflight":
            assert "spaceflight study" in s
        else:
            assert "does not say" in s
        assert (", ".join(card.organism) if card.organism else i18n.t("op_osdr_unknown_organism", "en")) in s
    unknown = O.build_card({**O.normalize(ACCS[0], raw_of(ACCS[0]), TODAY), "setting": "unknown", "organism": []},
                           "plants", O.OFFLINE)
    assert "a biological subject" in unknown.render("en")["summary"] and "does not say" in unknown.render("en")["summary"]


def test_card_labels_the_data_source_and_never_calls_saved_data_live(tmp_path):
    for src, text in ((O.LIVE, "Live data"), (O.CACHED, "not live"), (O.OFFLINE, "not live")):
        card = O.build_card(O.normalize(ACCS[0], raw_of(ACCS[0]), TODAY), "plants", src)
        assert text in card.render("en")["data_status"]
    assert "Live" not in O.build_card(O.normalize(ACCS[0], raw_of(ACCS[0]), TODAY), "plants",
                                      O.OFFLINE).render("en")["data_status"]


def test_building_a_card_rejects_bad_input():
    rec = O.normalize(ACCS[0], raw_of(ACCS[0]), TODAY)
    with pytest.raises(O.OsdrError):
        O.build_card({**rec, "title": ""}, "plants", O.LIVE)
    with pytest.raises(O.OsdrError):
        O.build_card(rec, "astrology", O.LIVE)


def test_cards_render_in_both_languages_and_arabic_keeps_nasa_text_in_english(tmp_path):
    for card in entry_cards(tmp_path):
        en, ar = card.render("en"), card.render("ar")
        assert ar["official_title"] == en["official_title"] and not i18n.has_arabic(ar["official_title"])
        for k in ("topic", "setting", "summary", "gameplay_note", "disclaimer", "source_label", "data_status"):
            assert en[k] != ar[k] and i18n.has_arabic(ar[k]), k


# ======================================================================= bilingual coverage
def _osdr_keys():
    topics, settings = O.TOPICS, O.SETTINGS
    keys = {f"op_osdr_topic_{t}" for t in topics} | {f"op_osdr_game_{t}" for t in topics}
    keys |= {f"op_osdr_setting_{s}" for s in settings} | {f"op_osdr_summary_{s}" for s in settings}
    keys |= {f"op_osdr_src_{s}" for s in O.SOURCES} | {f"op_osdr_card_{s}" for s in (O.LIVE, O.CACHED, O.OFFLINE)}
    keys |= {"op_osdr_unknown_organism", "op_osdr_disclaimer", "op_osdr_source", "op_osdr_loading", "op_osdr_error",
             "op_osdr_empty", "op_osdr_card_title", "op_osdr_accession", "op_osdr_organism", "op_osdr_material",
             "op_osdr_mission", "op_osdr_platform", "op_osdr_title", "op_osdr_description", "op_osdr_view",
             "op_osdr_game_label"}
    return keys


def test_every_osdr_string_exists_in_english_and_arabic_with_matching_placeholders():
    ph = lambda s: sorted(re.findall(r"{(\w+)}", s))
    for k in _osdr_keys():
        assert i18n.has_key(k, "en") and i18n.has_key(k, "ar"), k
        assert ph(i18n.STRINGS["en"][k]) == ph(i18n.STRINGS["ar"][k]), k
        assert i18n.STRINGS["en"][k] != i18n.STRINGS["ar"][k] and i18n.has_arabic(i18n.STRINGS["ar"][k]), k


def test_no_osdr_key_is_duplicated_or_missing_from_the_module_usage():
    src = (ROOT / "astro" / "osdr_data.py").read_text(encoding="utf-8")
    literal = set(re.findall(r'"(op_osdr_[a-z_]+)"', src))
    assert literal <= _osdr_keys()
    all_keys = [k for k in i18n.STRINGS["en"] if k.startswith("op_osdr_")]
    assert set(all_keys) == _osdr_keys()                                              # nothing unused or undeclared


def test_status_messages_for_every_situation_exist_in_both_languages():
    for lang in ("en", "ar"):
        for k in ("op_osdr_loading", "op_osdr_error", "op_osdr_empty"):
            assert i18n.t(k, lang)
        for src in O.SOURCES:
            assert "{date}" not in i18n.t(f"op_osdr_src_{src}", lang, date="2026-01-02")
    assert "2026-01-02" in i18n.t("op_osdr_src_cached", "ar", date="2026-01-02")
    assert "2026-01-02" in i18n.t("op_osdr_src_offline", "en", date="2026-01-02")


# ======================================================================= no restricted data
def test_records_contain_only_whitelisted_study_level_fields():
    for a in ACCS:
        rec = O.normalize(a, raw_of(a), TODAY)
        assert set(rec) == set(O.RECORD_KEYS)
        text = json.dumps(rec).lower()
        for banned in ("study person", "last name", "first name", "download", "geode-py", ".fastq", "sample name",
                       "api_key", "password", "token"):
            assert banned not in text, (a, banned)


def test_personal_names_and_file_links_in_the_raw_response_are_not_copied():
    acc = ACCS[0]
    raw = _with(acc, **{"study person.last name": "Doe", "study person.first name": "Jane",
                        "thumbnail": "/geode-py/ws/studies/x/image", "study funding agency": "secret grant"})
    raw[acc]["files"]["URL"] = "https://osdr.nasa.gov/geode-py/ws/studies/x/download?file=big.fastq.gz"
    text = json.dumps(O.normalize(acc, raw, TODAY))
    assert "Doe" not in text and "Jane" not in text and "big.fastq" not in text and "secret grant" not in text


def test_the_module_never_requests_files_or_samples(tmp_path):
    s = real_session()
    r = O.get_studies(s, TODAY, tmp_path / "cache.json", write_offline(tmp_path / "off.json"), now=NOW)
    O.fetch_studies(ACCS, s, TODAY)
    assert r.source == O.LIVE and len(s.calls) > len(ACCS)                            # the network path really ran
    assert all(re.fullmatch(r"/v2/dataset/OSD-[0-9]+/", c["path"]) for c in s.calls)  # study metadata only


# ======================================================================= the shipped offline dataset
SHIPPED = ROOT / "data" / "osdr_studies.json"


def test_the_shipped_offline_dataset_exists_is_consistent_and_loads_offline(tmp_path, monkeypatch):
    assert SHIPPED.exists(), "run: python scripts/build_osdr_dataset.py"
    assert O.verify_offline(SHIPPED) == []
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))
    r = O.get_studies(None, TODAY, tmp_path / "none.json", SHIPPED, allow_network=False, now=NOW)
    assert r.source == O.OFFLINE and not r.is_live and len(r.entries) >= 8
    assert len(r.cards()) == len(r.entries)


def test_shipped_dataset_provenance_dates_and_separation_of_verified_and_app_text():
    d = json.loads(SHIPPED.read_text(encoding="utf-8"))
    assert set(d) == {"dataset", "retrieved", "provenance", "studies"}
    prov = d["provenance"]
    assert prov["authentication"] == "none" and prov["base_url"] == "https://visualization.osdr.nasa.gov/biodata/api"
    assert "verified" in prov["verified_vs_app_text"] and "Astro Play team" in prov["verified_vs_app_text"]
    assert "https://www.nasa.gov/osdr-api/" in prov["documentation"]
    dt.date.fromisoformat(d["retrieved"])
    for s in d["studies"]:
        assert set(s) == {"verified", "app", "retrieved"} and set(s["app"]) == {"topic", "why_selected"}
        assert set(s["verified"]) == set(O.RECORD_KEYS)
        assert dt.date.fromisoformat(s["retrieved"]) == dt.date.fromisoformat(d["retrieved"])
        assert s["verified"]["source_url"].endswith(s["verified"]["accession"])


def test_shipped_dataset_covers_every_topic_has_unique_real_ids_and_labels_ground_work():
    d = json.loads(SHIPPED.read_text(encoding="utf-8"))
    ids = [s["verified"]["accession"] for s in d["studies"]]
    assert len(ids) == len(set(ids)) and all(O.ACCESSION.match(i) for i in ids)
    assert {s["app"]["topic"] for s in d["studies"]} == set(O.TOPICS)
    settings = {s["verified"]["setting"] for s in d["studies"]}
    assert "spaceflight" in settings
    for s in d["studies"]:
        v = s["verified"]
        assert v["title"] and dt.date.fromisoformat(v["release_date"]) <= dt.date.fromisoformat(d["retrieved"])
        if "ground" in (v["project"]["type"] or "").lower():
            assert v["setting"] == "ground"                                            # never relabelled as flight
        if v["setting"] == "spaceflight":
            assert "flight" in (v["project"]["type"] or "").lower()


def test_shipped_dataset_is_small_and_has_no_restricted_or_bulk_data():
    text = SHIPPED.read_text(encoding="utf-8")
    assert len(text) < 120_000
    for banned in ("study person", "download", "geode-py", ".fastq", ".csv", "api_key", "password"):
        assert banned not in text.lower(), banned
    assert not any(re.search(r"[0-9a-f]{40}", text) for _ in [0])                      # no hashes or blobs


def test_why_selected_notes_make_no_claims_about_findings():
    d = json.loads(SHIPPED.read_text(encoding="utf-8"))
    for s in d["studies"]:
        note = s["app"]["why_selected"].lower()
        assert 20 < len(note) < 400
        for banned in ("proves", "showed that", "found that", "demonstrates", "causes", "safe", "threshold", "dose of"):
            assert banned not in note, (s["verified"]["accession"], banned)


# ======================================================================= the build script
def _script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_osdr_dataset", ROOT / "scripts" / "build_osdr_dataset.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _selection():
    return [(a, TOPIC_CYCLE[i % 5], f"Selected for the {TOPIC_CYCLE[i % 5]} topic.") for i, a in enumerate(ACCS)]


def test_build_script_writes_a_verified_dataset_from_retrieved_metadata(tmp_path, monkeypatch, capsys):
    mod = _script()
    monkeypatch.setattr(mod, "SELECTION", _selection())
    monkeypatch.setattr(config, "OSDR_STUDIES_PATH", tmp_path / "studies.json")
    assert mod.main([], session=real_session()) == 0
    assert O.verify_offline(tmp_path / "studies.json") == []
    out = capsys.readouterr().out
    assert "source='offline'" in out and "live=False" in out
    d = json.loads((tmp_path / "studies.json").read_text(encoding="utf-8"))
    for s in d["studies"]:
        assert s["verified"] == O.normalize(s["verified"]["accession"], raw_of(s["verified"]["accession"]),
                                            dt.date.fromisoformat(d["retrieved"]))


def test_build_script_refuses_to_overwrite_and_writes_nothing_on_failure(tmp_path, monkeypatch, capsys):
    mod = _script()
    monkeypatch.setattr(mod, "SELECTION", _selection())
    target = tmp_path / "studies.json"
    monkeypatch.setattr(config, "OSDR_STUDIES_PATH", target)
    assert mod.main([], session=down()) == 1 and not target.exists()                  # nothing is invented
    assert mod.main([], session=real_session()) == 0
    before = target.read_text(encoding="utf-8")
    capsys.readouterr()
    s = real_session()
    assert mod.main([], session=s) == 2 and s.calls == []
    out = capsys.readouterr().out
    assert "already exists" in out and "integrity: OK" in out and "--force" in out
    assert mod.main(["--force"], session=down()) == 1 and target.read_text(encoding="utf-8") == before


def test_build_script_fails_if_any_selected_study_is_missing(tmp_path, monkeypatch):
    mod = _script()
    monkeypatch.setattr(mod, "SELECTION", _selection() + [("OSD-77777", "plants", "Selected for the plants topic.")])
    monkeypatch.setattr(config, "OSDR_STUDIES_PATH", tmp_path / "studies.json")
    assert mod.main([], session=real_session()) == 1 and not (tmp_path / "studies.json").exists()


def test_verify_offline_detects_damage(tmp_path):
    good = write_offline(tmp_path / "g.json")
    assert O.verify_offline(good) == []
    d = json.loads(good.read_text(encoding="utf-8"))
    d["studies"][0]["verified"]["title"] = ""
    d["studies"][1]["app"]["topic"] = "astrology"
    d["studies"].append(copy.deepcopy(d["studies"][2]))
    del d["provenance"]
    (tmp_path / "b.json").write_text(json.dumps(d), encoding="utf-8")
    problems = " | ".join(O.verify_offline(tmp_path / "b.json"))
    for fragment in ("provenance missing", "title missing", "app notes missing", "duplicate accession"):
        assert fragment in problems
    assert O.verify_offline(tmp_path / "nope.json") == ["missing or unreadable"]


# ======================================================================= independence and configuration
def _imports(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods |= {(n.module or "").split(".")[0]} | {a.name for a in n.names}
    return mods


def test_the_simulation_does_not_depend_on_osdr_and_osdr_has_no_ui_imports():
    for name in ("outpost.py", "outpost_config.py"):
        assert not _imports(ROOT / "astro" / name) & {"osdr_data", "requests", "nasa_data"}, name
    assert not _imports(ROOT / "astro" / "osdr_data.py") & {"ursina", "panda3d", "sqlite3", "outpost", "game"}


def test_osdr_config_is_complete_and_does_not_touch_the_simulation_balance():
    o = C.OSDR
    assert o["timeout_s"][0] > 0 < o["timeout_s"][1] and o["budget_s"] > 0 and o["cache_ttl_days"] > 0
    assert o["page_size"] >= 1 and o["max_studies"] >= o["page_size"] and set(o["topics"]) == set(O.TOPICS)
    assert set(o["filters"]) == {"organism", "spaceflight", "radiation"}
    sim = (ROOT / "astro" / "outpost.py").read_text(encoding="utf-8")
    assert "OSDR" not in sim and "osdr" not in sim


def test_cache_is_git_ignored_but_the_offline_dataset_ships():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/osdr_cache.json" in ignore and "osdr_studies" not in ignore
