"""
Shared pytest fixtures for the Ledgr eval harness.

Two tiers of tests live in this folder:
  - Pure math tests (test_tools_math.py) — no Ollama needed, test the real
    arithmetic tools directly. These should always run, in CI or offline.
  - Integration/scenario tests (test_routing.py, test_scenarios.py) — need
    a live Ollama + Gemma to actually call the model. These auto-skip if
    Ollama isn't reachable, rather than failing noisily, so `pytest` still
    gives a clean pure-math signal even before Ollama is set up.
"""

import os
import socket
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "db"))

import pytest


def _ollama_available() -> bool:
    try:
        with socket.create_connection(("localhost", 11434), timeout=1):
            return True
    except OSError:
        return False


OLLAMA_AVAILABLE = _ollama_available()


@pytest.fixture(scope="session", autouse=True)
def seeded_db():
    """
    Seeds the demo DB with known values before any test runs, so tests can
    assert against specific numbers (e.g. cement: 200 on hand, 120 already
    committed -> 80 available) instead of guessing at whatever state
    happens to already be in saathi.db.
    """
    import seed_data

    seed_data.seed()
    yield
