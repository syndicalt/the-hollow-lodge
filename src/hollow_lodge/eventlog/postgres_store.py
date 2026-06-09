from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlparse, urlunparse

from pydantic import ValidationError

from hollow_lodge.domain.events import EventVisibility, GameEvent, canonical_json_bytes
from hollow_lodge.eventlog.jsonl_store import (
    EventLogIntegrityError,
    EventStore,
    IdempotencyConflictError,
    IntegrityReport,
    _command_fingerprint,
    _find_idempotent,
    validate_event_chain,
)
from hollow_lodge.eventlog.visibility import Principal, filter_visible_events


class PostgresEventStore(EventStore):
    backend = "postgres"

    def __init__(
        self,
        database_url: str,
        *,
        database_url_env: str = "HOLLOW_LODGE_EVENT_DATABASE_URL",
    ):
        self.database_url = database_url
        self.safe_database_url = _redact_database_url(database_url)
        self.database_url_env = database_url_env

    def append(
        self,
        *,
        event_type: str,
        actor_id: str,
        visibility: EventVisibility,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> GameEvent:
        with self._connect() as connection:
            self._ensure_schema(connection)
            self._lock_event_log(connection)
            events = self._read_unlocked(connection)
            validate_event_chain(events)
            if idempotency_key:
                fingerprint = _command_fingerprint(
                    event_type=event_type,
                    actor_id=actor_id,
                    visibility=visibility,
                    payload=payload,
                )
                existing = _find_idempotent(events, idempotency_key)
                if existing is not None:
                    if existing.command_fingerprint != fingerprint:
                        raise IdempotencyConflictError("idempotency key conflict")
                    return existing
            else:
                fingerprint = None
            previous_hash = events[-1].event_hash if events else None
            event = GameEvent.new(
                sequence=len(events) + 1,
                event_type=event_type,
                actor_id=actor_id,
                visibility=visibility,
                payload=payload,
                previous_hash=previous_hash,
                idempotency_key=idempotency_key,
                command_fingerprint=fingerprint,
            )
            connection.execute(
                """
                insert into event_log (
                    sequence,
                    event_id,
                    event_type,
                    actor_id,
                    visibility_json,
                    payload_json,
                    previous_hash,
                    event_hash,
                    schema_version,
                    idempotency_key,
                    command_fingerprint,
                    event_json
                ) values (
                    %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb
                )
                """,
                (
                    event.sequence,
                    event.event_id,
                    event.type,
                    event.actor_id,
                    _json_dumps(event.visibility.model_dump(mode="json", by_alias=True)),
                    _json_dumps(event.payload),
                    event.previous_hash,
                    event.event_hash,
                    event.schema_version,
                    event.idempotency_key,
                    event.command_fingerprint,
                    _json_dumps(event.model_dump(mode="json")),
                ),
            )
            connection.commit()
        return event

    def append_command(
        self,
        *,
        event_type: str,
        actor_id: str,
        visibility: EventVisibility,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> GameEvent:
        if not idempotency_key:
            raise ValueError("command-derived events require an idempotency key")
        return self.append(
            event_type=event_type,
            actor_id=actor_id,
            visibility=visibility,
            payload=payload,
            idempotency_key=idempotency_key,
        )

    def read(
        self,
        *,
        start_sequence: int | None = None,
        end_sequence: int | None = None,
    ) -> list[GameEvent]:
        with self._connect() as connection:
            self._ensure_schema(connection)
            events = self._read_unlocked(connection)
        validate_event_chain(events)
        if start_sequence is not None:
            events = [event for event in events if event.sequence >= start_sequence]
        if end_sequence is not None:
            events = [event for event in events if event.sequence <= end_sequence]
        return events

    def read_for_principal(
        self,
        principal: Principal,
        *,
        start_sequence: int | None = None,
        end_sequence: int | None = None,
    ) -> list[GameEvent]:
        return filter_visible_events(
            self.read(start_sequence=start_sequence, end_sequence=end_sequence),
            principal,
        )

    def verify_integrity(self, *, repair: bool = False) -> IntegrityReport:
        if repair:
            raise TypeError("Postgres event log repair is not supported")
        events = self.read()
        return IntegrityReport(ok=True, event_count=len(events))

    def diagnostics(self) -> dict[str, Any]:
        try:
            with self._connect() as connection:
                self._ensure_schema(connection)
                chain_rows = self._read_chain_metadata(connection)
                self._validate_chain_metadata(chain_rows)
                chain_digest = _event_hash_chain_digest_from_rows(chain_rows)
        except Exception:
            return {
                "backend": self.backend,
                "database_url": self.safe_database_url,
                "database_url_env": self.database_url_env,
                "exists": False,
                "status": "unavailable",
                "event_count": 0,
                "last_sequence": None,
                "last_event_hash": None,
                "event_hash_chain_sha256": None,
            }
        last_row = chain_rows[-1] if chain_rows else None
        last_sequence = int(last_row["sequence"]) if last_row is not None else None
        last_event_hash = str(last_row["event_hash"]) if last_row is not None else None
        return {
            "backend": self.backend,
            "database_url": self.safe_database_url,
            "database_url_env": self.database_url_env,
            "exists": True,
            "status": "available",
            "event_count": len(chain_rows),
            "last_sequence": last_sequence,
            "last_event_hash": last_event_hash,
            "event_hash_chain_sha256": chain_digest,
        }

    def import_events(self, events: list[GameEvent]) -> IntegrityReport:
        validate_event_chain(events)
        with self._connect() as connection:
            self._ensure_schema(connection)
            self._lock_event_log(connection)
            existing = self._read_unlocked(connection)
            validate_event_chain(existing)
            if existing:
                raise EventLogIntegrityError(
                    "destination event log is not empty; refusing import"
                )
            for event in events:
                self._insert_existing_event(connection, event)
            connection.commit()
        return IntegrityReport(ok=True, event_count=len(existing) + len(events))

    def _connect(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("Postgres event backend requires the psycopg package") from exc
        return psycopg.connect(self.database_url)

    def _ensure_schema(self, connection: Any) -> None:
        connection.execute(
            """
            create table if not exists event_log (
                sequence bigint primary key,
                event_id text not null unique,
                event_type text not null,
                actor_id text not null,
                visibility_json jsonb not null,
                payload_json jsonb not null,
                previous_hash text,
                event_hash text not null unique,
                schema_version integer not null,
                idempotency_key text unique,
                command_fingerprint text,
                event_json jsonb not null
            )
            """
        )
        connection.execute(
            """
            create index if not exists idx_event_log_event_type
            on event_log (event_type)
            """
        )
        connection.execute(
            """
            create index if not exists idx_event_log_idempotency_key
            on event_log (idempotency_key)
            where idempotency_key is not null
            """
        )

    def _lock_event_log(self, connection: Any) -> None:
        connection.execute("select pg_advisory_xact_lock(746930728)")

    def _insert_existing_event(self, connection: Any, event: GameEvent) -> None:
        connection.execute(
            """
            insert into event_log (
                sequence,
                event_id,
                event_type,
                actor_id,
                visibility_json,
                payload_json,
                previous_hash,
                event_hash,
                schema_version,
                idempotency_key,
                command_fingerprint,
                event_json
            ) values (
                %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb
            )
            """,
            (
                event.sequence,
                event.event_id,
                event.type,
                event.actor_id,
                _json_dumps(event.visibility.model_dump(mode="json", by_alias=True)),
                _json_dumps(event.payload),
                event.previous_hash,
                event.event_hash,
                event.schema_version,
                event.idempotency_key,
                event.command_fingerprint,
                _json_dumps(event.model_dump(mode="json")),
            ),
        )

    def _read_unlocked(
        self,
        connection: Any,
    ) -> list[GameEvent]:
        rows = connection.execute(
            "select event_json from event_log order by sequence"
        ).fetchall()
        events: list[GameEvent] = []
        for index, row in enumerate(rows):
            try:
                events.append(GameEvent.model_validate(_load_json(row[0])))
            except ValidationError as exc:
                raise EventLogIntegrityError(f"invalid event row {index + 1}") from exc
        return events

    def _read_chain_metadata(self, connection: Any) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            select sequence, event_id, event_hash, previous_hash
            from event_log
            order by sequence
            """
        ).fetchall()
        return [
            {
                "sequence": int(row[0]),
                "event_id": str(row[1]),
                "event_hash": str(row[2]),
                "previous_hash": None if row[3] is None else str(row[3]),
            }
            for row in rows
        ]

    def _validate_chain_metadata(self, rows: list[dict[str, Any]]) -> None:
        previous_hash: str | None = None
        expected_sequence = 1
        for row in rows:
            sequence = row["sequence"]
            if sequence != expected_sequence:
                raise EventLogIntegrityError(
                    f"invalid sequence {sequence}; expected {expected_sequence}"
                )
            if row["previous_hash"] != previous_hash:
                raise EventLogIntegrityError(f"hash chain break at sequence {sequence}")
            previous_hash = row["event_hash"]
            expected_sequence += 1


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _event_hash_chain_digest_from_rows(rows: list[dict[str, Any]]) -> str:
    chain_rows = [
        {
            "sequence": row["sequence"],
            "event_id": row["event_id"],
            "event_hash": row["event_hash"],
            "previous_hash": row["previous_hash"],
        }
        for row in rows
    ]
    return hashlib.sha256(canonical_json_bytes(chain_rows)).hexdigest()


def _load_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _redact_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if parsed.password is None:
        return database_url
    netloc = parsed.hostname or ""
    if parsed.username:
        netloc = f"{parsed.username}:***@{netloc}"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))
