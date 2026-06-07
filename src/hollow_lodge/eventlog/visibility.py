from __future__ import annotations

from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hollow_lodge.domain.events import GameEvent


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["player", "crew", "server", "public"]
    id: str | None = Field(default=None)

    @model_validator(mode="after")
    def validate_id_shape(self) -> Principal:
        if self.kind in {"player", "crew"} and not self.id:
            raise ValueError("player and crew principals require non-empty ids")
        if self.kind in {"server", "public"} and self.id is not None:
            raise ValueError("server and public principals must not include an id")
        return self

    @classmethod
    def player(cls, player_id: str) -> Principal:
        return cls(kind="player", id=player_id)

    @classmethod
    def crew(cls, crew_id: str) -> Principal:
        return cls(kind="crew", id=crew_id)

    @classmethod
    def server(cls) -> Principal:
        return cls(kind="server")

    @classmethod
    def public(cls) -> Principal:
        return cls(kind="public")


def is_visible_to(event: GameEvent, principal: Principal) -> bool:
    if any(explicit.kind == "public" for explicit in event.visibility.entries):
        return True
    return any(
        explicit.kind == principal.kind and explicit.id == principal.id
        for explicit in event.visibility.entries
    )


def filter_visible_events(events: Iterable[GameEvent], principal: Principal) -> list[GameEvent]:
    return [event for event in events if is_visible_to(event, principal)]
