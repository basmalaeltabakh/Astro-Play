"""Outpost Command flow tests: database, background loading, NASA state, session logic. No window, no network."""
import ast
import json
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from astro import db as dbmod
from astro import i18n, nasa_data, osdr_data
from astro import outpost as O
from astro import outpost_config as C
from astro.db import Database
from astro.outpost_flow import BackgroundLoader, NasaData, OutpostSession, state_from_json, state_to_json

ROOT = Path(__file__).resolve().parent.parent
SOLAR = nasa_data.SolarActivity(0.42, nasa_data.CACHED, "2026-11-01", ("2026-10-01", "2026-10-31"))


@pytest.fixture(autouse=True)
def nasa_caches_in_a_temp_folder(tmp_path, monkeypatch):
    """The NASA caches live in a temp folder for every test here (real HTTP is blocked suite-wide by tests/netguard.py)."""
    from astro import config
    monkeypatch.setattr(config, "DONKI_CACHE_PATH", tmp_path / "donki_cache.json")
    monkeypatch.setattr(config, "OSDR_CACHE_PATH", tmp_path / "osdr_cache.json")


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "t.db")


def new_session(db, profile_id=None, site="moon", difficulty="normal", seed=123, solar=SOLAR):
    return OutpostSession.new(db, profile_id, site, difficulty, solar, seed)


def plan(s):
    """A sensible plan for the current sol (used to play whole runs)."""
    s.reset()
    for cat, want in (("life_support", 12), ("shielding", 6), ("comms", 5), ("science", 4)):
        s.adjust(cat, want)


def play_out(s, max_sols=40):
    n = 0
    while s.running and n < max_sols:
        plan(s)
        assert s.advance()
        n += 1
    return s


# ======================================================================= database
def test_outpost_runs_table_is_created_and_has_no_credentials_column(tmp_path):
    d = Database(tmp_path / "x.db")
    with sqlite3.connect(d.path) as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(outpost_runs)")]
    for needed in ("profile_id", "site", "difficulty", "seed", "status", "sol", "score", "stars", "fail_reason",
                   "solar_level", "solar_source", "solar_as_of", "state_json", "history_json", "created_at", "updated_at"):
        assert needed in cols
    assert not [c for c in cols if any(w in c.lower() for w in ("key", "token", "password", "email", "name"))]


def test_existing_tables_and_records_are_preserved_when_the_new_table_is_added(tmp_path):
    old_schema = dbmod.SCHEMA.split("CREATE TABLE IF NOT EXISTS outpost_runs")[0]
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as c:                                   # a database made BEFORE Outpost Command existed
        c.executescript(old_schema)
        c.execute("INSERT INTO profiles (name, age_group, xp, skill) VALUES ('Nova', 'mid', 123, 0.7)")
        c.execute("INSERT INTO mission_progress (profile_id, mission_id, completed, best_stars, attempts) "
                  "VALUES (1, 'moon', 1, 3, 2)")
        c.execute("INSERT INTO achievements (profile_id, achievement_id) VALUES (1, 'first_mission')")
        c.execute("INSERT INTO settings (profile_id, key, value) VALUES (1, 'samples_analyzed', '4')")
        c.execute("INSERT INTO performance (profile_id, mission_id, mistakes, hints, seconds, tier, skill_after) "
                  "VALUES (1, 'moon', 1, 0, 90.5, 'normal', 0.7)")
        assert not c.execute("SELECT name FROM sqlite_master WHERE name='outpost_runs'").fetchall()
    d = Database(path)                                                  # opening it with the new code
    assert d.get_profile(1)["xp"] == 123 and d.get_profile(1)["name"] == "Nova"
    assert d.get_progress(1)["moon"]["best_stars"] == 3 and d.completed_missions(1) == {"moon"}
    assert d.list_achievements(1) == ["first_mission"] and d.get_setting(1, "samples_analyzed") == "4"
    assert d.performance_history(1)[0]["seconds"] == 90.5
    assert d.list_outpost_runs(1) == []                                 # the new table exists and is empty


def test_init_schema_is_idempotent_and_never_drops_outpost_runs(tmp_path):
    d = Database(tmp_path / "x.db")
    rid = d.create_outpost_run(None, "moon", "normal", 5, 0.3, "default", None, "{}")
    d.init_schema()
    Database(d.path)
    assert d.get_outpost_run(rid)["seed"] == 5


def test_run_rows_store_the_required_fields(db):
    s = new_session(db, None, "mars", "hard", 777)
    row = db.get_outpost_run(s.run_id)
    assert (row["site"], row["difficulty"], row["seed"], row["status"], row["profile_id"]) == ("mars", "hard", 777,
                                                                                               "running", None)
    assert (row["solar_level"], row["solar_source"], row["solar_as_of"]) == (0.42, "cached", "2026-11-01")
    assert row["created_at"] and row["updated_at"] and state_from_json(row["state_json"]) == s.state


def test_finished_runs_store_result_score_and_timestamp(db):
    s = play_out(new_session(db, difficulty="easy", seed=3))
    row = db.get_outpost_run(s.run_id)
    assert row["status"] in ("won", "lost") and row["status"] == s.state.status
    assert row["score"] == s.state.score and row["stars"] == O.rating(s.state) and row["updated_at"]
    assert (row["fail_reason"] is None) == (s.state.status == O.WON)
    assert len(json.loads(row["history_json"])) == len(s.history)


def test_runs_belong_to_profiles_and_are_deleted_with_them(db):
    pid = db.create_profile("Astro")
    other = db.create_profile("Luna")
    a, b, anon = new_session(db, pid), new_session(db, other), new_session(db, None)
    assert [r["id"] for r in db.list_outpost_runs(pid)] == [a.run_id]
    assert [r["id"] for r in db.list_outpost_runs(None)] == [anon.run_id]
    db.delete_profile(pid)
    assert db.get_outpost_run(a.run_id) is None and db.get_outpost_run(b.run_id) is not None
    assert db.get_outpost_run(anon.run_id) is not None


def test_invalid_status_is_rejected_and_queries_are_parameterised(db):
    s = new_session(db)
    with pytest.raises(ValueError):
        db.update_outpost_run(s.run_id, status="cheating", sol=1, score=0, stars=0, fail_reason=None, state_json="{}",
                              history_json="[]")
    assert db.list_outpost_runs("1; DROP TABLE profiles; --") == []
    assert db.get_outpost_run("1 OR 1=1") is None
    assert db.get_profile is not None and db.list_profiles() == []


def test_best_score_counts_only_won_runs_per_player(db):
    pid = db.create_profile("Astro")
    a = new_session(db, pid)
    db.update_outpost_run(a.run_id, status="won", sol=10, score=321.5, stars=2, fail_reason=None, state_json="{}",
                          history_json="[]")
    b = new_session(db, pid)
    db.update_outpost_run(b.run_id, status="lost", sol=3, score=999, stars=0, fail_reason="food", state_json="{}",
                          history_json="[]")
    assert db.best_outpost_score(pid) == 321.5 and db.best_outpost_score(None) == 0.0


# ======================================================================= saving and loading a state
def test_state_roundtrips_through_json_exactly():
    s = O.new_state("mars", "hard")
    for ev in (None, "dust_storm", "comms_blackout", "solar_storm"):
        s = O.step_sol(s, {"life_support": 6, "comms": 3}, ev)
        assert state_from_json(state_to_json(s)) == s


@pytest.mark.parametrize("bad", ["", "not json", "[]", "null", "{}", '{"sol": 1}',
                                 '{"sol": "x", "power": 1}', json.dumps({**json.loads(state_to_json(O.new_state())),
                                                                         "site": "venus"}),
                                 json.dumps({**json.loads(state_to_json(O.new_state())), "status": "cheating"}),
                                 json.dumps({**json.loads(state_to_json(O.new_state())), "oxygen": True}),
                                 json.dumps({**json.loads(state_to_json(O.new_state())), "sol": 0}),
                                 json.dumps({**json.loads(state_to_json(O.new_state())), "log": [[1, 2, 3]]})])
def test_damaged_saved_states_are_rejected_without_raising(bad):
    assert state_from_json(bad) is None


# ======================================================================= background loader
def test_jobs_run_off_the_calling_thread_and_results_are_polled_later():
    gate, seen = threading.Event(), {}
    loader = BackgroundLoader()

    def job():
        seen["thread"] = threading.current_thread()
        gate.wait(5)
        return 42
    assert loader.start("x", job) is True                                # returns at once
    assert loader.is_loading("x") and loader.is_loading() and loader.poll() == []
    gate.set()
    for _ in range(200):
        out = loader.poll()
        if out:
            break
        threading.Event().wait(0.01)
    assert out == [("x", True, 42)] and seen["thread"] is not threading.current_thread() and seen["thread"].daemon
    for _ in range(100):
        if not loader.is_loading("x"):
            break
        threading.Event().wait(0.01)
    assert not loader.is_loading("x") and loader.poll() == []


def test_a_running_job_is_never_started_twice():
    gate, calls = threading.Event(), []
    loader = BackgroundLoader()
    assert loader.start("x", lambda: (calls.append(1), gate.wait(5))[1]) is True
    assert [loader.start("x", lambda: calls.append(2)) for _ in range(5)] == [False] * 5
    gate.set()
    for _ in range(200):
        if loader.poll():
            break
        threading.Event().wait(0.01)
    assert calls == [1]


def test_worker_errors_are_captured_not_raised():
    loader = BackgroundLoader()
    loader.start("bad", lambda: (_ for _ in ()).throw(ValueError("secret detail")))
    for _ in range(200):
        out = loader.poll()
        if out:
            break
        threading.Event().wait(0.01)
    assert out == [("bad", False, "ValueError")]                         # only the error NAME is passed on


def test_inline_mode_runs_synchronously():
    loader = BackgroundLoader(inline=True)
    assert loader.start("a", lambda: 1) and loader.start("a", lambda: 2)  # finished, so it can run again
    assert loader.poll() == [("a", True, 1), ("a", True, 2)]
    loader.start("e", lambda: 1 / 0)
    assert loader.poll() == [("e", False, "ZeroDivisionError")] and not loader.is_loading()


def test_poll_never_blocks_and_independent_jobs_do_not_interfere():
    gate = threading.Event()
    loader = BackgroundLoader()
    loader.start("slow", lambda: gate.wait(5))
    loader.start("fast", lambda: "done")
    for _ in range(200):
        out = loader.poll()
        if out:
            break
        threading.Event().wait(0.01)
    assert out == [("fast", True, "done")] and loader.is_loading("slow")
    gate.set()


# ======================================================================= NASA data state
def fake_solar(level=0.7, source=nasa_data.LIVE):
    return nasa_data.SolarActivity(level, source, "2026-11-09", ("2026-10-10", "2026-11-09"), {})


def test_nasa_data_starts_from_local_files_only_so_the_game_works_offline(monkeypatch):
    calls = []
    real_solar, real_studies = nasa_data.get_solar_activity, osdr_data.get_studies
    monkeypatch.setattr(nasa_data, "get_solar_activity", lambda **kw: (calls.append(("d", kw)), real_solar(**kw))[1])
    monkeypatch.setattr(osdr_data, "get_studies", lambda **kw: (calls.append(("o", kw)), real_studies(**kw))[1])
    monkeypatch.setattr("requests.get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))
    n = NasaData(BackgroundLoader(inline=True))
    assert [kw["allow_network"] for _, kw in calls] == [False, False]
    assert n.solar.source in (nasa_data.CACHED, nasa_data.ARCHIVED, nasa_data.DEFAULT)
    assert n.studies.source in (osdr_data.CACHED, osdr_data.OFFLINE) and len(n.studies.entries) >= 8
    assert n.state == {"donki": "idle", "osdr": "idle"} and not n.loading


def test_refresh_starts_both_jobs_once_and_pump_applies_results(monkeypatch):
    studies = osdr_data.get_studies(allow_network=False)
    monkeypatch.setattr(nasa_data, "get_solar_activity", lambda **kw: fake_solar() if kw.get("allow_network", True)
                        else nasa_data.SolarActivity(0.3, nasa_data.DEFAULT))
    monkeypatch.setattr(osdr_data, "get_studies", lambda **kw: studies)
    n = NasaData(BackgroundLoader(inline=True))
    assert n.refresh() is True and n.state == {"donki": "loading", "osdr": "loading"} and n.loading
    assert n.pump() is True
    assert n.state == {"donki": "ok", "osdr": "ok"} and n.solar.source == nasa_data.LIVE and n.solar.level == 0.7
    assert not n.loading and n.pump() is False                           # nothing more to apply


def test_a_second_refresh_while_loading_is_ignored(monkeypatch):
    gate, calls = threading.Event(), []
    monkeypatch.setattr(nasa_data, "get_solar_activity", lambda **kw: (calls.append("d"), gate.wait(5), fake_solar())[2]
                        if kw.get("allow_network", True) else nasa_data.SolarActivity(0.3, nasa_data.DEFAULT))
    monkeypatch.setattr(osdr_data, "get_studies", lambda **kw: (calls.append("o"), gate.wait(5),
                                                                 osdr_data.StudySet([], osdr_data.NONE))[2]
                        if kw.get("allow_network", True) else osdr_data.StudySet([], osdr_data.NONE))
    n = NasaData(BackgroundLoader())
    assert n.refresh() is True
    assert [n.refresh() for _ in range(4)] == [False] * 4
    gate.set()
    for _ in range(300):
        n.pump()
        if not n.loading:
            break
        threading.Event().wait(0.01)
    assert sorted(calls) == ["d", "o"] and not n.loading


def test_worker_failures_mark_an_error_and_keep_the_previous_data(monkeypatch):
    def boom(**kw):
        if kw.get("allow_network", True):
            raise RuntimeError("boom")
        return fake_solar(0.5, nasa_data.ARCHIVED)
    monkeypatch.setattr(nasa_data, "get_solar_activity", boom)
    monkeypatch.setattr(osdr_data, "get_studies", lambda **kw: osdr_data.StudySet([], osdr_data.NONE))
    n = NasaData(BackgroundLoader(inline=True))
    before = n.solar
    n.refresh()
    n.pump()
    assert n.state["donki"] == "error" and n.error["donki"] == "RuntimeError" and n.solar == before
    assert n.state["osdr"] == "ok" and "error" in n.state.values() and n.unreachable


def test_an_empty_osdr_result_never_replaces_saved_cards(monkeypatch):
    saved = osdr_data.get_studies(allow_network=False)
    monkeypatch.setattr(nasa_data, "get_solar_activity", lambda **kw: fake_solar())
    monkeypatch.setattr(osdr_data, "get_studies", lambda **kw: saved if not kw.get("allow_network", True) is True
                        else osdr_data.StudySet([], osdr_data.NONE))
    n = NasaData(BackgroundLoader(inline=True))
    n.refresh()
    n.pump()
    assert len(n.studies.entries) == len(saved.entries) > 0


def test_unreachable_is_reported_when_only_fallback_data_came_back(monkeypatch):
    monkeypatch.setattr(nasa_data, "get_solar_activity", lambda **kw: nasa_data.SolarActivity(0.3, nasa_data.DEFAULT))
    saved = osdr_data.get_studies(allow_network=False)
    monkeypatch.setattr(osdr_data, "get_studies", lambda **kw: saved)
    n = NasaData(BackgroundLoader(inline=True))
    n.refresh()
    n.pump()
    assert n.unreachable and not n.solar.is_live


# ======================================================================= the session: budget and allocation
def test_new_session_starts_a_saved_run_with_the_chosen_setup(db):
    s = new_session(db, None, "mars", "easy", 9)
    assert s.state == O.new_state("mars", "easy") and s.running and s.seed == 9
    assert s.available() == O.available_power(s.state) and s.allocated() == 0 and s.unspent() == s.available()
    assert s.solar().level == 0.42 and s.solar().source == "cached" and s.solar().as_of == "2026-11-01"


def test_adjusting_respects_limits_budget_and_never_goes_negative(db):
    s = new_session(db)
    assert s.adjust("science", -5) is False and s.alloc["science"] == 0
    assert s.adjust("science", 100) is True and s.alloc["science"] == C.ALLOC_LIMIT["science"]
    assert s.adjust("science", 1) is False
    for cat in ("life_support", "shielding", "comms"):
        s.adjust(cat, 100)
    assert s.allocated() <= s.available() and s.unspent() >= 0
    assert all(s.alloc[c] <= C.ALLOC_LIMIT[c] for c in C.ALLOCATIONS)
    assert s.adjust("nuclear", 1) is False and "nuclear" not in s.alloc
    s.reset()
    assert s.allocated() == 0


def test_the_budget_binds_before_the_limits_do(db):
    s = new_session(db)
    for cat in C.ALLOCATIONS:
        s.adjust(cat, 100)
    assert s.allocated() == s.available() < sum(C.ALLOC_LIMIT.values())
    assert s.unspent() == 0 and s.adjust("science", 1) is False
    assert s.adjust("science", -1) is True and s.unspent() == 1


def test_focus_only_accepts_the_configured_choices(db):
    s = new_session(db)
    assert s.set_focus(1.0) and s.focus == 1.0 and s.set_focus(0.0)
    assert not s.set_focus(0.3) and s.focus == 0.0 and not s.set_focus("x")
    assert set(C.LS_FOCUS_CHOICES) == {1.0, C.LS_FOCUS_DEFAULT, 0.0}


def test_comms_and_science_are_only_allocation_categories(db):
    s = new_session(db)
    assert set(s.alloc) == {"life_support", "shielding", "comms", "science"}
    assert set(O.resources(s.state)) == {"power", "life_support", "shielding"}
    assert "comms" not in O.resources(s.state) and "science" not in O.resources(s.state)


# ======================================================================= the preview (consequences before advancing)
def test_preview_matches_what_actually_happens_when_no_event_occurs(db):
    s = new_session(db, seed=1)
    s._event = None
    plan(s)
    p = s.preview()
    s.advance()
    st = s.state
    assert p["valid"] and p["next"]["oxygen"] == pytest.approx(st.oxygen) and p["next"]["power"] == pytest.approx(st.power)
    assert p["next"]["shielding"] == pytest.approx(st.shielding) and p["next"]["crew_health"] == pytest.approx(st.crew_health)


def test_preview_is_pure_and_does_not_depend_on_the_hidden_event(db):
    s = new_session(db)
    plan(s)
    before = (s.state, dict(s.alloc), s.focus, s.run_id)
    previews = []
    for ev in (None, "solar_storm", "dust_storm", "equipment_fault", "science_discovery"):
        s._event = ev
        previews.append(s.preview())
    assert all(p == previews[0] for p in previews)                       # events cannot leak through the preview
    assert (s.state, dict(s.alloc), s.focus, s.run_id) == before and s.history == []


def test_preview_warns_about_dangerous_plans(db):
    s = new_session(db)
    s.state = replace(s.state, oxygen=C.CONSUME["oxygen"] + 1)
    s.reset()
    assert "op_ui_warn_oxygen" in s.preview()["warnings"]                      # low but alive
    s.state = replace(s.state, oxygen=C.CONSUME["oxygen"])
    assert "op_ui_warn_lost_oxygen" in s.preview()["warnings"]                 # would reach zero
    s.state = replace(s.state, oxygen=60.0, food=C.CONSUME["food"] + C.LOW_LEVEL - 5)
    assert "op_ui_warn_food" in s.preview()["warnings"]
    s.state = replace(s.state, food=60.0, shielding=C.LOW_LEVEL + C.SHIELD_WEAR - 1)
    assert "op_ui_warn_shielding" in s.preview()["warnings"]
    for key in ("op_ui_warn_oxygen", "op_ui_warn_food", "op_ui_warn_shielding", "op_ui_warn_power",
                "op_ui_warn_lost_oxygen", "op_ui_warn_lost_food", "op_ui_warn_lost_crew_health"):
        assert i18n.has_key(key, "en") and i18n.has_key(key, "ar")
    assert new_session(db).preview()["valid"] and not play_out(new_session(db, difficulty="easy")).preview()["valid"]


# ======================================================================= forecasts: only what the rules allow
def views_for(db, comms_level, event, blackout=0):
    s = new_session(db)
    s.state = replace(s.state, comms_level=comms_level, comms_down_left=blackout)
    s._event = event
    return s.forecast_view()


def test_without_enough_communications_no_forecast_is_given_and_the_event_is_not_revealed(db):
    for level in range(0, C.COMMS_FORECAST_MIN):
        views = {ev: views_for(db, level, ev) for ev in [None, *C.EVENTS]}
        first = next(iter(views.values()))
        assert all(v == first for v in views.values()), level               # identical whatever the pending event is
        assert first["kind"] == "none" and not first["comms_ok"]
        for ev in C.EVENTS:
            assert ev not in json.dumps(first)


def test_basic_communications_reveal_only_the_category(db):
    for level in range(C.COMMS_FORECAST_MIN, C.COMMS_FORECAST_FULL):
        for ev, v in C.EVENTS.items():
            view = views_for(db, level, ev)
            assert view["kind"] == "category" and view["category"] == v["category"]
            assert ev not in json.dumps(view) and "severity" not in view and "event" not in view
        a, b = views_for(db, level, "dust_storm"), views_for(db, level, "dust_accumulation")
        assert a == b                                                         # two events, one category: indistinguishable
        assert views_for(db, level, None)["kind"] == "quiet"


def test_strong_communications_reveal_the_exact_event_and_its_severity(db):
    for ev, v in C.EVENTS.items():
        view = views_for(db, C.COMMS_FORECAST_FULL, ev)
        assert view["kind"] == "exact" and view["event"] == ev and view["severity"] == v["severity"]
    assert views_for(db, C.COMMS_FORECAST_FULL, None)["kind"] == "quiet"


def test_a_communications_blackout_removes_the_forecast_and_is_reported(db):
    view = views_for(db, 0, "solar_storm", blackout=2)
    assert view["kind"] == "none" and view["blackout_sols"] == 2 and "solar_storm" not in json.dumps(view)


def test_forecast_view_is_pure(db):
    s = new_session(db)
    s.state = replace(s.state, comms_level=C.COMMS_FORECAST_FULL)
    snapshot = (s.state, s._event, s.rng.getstate(), dict(s.alloc))
    for _ in range(5):
        s.forecast_view()
    assert (s.state, s._event, s.rng.getstate(), dict(s.alloc)) == snapshot


# ======================================================================= what already happened
def test_effects_and_last_sol_show_only_what_has_happened(db):
    s = new_session(db, seed=4)
    assert s.effects_view() == [] and s.last_sol_view() is None
    s._event = "dust_storm"
    plan(s)
    s.advance()
    eff = s.effects_view()
    assert eff and eff[0]["key"] == "op_ui_effect_dust" and eff[0]["sols"] == C.EVENTS["dust_storm"]["dust_sols"]
    assert eff[0]["percent"] == round(C.EVENTS["dust_storm"]["dust_factor"] * 100)
    last = s.last_sol_view()
    assert last["sol"] == 1 and last["event"] == "dust_storm" and last["severity"] == "medium"
    s._event = "comms_blackout"
    plan(s)
    s.advance()
    assert {e["key"] for e in s.effects_view()} >= {"op_ui_effect_comms_down"}


def test_quiet_sols_are_reported_as_quiet(db):
    s = new_session(db, seed=2)
    s._event = None
    plan(s)
    s.advance()
    assert s.last_sol_view()["event"] is None and s.last_sol_view()["severity"] is None


# ======================================================================= playing and finishing
def test_advancing_saves_the_run_every_sol(db):
    s = new_session(db, seed=11)
    for k in range(1, 4):
        plan(s)
        assert s.advance()
        row = db.get_outpost_run(s.run_id)
        assert row["sol"] == s.state.sol == k + 1 and state_from_json(row["state_json"]) == s.state
        assert len(json.loads(row["history_json"])) == k and row["status"] == "running"


def test_invalid_allocations_cannot_advance_and_change_nothing(db):
    s = new_session(db)
    s.alloc["life_support"] = 10 ** 6                                     # bypassing adjust(), as a bug or a hack might
    before = s.state
    assert s.advance() is False and s.state == before and s.history == []


def test_finishing_a_run_gives_a_result_with_explanation_and_stops_play(db):
    s = play_out(new_session(db, difficulty="hard", seed=5))
    r = s.result()
    assert r["status"] == s.state.status and r["seed"] == 5 and r["score"] == s.state.score
    if r["status"] == O.LOST:
        assert r["failure_key"].startswith("op_fail_") and len(r["failure_text"]) > 60 and r["stars"] == 0
    else:
        assert r["stars"] in (1, 2, 3) and r["failure_text"] == ""
    assert s.advance() is False and s.adjust("science", 1) is False and not s.preview()["valid"]
    assert new_session(db).result() is None


def test_a_run_that_cannot_survive_ends_in_failure_with_the_educational_text(db):
    s = new_session(db, difficulty="hard", seed=1)
    for _ in range(30):
        s.reset()
        if not s.advance():
            break
    r = s.result()
    assert r and r["status"] == O.LOST and r["failure_text"] and r["failure_key"] in (
        "op_fail_oxygen", "op_fail_food", "op_fail_crew_health")
    assert db.get_outpost_run(s.run_id)["fail_reason"] == s.state.fail_reason


def test_allocation_is_carried_to_the_next_sol_and_trimmed_to_the_budget(db):
    s = new_session(db, seed=3)
    s._event = None
    plan(s)
    first = dict(s.alloc)
    s.advance()
    assert all(s.alloc[c] <= first[c] for c in C.ALLOCATIONS) and s.allocated() <= s.available()
    assert s.alloc == first or s.allocated() == s.available()


# ======================================================================= resume and determinism
def test_resuming_continues_exactly_as_an_uninterrupted_run(db, tmp_path):
    reference = play_out(new_session(Database(tmp_path / "ref.db"), seed=77, difficulty="normal"))
    for stop_after in (1, 3, 5, 8):
        d = Database(tmp_path / f"r{stop_after}.db")
        s = new_session(d, seed=77, difficulty="normal")
        for _ in range(stop_after):
            if s.running:
                plan(s)
                s.advance()
        if not s.running:
            continue
        resumed = OutpostSession.resume(d, None)
        assert resumed is not None and resumed.run_id == s.run_id and resumed.state == s.state
        assert resumed._event == s._event                                  # even the pending event is the same
        play_out(resumed)
        assert resumed.state == reference.state and resumed.history == reference.history, stop_after


def test_same_seed_and_plans_give_identical_runs_and_different_seeds_differ(tmp_path):
    runs = [play_out(new_session(Database(tmp_path / f"{i}.db"), seed=sd)).history for i, sd in enumerate((5, 5, 6, 7))]
    assert runs[0] == runs[1]
    assert runs[0] != runs[2] or runs[0] != runs[3]


def test_only_one_unfinished_run_per_player_and_resume_returns_the_latest(db):
    pid = db.create_profile("Astro")
    a = new_session(db, pid, seed=1)
    b = new_session(db, pid, seed=2)
    assert db.get_outpost_run(a.run_id)["status"] == "abandoned" and db.get_outpost_run(b.run_id)["status"] == "running"
    assert OutpostSession.resume(db, pid).run_id == b.run_id
    anon = new_session(db, None, seed=3)
    assert OutpostSession.resume(db, None).run_id == anon.run_id and OutpostSession.resume(db, pid).run_id == b.run_id


def test_finished_and_abandoned_runs_cannot_be_resumed(db):
    s = play_out(new_session(db, difficulty="easy", seed=2))
    assert OutpostSession.resume(db, None) is None
    t = new_session(db, seed=9)
    t.abandon()
    assert OutpostSession.resume(db, None) is None and db.get_outpost_run(t.run_id)["status"] == "abandoned"


@pytest.mark.parametrize("damage", ["state", "history", "garbage_state"])
def test_a_damaged_save_is_retired_not_trusted(db, damage):
    s = new_session(db, seed=4)
    plan(s)
    s.advance()
    row = db.get_outpost_run(s.run_id)
    if damage == "state":
        db.update_outpost_run(s.run_id, status="running", sol=2, score=0, stars=0, fail_reason=None,
                              state_json='{"sol": "bad"}', history_json=row["history_json"])
    elif damage == "history":
        db.update_outpost_run(s.run_id, status="running", sol=2, score=0, stars=0, fail_reason=None,
                              state_json=row["state_json"], history_json="[]")           # one sol played, no history
    else:
        db.update_outpost_run(s.run_id, status="running", sol=2, score=0, stars=0, fail_reason=None,
                              state_json="not json", history_json="also not json")
    assert OutpostSession.resume(db, None) is None
    assert db.get_outpost_run(s.run_id)["status"] == "abandoned" and OutpostSession.resume(db, None) is None


def test_resume_with_no_saved_run_is_none(db):
    assert OutpostSession.resume(db, None) is None and OutpostSession.resume(db, 999) is None


# ======================================================================= scope and independence
def _imports(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods |= {(n.module or "").split(".")[0]} | {a.name for a in n.names}
    return mods


def test_flow_has_no_ui_engine_and_the_simulation_does_not_know_the_flow():
    assert not _imports(ROOT / "astro" / "outpost_flow.py") & {"ursina", "panda3d", "game"}
    for name in ("outpost.py", "outpost_config.py", "nasa_data.py", "osdr_data.py"):
        assert not _imports(ROOT / "astro" / name) & {"outpost_flow", "outpost_ui", "ursina", "panda3d"}, name


def test_outpost_is_not_part_of_the_mission_collection():
    from astro.missions import MISSIONS, ORDER
    assert [m.id for m in MISSIONS] == list(ORDER) == ["moon", "mars", "orbital", "europa"]
    assert not [m for m in MISSIONS if "outpost" in m.id.lower()]


def test_playing_outpost_does_not_touch_profile_progress(db):
    pid = db.create_profile("Astro")
    db.add_xp(pid, 77)
    db.set_skill(pid, 0.6)
    db.record_completion(pid, "moon", 2)
    before = (db.get_profile(pid)["xp"], db.get_profile(pid)["skill"], db.get_progress(pid), db.list_achievements(pid),
              db.performance_history(pid))
    play_out(new_session(db, pid, seed=8))
    after = (db.get_profile(pid)["xp"], db.get_profile(pid)["skill"], db.get_progress(pid), db.list_achievements(pid),
             db.performance_history(pid))
    assert before == after


def test_ui_keys_are_translated_in_both_languages_with_matching_placeholders():
    import re
    ph = lambda s: sorted(re.findall(r"{(\w+)}", s))
    ui_keys = {k for k in i18n.STRINGS["en"] if k.startswith("op_ui_")}
    assert len(ui_keys) > 70
    for k in ui_keys:
        assert i18n.has_key(k, "en") and i18n.has_key(k, "ar"), k
        assert ph(i18n.STRINGS["en"][k]) == ph(i18n.STRINGS["ar"][k]), k
        if k != "op_ui_value_delta":                                       # a pure "{name}: {value} ({delta})" template
            assert i18n.STRINGS["en"][k] != i18n.STRINGS["ar"][k] and i18n.has_arabic(i18n.STRINGS["ar"][k]), k
    used = set(re.findall(r'"(op_ui_[a-z_]+)"', (ROOT / "astro" / "game" / "outpost_ui.py").read_text(encoding="utf-8")))
    used |= set(re.findall(r'"(op_ui_[a-z_]+)"', (ROOT / "astro" / "outpost_flow.py").read_text(encoding="utf-8")))
    used = {k for k in used if not k.endswith("_")}                      # "op_ui_hint_" + cat style prefixes: see below
    assert used <= ui_keys
    dynamic = ({f"op_ui_site_{s}" for s in C.SITES} | {f"op_ui_status_{s}" for s in (O.RUNNING, O.WON, O.LOST)}
               | {f"op_ui_sev_{s}" for s in ("low", "medium", "high")} | {f"op_ui_hint_{c}" for c in C.ALLOCATIONS}
               | {f"op_ui_warn_lost_{r}" for r in ("oxygen", "food", "crew_health")})
    assert dynamic <= ui_keys
    for cat in C.ALLOCATIONS:                                              # category names reuse the earlier op_* strings
        assert i18n.has_key(f"op_{cat}", "en") and i18n.has_key(f"op_{cat}", "ar")
    for diff in C.DIFFICULTY:
        assert i18n.has_key(diff, "en") and i18n.has_key(diff, "ar")
