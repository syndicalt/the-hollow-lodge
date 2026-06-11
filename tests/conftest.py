from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def deterministic_oracle_env(monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ORACLE_PROVIDER", "deterministic")
    monkeypatch.delenv("HOLLOW_LODGE_OPENAI_API_KEY", raising=False)
    # Tests simulate phase time by asserting hours_elapsed on lock requests.
    # Production ignores the client clock (see trust_client_phase_clock).
    monkeypatch.setenv("HOLLOW_LODGE_TRUST_CLIENT_PHASE_CLOCK", "1")
    # Tests drive the world explicitly; the autopilot loop stays off.
    monkeypatch.setenv("HOLLOW_LODGE_AUTOPILOT_INTERVAL_SECONDS", "0")
