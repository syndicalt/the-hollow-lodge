from __future__ import annotations


PRODUCTION_POSTGRES_ENV = "HOLLOW_LODGE_PRODUCTION_POSTGRES"


def production_postgres_enabled() -> bool:
    return env_flag(PRODUCTION_POSTGRES_ENV)


def env_flag(name: str) -> bool:
    import os

    value = os.environ.get(name, "").strip().lower()
    if value in {"", "0", "false", "no", "off"}:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    raise RuntimeError(
        f"{name} must be one of 1, true, yes, on, 0, false, no, or off; "
        f"got {value!r}"
    )
