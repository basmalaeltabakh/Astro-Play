"""The suite-wide HTTP guard (tests/netguard.py) must itself be trustworthy: an attempted real request fails at once,
cannot be hidden by code that swallows errors, covers DONKI and OSDR, and the opt-in for live tests is explicit."""
import datetime as dt
import os
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
import requests

from astro import nasa_data, osdr_data
from tests import netguard
from tests.netguard import ATTEMPTS, NetworkBlockedError, live_network_allowed

ROOT = Path(__file__).resolve().parent.parent
URL = "https://example.invalid/anything?secret=1"
TODAY = dt.date(2026, 11, 9)


def consume(expected: int, fragment: str = ""):
    """The test provoked ``expected`` blocked requests on purpose: check them, then remove them so the teardown stays green."""
    assert len(ATTEMPTS) >= expected, ATTEMPTS
    taken = ATTEMPTS[-expected:] if expected else []
    del ATTEMPTS[len(ATTEMPTS) - expected:]
    if fragment:
        assert all(fragment in u for _, _, u in taken), taken
    return taken


@pytest.fixture
def no_sockets(monkeypatch):
    """Fail loudly if anything gets as far as opening a connection."""
    calls = []
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: calls.append(("create_connection", a)))
    monkeypatch.setattr(socket.socket, "connect", lambda self, *a, **k: calls.append(("connect", a)))
    yield calls
    assert calls == [], f"a socket was opened: {calls}"


# ======================================================================= an attempt fails immediately
@pytest.mark.parametrize("call", [
    lambda: requests.get(URL), lambda: requests.post(URL, data={"a": 1}), lambda: requests.put(URL),
    lambda: requests.patch(URL), lambda: requests.delete(URL), lambda: requests.head(URL),
    lambda: requests.options(URL), lambda: requests.request("GET", URL),
    lambda: requests.Session().get(URL), lambda: requests.Session().post(URL),
    lambda: requests.Session().request("GET", URL),
    lambda: requests.Session().send(requests.Request("GET", URL).prepare()),
    lambda: requests.adapters.HTTPAdapter().send(requests.Request("GET", URL).prepare()),
], ids=["get", "post", "put", "patch", "delete", "head", "options", "request", "Session.get", "Session.post",
        "Session.request", "Session.send", "HTTPAdapter.send"])
def test_every_way_of_calling_requests_fails_at_once_without_opening_a_socket(call, no_sockets):
    t0 = time.monotonic()
    with pytest.raises(NetworkBlockedError, match="real HTTP is blocked"):
        call()
    assert time.monotonic() - t0 < 0.5                                    # immediately: no DNS lookup, no timeout
    (_, method, url), = consume(1)
    assert url == "https://example.invalid/anything" and "secret" not in url      # the query string is never recorded


def test_the_blocked_error_is_not_a_requests_error_so_handlers_cannot_turn_it_into_a_quiet_offline_result():
    assert not issubclass(NetworkBlockedError, requests.RequestException)


# ======================================================================= DONKI and OSDR are covered
def test_donki_code_paths_cannot_reach_the_network(no_sockets, tmp_path):
    with pytest.raises(NetworkBlockedError):
        nasa_data.fetch_events("FLR", TODAY, TODAY)                                  # session=None -> real requests
    consume(1, "DONKI-API/get/FLR")
    result = nasa_data.get_solar_activity(TODAY, None, tmp_path / "c.json", tmp_path / "a.json",
                                          now=dt.datetime(2026, 11, 9, 12))             # swallows the error: falls back
    assert result.source == nasa_data.DEFAULT                                      # ...so only the guard can notice
    consume(1, "DONKI-API/get/FLR")


def test_osdr_code_paths_cannot_reach_the_network(no_sockets, tmp_path):
    with pytest.raises(NetworkBlockedError):
        osdr_data.list_accessions()
    with pytest.raises(NetworkBlockedError):
        osdr_data.fetch_study("OSD-48", today=TODAY)
    with pytest.raises(NetworkBlockedError):
        osdr_data.search(organism="mus musculus")
    consume(3, "biodata/api")
    shipped = Path(osdr_data.config.OSDR_STUDIES_PATH)
    studies = osdr_data.get_studies(None, TODAY, tmp_path / "cache.json", shipped, now=dt.datetime(2026, 11, 9, 12))
    assert studies.source == osdr_data.OFFLINE and len(studies.entries) >= 8       # falls back to the curated data
    consume(1, "/v2/dataset/")                                                     # ...and the attempt was recorded


# ======================================================================= swallowed errors still fail the test
def _run_inner(tmp_path: Path, test_source: str, env_extra=None):
    """Run a throw-away test file in a separate pytest with only the suite guard loaded."""
    (tmp_path / "test_inner.py").write_text(textwrap.dedent(test_source), encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    live_network: opt-in live test\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    env.pop(netguard.LIVE_ENV, None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-m", "pytest", "test_inner.py", "-p", "tests.netguard", "-q", "-p",
                           "no:cacheprovider"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)


def test_code_that_catches_every_exception_cannot_hide_a_real_request(tmp_path):
    """The original leak: production code falls back gracefully, so a raise alone would have passed silently."""
    r = _run_inner(tmp_path, """
        import requests
        def test_swallows_everything():
            try:
                requests.get("https://example.invalid/x")
            except Exception:
                pass
            assert True                    # the test body is happy, only the guard can object
    """)
    assert r.returncode != 0, r.stdout
    assert "tried to use the real network" in r.stdout and "GET https://example.invalid/x" in r.stdout


def test_a_test_that_never_touches_the_network_is_unaffected(tmp_path):
    r = _run_inner(tmp_path, """
        def test_pure():
            assert 1 + 1 == 2
    """)
    assert r.returncode == 0 and "1 passed" in r.stdout


# ======================================================================= the explicit opt-in
def test_live_network_opt_in_rules():
    assert live_network_allowed(True, {"ASTRO_LIVE_TESTS": "1"}) is True
    assert live_network_allowed(True, {}) is False
    assert live_network_allowed(True, {"ASTRO_LIVE_TESTS": "0"}) is False
    assert live_network_allowed(True, {"ASTRO_LIVE_TESTS": "yes"}) is False
    assert live_network_allowed(False, {"ASTRO_LIVE_TESTS": "1"}) is False       # unmarked tests are never opened up


LIVE_TEST = """
    import pytest, requests
    @pytest.mark.live_network
    def test_needs_the_internet():
        assert requests.get.__module__ == "requests.api"         # the real function: the guard stepped aside
"""


def test_a_live_network_test_is_skipped_unless_explicitly_enabled(tmp_path):
    r = _run_inner(tmp_path, LIVE_TEST)
    assert r.returncode == 0 and "1 skipped" in r.stdout and "1 passed" not in r.stdout


def test_a_marked_test_runs_for_real_when_the_environment_variable_is_set(tmp_path):
    r = _run_inner(tmp_path, LIVE_TEST, {"ASTRO_LIVE_TESTS": "1"})
    assert r.returncode == 0 and "1 passed" in r.stdout and "skipped" not in r.stdout


def test_the_environment_variable_alone_never_opens_the_network_for_an_unmarked_test(tmp_path):
    r = _run_inner(tmp_path, """
        import requests
        def test_unmarked():
            try:
                requests.get("https://example.invalid/x")
            except Exception:
                pass
    """, {"ASTRO_LIVE_TESTS": "1"})
    assert r.returncode != 0 and "tried to use the real network" in r.stdout
