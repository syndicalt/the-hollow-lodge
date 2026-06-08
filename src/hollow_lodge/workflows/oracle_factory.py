from __future__ import annotations

import os

from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_boundary import ResolutionOracle


def resolution_oracle_from_env() -> ResolutionOracle:
    provider = os.environ.get("HOLLOW_LODGE_ORACLE_PROVIDER", "deterministic").strip().lower()
    if provider in {"", "deterministic", "openai"}:
        return DeterministicResolutionOracle()
    raise ValueError(f"unsupported resolution oracle provider: {provider}")
