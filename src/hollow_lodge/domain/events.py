from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hollow_lodge.domain.ids import EventId, new_event_id


SCHEMA_VERSION = 1


class VisibilityPrincipal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["player", "crew", "server", "public"]
    id: str | None = None

    @model_validator(mode="after")
    def validate_id_shape(self) -> VisibilityPrincipal:
        if self.kind in {"player", "crew"} and not self.id:
            raise ValueError("player and crew visibility principals require non-empty ids")
        if self.kind in {"server", "public"} and self.id is not None:
            raise ValueError("server and public visibility principals must not include an id")
        return self


class EventVisibility(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    entries: tuple[VisibilityPrincipal, ...] = Field(
        default_factory=tuple,
        validation_alias="principals",
        serialization_alias="principals",
    )

    @classmethod
    def deny_all(cls) -> EventVisibility:
        return cls()

    @classmethod
    def server_only(cls) -> EventVisibility:
        return cls(principals=(VisibilityPrincipal(kind="server"),))

    @classmethod
    def public(cls) -> EventVisibility:
        return cls(principals=(VisibilityPrincipal(kind="public"),))

    @classmethod
    def players(cls, player_ids: list[str] | tuple[str, ...]) -> EventVisibility:
        return cls.principals(players=player_ids, crews=())

    @classmethod
    def crews(cls, crew_ids: list[str] | tuple[str, ...]) -> EventVisibility:
        return cls.principals(players=(), crews=crew_ids)

    @classmethod
    def principals(
        cls,
        *,
        players: list[str] | tuple[str, ...] = (),
        crews: list[str] | tuple[str, ...] = (),
        server: bool = False,
    ) -> EventVisibility:
        explicit: list[VisibilityPrincipal] = []
        explicit.extend(VisibilityPrincipal(kind="player", id=player_id) for player_id in players)
        explicit.extend(VisibilityPrincipal(kind="crew", id=crew_id) for crew_id in crews)
        if server:
            explicit.append(VisibilityPrincipal(kind="server"))
        return cls(entries=tuple(explicit))


class GameEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: EventId
    sequence: int = Field(ge=1)
    timestamp: datetime
    type: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    visibility: EventVisibility
    payload: dict[str, Any] = Field(default_factory=dict)
    previous_hash: str | None = None
    event_hash: str
    schema_version: Literal[1]
    idempotency_key: str | None = None
    command_fingerprint: str | None = None

    @classmethod
    def new(
        cls,
        *,
        sequence: int,
        event_type: str,
        actor_id: str,
        visibility: EventVisibility,
        payload: dict[str, Any],
        previous_hash: str | None,
        idempotency_key: str | None = None,
        command_fingerprint: str | None = None,
        timestamp: datetime | None = None,
        event_id: EventId | None = None,
    ) -> GameEvent:
        event_data = {
            "event_id": event_id or new_event_id(),
            "sequence": sequence,
            "timestamp": timestamp or datetime.now(UTC),
            "type": event_type,
            "actor_id": actor_id,
            "visibility": visibility,
            "payload": payload,
            "previous_hash": previous_hash,
            "schema_version": SCHEMA_VERSION,
            "idempotency_key": idempotency_key,
            "command_fingerprint": command_fingerprint,
        }
        event_hash = compute_event_hash(event_data)
        return cls(event_hash=event_hash, **event_data)


def canonical_json_bytes(data: Any) -> bytes:
    def default(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat().replace("+00:00", "Z")
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        return str(value)

    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=default,
    ).encode("utf-8")


def compute_event_hash(event_data: dict[str, Any]) -> str:
    hashable = dict(event_data)
    hashable.pop("event_hash", None)
    return hashlib.sha256(canonical_json_bytes(hashable)).hexdigest()
