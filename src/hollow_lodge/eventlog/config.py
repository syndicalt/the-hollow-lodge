from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from hollow_lodge.eventlog.jsonl_store import JsonlEventStore
from hollow_lodge.eventlog.postgres_store import PostgresEventStore


EVENT_DATABASE_URL_ENV = "HOLLOW_LODGE_EVENT_DATABASE_URL"
REQUIRE_POSTGRES_EVENT_LOG_ENV = "HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG"


def event_store_from_env(root: Path) -> JsonlEventStore | PostgresEventStore:
    database_url = os.environ.get(EVENT_DATABASE_URL_ENV, "").strip()
    require_postgres = _env_flag(REQUIRE_POSTGRES_EVENT_LOG_ENV)
    if not database_url:
        if require_postgres:
            raise RuntimeError(
                f"{REQUIRE_POSTGRES_EVENT_LOG_ENV}=1 requires "
                f"{EVENT_DATABASE_URL_ENV}=postgresql://..."
            )
        return JsonlEventStore(root / "server-events.jsonl")

    parsed = urlparse(database_url)
    scheme = parsed.scheme.lower()
    if scheme in {"postgres", "postgresql"}:
        return PostgresEventStore(database_url, database_url_env=EVENT_DATABASE_URL_ENV)

    if require_postgres:
        raise RuntimeError(
            f"{REQUIRE_POSTGRES_EVENT_LOG_ENV}=1 rejects non-Postgres event log "
            f"URLs; configured URL: {PostgresEventStore(database_url).safe_database_url}"
        )

    raise RuntimeError(
        "Unsupported event database URL scheme "
        f"{scheme!r}; expected postgresql://. "
        f"Configured URL: {PostgresEventStore(database_url).safe_database_url}"
    )


def _env_flag(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if value in {"", "0", "false", "no", "off"}:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    raise RuntimeError(
        f"{name} must be one of 1, true, yes, on, 0, false, no, or off; "
        f"got {value!r}"
    )
