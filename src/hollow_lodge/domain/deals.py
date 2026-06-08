from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from hollow_lodge.domain.events import GameEvent


DealStatus = Literal["proposed", "accepted", "fulfilled", "declined", "canceled"]


class Deal(BaseModel):
    model_config = ConfigDict(frozen=True)

    deal_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    proposer_crew_id: str = Field(min_length=1)
    recipient_crew_id: str = Field(min_length=1)
    status: DealStatus
    offered_artifact_ids: tuple[str, ...]
    requested_artifact_ids: tuple[str, ...]
    soft_terms: tuple[str, ...] = ()
    expires_phase: str | None = None
    proposer_player_id: str = Field(min_length=1)
    accepted_by_player_id: str | None = None
    proposer_received_artifact_ids: tuple[str, ...] = ()
    recipient_received_artifact_ids: tuple[str, ...] = ()

    def visible_to_crew(self, crew_id: str) -> bool:
        return crew_id in {self.proposer_crew_id, self.recipient_crew_id}


def deal_rows_from_events(events: list[GameEvent] | tuple[GameEvent, ...]) -> list[dict]:
    deals: dict[str, Deal] = {}
    for item in events:
        if item.type == "deal.proposed":
            deals[item.payload["deal_id"]] = Deal(
                deal_id=item.payload["deal_id"],
                contract_id=item.payload["contract_id"],
                proposer_crew_id=item.payload["proposer_crew_id"],
                recipient_crew_id=item.payload["recipient_crew_id"],
                status="proposed",
                offered_artifact_ids=tuple(item.payload["offered_artifact_ids"]),
                requested_artifact_ids=tuple(item.payload["requested_artifact_ids"]),
                soft_terms=tuple(item.payload.get("soft_terms", [])),
                expires_phase=item.payload.get("expires_phase"),
                proposer_player_id=item.payload["proposer_player_id"],
                accepted_by_player_id=item.payload.get("accepted_by_player_id"),
            )
        elif item.type in {"deal.accepted", "deal.fulfilled", "deal.declined", "deal.canceled"}:
            deal_id = item.payload["deal_id"]
            if deal_id not in deals:
                continue
            deals[deal_id] = _apply_lifecycle_event(deals[deal_id], item)
    return [
        deal.model_dump(mode="json")
        for deal in sorted(deals.values(), key=lambda candidate: candidate.deal_id)
    ]


def _apply_lifecycle_event(deal: Deal, event: GameEvent) -> Deal:
    if event.type == "deal.accepted":
        return deal.model_copy(
            update={
                "status": "accepted",
                "accepted_by_player_id": event.payload["accepted_by_player_id"],
            }
        )
    if event.type == "deal.fulfilled":
        return deal.model_copy(
            update={
                "status": "fulfilled",
                "proposer_received_artifact_ids": tuple(
                    event.payload.get("proposer_received_artifact_ids", [])
                ),
                "recipient_received_artifact_ids": tuple(
                    event.payload.get("recipient_received_artifact_ids", [])
                ),
            }
        )
    if event.type == "deal.declined":
        return deal.model_copy(update={"status": "declined"})
    if event.type == "deal.canceled":
        return deal.model_copy(update={"status": "canceled"})
    return deal
