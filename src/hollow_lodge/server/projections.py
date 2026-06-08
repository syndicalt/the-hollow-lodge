from __future__ import annotations

from typing import Any

from hollow_lodge.domain.contracts import Campaign, Contract
from hollow_lodge.domain.events import GameEvent


def contract_board_from_events(events: list[GameEvent]) -> dict[str, Any]:
    campaign: Campaign | None = None
    contracts: dict[str, Contract] = {}
    phase_results: dict[str, dict[str, Any]] = {}
    phase_locks: dict[str, dict[str, Any]] = {}
    lifecycle_statuses: dict[str, str] = {}
    for event in events:
        if event.type == "campaign.seeded":
            campaign = Campaign.model_validate(event.payload)
        elif event.type == "contract.board.published":
            contract = Contract.model_validate(event.payload)
            contracts[contract.contract_id] = contract
        elif event.type == "contract.phase.resolved":
            phase_results[event.payload["contract_id"]] = event.payload["reveal"]
        elif event.type == "contract.phase.locked":
            phase_locks[event.payload["contract_id"]] = event.payload
        elif event.type == "contract.lifecycle.changed":
            lifecycle_statuses[event.payload["contract_id"]] = event.payload["status"]
    contract_rows = []
    for contract in sorted(contracts.values(), key=lambda item: item.contract_id):
        row = contract.model_dump(mode="json")
        if contract.contract_id in phase_results:
            row["phase_result"] = phase_results[contract.contract_id]
            row["phase"]["status"] = "resolved"
        elif contract.contract_id in phase_locks:
            row["phase"]["status"] = "locked"
        row["lifecycle_status"] = lifecycle_statuses.get(contract.contract_id, "active")
        contract_rows.append(row)
    return {
        "campaign": campaign.model_dump(mode="json") if campaign is not None else None,
        "contracts": contract_rows,
    }


def inbox_from_board(*, player_id: str, board: dict[str, Any]) -> dict[str, Any]:
    return {
        "player_id": player_id,
        "active_contracts": board["contracts"],
        "incoming_proof_fragments": [],
    }


def crew_legacy_from_contracts(*, crew_id: str, contracts: list[dict[str, Any]]) -> dict[str, Any]:
    completed_contracts: list[dict[str, Any]] = []
    reputation = 0
    heat = 0
    favors = 0
    debts = 0
    scars: list[str] = []

    for contract in contracts:
        phase_result = contract.get("phase_result")
        if not phase_result:
            continue
        standing = _standing_for_crew(phase_result, crew_id)
        if standing is None:
            continue
        outcome = _outcome_key(standing)
        completed_contracts.append(
            {
                "contract_id": contract["contract_id"],
                "title": contract["title"],
                "phase": contract.get("phase", {}).get("name", phase_result.get("phase", "")),
                "standing": standing["standing"],
                "score": standing["score"],
                "outcome": outcome,
            }
        )
        if outcome == "strong_lead":
            reputation += 2
            heat += 1
            favors += 1
        elif outcome == "viable":
            reputation += 1
        else:
            debts += 1
            scars.append(f"Bruised by {contract['title']}")

    future_opportunities = []
    for contract in contracts:
        if contract.get("phase_result"):
            continue
        modifiers = _future_modifiers(contract=contract, reputation=reputation, heat=heat)
        if modifiers:
            future_opportunities.append(
                {
                    "contract_id": contract["contract_id"],
                    "title": contract["title"],
                    "modifiers": modifiers,
                }
            )

    return {
        "crew_id": crew_id,
        "reputation": reputation,
        "heat": heat,
        "favors": favors,
        "debts": debts,
        "scars": scars,
        "completed_contracts": completed_contracts,
        "future_opportunities": future_opportunities,
    }


def apply_crew_modifiers_to_contracts(
    *,
    contracts: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
) -> None:
    modifiers_by_contract = {
        opportunity["contract_id"]: opportunity["modifiers"]
        for opportunity in opportunities
    }
    for contract in contracts:
        modifiers = modifiers_by_contract.get(contract["contract_id"])
        if modifiers:
            contract["crew_modifiers"] = modifiers


def _standing_for_crew(phase_result: dict[str, Any], crew_id: str) -> dict[str, Any] | None:
    for standing in phase_result.get("standings", []):
        if standing.get("crew_id") == crew_id:
            return standing
    return None


def _outcome_key(standing: dict[str, Any]) -> str:
    if standing.get("score", 0) >= 70 or standing.get("standing") == "Strong lead":
        return "strong_lead"
    if standing.get("score", 0) >= 40 or str(standing.get("standing", "")).startswith("Viable"):
        return "viable"
    return "weak"


def _future_modifiers(*, contract: dict[str, Any], reputation: int, heat: int) -> list[dict[str, Any]]:
    modifiers: list[dict[str, Any]] = []
    title = contract["title"]
    if reputation:
        modifiers.append(
            {
                "kind": "reputation_leverage",
                "label": "Reputation leverage",
                "description": f"Prior strong work gives this crew an opening on {title}.",
                "value": reputation,
            }
        )
    if heat:
        modifiers.append(
            {
                "kind": "heat_attention",
                "label": "Heat attention",
                "description": f"Prior heat makes {title} riskier for this crew.",
                "value": heat,
            }
        )
    return modifiers
