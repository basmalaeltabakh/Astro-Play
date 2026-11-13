"""Suite-wide guard: ordinary pytest runs are OFFLINE.

Every test runs with real HTTP blocked at three levels (``requests.get`` and friends, ``requests.Session.request`` and the
transport adapter). An attempt

  1. raises ``NetworkBlockedError`` immediately, before any socket is opened, and
  2. is recorded, and the test FAILS at teardown even if the code under test caught the exception.

(2) matters because production code catches errors on purpose (a missing network must not crash the game): a guard
that only raised would let such a test pass silently, which is exactly how one leak went unnoticed before.

Opt-in for a test that genuinely needs the live internet: mark it ``@pytest.mark.live_network`` AND run pytest with
``ASTRO_LIVE_TESTS=1``. Marked tests are skipped otherwise, and unmarked tests can never reach the network.
"""
import os
from typing import List, Tuple

import pytest
import requests

ATTEMPTS: List[Tuple[str, str, str]] = []                      # (test id, method, url without query string)
_CURRENT = {"id": "?"}
LIVE_ENV = "ASTRO_LIVE_TESTS"


class NetworkBlockedError(Exception):
    """A test tried to make a real HTTP request. Deliberately NOT a ``requests.RequestException``, so error handlers that
    turn network failures into fallbacks do not convert it into a quiet 'offline' result."""


def live_network_allowed(has_marker: bool, environ=None) -> bool:
    """True only for a test marked live_network when the opt-in environment variable is set to 1."""
    env = os.environ if environ is None else environ
    return bool(has_marker) and env.get(LIVE_ENV) == "1"


def _blocked(method: str, url: str) -> None:
    ATTEMPTS.append((_CURRENT["id"], str(method).upper(), str(url).split("?")[0]))
    raise NetworkBlockedError(f"real HTTP is blocked in tests: {str(method).upper()} {str(url).split('?')[0]}")


@pytest.fixture(autouse=True)
def no_real_http(request, monkeypatch):
    marked = request.node.get_closest_marker("live_network") is not None
    if marked and not live_network_allowed(True):
        pytest.skip(f"live-network test: set {LIVE_ENV}=1 to run it")
    if marked:                                                  # explicitly opted in: the real network is allowed
        yield
        return
    _CURRENT["id"] = request.node.nodeid
    start = len(ATTEMPTS)

    def session_request(self, method, url, *a, **k):
        _blocked(method, url)

    def adapter_send(self, request, *a, **k):
        _blocked(request.method, request.url)

    monkeypatch.setattr(requests.Session, "request", session_request)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", adapter_send)
    for name in ("get", "post", "put", "patch", "delete", "head", "options"):
        monkeypatch.setattr(requests, name, lambda url, *a, _n=name, **k: _blocked(_n, url))
    monkeypatch.setattr(requests, "request", lambda method, url, *a, **k: _blocked(method, url))
    yield
    new = ATTEMPTS[start:]
    if new:
        del ATTEMPTS[start:]
        pytest.fail("a test tried to use the real network (even if the code under test swallowed the error): "
                    + "; ".join(f"{m} {u}" for _, m, u in new), pytrace=False)
