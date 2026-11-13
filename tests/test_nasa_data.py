"""NASA DONKI integration tests. No test touches the network.

Two kinds of evidence are used besides fake HTTP sessions:
  * tests/fixtures/donki_openapi_fields.json : field names / server / authentication copied from the OFFICIAL DONKI
    OpenAPI document (https://ccmc.gsfc.nasa.gov/DONKI/api/openapi/, version 2.0).
  * tests/fixtures/donki_recorded.json       : REAL responses recorded from the official API.
The small event dictionaries defined below are synthetic and only exercise edge cases (never shipped as data)."""
import ast
import datetime as dt
import json
import logging
import random
from dataclasses import replace
from pathlib import Path

import pytest
import requests

from astro import config, fileio, i18n
from astro import nasa_data as N
from astro import outpost as O
from astro import outpost_config as C

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "tests" / "fixtures" / "donki_openapi_fields.json").read_text(encoding="utf-8"))
REAL = json.loads((ROOT / "tests" / "fixtures" / "donki_recorded.json").read_text(encoding="utf-8"))
SECRET = "SECRET-TEST-VALUE-123"          # must never appear in requests, logs, caches or errors
TODAY = dt.date(2026, 11, 9)
NOW = dt.datetime(2026, 11, 9, 12, 0, 0)


class Resp:
    def __init__(self, status=200, data=None, text=None):
        self.status_code = status
        self.text = text if text is not None else ("" if data is None else json.dumps(data))

    def json(self):
        return json.loads(self.text)


class FakeSession:
    """Answers per endpoint; a value may be a Resp, an Exception to raise, or a list (becomes a 200 JSON body)."""

    def __init__(self, by_endpoint=None, default=None):
        self.by, self.default, self.calls = by_endpoint or {}, default, []

    def get(self, url, params=None, headers=None, timeout=None):
        ep = url.rsplit("/", 1)[-1]
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout, "ep": ep})
        out = self.by.get(ep, self.default)
        if isinstance(out, Exception):
            raise out
        if isinstance(out, list):
            return Resp(200, out)
        return out if out is not None else Resp(200, [])


FLR = [{"flrID": "a", "classType": "X1.2"}, {"flrID": "b", "classType": "M5.0"}, {"flrID": "c", "classType": "m1.1"},
       {"flrID": "d", "classType": "C2.3"}, {"flrID": "e", "classType": "B1.0"}, {"flrID": "f"}]
CME = [{"activityID": "1"}, {"activityID": "2"}]
GST = [{"gstID": "g1", "allKpIndex": [{"kpIndex": 5}, {"kpIndex": 7}]}, {"gstID": "g2", "allKpIndex": [{"kpIndex": 4}]}]
SEP = [{"sepID": "s1"}]
BUSY = {"FLR": FLR, "CME": CME, "GST": GST, "SEP": SEP}


def busy_session():
    return FakeSession(dict(BUSY))


def down_session(exc=None):
    return FakeSession(default=exc or Resp(503, text="upstream connect error"))


def recorded_session():
    return FakeSession({ep: list(v) for ep, v in REAL["data"].items()})


# ======================================================================= official contract (spec + real data)
def test_official_spec_server_paths_and_no_authentication():
    assert SPEC["servers"] == ["https://ccmc.gsfc.nasa.gov/DONKI-API"]
    assert SPEC["securitySchemes"] is None and SPEC["globalSecurity"] is None        # no key / token required
    assert set(C.DONKI["endpoints"]) <= set(SPEC["paths"])


def test_our_base_url_is_the_official_one_and_not_the_old_gateway():
    assert config.DONKI_BASE_URL == SPEC["servers"][0] + "/get" or "ASTRO_DONKI_URL" in __import__("os").environ
    src = (ROOT / "astro" / "config.py").read_text(encoding="utf-8")
    assert f'"{SPEC["servers"][0]}/get"' in src
    assert 'getenv("ASTRO_DONKI_URL", "https://api.nasa.gov' not in src
    assert not hasattr(config, "NASA_API_KEY")                       # DONKI needs no key, so none is read


def test_we_only_send_parameters_the_spec_defines_and_always_the_required_ones():
    sent = {"startDate", "endDate"}
    for ep in C.DONKI["endpoints"]:
        info = SPEC["paths"][ep]
        assert sent <= set(info["params"]) and set(info["required"]) <= sent       # CME requires both dates
    assert SPEC["dateFormat"].startswith("Start date (yyyy-MM-dd)")
    assert 0 < C.DONKI["window_days"] <= 60                                          # the documented maximum window


def test_every_field_we_read_exists_in_the_official_schemas():
    fl, gst, cme, sep = (set(SPEC["schemas"][n]) for n in ("FLRObject", "GSTObject", "CMEJSON", "SEPObject"))
    assert {"flrID", "classType"} <= fl
    assert {"gstID", "allKpIndex"} <= gst and "kpIndex" in set(SPEC["schemas"]["KpIndexObject"])
    assert "activityID" in cme and "sepID" in sep
    assert {ep: N._ID_FIELD[ep] for ep in N._ID_FIELD} == {"FLR": "flrID", "CME": "activityID", "GST": "gstID",
                                                           "SEP": "sepID"}


def test_recorded_real_responses_have_the_documented_shape():
    assert REAL["_recorded"] and REAL["_source"].startswith("https://ccmc.gsfc.nasa.gov/DONKI-API/get")
    for ep, events in REAL["data"].items():
        assert isinstance(events, list)
        fields = set(SPEC["schemas"][SPEC["paths"][ep]["item"]])
        for e in events:
            assert N._ID_FIELD[ep] in e and set(e) <= fields, (ep, set(e) - fields)
    for e in REAL["data"]["FLR"]:
        assert e["classType"][0] in "ABCMX" and e["classType"][1:].replace(".", "").isdigit()
    for e in REAL["data"]["GST"]:
        assert e["allKpIndex"] and all(isinstance(k["kpIndex"], (int, float)) for k in e["allKpIndex"])


def test_summarize_matches_an_independent_count_of_the_recorded_real_data():
    real = REAL["data"]
    counts = N.summarize(real)
    letters = [e["classType"][0] for e in real["FLR"]]
    assert counts["flare_x"] == letters.count("X") and counts["flare_m"] == letters.count("M")
    assert counts["flare_c"] == letters.count("C")
    assert counts["flare_minor"] == len(letters) - sum(letters.count(c) for c in "XMC")
    assert counts["gst"] == len(real["GST"])
    strong = sum(max(k["kpIndex"] for k in e["allKpIndex"]) >= C.DONKI["gst_strong_kp"] for e in real["GST"])
    assert counts["gst_strong"] == strong
    assert counts["cme"] == len(real["CME"]) and counts["sep"] == len(real["SEP"]) == 0
    assert 0.0 <= N.activity_level(counts) <= 1.0


def test_the_full_pipeline_works_on_recorded_real_responses(tmp_path):
    s = recorded_session()
    r = N.get_solar_activity(TODAY, s, tmp_path / "c.json", tmp_path / "a.json", now=NOW)
    assert r.source == N.LIVE and r.counts == N.summarize(REAL["data"]) and 0.0 <= r.level <= 1.0
    assert [c["url"] for c in s.calls] == [f"{config.DONKI_BASE_URL}/{ep}" for ep in C.DONKI["endpoints"]]


def test_an_empty_event_list_is_a_valid_answer():
    for body in ("[]", "[ ]", "", "  "):
        assert N.fetch_events("SEP", TODAY, TODAY, FakeSession({"SEP": Resp(200, text=body)})) == []


# ======================================================================= request building
def test_request_matches_the_official_contract_and_sends_no_credentials():
    s = FakeSession({"FLR": []})
    N.fetch_events("FLR", dt.date(2026, 10, 1), dt.date(2026, 10, 31), s)
    c = s.calls[0]
    assert c["url"] == f"{config.DONKI_BASE_URL}/FLR"
    assert c["params"] == {"startDate": "2026-10-01", "endDate": "2026-10-31"}      # official yyyy-MM-dd, nothing else
    assert c["timeout"] == C.DONKI["timeout_s"]
    assert set(c["headers"]) == {"User-Agent"} and "@" not in c["headers"]["User-Agent"]


def test_no_credential_is_ever_sent_even_when_keys_exist_in_the_environment(tmp_path, monkeypatch):
    for name in ("NASA_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.setenv(name, SECRET)
    s = busy_session()
    N.get_solar_activity(TODAY, s, tmp_path / "c.json", tmp_path / "a.json", now=NOW)
    assert len(s.calls) == 4
    for c in s.calls:
        assert set(c["params"]) == {"startDate", "endDate"}
        assert SECRET not in json.dumps(c, default=str)


def test_unknown_endpoint_is_rejected_before_any_request():
    s = FakeSession()
    with pytest.raises(ValueError):
        N.fetch_events("NOPE", TODAY, TODAY, s)
    assert s.calls == []


# ======================================================================= response handling
def test_good_empty_and_filtered_responses():
    assert N.fetch_events("FLR", TODAY, TODAY, FakeSession({"FLR": FLR})) == FLR
    assert N.fetch_events("FLR", TODAY, TODAY, FakeSession({"FLR": [{"a": 1}, "junk", 5, None]})) == [{"a": 1}]


@pytest.mark.parametrize("resp,fragment", [
    (Resp(429, text="slow down"), "rate limited"),
    (Resp(503, text="upstream connect error"), "HTTP 503"),
    (Resp(500, text="oops"), "HTTP 500"),
    (Resp(404, text="nope"), "HTTP 404"),
    (Resp(200, text="<html>not json</html>"), "not JSON"),
    (Resp(200, text='{"a": 1}'), "unexpected response shape"),
])
def test_bad_responses_raise_donki_error(resp, fragment):
    with pytest.raises(N.DonkiError, match=fragment):
        N.fetch_events("GST", TODAY, TODAY, FakeSession({"GST": resp}))


@pytest.mark.parametrize("exc", [requests.Timeout(f"timed out for api_key={SECRET}"),
                                 requests.ConnectionError(f"https://example.invalid/DONKI/FLR?api_key={SECRET}")])
def test_network_errors_become_short_donki_errors_without_the_url(exc):
    with pytest.raises(N.DonkiError) as e:
        N.fetch_events("FLR", TODAY, TODAY, FakeSession({"FLR": exc}))
    assert SECRET not in str(e.value) and "http" not in str(e.value) and str(e.value).startswith("FLR: ")
    assert e.value.__suppress_context__ and e.value.__cause__ is None             # the original text is not chained


# ======================================================================= counting and mapping
def test_summarize_counts_each_kind_defensively():
    c = N.summarize(BUSY)
    assert c == {"flare_x": 1, "flare_m": 2, "flare_c": 1, "flare_minor": 2, "cme": 2, "gst": 2, "gst_strong": 1,
                 "sep": 1}
    assert set(c) == set(N.COUNT_KEYS)


def test_summarize_survives_garbage_and_missing_endpoints():
    garbage = {"FLR": [{"classType": None}, {"classType": 5}, {"classType": ""}],
               "GST": [{"allKpIndex": "oops"}, {"allKpIndex": [None, {"kpIndex": "x"}, {"kpIndex": None}]}, {}]}
    c = N.summarize(garbage)
    assert c["flare_minor"] == 3 and c["gst"] == 3 and c["gst_strong"] == 0 and c["cme"] == 0 and c["sep"] == 0
    assert N.summarize({}) == {k: 0 for k in N.COUNT_KEYS}


def test_the_same_event_id_is_never_counted_twice():
    dup = {"FLR": [{"flrID": "x", "classType": "X1.0"}, {"flrID": "x", "classType": "X1.0"}],
           "CME": [{"activityID": "c"}, {"activityID": "c"}, {"activityID": "d"}],
           "GST": [{"gstID": "g", "allKpIndex": [{"kpIndex": 8}]}, {"gstID": "g", "allKpIndex": [{"kpIndex": 8}]}],
           "SEP": [{"sepID": "s"}, {"sepID": "s"}]}
    c = N.summarize(dup)
    assert (c["flare_x"], c["cme"], c["gst"], c["gst_strong"], c["sep"]) == (1, 2, 1, 1, 1)
    noid = N.summarize({"CME": [{}, {}, {"note": "x"}]})
    assert noid["cme"] == 3                                                          # entries without an id all count


def test_activity_level_is_bounded_monotonic_and_uses_the_config():
    zero = {k: 0 for k in N.COUNT_KEYS}
    assert N.activity_level(zero) == 0.0 and N.activity_level({}) == 0.0
    assert N.activity_level({"flare_x": 10 ** 6}) == 1.0
    prev = 0.0
    for n in range(0, 30, 3):
        lvl = N.activity_level({**zero, "flare_m": n})
        assert prev <= lvl <= 1.0
        prev = lvl
    for key, pts in C.DONKI["points"].items():
        assert pts > 0
        assert N.activity_level({**zero, key: 1}) == pytest.approx(min(1.0, pts / C.DONKI["full_points"]))
    assert N.activity_level({"flare_x": -5, "cme": -1}) == 0.0                  # nonsense counts never lower it


def test_bigger_events_count_for_more():
    p = C.DONKI["points"]
    assert p["flare_x"] > p["flare_m"] > p["flare_c"] > 0
    assert p["gst_strong"] > 0 and p["sep"] > p["cme"]


def test_level_labels():
    lo, hi = C.DONKI["levels"]
    mk = lambda v: N.SolarActivity(v, N.DEFAULT)
    assert (mk(0.0).level_key, mk(lo).level_key, mk(hi).level_key) == ("op_solar_low", "op_solar_medium",
                                                                       "op_solar_high")


# ======================================================================= live fetch, timeouts
def test_fetch_live_asks_every_endpoint_over_the_configured_window():
    s = busy_session()
    live = N.fetch_live(TODAY, s, NOW)
    assert [c["ep"] for c in s.calls] == list(C.DONKI["endpoints"])
    start = TODAY - dt.timedelta(days=C.DONKI["window_days"])
    assert all(c["params"] == {"startDate": start.isoformat(), "endDate": TODAY.isoformat()} for c in s.calls)
    assert live.source == N.LIVE and live.is_live and live.is_nasa_data
    assert live.as_of == "2026-11-09" and live.window == (start.isoformat(), TODAY.isoformat())
    assert live.counts == N.summarize(BUSY) and live.level == N.activity_level(live.counts)


def test_fetch_live_is_all_or_nothing():
    for bad in C.DONKI["endpoints"]:
        with pytest.raises(N.DonkiError):
            N.fetch_live(TODAY, FakeSession({**BUSY, bad: Resp(503, text="x")}), NOW)


def test_fetch_live_stops_at_the_first_failure():
    s = down_session()
    with pytest.raises(N.DonkiError):
        N.fetch_live(TODAY, s, NOW)
    assert len(s.calls) == 1                                                    # does not hammer a dead service


def test_per_request_timeouts_are_capped_by_the_remaining_budget(monkeypatch):
    s = busy_session()
    N.fetch_live(TODAY, s, NOW)
    connect, read = C.DONKI["timeout_s"]
    assert all(c["timeout"][0] <= connect and c["timeout"][1] <= read for c in s.calls)
    monkeypatch.setitem(C.DONKI, "budget_s", 2)
    s = busy_session()
    N.fetch_live(TODAY, s, NOW)
    assert all(c["timeout"][0] <= 2 and c["timeout"][1] <= 2 for c in s.calls)   # never longer than what is left


def test_an_exhausted_budget_stops_before_any_request(monkeypatch):
    monkeypatch.setitem(C.DONKI, "budget_s", -1)
    s = busy_session()
    with pytest.raises(N.DonkiError, match="budget"):
        N.fetch_live(TODAY, s, NOW)
    assert s.calls == []


def test_the_budget_runs_out_across_endpoints(monkeypatch):
    clock = iter([0.0, 0.0, 10.0, 99.0])                      # deadline, then one reading before each request
    monkeypatch.setattr(N.time, "monotonic", lambda: next(clock))
    monkeypatch.setitem(C.DONKI, "budget_s", 25)
    s = busy_session()
    with pytest.raises(N.DonkiError, match="budget"):
        N.fetch_live(TODAY, s, NOW)
    assert len(s.calls) == 2 and s.calls[1]["timeout"] == (5, 15)                # 15 s were still left for the 2nd call


# ======================================================================= the fallback chain and honest labels
def paths(tmp_path):
    return tmp_path / "cache.json", tmp_path / "archive.json"


def get(tmp_path, session, **kw):
    cache, archive = paths(tmp_path)
    return N.get_solar_activity(TODAY, session, cache, archive, now=kw.pop("now", NOW), **kw)


def test_live_data_is_labeled_live_and_cached_with_only_counts(tmp_path):
    r = get(tmp_path, busy_session())
    assert r.source == N.LIVE
    saved = json.loads(paths(tmp_path)[0].read_text(encoding="utf-8"))
    assert set(saved) == {"fetched_at", "window", "counts"} and saved["counts"] == r.counts
    assert saved["fetched_at"].startswith("2026-11-09")


def test_a_fresh_cache_is_reused_without_asking_nasa_and_is_not_called_live(tmp_path):
    get(tmp_path, busy_session())
    s = busy_session()
    later = NOW + dt.timedelta(hours=C.DONKI["cache_ttl_hours"] - 1)
    r = get(tmp_path, s, now=later)
    assert s.calls == [] and r.source == N.CACHED and not r.is_live and r.as_of == "2026-11-09"


def test_a_stale_cache_triggers_a_new_live_fetch(tmp_path):
    get(tmp_path, busy_session())
    s = FakeSession({"FLR": [], "CME": [], "GST": [], "SEP": []})
    r = get(tmp_path, s, now=NOW + dt.timedelta(hours=C.DONKI["cache_ttl_hours"] + 1))
    assert len(s.calls) == 4 and r.source == N.LIVE and r.level == 0.0


def test_when_nasa_is_down_an_older_cache_is_used_and_labeled_cached(tmp_path):
    first = get(tmp_path, busy_session())
    r = get(tmp_path, down_session(), now=NOW + dt.timedelta(days=3))
    assert r.source == N.CACHED and not r.is_live and r.as_of == "2026-11-09" and r.level == first.level


def test_when_nasa_is_down_and_there_is_no_cache_the_archive_is_used_and_labeled_archived(tmp_path):
    N.refresh_archive(paths(tmp_path)[1], TODAY, busy_session(), NOW - dt.timedelta(days=40))
    r = get(tmp_path, down_session())
    assert r.source == N.ARCHIVED and not r.is_live and r.is_nasa_data and r.as_of == "2026-09-30"


def test_with_no_data_anywhere_the_default_is_used_and_labeled_default(tmp_path):
    r = get(tmp_path, down_session())
    assert r.source == N.DEFAULT and r.level == C.SOLAR_ACTIVITY_DEFAULT and not r.is_nasa_data and r.as_of is None


def test_each_fallback_has_exactly_the_right_label_and_never_claims_to_be_live(tmp_path):
    """live -> cached -> archived -> default, each one honest about what it is."""
    labels = []
    N.refresh_archive(paths(tmp_path)[1], TODAY, busy_session(), NOW - dt.timedelta(days=40))
    for session, now, drop_cache in ((busy_session(), NOW, False),
                                     (busy_session(), NOW + dt.timedelta(minutes=30), False),     # inside the cache window
                                     (down_session(), NOW + dt.timedelta(days=2), False),
                                     (down_session(), NOW + dt.timedelta(days=2), True)):
        if drop_cache:
            paths(tmp_path)[0].unlink()
        labels.append(get(tmp_path, session, now=now).source)
    assert labels == [N.LIVE, N.CACHED, N.CACHED, N.ARCHIVED]
    (paths(tmp_path)[1]).unlink()
    assert get(tmp_path, down_session(), now=NOW + dt.timedelta(days=2)).source == N.DEFAULT


def test_offline_mode_never_touches_the_network(tmp_path):
    s = busy_session()
    assert get(tmp_path, s, allow_network=False).source == N.DEFAULT and s.calls == []
    get(tmp_path, busy_session())                                       # create a cache
    s = busy_session()
    r = get(tmp_path, s, allow_network=False, now=NOW + dt.timedelta(days=9))
    assert r.source == N.CACHED and s.calls == []


@pytest.mark.parametrize("junk", ["", "not json", "[]", '{"counts": 5}', '{"counts": {}}',
                                  '{"counts": {}, "fetched_at": "yesterday-ish"}', "\x00\x01"])
def test_corrupt_cache_and_archive_are_ignored(tmp_path, junk):
    cache, archive = paths(tmp_path)
    cache.write_text(junk, encoding="utf-8")
    archive.write_text(junk, encoding="utf-8")
    assert get(tmp_path, down_session()).source == N.DEFAULT
    assert get(tmp_path, busy_session()).source == N.LIVE               # and a good fetch repairs the cache


def test_get_solar_activity_never_raises(tmp_path, monkeypatch):
    # session=None means "use the real requests library": redirect it to a simulated outage so no real request is made
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("offline")))
    for session in (down_session(), down_session(requests.Timeout("t")), down_session(RuntimeError("boom")),
                    down_session(ValueError("odd")), down_session(KeyError("k")), None):
        r = N.get_solar_activity(TODAY, session, tmp_path / "c.json", tmp_path / "a.json", now=NOW)
        assert r.source in N.SOURCES and 0.0 <= r.level <= 1.0


def test_unexpected_errors_still_fall_back_to_saved_data(tmp_path):
    get(tmp_path, busy_session())
    r = get(tmp_path, down_session(RuntimeError("boom")), now=NOW + dt.timedelta(days=2))
    assert r.source == N.CACHED


def test_unwritable_cache_does_not_stop_a_live_result(tmp_path):
    (tmp_path / "blocked").mkdir()
    r = N.get_solar_activity(TODAY, busy_session(), tmp_path / "blocked", tmp_path / "a.json", now=NOW)
    assert r.source == N.LIVE


def test_future_dated_cache_is_not_trusted_as_fresh(tmp_path):
    get(tmp_path, busy_session(), now=NOW + dt.timedelta(days=5))
    s = busy_session()
    assert get(tmp_path, s).source == N.LIVE and len(s.calls) == 4


def test_refresh_archive_only_writes_real_fetched_data(tmp_path):
    target = tmp_path / "archive.json"
    with pytest.raises(N.DonkiError):
        N.refresh_archive(target, TODAY, down_session(), NOW)
    assert not target.exists()                                          # nothing is ever made up
    live = N.refresh_archive(target, TODAY, busy_session(), NOW)
    assert json.loads(target.read_text(encoding="utf-8"))["counts"] == live.counts
    keep = target.read_text(encoding="utf-8")
    with pytest.raises(N.DonkiError):
        N.refresh_archive(target, TODAY, down_session(), NOW)
    assert target.read_text(encoding="utf-8") == keep                   # a failed refresh keeps the old archive


# ======================================================================= secrets hygiene
def test_nothing_secret_reaches_logs_results_errors_or_files(tmp_path, caplog, monkeypatch):
    monkeypatch.setenv("NASA_API_KEY", SECRET)
    caplog.set_level(logging.DEBUG)
    s = down_session(requests.ConnectionError(f"https://example.invalid/DONKI/FLR?api_key={SECRET}"))
    r = get(tmp_path, s)
    get(tmp_path, busy_session())
    assert SECRET not in caplog.text and SECRET not in repr(r)
    for f in tmp_path.iterdir():
        assert SECRET not in f.read_text(encoding="utf-8")


# ======================================================================= honest labelling
def test_only_live_data_is_ever_called_live_and_defaults_are_not_nasa_data():
    for src in N.SOURCES:
        sa = N.SolarActivity(0.5, src, "2026-01-02")
        assert sa.is_live == (src == N.LIVE) and sa.is_nasa_data == (src != N.DEFAULT)


def test_labels_are_bilingual_and_state_the_date_for_non_live_data():
    for src in N.SOURCES:
        sa = N.SolarActivity(0.5, src, "2026-01-02")
        en, ar = sa.describe("en"), sa.describe("ar")
        assert en != ar and i18n.has_arabic(ar)
        if src in (N.CACHED, N.ARCHIVED):
            assert "2026-01-02" in en and "2026-01-02" in ar and "Not live" in en
        else:
            assert "2026" not in en
    assert "Live" in N.SolarActivity(0.1, N.LIVE).describe("en")
    assert "standard" in N.SolarActivity(0.3, N.DEFAULT).describe("en")


def test_every_label_key_exists_in_both_languages():
    for key in [f"op_src_{s}" for s in N.SOURCES] + ["op_solar_low", "op_solar_medium", "op_solar_high"]:
        assert i18n.has_key(key, "en") and i18n.has_key(key, "ar"), key


# ======================================================================= integration with the simulation
def test_solar_activity_from_donki_makes_storms_likelier_in_the_simulation():
    calm = N.SolarActivity(N.activity_level({}), N.LIVE)
    stormy = N.SolarActivity(N.activity_level({"flare_x": 5, "sep": 3, "gst_strong": 2}), N.LIVE)
    assert calm.level == 0.0 and 0.0 < stormy.level <= 1.0
    state = replace(O.new_state(), sol=4)                     # solar storms are not allowed on sol 1

    def storms(level):
        rng = random.Random(5)
        return sum(O.roll_event(state, rng, level) == "solar_storm" for _ in range(600))
    assert storms(stormy.level) > storms(calm.level)


def _imports(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods |= {(n.module or "").split(".")[0]} | {a.name for a in n.names}
    return tree, mods


def test_the_simulation_stays_independent_of_nasa_data_and_the_network():
    for name in ("outpost.py", "outpost_config.py"):
        _, mods = _imports(ROOT / "astro" / name)
        assert not mods & {"requests", "nasa_data", "ursina", "panda3d", "sqlite3"}, (name, mods)


def test_nasa_data_has_no_ui_or_engine_imports_and_no_balance_numbers():
    tree, mods = _imports(ROOT / "astro" / "nasa_data.py")
    assert not mods & {"ursina", "panda3d", "sqlite3", "outpost"}
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            # allowed: trivial values, a date slice [:10], an indent of 2, and the HTTP status codes 200 and 429
            assert n.value in (0, 0.0, 1, 2, 10, 200, 429), f"balance-like number {n.value} at line {n.lineno}"


# ======================================================================= calibration (24 real historical windows)
HISTORY = json.loads((ROOT / "tests" / "fixtures" / "donki_history_windows.json").read_text(encoding="utf-8"))["windows"]


def _level(counts):
    return N.activity_level(counts)


def _marker(c):
    return (c["flare_x"] > 0) + (c["gst_strong"] > 0) + (c["sep"] > 0)


def test_history_fixture_covers_at_least_twelve_non_overlapping_30_day_windows():
    assert len(HISTORY) >= 12
    for w in HISTORY:
        a, b = dt.date.fromisoformat(w["start"]), dt.date.fromisoformat(w["end"])
        assert (b - a).days + 1 == C.DONKI["window_days"] and set(w["counts"]) == set(N.COUNT_KEYS)
    for prev, nxt in zip(HISTORY, HISTORY[1:]):
        assert dt.date.fromisoformat(prev["end"]) < dt.date.fromisoformat(nxt["start"])         # no overlap


def test_provisional_full_points_is_160():
    assert C.DONKI["full_points"] == 160.0


def test_historical_levels_are_spread_out_not_pinned_to_the_maximum():
    levels = sorted(_level(w["counts"]) for w in HISTORY)
    assert levels[0] < 0.5 and levels[-1] == 1.0                                # quiet windows are clearly lower
    assert sum(lv >= 1.0 for lv in levels) / len(levels) <= 0.45                # most windows do not saturate
    assert len({round(lv, 1) for lv in levels}) >= 6                            # genuinely different values


def test_cme_counts_alone_can_never_saturate_the_level():
    worst = max(w["counts"]["cme"] for w in HISTORY)
    alone = _level({"cme": worst})
    assert alone < 0.7, alone
    assert alone < _level({"cme": worst, "flare_x": 2, "gst_strong": 1, "sep": 5})        # real severity adds to it


def test_busy_historical_windows_score_higher_than_quiet_ones():
    quiet = [_level(w["counts"]) for w in HISTORY if _marker(w["counts"]) == 0]
    busy = [_level(w["counts"]) for w in HISTORY if _marker(w["counts"]) >= 2]
    assert quiet and busy
    assert sum(busy) / len(busy) - sum(quiet) / len(quiet) >= 0.2


def test_level_rises_with_event_severity_at_the_same_cme_count():
    base = {k: 0 for k in N.COUNT_KEYS} | {"cme": 100}
    steps = [base, base | {"flare_c": 5}, base | {"flare_c": 5, "flare_m": 5}, base | {"flare_x": 3, "flare_m": 5},
             base | {"flare_x": 3, "flare_m": 5, "gst_strong": 1},
             base | {"flare_x": 3, "flare_m": 5, "gst_strong": 1, "sep": 5}]
    levels = [_level(c) for c in steps]
    assert levels == sorted(levels) and levels[0] < levels[-1]


# ======================================================================= the bundled archive
def _write_archive(tmp_path, session=None, **kw):
    target = tmp_path / "archive.json"
    live = N.refresh_archive(target, TODAY, session or recorded_session(), NOW, **kw)
    return target, live, json.loads(target.read_text(encoding="utf-8"))


def test_archive_keeps_real_values_dates_and_provenance(tmp_path):
    target, live, d = _write_archive(tmp_path)
    assert set(d) == {"fetched_at", "window", "counts", "provenance", "events"}
    assert d["fetched_at"] == fileio.as_aware(NOW).isoformat(timespec="seconds")          # stored with its UTC offset
    assert d["window"] == [(TODAY - dt.timedelta(days=C.DONKI["window_days"])).isoformat(), TODAY.isoformat()]
    p = d["provenance"]
    assert p["authentication"] == "none" and p["base_url"] == config.DONKI_BASE_URL
    assert p["documentation"] == "https://ccmc.gsfc.nasa.gov/DONKI/api/" and "verbatim" in p["note"]
    assert p["returned_by_endpoint"] == {ep: len(REAL["data"][ep]) for ep in C.DONKI["endpoints"]}
    for ep in C.DONKI["endpoints"]:                                  # stored values equal what the API returned
        for stored, real in zip(d["events"][ep], REAL["data"][ep]):
            assert stored == {k: real[k] for k in N._KEEP[ep] if k in real}
    assert d["counts"] == live.counts == N.summarize(REAL["data"])
    assert N.verify_archive(target) == []


def test_archive_handles_an_empty_endpoint_correctly(tmp_path):
    assert REAL["data"]["SEP"] == []                                 # the real SEP answer for the recorded window
    target, live, d = _write_archive(tmp_path)
    assert d["events"]["SEP"] == [] and d["provenance"]["returned_by_endpoint"]["SEP"] == 0
    assert d["counts"]["sep"] == 0 and N.verify_archive(target) == []
    target2, _, d2 = _write_archive(tmp_path, FakeSession({"FLR": [], "CME": [], "GST": [], "SEP": []}))
    assert d2["counts"] == {k: 0 for k in N.COUNT_KEYS} and N.verify_archive(target2) == []


def test_archive_never_contains_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("NASA_API_KEY", SECRET)
    target, _, _ = _write_archive(tmp_path)
    text = target.read_text(encoding="utf-8")
    assert SECRET not in text and "api_key" not in text.lower()


def test_verify_archive_detects_tampering_and_damage(tmp_path):
    target, _, d = _write_archive(tmp_path)
    d["counts"]["cme"] += 1
    target.write_text(json.dumps(d), encoding="utf-8")
    assert "counts do not match the stored events" in N.verify_archive(target)
    d["counts"]["cme"] -= 1
    del d["provenance"]
    target.write_text(json.dumps(d), encoding="utf-8")
    assert "provenance missing" in N.verify_archive(target)
    target.write_text("{}", encoding="utf-8")
    assert N.verify_archive(target) == ["missing or unreadable"]
    assert N.verify_archive(tmp_path / "nope.json") == ["missing or unreadable"]


def test_archive_loads_through_the_fallback_and_is_labeled_archived_never_live(tmp_path):
    target, live, _ = _write_archive(tmp_path)
    r = N.get_solar_activity(TODAY, down_session(), tmp_path / "nocache.json", target, now=NOW + dt.timedelta(days=1))
    assert r.source == N.ARCHIVED and not r.is_live and r.is_nasa_data
    assert r.counts == live.counts and r.level == live.level and r.as_of == NOW.date().isoformat()
    assert "Archived" in r.describe("en") and "Not live" in r.describe("en") and "Live" not in r.describe("en")[:5]
    assert i18n.has_arabic(r.describe("ar"))


def test_old_archives_without_events_still_load(tmp_path):
    old = tmp_path / "archive.json"
    old.write_text(json.dumps({"fetched_at": "2026-01-01T00:00:00", "window": ["2025-12-01", "2026-01-01"],
                               "counts": {"flare_m": 3}}), encoding="utf-8")
    r = N.get_solar_activity(TODAY, down_session(), tmp_path / "c.json", old, now=NOW)
    assert r.source == N.ARCHIVED and r.counts["flare_m"] == 3


def _load_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("fetch_donki_archive", ROOT / "scripts" / "fetch_donki_archive.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_script_creates_an_archive_and_verifies_it(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "DONKI_ARCHIVE_PATH", tmp_path / "archive.json")
    assert _load_script().main([], session=recorded_session()) == 0
    out = capsys.readouterr().out
    assert "source='archived'" in out and "live=False" in out and N.verify_archive(tmp_path / "archive.json") == []


def test_script_refuses_to_overwrite_without_force_and_shows_the_existing_contents(tmp_path, monkeypatch, capsys):
    target = tmp_path / "archive.json"
    monkeypatch.setattr(config, "DONKI_ARCHIVE_PATH", target)
    script = _load_script()
    assert script.main([], session=recorded_session()) == 0
    before = target.read_text(encoding="utf-8")
    capsys.readouterr()
    s = busy_session()
    assert script.main([], session=s) == 2
    out = capsys.readouterr().out
    assert "already exists" in out and "integrity: OK" in out and "counts" in out and "--force" in out
    assert s.calls == [] and target.read_text(encoding="utf-8") == before               # nothing fetched or changed
    assert script.main(["--force"], session=busy_session()) == 0
    assert target.read_text(encoding="utf-8") != before


def test_script_reports_and_keeps_the_old_archive_when_nasa_is_down(tmp_path, monkeypatch, capsys):
    target = tmp_path / "archive.json"
    monkeypatch.setattr(config, "DONKI_ARCHIVE_PATH", target)
    script = _load_script()
    assert script.main([], session=down_session()) == 1 and not target.exists()          # no archive is invented
    script.main([], session=recorded_session())
    before = target.read_text(encoding="utf-8")
    assert script.main(["--force"], session=down_session()) == 1
    assert target.read_text(encoding="utf-8") == before


def test_script_shows_a_damaged_existing_archive_before_refusing(tmp_path, monkeypatch, capsys):
    target = tmp_path / "archive.json"
    target.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(config, "DONKI_ARCHIVE_PATH", target)
    assert _load_script().main([], session=busy_session()) == 2
    assert "unreadable" in capsys.readouterr().out and target.read_text(encoding="utf-8") == "not json"


def test_the_shipped_archive_is_real_consistent_and_labeled_archived(tmp_path):
    shipped = ROOT / "data" / "donki_archive.json"
    assert shipped.exists(), "run: python scripts/fetch_donki_archive.py"
    assert N.verify_archive(shipped) == []
    d = json.loads(shipped.read_text(encoding="utf-8"))
    start, end = (dt.date.fromisoformat(x) for x in d["window"])
    assert (end - start).days == C.DONKI["window_days"] and dt.datetime.fromisoformat(d["fetched_at"]).date() >= end
    assert d["provenance"]["base_url"].startswith("https://ccmc.gsfc.nasa.gov/DONKI-API") and \
        d["provenance"]["authentication"] == "none"
    text = shipped.read_text(encoding="utf-8")
    assert "api_key" not in text.lower() and "key=" not in text.lower()
    for ep, idf in N._ID_FIELD.items():                                    # every stored event carries its NASA id
        assert all(idf in e for e in d["events"][ep])
    r = N.get_solar_activity(TODAY, down_session(), tmp_path / "nocache.json", shipped, now=NOW)
    assert r.source == N.ARCHIVED and not r.is_live and r.counts == d["counts"]


# ======================================================================= configuration and shipped files
def test_donki_config_is_complete_and_sane():
    d = C.DONKI
    assert set(d["endpoints"]) == {"FLR", "CME", "GST", "SEP"}
    assert d["window_days"] > 0 and d["cache_ttl_hours"] > 0 and d["budget_s"] > 0 and d["full_points"] > 0
    assert 0 < d["levels"][0] < d["levels"][1] < 1
    assert set(d["points"]) <= set(N.COUNT_KEYS)


def test_cache_file_is_git_ignored_but_the_archive_is_not():
    ignore = (ROOT / "tests" / ".." / ".gitignore").read_text(encoding="utf-8")
    assert "data/donki_cache.json" in ignore and "donki_archive" not in ignore          # the archive ships with the game
