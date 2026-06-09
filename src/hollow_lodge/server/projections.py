from __future__ import annotations

from typing import Any

from hollow_lodge.domain.contracts import Campaign, Contract
from hollow_lodge.domain.crews import Crew
from hollow_lodge.domain.events import GameEvent
from hollow_lodge.server.contract_seed import ContractUnlockRequirement


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
        "active_contracts": [
            contract
            for contract in board["contracts"]
            if contract.get("lifecycle_status", "active") != "archived"
        ],
        "incoming_proof_fragments": [],
    }


def crew_summaries_from_events(events: list[GameEvent]) -> dict[str, dict[str, Any]]:
    crews: dict[str, Crew] = {}
    for event in events:
        if event.type == "crew.created":
            crew = Crew(
                crew_id=event.payload["crew_id"],
                name=event.payload["name"],
                join_code="",
            )
            crew.add_member(event.payload["owner_id"])
            crews[crew.crew_id] = crew
        elif event.type == "crew.member.joined":
            crew = crews.get(event.payload["crew_id"])
            if crew is not None:
                crew.add_member(event.payload["player_id"])
    return {
        crew_id: {
            "crew_id": crew.crew_id,
            "name": crew.name,
            "member_ids": list(crew.member_ids),
            "member_count": len(crew.member_ids),
            "ready_for_full_contracts": crew.ready_for_full_contracts,
            "readiness_warning": crew.readiness_warning,
        }
        for crew_id, crew in sorted(crews.items())
    }


def apply_contract_unlock_status(
    *,
    contracts: list[dict[str, Any]],
    crew_ids: list[str],
    events: list[GameEvent],
    deals_by_crew: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    requirements_by_contract = _unlock_requirements_by_contract(events)
    for contract in contracts:
        requirements = requirements_by_contract.get(contract["contract_id"], ())
        if not requirements:
            continue
        status = _unlock_status_for_contract(
            contract=contract,
            contracts=contracts,
            crew_ids=crew_ids,
            events=events,
            requirements=requirements,
            deals_by_crew=deals_by_crew or {},
        )
        contract["unlock_status"] = status


def unlocked_actionable_contracts(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        contract
        for contract in contracts
        if contract.get("lifecycle_status", "active") != "archived"
        and contract.get("unlock_status", {}).get("state") != "locked"
    ]


def crew_legacy_from_contracts(
    *,
    crew_id: str,
    contracts: list[dict[str, Any]],
    deals: list[dict[str, Any]] | None = None,
    events: list[GameEvent] | None = None,
) -> dict[str, Any]:
    completed_contracts: list[dict[str, Any]] = []
    reputation = 0
    heat = 0
    favors = 0
    debts = 0
    scars: list[str] = []
    deal_conduct = deal_conduct_from_deals(crew_id=crew_id, deals=deals or [])
    counterintelligence = counterintelligence_from_events(
        crew_id=crew_id,
        events=events or [],
    )
    rumor_memory = rumor_memory_from_events(
        crew_id=crew_id,
        events=events or [],
    )
    rumor_escalation = rumor_escalation_from_events(
        crew_id=crew_id,
        events=events or [],
    )
    explicit_completed_keys: set[tuple[str, str, str]] = set()

    for event in events or []:
        if event.type != "crew.legacy.delta.recorded":
            continue
        payload = event.payload
        if payload.get("crew_id") != crew_id:
            continue
        deltas = _shape_legacy_deltas(payload.get("deltas", {}))
        contract_id = str(payload.get("contract_id", ""))
        phase = str(payload.get("phase", ""))
        explicit_completed_keys.add((contract_id, phase, crew_id))
        completed_contracts.append(
            {
                "contract_id": contract_id,
                "title": str(payload.get("contract_title", "")),
                "phase": phase,
                "standing": str(payload.get("standing", "")),
                "score": int(payload.get("score", 0)),
                "outcome": str(payload.get("outcome", "")),
            }
        )
        reputation += deltas["reputation"]
        heat += deltas["heat"]
        favors += deltas["favors"]
        debts += deltas["debts"]
        scars.extend(deltas["scars"])

    for contract in contracts:
        phase_result = contract.get("phase_result")
        if not phase_result:
            continue
        standing = _standing_for_crew(phase_result, crew_id)
        if standing is None:
            continue
        phase = contract.get("phase", {}).get("name", phase_result.get("phase", ""))
        if (contract["contract_id"], phase, crew_id) in explicit_completed_keys:
            continue
        delta = legacy_delta_for_standing(
            contract_id=contract["contract_id"],
            contract_title=contract["title"],
            phase=phase,
            standing=standing,
        )
        completed_contracts.append(
            {
                "contract_id": delta["contract_id"],
                "title": delta["contract_title"],
                "phase": delta["phase"],
                "standing": delta["standing"],
                "score": delta["score"],
                "outcome": delta["outcome"],
            }
        )
        deltas = delta["deltas"]
        reputation += deltas["reputation"]
        heat += deltas["heat"]
        favors += deltas["favors"]
        debts += deltas["debts"]
        scars.extend(deltas["scars"])
    heat += counterintelligence["heat_from_containment"]

    future_opportunities = []
    for contract in contracts:
        if contract.get("phase_result"):
            continue
        modifiers = _future_modifiers(
            contract=contract,
            reputation=reputation,
            heat=heat,
            scars=scars,
            deal_conduct=deal_conduct,
            rumor_escalation=rumor_escalation,
        )
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
        "deal_conduct": deal_conduct,
        "counterintelligence": counterintelligence,
        "rumor_memory": rumor_memory,
        "rumor_escalation": rumor_escalation,
        "completed_contracts": completed_contracts,
        "future_opportunities": future_opportunities,
    }


def _unlock_requirements_by_contract(
    events: list[GameEvent],
) -> dict[str, tuple[ContractUnlockRequirement, ...]]:
    requirements_by_contract: dict[str, tuple[ContractUnlockRequirement, ...]] = {}
    for event in events:
        if event.type != "artifact.graph.seeded":
            continue
        payload = event.payload
        graph_payload = payload.get("graph", payload)
        contract_id = str(graph_payload.get("contract_id", ""))
        requirements_by_contract[contract_id] = tuple(
            ContractUnlockRequirement.model_validate(requirement)
            for requirement in payload.get("unlock_requirements", ())
        )
    return requirements_by_contract


def _unlock_status_for_contract(
    *,
    contract: dict[str, Any],
    contracts: list[dict[str, Any]],
    crew_ids: list[str],
    events: list[GameEvent],
    requirements: tuple[ContractUnlockRequirement, ...],
    deals_by_crew: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    if not crew_ids:
        shaped = [
            _shape_unlock_requirement(requirement, current=0)
            for requirement in requirements
        ]
        return {"state": "locked", "requirements": shaped}

    per_crew_statuses = [
        [
            _shape_unlock_requirement(
                requirement,
                current=_unlock_metric_value(
                    requirement,
                    crew_legacy_from_contracts(
                        crew_id=crew_id,
                        contracts=contracts,
                        deals=deals_by_crew.get(crew_id, []),
                        events=events,
                    ),
                ),
            )
            for requirement in requirements
        ]
        for crew_id in crew_ids
    ]
    for status in per_crew_statuses:
        if all(requirement["satisfied"] for requirement in status):
            return {"state": "unlocked", "requirements": status}
    best_status = max(
        per_crew_statuses,
        key=lambda status: sum(int(requirement["satisfied"]) for requirement in status),
    )
    return {"state": "locked", "requirements": best_status}


def _shape_unlock_requirement(
    requirement: ContractUnlockRequirement,
    *,
    current: int,
) -> dict[str, Any]:
    shaped = {
        "scope": requirement.scope,
        "metric": requirement.metric,
        "minimum": requirement.minimum,
        "current": current,
        "label": requirement.label,
        "description": requirement.description,
        "satisfied": current >= requirement.minimum,
    }
    if requirement.required_contract_id is not None:
        shaped["required_contract_id"] = requirement.required_contract_id
    return shaped


def _unlock_metric_value(
    requirement: ContractUnlockRequirement,
    legacy: dict[str, Any],
) -> int:
    metric = requirement.metric
    if metric in {"reputation", "favors"}:
        return int(legacy.get(metric, 0))
    if metric == "deal_conduct_score":
        return int(legacy.get("deal_conduct", {}).get("score", 0))
    if metric == "rumor_containment":
        return int(legacy.get("rumor_escalation", {}).get("contain_count", 0))
    if metric == "rumor_exploitation":
        return int(legacy.get("rumor_escalation", {}).get("exploit_count", 0))
    if metric == "rumor_integration":
        return int(legacy.get("rumor_escalation", {}).get("integrate_count", 0))
    if metric == "completed_contract":
        return int(
            any(
                completed.get("contract_id") == requirement.required_contract_id
                for completed in legacy.get("completed_contracts", [])
            )
        )
    return 0


def legacy_delta_for_standing(
    *,
    contract_id: str,
    contract_title: str,
    phase: str,
    standing: dict[str, Any],
) -> dict[str, Any]:
    outcome = _outcome_key(standing)
    deltas = {
        "reputation": 0,
        "heat": 0,
        "favors": 0,
        "debts": 0,
        "scars": [],
    }
    if outcome == "strong_lead":
        deltas["reputation"] = 2
        deltas["heat"] = 1
        deltas["favors"] = 1
    elif outcome == "viable":
        deltas["reputation"] = 1
    else:
        deltas["debts"] = 1
        deltas["scars"] = [f"Bruised by {contract_title}"]
    return {
        "schema_version": 1,
        "crew_id": standing["crew_id"],
        "contract_id": contract_id,
        "contract_title": contract_title,
        "phase": phase,
        "standing": standing["standing"],
        "score": int(standing["score"]),
        "outcome": outcome,
        "deltas": deltas,
        "summary": _legacy_delta_summary(
            contract_title=contract_title,
            standing=standing["standing"],
            deltas=deltas,
        ),
    }


def _shape_legacy_deltas(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "reputation": int(raw.get("reputation", 0)),
        "heat": int(raw.get("heat", 0)),
        "favors": int(raw.get("favors", 0)),
        "debts": int(raw.get("debts", 0)),
        "scars": [str(scar) for scar in raw.get("scars", [])],
    }


def _legacy_delta_summary(
    *,
    contract_title: str,
    standing: str,
    deltas: dict[str, Any],
) -> str:
    parts = []
    for key in ("reputation", "heat", "favors", "debts"):
        value = int(deltas.get(key, 0))
        if value:
            parts.append(f"{key} +{value}")
    scars = [str(scar) for scar in deltas.get("scars", [])]
    if scars:
        parts.append(f"scars +{len(scars)}")
    if not parts:
        parts.append("no legacy change")
    return f"{standing} on {contract_title}: {', '.join(parts)}."


def counterintelligence_from_events(
    *,
    crew_id: str,
    events: list[GameEvent],
) -> dict[str, int]:
    investigations_started = 0
    containments_started = 0
    heat_from_containment = 0

    for event in events:
        if event.type != "contract.rumor.responded":
            continue
        if event.payload.get("crew_id") != crew_id:
            continue
        if event.payload.get("mode", "investigate") == "contain":
            containments_started += 1
            heat_from_containment += int(event.payload.get("heat_delta", 0))
        else:
            investigations_started += 1

    return {
        "investigations_started": investigations_started,
        "containments_started": containments_started,
        "heat_from_containment": heat_from_containment,
    }


def rumor_memory_from_events(
    *,
    crew_id: str,
    events: list[GameEvent],
) -> dict[str, Any]:
    assessment_counts: dict[str, int] = {}
    recent: list[dict[str, Any]] = []

    for event in events:
        if event.type != "contract.rumor.verified":
            continue
        payload = event.payload
        if payload.get("crew_id") != crew_id:
            continue
        assessment = str(payload.get("assessment", "unknown"))
        assessment_counts[assessment] = assessment_counts.get(assessment, 0) + 1
        memory = {
            "rumor_id": str(payload.get("rumor_id", "")),
            "pressure": str(payload.get("pressure", "")),
            "assessment": assessment,
            "confidence": str(payload.get("confidence", "")),
            "summary": str(payload.get("summary", "")),
        }
        if payload.get("contract_id"):
            memory["contract_id"] = str(payload["contract_id"])
        recent.append(memory)

    return {
        "verified_count": len(recent),
        "assessment_counts": dict(sorted(assessment_counts.items())),
        "recent": recent[-5:],
    }


def rumor_escalation_from_events(
    *,
    crew_id: str,
    events: list[GameEvent],
) -> dict[str, int]:
    counts = {
        "contain_count": 0,
        "exploit_count": 0,
        "integrate_count": 0,
        "credible_count_total": 0,
    }

    for event in events:
        if event.type != "contract.rumor.escalated":
            continue
        payload = event.payload
        if payload.get("crew_id") != crew_id:
            continue
        mode = str(payload.get("mode", ""))
        if mode in {"contain", "exploit", "integrate"}:
            counts[f"{mode}_count"] += 1
        counts["credible_count_total"] += max(
            0,
            int(payload.get("credible_count", 0)),
        )

    return counts


def deal_conduct_from_deals(*, crew_id: str, deals: list[dict[str, Any]]) -> dict[str, Any]:
    fulfilled_count = 0
    canceled_count = 0
    declined_count = 0
    open_count = 0
    score = 0

    for deal in deals:
        proposer_crew_id = deal.get("proposer_crew_id")
        recipient_crew_id = deal.get("recipient_crew_id")
        if crew_id not in {proposer_crew_id, recipient_crew_id}:
            continue
        status = deal.get("status")
        if status == "fulfilled":
            fulfilled_count += 1
            score += 2
        elif status == "canceled":
            canceled_count += 1
            if proposer_crew_id == crew_id:
                score -= 1
        elif status == "declined":
            declined_count += 1
        elif status in {"proposed", "accepted"}:
            open_count += 1

    clamped_score = max(-3, min(5, score))
    return {
        "score": clamped_score,
        "fulfilled_count": fulfilled_count,
        "canceled_count": canceled_count,
        "declined_count": declined_count,
        "open_count": open_count,
        "reliability": _deal_reliability_label(clamped_score),
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


def _future_modifiers(
    *,
    contract: dict[str, Any],
    reputation: int,
    heat: int,
    scars: list[str] | None = None,
    deal_conduct: dict[str, Any] | None = None,
    rumor_escalation: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
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
    scar_count = len(scars or [])
    if scar_count:
        modifiers.append(
            {
                "kind": "scar_burden",
                "label": "Scar burden",
                "description": f"A prior scar makes {title} more dangerous for this crew.",
                "value": scar_count,
            }
        )
    deal_score = (deal_conduct or {}).get("score", 0)
    if deal_score > 0:
        modifiers.append(
            {
                "kind": "deal_reliability",
                "label": "Deal reliability",
                "description": (
                    "Recent escrowed trades make this crew easier to trust on side "
                    f"arrangements for {title}."
                ),
                "value": deal_score,
            }
        )
    escalation = rumor_escalation or {}
    contain_count = min(3, int(escalation.get("contain_count", 0)))
    if contain_count > 0:
        modifiers.append(
            {
                "kind": "rumor_containment",
                "label": "Rumor containment",
                "description": (
                    "Recent containment work gives this crew a quieter "
                    f"approach to {title}."
                ),
                "value": contain_count,
            }
        )
    exploit_count = min(3, int(escalation.get("exploit_count", 0)))
    if exploit_count > 0:
        modifiers.append(
            {
                "kind": "rumor_exploitation",
                "label": "Rumor exploitation",
                "description": (
                    "Recent rumor exploitation gives this crew leverage on "
                    f"{title}."
                ),
                "value": exploit_count,
            }
        )
    integrate_count = min(3, int(escalation.get("integrate_count", 0)))
    if integrate_count > 0:
        modifiers.append(
            {
                "kind": "rumor_integration",
                "label": "Rumor integration",
                "description": (
                    "Integrated rumor signals improve this crew's dossier "
                    f"framing for {title}."
                ),
                "value": integrate_count,
            }
        )
    return modifiers


def _deal_reliability_label(score: int) -> str:
    if score > 0:
        return "reliable_escrow_partner"
    if score < 0:
        return "strained_escrow_partner"
    return "unproven"
