"""Freshness and date display for the NASA data in Outpost Command. Everything here is offline (fake HTTP sessions).

Three different moments are kept apart on purpose:
  * WHEN THE EVENT HAPPENED  - NASA's own timestamp, never altered ("Newest NASA event").
  * WHEN WE RETRIEVED IT     - the exact moment the data came from NASA ("Retrieved", local time, stored with its UTC offset).
  * WHEN WE LAST ASKED NASA  - the last attempt, successful or not ("Last checked")."""
import datetime as dt
import json
from pathlib import Path

import pytest

from astro import config, fileio
from astro import nasa_data as N
from astro import osdr_data as O
from astro import outpost_config as C
from astro.outpost_flow import BackgroundLoader, NasaData
from tests.test_nasa_data import FakeSession, Resp, busy_session, down_session
from tests.test_osdr_data import ACCS, down, real_session, write_offline

UTC = dt.timezone.utc
TZ_NEW_YORK = dt.timezone(dt.timedelta(hours=-5))
TZ_CAIRO = dt.timezone(dt.timedelta(hours=2))
TZ_KOLKATA = dt.timezone(dt.timedelta(hours=5, minutes=30))
NOW = dt.datetime(2026, 11, 9, 12, 0, 0, tzinfo=TZ_CAIRO)
TODAY = NOW.date()

OLD_EVENTS = {                                   # synthetic edge-case events: real field names, dates well before "today"
    "FLR": [{"flrID": "f1", "classType": "M1.0", "beginTime": "2026-10-01T04:00Z", "peakTime": "2026-10-01T04:20Z"},
            {"flrID": "f2", "classType": "C5.0", "beginTime": "2026-10-03T09:00Z", "peakTime": "2026-10-03T09:12Z"}],
    "CME": [{"activityID": "c1", "startTime": "2026-10-02T23:48Z"}],
    "GST": [{"gstID": "g1", "startTime": "2026-10-02T15:00Z", "allKpIndex": [{"kpIndex": 5.0}]}],
    "SEP": [],
}


def paths(tmp_path):
    return tmp_path / "cache.json", tmp_path / "archive.json"


def get(tmp_path, session, now=NOW, **kw):
    cache, archive = paths(tmp_path)
    return N.get_solar_activity(TODAY, session, cache, archive, now=now, **kw)


# ======================================================================= the newest EVENT keeps NASA's own date
def test_the_newest_event_keeps_the_date_nasa_gave_it_and_is_never_replaced_by_today(tmp_path):
    r = get(tmp_path, FakeSession(dict(OLD_EVENTS)))
    assert r.source == N.LIVE
    assert r.latest_event == "2026-10-03T09:12Z" and r.latest_event_date == "2026-10-03"      # NASA's value, unchanged
    assert r.latest_event_date != TODAY.isoformat() and r.as_of == TODAY.isoformat()          # retrieved today, event older


def test_the_event_date_survives_the_cache_round_trip_unchanged(tmp_path):
    get(tmp_path, FakeSession(dict(OLD_EVENTS)))
    saved = json.loads(paths(tmp_path)[0].read_text(encoding="utf-8"))
    assert saved["latest_event"] == "2026-10-03T09:12Z"
    later = get(tmp_path, busy_session(), now=NOW + dt.timedelta(minutes=10))               # inside the cache window
    assert later.source == N.CACHED and later.latest_event == "2026-10-03T09:12Z"
    assert later.retrieved_at.startswith("2026-11-09T12:00:00")                              # retrieval time NOT moved


def test_a_failed_check_keeps_the_old_event_date_and_the_original_retrieval_time(tmp_path):
    get(tmp_path, FakeSession(dict(OLD_EVENTS)))
    r = get(tmp_path, down_session(), now=NOW + dt.timedelta(days=3))
    assert r.source == N.CACHED and not r.is_live
    assert r.latest_event == "2026-10-03T09:12Z" and r.as_of == "2026-11-09"                  # last SUCCESSFUL retrieval
    assert r.retrieved_text(TZ_CAIRO) == "2026-11-09 12:00"


def test_when_nasa_lists_no_events_there_is_no_event_date_and_none_is_invented(tmp_path):
    r = get(tmp_path, FakeSession({ep: [] for ep in C.DONKI["endpoints"]}))
    assert r.source == N.LIVE and r.latest_event is None and r.latest_event_date is None
    assert r.counts and not any(r.counts.values())
    assert "latest_event" not in json.loads(paths(tmp_path)[0].read_text(encoding="utf-8"))


def test_events_without_a_usable_time_are_ignored_not_guessed():
    events = {"FLR": [{"flrID": "x"}, {"flrID": "y", "beginTime": "garbage"}, {"flrID": "z", "beginTime": 5}],
              "CME": [{"activityID": "c", "startTime": "2026-08-01T01:02Z"}], "GST": [], "SEP": []}
    assert N.latest_event_time(events) == "2026-08-01T01:02Z"
    assert N.latest_event_time({"FLR": [{"flrID": "x"}], "CME": [], "GST": [], "SEP": []}) is None
    assert N.latest_event_time({}) is None


def test_every_endpoint_counts_towards_the_newest_event():
    for ep, key in (("FLR", "peakTime"), ("CME", "startTime"), ("GST", "startTime"), ("SEP", "eventTime")):
        events = {e: [] for e in ("FLR", "CME", "GST", "SEP")}
        events[ep] = [{key: "2026-11-01T10:00Z"}]
        assert N.latest_event_time(events) == "2026-11-01T10:00Z"


def test_the_bundled_archive_reports_its_real_newest_event_separately_from_when_it_was_saved(tmp_path):
    archive = json.loads(Path(config.DONKI_ARCHIVE_PATH).read_text(encoding="utf-8"))
    newest = N.latest_event_time(archive["events"])
    r = N.get_solar_activity(TODAY, down_session(), tmp_path / "none.json", Path(config.DONKI_ARCHIVE_PATH), now=NOW)
    assert r.source == N.ARCHIVED and not r.is_live and r.latest_event == newest
    assert r.as_of == fileio.local_date(fileio.parse_time(archive["fetched_at"])).isoformat()     # the SNAPSHOT's own date


def test_the_solar_activity_number_is_unchanged_by_the_new_date_fields(tmp_path):
    r = get(tmp_path, FakeSession(dict(OLD_EVENTS)))
    assert r.level == N.activity_level(r.counts) == N.activity_level(N.summarize(OLD_EVENTS))
    again = get(tmp_path, down_session(), now=NOW + dt.timedelta(days=2))
    assert again.level == r.level and again.counts == r.counts


# ======================================================================= timezones and the stored time
def test_retrieval_times_are_stored_with_their_utc_offset(tmp_path):
    get(tmp_path, busy_session())
    saved = json.loads(paths(tmp_path)[0].read_text(encoding="utf-8"))
    assert saved["fetched_at"] == "2026-11-09T12:00:00+02:00"
    assert fileio.parse_time(saved["fetched_at"]) == NOW


def test_cache_age_is_measured_in_real_time_across_timezones(tmp_path):
    """Written at 12:00 in Cairo (= 10:00 UTC). Later 'now' values are given in other timezones."""
    get(tmp_path, busy_session())
    same_moment = dt.datetime(2026, 11, 9, 15, 30, tzinfo=TZ_KOLKATA)                          # = 10:00 UTC exactly
    inside = dt.datetime(2026, 11, 9, 5, 30, tzinfo=TZ_NEW_YORK)                                # = 10:30 UTC, 30 min later
    outside = dt.datetime(2026, 11, 9, 7, 1, tzinfo=TZ_NEW_YORK)                                # = 12:01 UTC, just over 2 h later
    s = busy_session()
    assert get(tmp_path, s, now=same_moment).source == N.CACHED and s.calls == []
    assert get(tmp_path, s, now=inside).source == N.CACHED and s.calls == []
    assert get(tmp_path, busy_session(), now=outside).source == N.LIVE


def test_a_clock_set_back_never_makes_old_data_look_fresh(tmp_path):
    get(tmp_path, busy_session())
    s = busy_session()
    r = get(tmp_path, s, now=NOW - dt.timedelta(days=1))                                       # 'now' BEFORE the cache time
    assert r.source == N.LIVE and len(s.calls) == 4


def test_an_older_cache_written_without_an_offset_is_still_read(tmp_path):
    cache, _ = paths(tmp_path)
    cache.write_text(json.dumps({"fetched_at": "2026-11-09T12:00:00", "window": ["2026-10-10", "2026-11-09"],
                                 "counts": {k: 0 for k in N.COUNT_KEYS}}), encoding="utf-8")
    r = get(tmp_path, down_session(), now=NOW + dt.timedelta(days=2))
    assert r.source == N.CACHED and r.as_of == "2026-11-09" and r.retrieved_at and r.latest_event is None


def test_the_retrieval_time_is_shown_in_the_viewers_timezone_and_the_date_follows_it():
    sol = N.SolarActivity(0.4, N.CACHED, "2026-11-09", None, {}, "2026-11-09T23:30:00-05:00", None)
    assert sol.retrieved_text(TZ_NEW_YORK) == "2026-11-09 23:30"
    assert sol.retrieved_text(UTC) == "2026-11-10 04:30"                                       # the next day in UTC
    assert sol.retrieved_text(TZ_CAIRO) == "2026-11-10 06:30"
    assert fileio.local_text("2026-11-09T23:30:00-05:00", UTC) == "2026-11-10 04:30"
    assert fileio.local_text("not a time") is None and fileio.local_text(None) is None


def test_the_retrieved_date_is_the_local_date_not_the_storage_timezone(tmp_path):
    late_utc = dt.datetime(2026, 11, 9, 23, 30, tzinfo=UTC)
    r = N.fetch_live(late_utc.date(), busy_session(), late_utc)
    assert r.retrieved_at == "2026-11-09T23:30:00+00:00"
    assert r.as_of == fileio.local_date(late_utc).isoformat()                                  # local calendar day


def test_without_a_stored_time_the_date_alone_is_shown():
    sol = N.SolarActivity(0.3, N.ARCHIVED, "2026-11-09")
    assert sol.retrieved_text() == "2026-11-09"


# ======================================================================= when a fresh request is made
def test_opening_uses_a_recent_cache_but_the_refresh_button_always_asks_nasa(tmp_path):
    get(tmp_path, busy_session())
    s = busy_session()
    assert get(tmp_path, s, now=NOW + dt.timedelta(minutes=5)).source == N.CACHED and s.calls == []
    s = FakeSession(dict(OLD_EVENTS))
    r = get(tmp_path, s, now=NOW + dt.timedelta(minutes=5), force=True)
    assert len(s.calls) == 4 and r.source == N.LIVE and r.latest_event == "2026-10-03T09:12Z"
    assert r.retrieved_at.startswith("2026-11-09T12:05:00")


def test_a_forced_refresh_that_fails_still_shows_the_last_good_data_as_cached(tmp_path):
    first = get(tmp_path, busy_session())
    r = get(tmp_path, down_session(), now=NOW + dt.timedelta(minutes=5), force=True)
    assert r.source == N.CACHED and not r.is_live and r.retrieved_at == first.retrieved_at and r.level == first.level


def test_forced_refresh_never_touches_the_network_when_offline_mode_is_requested(tmp_path):
    s = busy_session()
    assert get(tmp_path, s, force=True, allow_network=False).source == N.DEFAULT and s.calls == []


def test_the_cache_window_is_short_enough_that_old_dates_do_not_linger():
    assert 0 < C.DONKI["cache_ttl_hours"] <= 1 and 0 < C.OSDR["cache_ttl_days"] <= 1


def test_a_successful_refresh_replaces_an_old_cache_with_the_new_retrieval_time(tmp_path):
    get(tmp_path, busy_session())
    later = NOW + dt.timedelta(days=4)
    get(tmp_path, busy_session(), now=later)
    saved = json.loads(paths(tmp_path)[0].read_text(encoding="utf-8"))
    assert fileio.parse_time(saved["fetched_at"]) == later


# ======================================================================= OSDR
def osdr_get(tmp_path, session, now=NOW, **kw):
    off = write_offline(tmp_path / "off.json")
    return O.get_studies(session, TODAY, tmp_path / "cache.json", off, now=now, **kw)


def test_osdr_live_studies_record_the_exact_retrieval_time_and_keep_the_study_dates(tmp_path):
    r = osdr_get(tmp_path, real_session())
    assert r.source == O.LIVE and r.retrieved_at.startswith("2026-11-09T12:00:00") and r.as_of == "2026-11-09"
    assert r.retrieved_text(TZ_CAIRO) == "2026-11-09 12:00"
    for e in r.entries:                                                   # the study's own release date is untouched
        assert e["record"]["release_date"] <= TODAY.isoformat() and e["retrieved"] == "2026-11-09"
    assert any(e["record"]["release_date"] != "2026-11-09" for e in r.entries)


def test_osdr_cache_times_have_an_offset_and_the_refresh_button_bypasses_the_cache(tmp_path):
    osdr_get(tmp_path, real_session())
    saved = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
    assert saved["fetched_at"] == "2026-11-09T12:00:00+02:00"
    s = real_session()
    assert osdr_get(tmp_path, s, now=NOW + dt.timedelta(minutes=5)).source == O.CACHED and s.calls == []
    s = real_session()
    r = osdr_get(tmp_path, s, now=NOW + dt.timedelta(minutes=5), force=True)
    assert len(s.calls) == len(ACCS) and r.source == O.LIVE and r.retrieved_at.startswith("2026-11-09T12:05:00")


def test_osdr_failed_refresh_shows_the_last_successful_retrieval_as_cached(tmp_path):
    osdr_get(tmp_path, real_session())
    r = osdr_get(tmp_path, down(), now=NOW + dt.timedelta(days=2), force=True)
    assert r.source == O.CACHED and not r.is_live and r.retrieved_text(TZ_CAIRO) == "2026-11-09 12:00"
    assert "Not live" in r.describe("en") and "retrieved 2026-11-09" in r.describe("en")


def test_osdr_offline_set_has_only_a_date_and_never_a_live_label(tmp_path):
    r = osdr_get(tmp_path, down())
    assert r.source == O.OFFLINE and r.retrieved_at is None and r.retrieved_text() == r.as_of == "2026-10-01"
    assert "Not live" in r.describe("en")


def test_osdr_cache_with_an_offsetless_older_time_is_still_usable(tmp_path):
    osdr_get(tmp_path, real_session())
    p = tmp_path / "cache.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["fetched_at"] = "2026-11-09T12:00:00"
    p.write_text(json.dumps(d), encoding="utf-8")
    r = osdr_get(tmp_path, down(), now=NOW + dt.timedelta(days=3))
    assert r.source == O.CACHED and len(r.entries) == len(ACCS) and r.as_of == "2026-11-09"


# ======================================================================= the background loader and "last checked"
@pytest.fixture
def recorded(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DONKI_CACHE_PATH", tmp_path / "d.json")
    monkeypatch.setattr(config, "OSDR_CACHE_PATH", tmp_path / "o.json")
    calls = []
    studies = O.get_studies(allow_network=False)

    def solar(**kw):
        calls.append(("donki", kw))
        if kw.get("allow_network", True) and kw.get("fail"):
            raise RuntimeError
        return N.SolarActivity(0.5, N.LIVE if kw.get("allow_network", True) else N.ARCHIVED, "2026-11-13")

    def osdr(**kw):
        calls.append(("osdr", kw))
        return studies
    monkeypatch.setattr(N, "get_solar_activity", solar)
    monkeypatch.setattr(O, "get_studies", osdr)
    return calls


def test_refresh_passes_force_only_when_the_player_asks(recorded):
    n = NasaData(BackgroundLoader(inline=True))
    n.refresh()
    n.pump()
    n.refresh(force=True)
    n.pump()
    online = [(name, kw) for name, kw in recorded if kw.get("allow_network", True)]
    assert [(name, kw["force"]) for name, kw in online] == [("donki", False), ("osdr", False), ("donki", True),
                                                             ("osdr", True)]


def test_last_checked_is_recorded_after_every_check_even_a_failed_one(recorded):
    n = NasaData(BackgroundLoader(inline=True))
    assert n.checked_at == {"donki": None, "osdr": None}
    when = dt.datetime(2026, 11, 13, 18, 30, tzinfo=TZ_CAIRO)
    n.refresh()
    n.pump(now=when)
    assert fileio.parse_time(n.checked_at["donki"]) == when and fileio.local_text(n.checked_at["osdr"], TZ_CAIRO) == "2026-11-13 18:30"
    n.loader._done.put(("donki", False, "ReadTimeout"))                     # a failed check still counts as "checked"
    later = when + dt.timedelta(minutes=7)
    n.pump(now=later)
    assert n.state["donki"] == "error" and fileio.parse_time(n.checked_at["donki"]) == later
    assert n.solar.source in (N.LIVE, N.ARCHIVED)                             # and the previous data stays on screen
