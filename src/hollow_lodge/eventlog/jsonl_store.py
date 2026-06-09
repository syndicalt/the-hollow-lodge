from __future__ import annotations

import json
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import ValidationError

from hollow_lodge.domain.events import (
    EventVisibility,
    GameEvent,
    canonical_json_bytes,
    compute_event_hash,
)
from hollow_lodge.eventlog.visibility import Principal, filter_visible_events


class EventLogIntegrityError(RuntimeError):
    pass


class IdempotencyConflictError(EventLogIntegrityError):
    pass


@dataclass(frozen=True)
class IntegrityReport:
    ok: bool
    event_count: int
    repaired_trailing_row: bool = False


def validate_event_chain(events: list[GameEvent]) -> None:
    previous_hash: str | None = None
    expected_sequence = 1
    for event in events:
        if event.sequence != expected_sequence:
            raise EventLogIntegrityError(
                f"invalid sequence {event.sequence}; expected {expected_sequence}"
            )
        if event.previous_hash != previous_hash:
            raise EventLogIntegrityError(f"hash chain break at sequence {event.sequence}")
        expected_hash = compute_event_hash(event.model_dump(mode="json", exclude={"event_hash"}))
        if event.event_hash != expected_hash:
            raise EventLogIntegrityError(f"invalid event hash at sequence {event.sequence}")
        previous_hash = event.event_hash
        expected_sequence += 1


class EventStore(ABC):
    @abstractmethod
    def append(
        self,
        *,
        event_type: str,
        actor_id: str,
        visibility: EventVisibility,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> GameEvent:
        raise NotImplementedError

    @abstractmethod
    def append_command(
        self,
        *,
        event_type: str,
        actor_id: str,
        visibility: EventVisibility,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> GameEvent:
        raise NotImplementedError

    @abstractmethod
    def read(
        self,
        *,
        start_sequence: int | None = None,
        end_sequence: int | None = None,
    ) -> list[GameEvent]:
        raise NotImplementedError

    @abstractmethod
    def read_for_principal(
        self,
        principal: Principal,
        *,
        start_sequence: int | None = None,
        end_sequence: int | None = None,
    ) -> list[GameEvent]:
        raise NotImplementedError

    @abstractmethod
    def verify_integrity(self, *, repair: bool = False) -> IntegrityReport:
        raise NotImplementedError

    @abstractmethod
    def diagnostics(self) -> dict[str, Any]:
        raise NotImplementedError


class JsonlEventStore(EventStore):
    _locks_guard = threading.Lock()
    _locks: dict[Path, threading.Lock] = {}

    def __init__(self, path: str | Path):
        self.path = Path(path)
        with self._locks_guard:
            self._write_lock = self._locks.setdefault(self.path.resolve(), threading.Lock())

    def append(
        self,
        *,
        event_type: str,
        actor_id: str,
        visibility: EventVisibility,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        ) -> GameEvent:
        with self._write_lock:
            events = self._read_unlocked(repair=False)
            self._validate_chain(events)
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
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("ab") as handle:
                handle.write(canonical_json_bytes(event.model_dump(mode="json", by_alias=False)))
                handle.write(b"\n")
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
        with self._write_lock:
            events = self._read_unlocked(repair=False)
            self._validate_chain(events)
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
        with self._write_lock:
            repaired_trailing_row = self._repair_trailing_invalid_json_row() if repair else False
            events = self._read_unlocked(repair=False, validate_hashes=False)
            self._validate_chain(events)
        return IntegrityReport(
            ok=True,
            event_count=len(events),
            repaired_trailing_row=repaired_trailing_row,
        )

    def diagnostics(self) -> dict[str, Any]:
        exists = self.path.exists()
        status = "available" if exists else "not_created"
        events = self.read() if exists else []
        event_count = len(events)
        last_event = events[-1] if events else None
        return {
            "backend": "jsonl",
            "path": str(self.path),
            "exists": exists,
            "status": status,
            "event_count": event_count,
            "last_sequence": last_event.sequence if last_event is not None else None,
            "last_event_hash": (
                last_event.event_hash if last_event is not None else None
            ),
        }

    def import_events(self, events: list[GameEvent]) -> IntegrityReport:
        validate_event_chain(events)
        with self._write_lock:
            existing = self._read_unlocked(repair=False)
            self._validate_chain(existing)
            if existing:
                raise EventLogIntegrityError(
                    "destination event log is not empty; refusing restore"
                )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("wb") as handle:
                for event in events:
                    handle.write(
                        canonical_json_bytes(
                            event.model_dump(mode="json", by_alias=False)
                        )
                    )
                    handle.write(b"\n")
        return IntegrityReport(ok=True, event_count=len(events))

    def _validate_chain(self, events: list[GameEvent]) -> None:
        validate_event_chain(events)

    def _read_unlocked(
        self,
        *,
        repair: bool,
        validate_hashes: bool = True,
    ) -> list[GameEvent]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        events: list[GameEvent] = []
        for index, line in enumerate(lines):
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                if repair and index == len(lines) - 1:
                    break
                raise EventLogIntegrityError(f"invalid JSON row {index + 1}") from exc
            try:
                event = GameEvent.model_validate(raw)
            except ValidationError as exc:
                raise EventLogIntegrityError(f"invalid event row {index + 1}") from exc
            if validate_hashes:
                expected_hash = compute_event_hash(event.model_dump(mode="json", exclude={"event_hash"}))
                if event.event_hash != expected_hash:
                    raise EventLogIntegrityError(f"invalid event hash at sequence {event.sequence}")
            events.append(event)
        return events

    def _repair_trailing_invalid_json_row(self) -> bool:
        if not self.path.exists():
            return False
        text = self.path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines:
            return False
        try:
            json.loads(lines[-1])
        except json.JSONDecodeError:
            valid_rows = lines[:-1]
            rewritten = "\n".join(valid_rows)
            if rewritten:
                rewritten += "\n"
            self.path.write_text(rewritten, encoding="utf-8")
            return True
        return False


def _find_idempotent(events: Iterable[GameEvent], idempotency_key: str) -> GameEvent | None:
    for event in events:
        if event.idempotency_key == idempotency_key:
            return event
    return None


def _command_fingerprint(
    *,
    event_type: str,
    actor_id: str,
    visibility: EventVisibility,
    payload: dict[str, Any],
) -> str:
    return canonical_json_bytes(
        {
            "actor_id": actor_id,
            "event_type": event_type,
            "payload": payload,
            "visibility": visibility,
        }
    ).hex()


StateT = TypeVar("StateT")


def rebuild_projection(
    events: Iterable[GameEvent],
    initial_state: StateT,
    apply_event: Callable[[StateT, GameEvent], StateT],
) -> StateT:
    state = initial_state
    for event in events:
        state = apply_event(state, event)
    return state
