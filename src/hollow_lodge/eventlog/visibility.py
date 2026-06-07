from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from hollow_lodge.domain.events import GameEvent


@dataclass(frozen=True)
class Principal:
    kind: str
    id: str | None = None

    @classmethod
    def player(cls, player_id: str) -> Principal:
        return cls(kind="player", id=player_id)

    @classmethod
    def crew(cls, crew_id: str) -> Principal:
        return cls(kind="crew", id=crew_id)

    @classmethod
    def server(cls) -> Principal:
        return cls(kind="server")


def is_visible_to(event: GameEvent, principal: Principal) -> bool:
    return any(
        explicit.kind == principal.kind and explicit.id == principal.id
        for explicit in event.visibility.entries
    )


def filter_visible_events(events: Iterable[GameEvent], principal: Principal) -> list[GameEvent]:
    return [event for event in events if is_visible_to(event, principal)]
