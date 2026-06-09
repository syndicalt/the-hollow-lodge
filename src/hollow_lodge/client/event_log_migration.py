from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from hollow_lodge.domain.events import GameEvent
from hollow_lodge.eventlog.jsonl_store import EventLogIntegrityError, validate_event_chain
from hollow_lodge.eventlog.postgres_store import PostgresEventStore


EVENT_DATABASE_URL_ENV = "HOLLOW_LODGE_EVENT_DATABASE_URL"


def migrate_event_log_to_postgres(
    *,
    source: Path,
    database_url: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    events = load_events(source)
    validate_event_chain(events)
    if dry_run:
        return {
            "dry_run": True,
            "event_count": len(events),
        }
    if not database_url.strip():
        raise RuntimeError(f"{EVENT_DATABASE_URL_ENV} or --database-url is required")
    store = PostgresEventStore(database_url.strip(), database_url_env=EVENT_DATABASE_URL_ENV)
    report = store.import_events(events)
    return {
        "dry_run": False,
        "event_count": report.event_count,
        "database_url": store.safe_database_url,
    }


def load_events(source: Path) -> list[GameEvent]:
    if not source.exists():
        raise RuntimeError(f"event source does not exist: {source}")
    text = source.read_text(encoding="utf-8")
    raw_events = _load_raw_events(text)
    events: list[GameEvent] = []
    for index, raw in enumerate(raw_events, start=1):
        try:
            events.append(GameEvent.model_validate(raw))
        except ValidationError as exc:
            raise EventLogIntegrityError(f"invalid event row {index}") from exc
    return events


def _load_raw_events(text: str) -> list[Any]:
    stripped = text.strip()
    if not stripped:
        return []
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        rows: list[Any] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"invalid JSONL row {line_number}") from exc
        return rows
    if isinstance(parsed, dict) and isinstance(parsed.get("events"), list):
        return parsed["events"]
    if isinstance(parsed, dict) and {"event_id", "sequence", "event_hash"} <= set(parsed):
        return [parsed]
    if isinstance(parsed, list):
        return parsed
    raise RuntimeError("event source must be an admin export, JSON array, or JSONL rows")
