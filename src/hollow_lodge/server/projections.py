from __future__ import annotations

from typing import Any

from hollow_lodge.domain.contracts import Campaign, Contract
from hollow_lodge.domain.events import GameEvent


def contract_board_from_events(events: list[GameEvent]) -> dict[str, Any]:
    campaign: Campaign | None = None
    contracts: dict[str, Contract] = {}
    for event in events:
        if event.type == "campaign.seeded":
            campaign = Campaign.model_validate(event.payload)
        elif event.type == "contract.board.published":
            contract = Contract.model_validate(event.payload)
            contracts[contract.contract_id] = contract
    return {
        "campaign": campaign.model_dump(mode="json") if campaign is not None else None,
        "contracts": [
            contract.model_dump(mode="json")
            for contract in sorted(contracts.values(), key=lambda item: item.contract_id)
        ],
    }


def inbox_from_board(*, player_id: str, board: dict[str, Any]) -> dict[str, Any]:
    return {
        "player_id": player_id,
        "active_contracts": board["contracts"],
        "incoming_proof_fragments": [],
    }
