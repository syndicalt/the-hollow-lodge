from __future__ import annotations

import pytest

from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_factory import resolution_oracle_from_env


def test_factory_defaults_to_deterministic_oracle_when_provider_unset(monkeypatch):
    monkeypatch.delenv("HOLLOW_LODGE_ORACLE_PROVIDER", raising=False)
    monkeypatch.delenv("HOLLOW_LODGE_ORACLE_TIMEOUT_SECONDS", raising=False)

    oracle = resolution_oracle_from_env()

    assert isinstance(oracle, DeterministicResolutionOracle)


def test_factory_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ORACLE_PROVIDER", "unknown")
    monkeypatch.delenv("HOLLOW_LODGE_ORACLE_TIMEOUT_SECONDS", raising=False)

    with pytest.raises(ValueError, match="unsupported oracle provider"):
        resolution_oracle_from_env()


def test_openai_provider_without_api_key_returns_deterministic_oracle(monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ORACLE_PROVIDER", "openai")
    monkeypatch.delenv("HOLLOW_LODGE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HOLLOW_LODGE_ORACLE_TIMEOUT_SECONDS", raising=False)

    oracle = resolution_oracle_from_env()

    assert isinstance(oracle, DeterministicResolutionOracle)


def test_factory_rejects_zero_timeout(monkeypatch):
    monkeypatch.delenv("HOLLOW_LODGE_ORACLE_PROVIDER", raising=False)
    monkeypatch.setenv("HOLLOW_LODGE_ORACLE_TIMEOUT_SECONDS", "0")

    with pytest.raises(ValueError, match="timeout"):
        resolution_oracle_from_env()


def test_factory_rejects_nonnumeric_timeout(monkeypatch):
    monkeypatch.delenv("HOLLOW_LODGE_ORACLE_PROVIDER", raising=False)
    monkeypatch.setenv("HOLLOW_LODGE_ORACLE_TIMEOUT_SECONDS", "soon")

    with pytest.raises(ValueError, match="timeout"):
        resolution_oracle_from_env()
