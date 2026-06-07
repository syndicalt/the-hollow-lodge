from __future__ import annotations

from dataclasses import dataclass, field


MIN_READY_CREW_SIZE = 3
MAX_CREW_SIZE = 5


@dataclass
class Crew:
    crew_id: str
    name: str
    member_ids: list[str] = field(default_factory=list)

    @property
    def ready_for_full_contracts(self) -> bool:
        return MIN_READY_CREW_SIZE <= len(self.member_ids) <= MAX_CREW_SIZE

    @property
    def readiness_warning(self) -> str | None:
        if self.ready_for_full_contracts:
            return None
        return "Crews should have 3-5 players for full contracts; 2-player starter slices are allowed."

    def add_member(self, player_id: str) -> None:
        if player_id in self.member_ids:
            return
        if len(self.member_ids) >= MAX_CREW_SIZE:
            raise ValueError("crew is full")
        self.member_ids.append(player_id)

