from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from hollow_lodge.domain.events import GameEvent
from hollow_lodge.eventlog.jsonl_store import EventLogIntegrityError, validate_event_chain
from hollow_lodge.eventlog.postgres_store import PostgresEventStore


EVENT_DATABASE_URL_ENV = "HOLLOW_LODGE_EVENT_DATABASE_URL"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import an exported Hollow Lodge event log into empty Postgres storage."
    )
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Event export file. Accepts admin export JSON, JSON array, or JSONL rows.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get(EVENT_DATABASE_URL_ENV, ""),
        help=f"Destination Postgres URL. Defaults to ${EVENT_DATABASE_URL_ENV}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the source chain without writing to Postgres.",
    )
    args = parser.parse_args()

    result = migrate_event_log(
        source=args.source,
        database_url=args.database_url,
        dry_run=args.dry_run,
    )
    if result["dry_run"]:
        print(f"event log import dry-run ok: {result['event_count']} events")
    else:
        print(
            "event log import ok: "
            f"{result['event_count']} events into {result['database_url']}"
        )


def migrate_event_log(
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
        return [
            json.loads(line)
            for line in text.splitlines()
            if line.strip()
        ]
    if isinstance(parsed, dict) and isinstance(parsed.get("events"), list):
        return parsed["events"]
    if isinstance(parsed, dict) and {"event_id", "sequence", "event_hash"} <= set(parsed):
        return [parsed]
    if isinstance(parsed, list):
        return parsed
    raise RuntimeError("event source must be an admin export, JSON array, or JSONL rows")


if __name__ == "__main__":
    main()
