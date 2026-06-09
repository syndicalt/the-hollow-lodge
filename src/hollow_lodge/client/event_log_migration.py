from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from hollow_lodge.domain.events import GameEvent
from hollow_lodge.eventlog.jsonl_store import (
    EventLogIntegrityError,
    JsonlEventStore,
    event_hash_chain_digest,
    validate_event_chain,
)
from hollow_lodge.eventlog.postgres_store import PostgresEventStore


EVENT_DATABASE_URL_ENV = "HOLLOW_LODGE_EVENT_DATABASE_URL"
MANIFEST_TYPE = "hollow_lodge_event_log_backup"
MANIFEST_VERSION = 1
MANIFEST_FIELDS = (
    "manifest_type",
    "manifest_version",
    "event_count",
    "first_sequence",
    "last_sequence",
    "first_event_id",
    "last_event_id",
    "first_event_hash",
    "last_event_hash",
    "schema_versions",
    "event_hash_chain_sha256",
)


def migrate_event_log_to_postgres(
    *,
    source: Path,
    database_url: str,
    manifest: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    events = load_events(source)
    validate_event_chain(events)
    if manifest is not None:
        verify_event_log_manifest(events, manifest)
    if dry_run:
        return {
            "dry_run": True,
            "event_count": len(events),
            "manifest_verified": manifest is not None,
        }
    if not database_url.strip():
        raise RuntimeError(f"{EVENT_DATABASE_URL_ENV} or --database-url is required")
    store = PostgresEventStore(database_url.strip(), database_url_env=EVENT_DATABASE_URL_ENV)
    report = store.import_events(events)
    return {
        "dry_run": False,
        "event_count": report.event_count,
        "database_url": store.safe_database_url,
        "manifest_verified": manifest is not None,
    }


def restore_event_log_to_jsonl(
    *,
    source: Path,
    destination: Path,
    manifest: Path | None = None,
) -> dict[str, Any]:
    events = load_events(source)
    validate_event_chain(events)
    if manifest is not None:
        verify_event_log_manifest(events, manifest)
    store = JsonlEventStore(destination)
    report = store.import_events(events)
    return {
        "event_count": report.event_count,
        "destination": str(destination),
        "last_sequence": events[-1].sequence if events else None,
        "last_event_hash": events[-1].event_hash if events else None,
        "manifest_verified": manifest is not None,
    }


def create_event_log_manifest(source: Path) -> dict[str, Any]:
    return build_event_log_manifest(load_events(source))


def load_event_log_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        raise RuntimeError(f"event manifest does not exist: {manifest_path}")
    try:
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid event manifest JSON: {manifest_path}") from exc
    if not isinstance(raw_manifest, dict):
        raise RuntimeError("event manifest must be a JSON object")
    validate_event_log_manifest_document(raw_manifest)
    return raw_manifest


def validate_event_log_manifest_document(raw_manifest: Any) -> None:
    if not isinstance(raw_manifest, dict):
        raise RuntimeError("event manifest must be a JSON object")
    if raw_manifest.get("manifest_type") != MANIFEST_TYPE:
        raise RuntimeError("event manifest type does not match Hollow Lodge event logs")
    if raw_manifest.get("manifest_version") != MANIFEST_VERSION:
        raise RuntimeError("event manifest version is not supported")
    missing_keys = sorted(set(MANIFEST_FIELDS) - set(raw_manifest))
    if missing_keys:
        raise RuntimeError("event manifest is missing fields: " + ", ".join(missing_keys))
    extra_keys = sorted(set(raw_manifest) - set(MANIFEST_FIELDS))
    if extra_keys:
        raise RuntimeError(
            "event manifest contains unexpected fields: " + ", ".join(extra_keys)
        )


def verify_event_log_manifest(events: list[GameEvent], manifest_path: Path) -> None:
    raw_manifest = load_event_log_manifest(manifest_path)
    expected = build_event_log_manifest(events)
    mismatches = [
        key
        for key, expected_value in expected.items()
        if raw_manifest.get(key) != expected_value
    ]
    if mismatches:
        raise RuntimeError(
            "event manifest does not match source export: "
            + ", ".join(sorted(mismatches))
        )


def build_event_log_manifest(events: list[GameEvent]) -> dict[str, Any]:
    validate_event_chain(events)
    if events:
        first = events[0]
        last = events[-1]
        first_sequence = first.sequence
        last_sequence = last.sequence
        first_event_id = first.event_id
        last_event_id = last.event_id
        first_event_hash = first.event_hash
        last_event_hash = last.event_hash
        schema_versions = sorted({event.schema_version for event in events})
    else:
        first_sequence = None
        last_sequence = None
        first_event_id = None
        last_event_id = None
        first_event_hash = None
        last_event_hash = None
        schema_versions = []
    return {
        "manifest_type": MANIFEST_TYPE,
        "manifest_version": MANIFEST_VERSION,
        "event_count": len(events),
        "first_sequence": first_sequence,
        "last_sequence": last_sequence,
        "first_event_id": first_event_id,
        "last_event_id": last_event_id,
        "first_event_hash": first_event_hash,
        "last_event_hash": last_event_hash,
        "schema_versions": schema_versions,
        "event_hash_chain_sha256": event_hash_chain_digest(events),
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
