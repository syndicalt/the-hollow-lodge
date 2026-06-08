from __future__ import annotations

import os

from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_boundary import ResolutionOracle
from hollow_lodge.workflows.openai_oracle import OpenAIResolutionOracle


def _openai_client(api_key: str):
    from openai import OpenAI

    return OpenAI(api_key=api_key)


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
    timeout_seconds = _timeout_seconds_from_env()
    provider = os.environ.get("HOLLOW_LODGE_ORACLE_PROVIDER", "deterministic").strip().lower()
    if provider in {"", "deterministic"}:
        return DeterministicResolutionOracle()
    if provider == "openai":
        api_key = os.environ.get("HOLLOW_LODGE_OPENAI_API_KEY")
        if not api_key:
            return DeterministicResolutionOracle()

        return OpenAIResolutionOracle(
            client=_openai_client(api_key),
            model=os.environ.get("HOLLOW_LODGE_ORACLE_MODEL", "gpt-4.1-mini"),
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"unsupported oracle provider: {provider}")
