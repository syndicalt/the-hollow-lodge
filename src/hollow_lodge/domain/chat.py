from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ChatKind = Literal["direct", "crew", "crew_to_crew"]


@dataclass(frozen=True)
class ChatMessage:
    message_id: str
    kind: ChatKind
    sender_player_id: str
    body: str
    recipient_player_id: str | None = None
    sender_crew_id: str | None = None
    recipient_crew_id: str | None = None
    artifact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_ids", tuple(self.artifact_ids))
