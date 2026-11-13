"""Safety nets under Outpost Command: loader lifecycle, atomic cache writes, database status enforcement.

No window needed; the window-level lifecycle tests live in test_outpost_ui.py."""
import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from astro import config, nasa_data, osdr_data
from astro import db as dbmod
from astro import fileio
from astro.db import Database
from astro.outpost_flow import BackgroundLoader, NasaData

ROOT = Path(__file__).resolve().parent.parent


def solar(level=0.7):
    return nasa_data.SolarActivity(level, nasa_data.LIVE, "2026-11-09", ("2026-10-10", "2026-11-09"), {})


def wait_for(cond, seconds=5.0):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


@pytest.fixture(autouse=True)
def caches_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DONKI_CACHE_PATH", tmp_path / "donki_cache.json")
    monkeypatch.setattr(config, "OSDR_CACHE_PATH", tmp_path / "osdr_cache.json")


# ======================================================================= loader lifecycle (no window)
def gated_network(monkeypatch):
    gate, calls = threading.Event(), []
    studies = osdr_data.get_studies(allow_network=False)

    def donki(**kw):
        if kw.get("allow_network", True):
            calls.append(("donki", threading.current_thread()))
            gate.wait(5)
            return solar(0.77)
        return nasa_data.SolarActivity(0.3, nasa_data.DEFAULT)

    def osdr(**kw):
        if kw.get("allow_network", True):
            calls.append(("osdr", threading.current_thread()))
            gate.wait(5)
        return studies
    monkeypatch.setattr(nasa_data, "get_solar_activity", donki)
    monkeypatch.setattr(osdr_data, "get_studies", osdr)
    return gate, calls


def test_results_wait_in_the_queue_until_the_main_thread_pumps_them(monkeypatch):
    gate, calls = gated_network(monkeypatch)
    n = NasaData(BackgroundLoader())
    before = n.solar
    n.refresh()
    gate.set()
    assert wait_for(lambda: not n.loader.is_loading())
    assert n.solar is before and n.state["donki"] == "loading"              # a worker never writes to the shared data
    assert n.pump() is True and n.solar.level == 0.77 and n.state == {"donki": "ok", "osdr": "ok"}
    main = threading.current_thread()
    assert calls and all(t is not main for _, t in calls)                   # the work ran on worker threads


def test_leaving_while_jobs_run_then_reentering_starts_no_duplicates(monkeypatch):
    gate, calls = gated_network(monkeypatch)
    n = NasaData(BackgroundLoader())
    assert n.refresh() is True                                               # first visit
    assert n.refresh() is False                                              # leave + re-enter: same jobs still running
    gate.set()
    assert wait_for(lambda: not n.loader.is_loading())
    n.pump()
    assert sorted(name for name, _ in calls) == ["donki", "osdr"]            # one lookup each, never two


def test_a_result_that_arrives_after_a_newer_job_started_keeps_the_status_loading(monkeypatch):
    """Old result applied (it is valid data) but the status stays 'loading' while the newer same-name job runs."""
    gate, _ = gated_network(monkeypatch)
    loader = BackgroundLoader()
    n = NasaData(loader)
    loader._done.put(("donki", True, solar(0.9)))                           # a result left over from an earlier visit
    loader._running.add("donki")                                            # and a newer donki job is running now
    n.state["donki"] = "loading"
    n.pump()
    assert n.solar.level == 0.9 and n.state["donki"] == "loading" and n.loading
    loader._running.discard("donki")
    loader._done.put(("donki", True, solar(0.95)))
    n.pump()
    assert n.state["donki"] == "ok" and n.solar.level == 0.95
    gate.set()


def test_a_failed_leftover_job_never_overwrites_good_data_and_reports_the_error(monkeypatch):
    n = NasaData(BackgroundLoader(inline=True))
    good = n.solar
    n.loader._done.put(("donki", False, "Timeout"))
    n.pump()
    assert n.solar is good and n.state["donki"] == "error" and n.error["donki"] == "Timeout"


def test_nothing_is_applied_to_the_data_until_pump_is_called(monkeypatch):
    n = NasaData(BackgroundLoader(inline=True))
    snapshot = (n.solar, n.studies, dict(n.state))
    n.loader._done.put(("donki", True, solar(0.99)))
    assert (n.solar, n.studies, n.state) == snapshot                         # queued results do not touch live state
    n.pump()
    assert n.solar.level == 0.99


def test_closing_the_game_while_a_worker_is_active_does_not_hang_the_exit(tmp_path):
    """Workers are daemon threads: the process must end promptly even though a job is blocked mid-'request'."""
    script = tmp_path / "exit_with_worker.py"
    script.write_text(textwrap.dedent(f"""
        import sys, threading, time
        sys.path.insert(0, {str(ROOT)!r})
        from astro.outpost_flow import BackgroundLoader
        started = threading.Event()
        def stuck():
            started.set()
            time.sleep(60)                      # a lookup that never answers
        loader = BackgroundLoader()
        assert loader.start("donki", stuck) and started.wait(5) and loader.is_loading("donki")
        print("exiting")                        # interpreter exit while the worker is still blocked
    """), encoding="utf-8")
    t0 = time.time()
    out = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0 and "exiting" in out.stdout and out.stderr == ""
    assert time.time() - t0 < 20


# ======================================================================= atomic writes
def test_atomic_write_creates_and_replaces_files_without_leaving_temp_files(tmp_path):
    p = tmp_path / "sub" / "a.json"
    fileio.atomic_write_text(p, "one")
    fileio.atomic_write_text(p, "two")
    assert p.read_text(encoding="utf-8") == "two" and [f.name for f in p.parent.iterdir()] == ["a.json"]


def test_a_failed_replace_keeps_the_previous_file_and_removes_the_temp_file(tmp_path, monkeypatch):
    p = tmp_path / "cache.json"
    p.write_text("OLD", encoding="utf-8")

    def broken(src, dst):
        raise OSError("disk problem")
    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(OSError):
        fileio.atomic_write_text(p, "NEW")
    assert p.read_text(encoding="utf-8") == "OLD" and [f.name for f in tmp_path.iterdir()] == ["cache.json"]


def test_a_failed_write_keeps_the_previous_file(tmp_path, monkeypatch):
    p = tmp_path / "cache.json"
    p.write_text("OLD", encoding="utf-8")
    monkeypatch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("full")))
    with pytest.raises(OSError):
        fileio.atomic_write_text(p, "NEW")
    assert p.read_text(encoding="utf-8") == "OLD" and [f.name for f in tmp_path.iterdir()] == ["cache.json"]


def test_a_process_killed_before_the_replace_leaves_the_old_cache_valid(tmp_path):
    """A hard kill (os._exit: no cleanup runs) between writing the temp file and replacing the target."""
    p = tmp_path / "donki_cache.json"
    when = nasa_data.dt.datetime(2026, 11, 8, 12, 0, 0)
    nasa_data._write(p, ("2026-10-09", "2026-11-08"), {"cme": 2, "flare_m": 1}, when)
    old = p.read_text(encoding="utf-8")
    script = tmp_path / "killed_mid_write.py"
    script.write_text(textwrap.dedent(f"""
        import os, sys, datetime as dt
        sys.path.insert(0, {str(ROOT)!r})
        from astro import nasa_data
        os.replace = lambda *a: os._exit(9)           # the process dies right before the swap
        nasa_data._write({str(p)!r}, ("2026-10-10", "2026-11-09"), {{"cme": 99}}, dt.datetime(2026, 11, 9, 12, 0, 0))
    """), encoding="utf-8")
    assert subprocess.run([sys.executable, "-I", str(script)], timeout=30).returncode == 9
    assert p.read_text(encoding="utf-8") == old                                    # untouched
    assert nasa_data._read(p)["counts"]["cme"] == 2                                # and still valid
    assert [f for f in tmp_path.glob(".donki_cache.json.*.tmp")]                   # the killed process's leftover...
    assert nasa_data._read(p)["counts"]["cme"] == 2                                # the reader only ever looks at the real file


def test_stale_temp_files_are_cleaned_up_by_the_next_good_write(tmp_path):
    p = tmp_path / "osdr_cache.json"
    stale = tmp_path / ".osdr_cache.json.4242.tmp"
    stale.write_text("{half", encoding="utf-8")
    old = time.time() - 3600
    os.utime(stale, (old, old))
    fresh = tmp_path / ".osdr_cache.json.4343.tmp"                                 # maybe another live writer: kept
    fresh.write_text("{", encoding="utf-8")
    fileio.atomic_write_text(p, "{}")
    assert not stale.exists() and fresh.exists() and p.exists()


def test_both_nasa_caches_are_written_through_the_atomic_helper(tmp_path, monkeypatch):
    seen = []
    real = fileio.atomic_write_text
    monkeypatch.setattr(nasa_data, "atomic_write_text", lambda p, t, **k: (seen.append(Path(p).name), real(p, t, **k))[1])
    monkeypatch.setattr(osdr_data, "atomic_write_text", lambda p, t, **k: (seen.append(Path(p).name), real(p, t, **k))[1])
    nasa_data._write(tmp_path / "d.json", ("2026-10-10", "2026-11-09"), {"cme": 1}, nasa_data.dt.datetime(2026, 11, 9))
    osdr_data._write_cache(tmp_path / "o.json", [], nasa_data.dt.datetime(2026, 11, 9))
    assert seen == ["d.json", "o.json"]


@pytest.mark.parametrize("junk", ["", "{", "[]", '{"counts": 1}', '{"fetched_at": "not a date", "counts": {}}', "\x00\x01"])
def test_a_corrupt_donki_cache_is_ignored_and_a_good_write_repairs_it(tmp_path, junk):
    p = tmp_path / "c.json"
    p.write_text(junk, encoding="utf-8")
    assert nasa_data._read(p) is None
    nasa_data._write(p, ("2026-10-10", "2026-11-09"), {"cme": 3}, nasa_data.dt.datetime(2026, 11, 9))
    assert nasa_data._read(p)["counts"]["cme"] == 3


@pytest.mark.parametrize("junk", ["", "{", "[]", '{"fetched_at": "x", "studies": []}', "\x00"])
def test_a_corrupt_osdr_cache_is_ignored_and_a_good_write_repairs_it(tmp_path, junk):
    p = tmp_path / "c.json"
    p.write_text(junk, encoding="utf-8")
    assert osdr_data._read_cache(p) == ([], None)
    osdr_data._write_cache(p, [], osdr_data.dt.datetime(2026, 11, 9))
    assert json.loads(p.read_text(encoding="utf-8"))["studies"] == []


# ======================================================================= database status enforcement
def raw(path):
    c = sqlite3.connect(path)
    c.execute("PRAGMA foreign_keys=ON")
    return c


INSERT = ("INSERT INTO outpost_runs (profile_id, site, difficulty, seed, status, sol, score, stars, solar_level, "
          "solar_source, state_json, history_json) VALUES (NULL, 'moon', 'normal', 1, ?, 0, 0, 0, 0.5, 'default', '{}', '[]')")


@pytest.mark.parametrize("status", list(dbmod.OUTPOST_STATUSES))
def test_database_accepts_every_valid_status(tmp_path, status):
    d = Database(tmp_path / "t.db")
    with raw(d.path) as c:
        c.execute(INSERT, (status,))
        assert c.execute("SELECT status FROM outpost_runs").fetchone()[0] == status


@pytest.mark.parametrize("bad", ["cheating", "", "RUNNING", "won ", "running'; --"])
def test_database_itself_rejects_an_invalid_status_on_insert(tmp_path, bad):
    d = Database(tmp_path / "t.db")
    with raw(d.path) as c, pytest.raises(sqlite3.IntegrityError, match="invalid outpost run status"):
        c.execute(INSERT, (bad,))
    with raw(d.path) as c:
        assert c.execute("SELECT COUNT(*) FROM outpost_runs").fetchone()[0] == 0


def test_database_itself_rejects_an_invalid_status_on_update_and_keeps_the_row(tmp_path):
    d = Database(tmp_path / "t.db")
    rid = d.create_outpost_run(None, "moon", "normal", 5, 0.3, "default", None, "{}")
    with raw(d.path) as c, pytest.raises(sqlite3.IntegrityError, match="invalid outpost run status"):
        c.execute("UPDATE outpost_runs SET status='hacked' WHERE id=?", (rid,))
    assert d.get_outpost_run(rid)["status"] == "running"
    with raw(d.path) as c:
        c.execute("UPDATE outpost_runs SET status='won' WHERE id=?", (rid,))
    assert d.get_outpost_run(rid)["status"] == "won"


def test_updates_to_other_columns_are_not_blocked_by_the_status_trigger(tmp_path):
    d = Database(tmp_path / "t.db")
    rid = d.create_outpost_run(None, "moon", "normal", 5, 0.3, "default", None, "{}")
    with raw(d.path) as c:
        c.execute("UPDATE outpost_runs SET score=42 WHERE id=?", (rid,))
    assert d.get_outpost_run(rid)["score"] == 42


def test_the_application_layer_still_validates_the_status_first(tmp_path):
    d = Database(tmp_path / "t.db")
    rid = d.create_outpost_run(None, "moon", "normal", 5, 0.3, "default", None, "{}")
    with pytest.raises(ValueError):
        d.update_outpost_run(rid, status="cheating", sol=1, score=0, stars=0, fail_reason=None, state_json="{}",
                             history_json="[]")
    assert d.get_outpost_run(rid)["status"] == "running"


def test_triggers_are_added_to_an_existing_database_without_touching_its_rows(tmp_path):
    """An Outpost table made BEFORE the triggers existed (containing even an invalid status) keeps every row."""
    schema = dbmod.SCHEMA
    table_only = schema.split("CREATE TRIGGER")[0]
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as c:
        c.executescript(table_only)
        c.execute(INSERT, ("running",))
        c.execute(INSERT, ("won",))
        c.execute(INSERT, ("legacy-junk",))                                       # nothing stopped this before
        assert not c.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
        before = c.execute("SELECT id, status, score FROM outpost_runs ORDER BY id").fetchall()
    d = Database(path)                                                            # opening with the new code adds triggers
    Database(path)                                                                # and doing it again is harmless
    with sqlite3.connect(path) as c:
        triggers = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        after = c.execute("SELECT id, status, score FROM outpost_runs ORDER BY id").fetchall()
    assert triggers == {"outpost_runs_status_insert", "outpost_runs_status_update"}
    assert after == before                                                        # rows untouched, even the invalid one
    with raw(path) as c, pytest.raises(sqlite3.IntegrityError):
        c.execute(INSERT, ("nope",))
    assert d.get_outpost_run(3)["status"] == "legacy-junk"                        # still readable, never rewritten


def test_a_pre_existing_invalid_row_is_never_resumed_or_counted_as_a_win(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as c:
        c.executescript(dbmod.SCHEMA.split("CREATE TRIGGER")[0])
        c.execute(INSERT, ("legacy-junk",))
    d = Database(path)
    assert d.latest_unfinished_outpost_run(None) is None
    assert d.best_outpost_score(None) == 0
    assert d.abandon_unfinished_outpost_runs(None) in (0, None)
    assert d.get_outpost_run(1)["status"] == "legacy-junk"                        # unrelated records are not rewritten


def test_the_other_tables_have_no_triggers_from_this_change(tmp_path):
    d = Database(tmp_path / "t.db")
    with sqlite3.connect(d.path) as c:
        rows = c.execute("SELECT tbl_name FROM sqlite_master WHERE type='trigger'").fetchall()
    assert {r[0] for r in rows} == {"outpost_runs"}
