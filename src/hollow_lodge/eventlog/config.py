from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from hollow_lodge.eventlog.jsonl_store import JsonlEventStore
from hollow_lodge.eventlog.postgres_store import PostgresEventStore


EVENT_DATABASE_URL_ENV = "HOLLOW_LODGE_EVENT_DATABASE_URL"


def event_store_from_env(root: Path) -> JsonlEventStore | PostgresEventStore:
    database_url = os.environ.get(EVENT_DATABASE_URL_ENV, "").strip()
    if not database_url:
        return JsonlEventStore(root / "server-events.jsonl")

    parsed = urlparse(database_url)
    scheme = parsed.scheme.lower()
    if scheme in {"postgres", "postgresql"}:
        return PostgresEventStore(database_url, database_url_env=EVENT_DATABASE_URL_ENV)

    raise RuntimeError(
        "Unsupported event database URL scheme "
        f"{scheme!r}; expected postgresql://. "
        f"Configured URL: {PostgresEventStore(database_url).safe_database_url}"
    )
