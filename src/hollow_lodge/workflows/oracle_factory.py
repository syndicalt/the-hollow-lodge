from __future__ import annotations

import os

from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_boundary import ResolutionOracle


def _timeout_seconds_from_env() -> float:
    raw = os.environ.get("HOLLOW_LODGE_ORACLE_TIMEOUT_SECONDS", "20")
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise ValueError("oracle timeout must be a number") from exc
    if timeout <= 0:
        raise ValueError("oracle timeout must be greater than zero")
    return timeout


def resolution_oracle_from_env() -> ResolutionOracle:
    _timeout_seconds_from_env()
    provider = os.environ.get("HOLLOW_LODGE_ORACLE_PROVIDER", "deterministic").strip().lower()
    if provider in {"", "deterministic", "openai"}:
        return DeterministicResolutionOracle()
    raise ValueError(f"unsupported oracle provider: {provider}")
