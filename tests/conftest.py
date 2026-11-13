"""Shared pytest setup. Every test runs OFFLINE: the autouse guard in tests/netguard.py blocks real HTTP."""
from tests.netguard import no_real_http  # noqa: F401  (autouse fixture, registered by importing it here)
