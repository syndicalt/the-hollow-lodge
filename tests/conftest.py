from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def deterministic_oracle_env(monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ORACLE_PROVIDER", "deterministic")
    monkeypatch.delenv("HOLLOW_LODGE_OPENAI_API_KEY", raising=False)
