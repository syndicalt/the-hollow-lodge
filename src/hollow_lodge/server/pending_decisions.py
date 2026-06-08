from __future__ import annotations

from typing import Any


Decision = dict[str, Any]


def pending_decisions_for_player(
    *,
    player_id: str,
    crew_ids: list[str] | tuple[str, ...],
    active_contracts: list[dict[str, Any]],
    deals: list[dict[str, Any]],
    crew_summaries: dict[str, dict[str, Any]],
    dossiers: dict[str, dict[str, Any]],
    actions_by_crew: dict[str, list[dict[str, Any]]] | None = None,
    rumors_by_crew: dict[str, list[dict[str, Any]]] | None = None,
    crew_legacies: dict[str, dict[str, Any]] | None = None,
) -> list[Decision]:
    decisions: list[Decision] = []
    visible_crew_ids = set(crew_ids)
    actions_by_crew = actions_by_crew or {}
    rumors_by_crew = rumors_by_crew or {}
    crew_legacies = crew_legacies or {}
    answered_rumor_ids = {
        action.get("responds_to_rumor_id")
        for actions in actions_by_crew.values()
        for action in actions
        if action.get("status") == "submitted" and action.get("responds_to_rumor_id")
    }
    answered_rumor_escalation_crew_ids = {
        crew_id
        for crew_id, actions in actions_by_crew.items()
        for action in actions
        if action.get("status") == "submitted"
        and action.get("responds_to_rumor_escalation") is True
    }

    for deal in deals:
        if deal.get("status") != "proposed":
            continue
        proposer_crew_id = deal.get("proposer_crew_id")
        recipient_crew_id = deal.get("recipient_crew_id")
        if recipient_crew_id in visible_crew_ids:
            decisions.append(
                {
                    "kind": "incoming_deal",
                    "label": "Incoming deal needs response",
                    "description": (
                        f"Deal {deal['deal_id']} from {proposer_crew_id} needs a response."
                    ),
                    "crew_id": recipient_crew_id,
                    "contract_id": deal["contract_id"],
                    "deal_id": deal["deal_id"],
                }
            )
        if proposer_crew_id in visible_crew_ids:
            decisions.append(
                {
                    "kind": "outgoing_deal",
                    "label": "Outgoing deal awaiting response",
                    "description": (
                        f"Deal {deal['deal_id']} is proposed to {recipient_crew_id}."
                    ),
                    "crew_id": proposer_crew_id,
                    "contract_id": deal["contract_id"],
                    "deal_id": deal["deal_id"],
                }
            )

    unresolved_contracts = [
        contract
        for contract in active_contracts
        if contract.get("phase", {}).get("status", "active") not in {"locked", "resolved"}
        and contract.get("unlock_status", {}).get("state") != "locked"
    ]
    for crew_id in crew_ids:
        escalation = _rumor_escalation_decision(
            crew_id=crew_id,
            legacy=crew_legacies.get(crew_id, {}),
        )
        if escalation is not None and crew_id not in answered_rumor_escalation_crew_ids:
            decisions.append(escalation)

        for rumor in rumors_by_crew.get(crew_id, []):
            if rumor["rumor_id"] in answered_rumor_ids:
                continue
            decisions.append(
                {
                    "kind": "rumor_response",
                    "label": "Rumor needs response",
                    "description": (
                        f"Rumor {rumor['rumor_id']} suggests {rumor['pressure']}. "
                        "Decide whether to verify, ignore, or answer with a crew action."
                    ),
                    "crew_id": crew_id,
                    "rumor_id": rumor["rumor_id"],
                    "source_type": rumor["source_type"],
                    "source_id": rumor["source_id"],
                    "pressure": rumor["pressure"],
                    "action": "review_rumor",
                }
            )

        dossier = dossiers.get(crew_id, {})
        for contract in unresolved_contracts:
            for need in _missing_dossier_needs(contract, dossier):
                decisions.append(
                    {
                        "kind": "dossier_need",
                        "label": f"Dossier needs {need}",
                        "description": (
                            f"{contract['title']} still needs dossier coverage for {need}."
                        ),
                        "crew_id": crew_id,
                        "contract_id": contract["contract_id"],
                        "missing_need": need,
                    }
                )
            active_actions = [
                action
                for action in actions_by_crew.get(crew_id, [])
                if action.get("status") == "submitted"
            ]
            if active_actions:
                action_ids = [action["action_id"] for action in active_actions]
                decisions.append(
                    {
                        "kind": "contract_action",
                        "label": "Submitted action open for edits",
                        "description": (
                            f"{contract['title']} has submitted action(s) that can "
                            "still be reviewed, edited, or canceled before lock."
                        ),
                        "crew_id": crew_id,
                        "contract_id": contract["contract_id"],
                        "action": "review_submitted_action",
                        "action_ids": action_ids,
                    }
                )
            else:
                decisions.append(
                    {
                        "kind": "contract_action",
                        "label": "Contract action opportunity",
                        "description": f"{contract['title']} is active and unresolved.",
                        "crew_id": crew_id,
                        "contract_id": contract["contract_id"],
                        "action": "submit_action",
                    }
                )

        summary = crew_summaries.get(crew_id, {})
        member_ids = summary.get("member_ids", [])
        packet_lead_player_id = dossier.get("packet_lead_player_id")
        if len(member_ids) > 1 and packet_lead_player_id != player_id:
            decisions.append(
                {
                    "kind": "packet_lead_vote",
                    "label": "Packet Lead vote available",
                    "description": (
                        f"The crew has multiple members and {player_id} is not Packet Lead."
                    ),
                    "crew_id": crew_id,
                    "candidate_player_id": player_id,
                }
            )

    return decisions


def _rumor_escalation_decision(
    *,
    crew_id: str,
    legacy: dict[str, Any],
) -> Decision | None:
    memory = legacy.get("rumor_memory", {})
    assessment_counts = {
        str(assessment): int(count)
        for assessment, count in dict(memory.get("assessment_counts", {})).items()
    }
    credible_count = sum(
        count
        for assessment, count in assessment_counts.items()
        if assessment.startswith("credible_")
    )
    if credible_count < 2:
        return None
    return {
        "kind": "rumor_escalation",
        "label": "Repeated credible rumor signals",
        "description": (
            f"Crew {crew_id} has {credible_count} credible rumor verifications. "
            "Decide whether to contain, exploit, or fold them into contract strategy."
        ),
        "crew_id": crew_id,
        "action": "review_rumor_escalation",
        "credible_count": credible_count,
        "assessment_counts": dict(sorted(assessment_counts.items())),
    }


def _missing_dossier_needs(
    contract: dict[str, Any],
    dossier: dict[str, Any],
) -> list[str]:
    covered_text = _dossier_text(dossier)
    return [
        need
        for need in contract.get("proof_dossier_needs", [])
        if need.lower() not in covered_text
    ]


def _dossier_text(dossier: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "claim",
        "reasoning",
        "weaknesses",
        "provenance_concerns",
    ):
        value = dossier.get(key)
        if value:
            parts.append(str(value))
    parts.extend(str(evidence_id) for evidence_id in dossier.get("evidence_ids", []))
    for citation in dossier.get("artifact_citations", []):
        parts.extend(
            str(citation[key])
            for key in ("artifact_id", "claim", "quote")
            if citation.get(key)
        )
    for contribution in dossier.get("member_contributions", []):
        if contribution.get("note"):
            parts.append(str(contribution["note"]))
        parts.extend(str(evidence_id) for evidence_id in contribution.get("evidence_ids", []))
    return "\n".join(parts).lower()
