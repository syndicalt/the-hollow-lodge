from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field


class RenderAction(BaseModel):
    label: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    requires_confirmation: bool = False


class RenderPacket(BaseModel):
    surface: Literal[
        "inbox",
        "contract_board",
        "crew_board",
        "deals",
        "deal_preview",
        "artifact",
        "artifact_graph",
        "activity",
        "thread",
    ]
    player_markdown: str = Field(min_length=1)
    agent_context: dict[str, Any]
    suggested_prompts: list[str] = Field(default_factory=list)
    actions: list[RenderAction] = Field(default_factory=list)


def _shape_campaign(campaign: dict[str, Any]) -> dict[str, Any] | None:
    if not campaign:
        return None
    return {
        key: campaign[key]
        for key in ("campaign_id", "title")
        if key in campaign
    }


def _shape_phase(phase: dict[str, Any]) -> dict[str, Any]:
    return {
        key: phase[key]
        for key in ("name", "remaining_hours", "status")
        if key in phase
    }


def _shape_phase_result(phase_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "standings": [
            {
                key: standing[key]
                for key in ("crew_id", "standing", "score")
                if key in standing
            }
            for standing in phase_result.get("standings", [])
        ]
    }


def _shape_contract(contract: dict[str, Any]) -> dict[str, Any]:
    shaped = {
        key: contract[key]
        for key in ("contract_id", "title", "crew_heat", "proof_dossier_needs")
        if key in contract
    }
    shaped["phase"] = _shape_phase(contract["phase"])
    if "phase_result" in contract:
        shaped["phase_result"] = _shape_phase_result(contract["phase_result"])
    return shaped


def _shape_proof_fragment(fragment: dict[str, Any]) -> dict[str, Any]:
    return {
        key: fragment[key]
        for key in ("fragment_id", "summary")
        if key in fragment
    }


def _shape_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        key: artifact[key]
        for key in ("artifact_id", "title", "kind", "public_summary")
        if key in artifact
    }


def _shape_deal(deal: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deal[key]
        for key in (
            "deal_id",
            "contract_id",
            "proposer_crew_id",
            "recipient_crew_id",
            "status",
            "offered_artifact_ids",
            "requested_artifact_ids",
            "soft_terms",
            "expires_phase",
            "proposer_received_artifact_ids",
            "recipient_received_artifact_ids",
        )
        if key in deal
    }


def _shape_chat_message(payload: dict[str, Any], sequence: int) -> dict[str, Any]:
    shaped = {
        "sequence": sequence,
        "message_id": payload.get("message_id"),
        "sender_player_id": payload.get("sender_player_id"),
        "sender_crew_id": payload.get("sender_crew_id"),
        "recipient_player_id": payload.get("recipient_player_id"),
        "recipient_crew_id": payload.get("recipient_crew_id"),
        "body": payload.get("body"),
        "artifact_ids": list(payload.get("artifact_ids", [])),
    }
    return {
        key: value
        for key, value in shaped.items()
        if value is not None
    }


def _shape_activity_event(event: dict[str, Any]) -> dict[str, Any]:
    sequence = int(event["sequence"])
    event_type = event["type"]
    payload = event.get("payload", {})
    shaped: dict[str, Any] = {
        "sequence": sequence,
        "type": event_type,
    }
    if event_type == "chat.message.created":
        message = _shape_chat_message(payload, sequence)
        message.pop("sequence", None)
        shaped["message"] = message
    elif event_type == "proof.fragment.transferred":
        surface = payload.get("surface", {})
        shaped["proof_fragment"] = {
            key: surface[key]
            for key in ("fragment_id", "content_summary")
            if key in surface
        }
    elif event_type == "proof.provenance.checked":
        result = payload.get("result", {})
        shaped["provenance"] = {
            key: result[key]
            for key in ("fragment_id", "provenance_flags")
            if key in result
        }
    elif event_type == "action.submitted":
        action = payload.get("action", {})
        shaped["action"] = {
            key: action[key]
            for key in ("action_id", "crew_id", "intent")
            if key in action
        }
    elif event_type == "contract.phase.resolved":
        reveal = payload.get("reveal", {})
        shaped["phase_result"] = _shape_phase_result(reveal)
    return shaped


def _render_activity_event(event: dict[str, Any]) -> str:
    sequence = int(event["sequence"])
    event_type = event["type"]
    payload = event.get("payload", {})
    if event_type == "chat.message.created":
        return f"{sequence} chat {payload.get('sender_player_id')}: {payload.get('body')}"
    if event_type == "proof.fragment.transferred":
        surface = payload.get("surface", {})
        return (
            f"{sequence} proof fragment {surface.get('fragment_id')}: "
            f"{surface.get('content_summary')}"
        )
    if event_type == "proof.provenance.checked":
        result = payload.get("result", {})
        flags = ", ".join(result.get("provenance_flags", [])) or "clear"
        return f"{sequence} provenance {result.get('fragment_id')}: {flags}"
    if event_type == "action.submitted":
        action = payload.get("action", {})
        return f"{sequence} action {action.get('action_id')}: {action.get('intent')}"
    if event_type == "contract.phase.resolved":
        standings = payload.get("reveal", {}).get("standings", [])
        if not standings:
            return f"{sequence} phase result"
        leader = standings[0]
        return (
            f"{sequence} phase result: {leader.get('crew_id')} "
            f"{leader.get('standing')} {leader.get('score')}"
        )
    return f"{sequence} {event_type}"


def payload_matches_conversation(payload: dict[str, Any], conversation_id: str) -> bool:
    if payload.get("message_id") == conversation_id:
        return True
    sender_crew_id = payload.get("sender_crew_id")
    recipient_crew_id = payload.get("recipient_crew_id")
    if sender_crew_id and recipient_crew_id:
        return conversation_id in {
            f"{sender_crew_id}:{recipient_crew_id}",
            f"{recipient_crew_id}:{sender_crew_id}",
        }
    return sender_crew_id == conversation_id


def build_activity_summary_packet(
    events: list[dict[str, Any]],
    *,
    recent_limit: int = 10,
) -> RenderPacket:
    visible_events = sorted(events, key=lambda event: int(event["sequence"]))
    recent_events = visible_events[-recent_limit:]
    lines = ["Recent visible activity:"]
    if recent_events:
        lines.extend(f"- {_render_activity_event(event)}" for event in recent_events)
    else:
        lines.append("- none")
    return RenderPacket(
        surface="activity",
        player_markdown="\n".join(lines),
        agent_context={
            "visible_event_count": len(visible_events),
            "event_type_counts": dict(
                Counter(event["type"] for event in visible_events)
            ),
            "recent_events": [
                _shape_activity_event(event)
                for event in recent_events
            ],
        },
        suggested_prompts=[
            "Open a conversation thread",
            "Review inbox",
            "Open the contract board",
        ],
    )


def build_thread_packet(
    events: list[dict[str, Any]],
    *,
    conversation_id: str,
) -> RenderPacket:
    messages = [
        event
        for event in sorted(events, key=lambda candidate: int(candidate["sequence"]))
        if event.get("type") == "chat.message.created"
        and payload_matches_conversation(event.get("payload", {}), conversation_id)
    ]
    lines = [f"Conversation: {conversation_id}"]
    if messages:
        lines.extend(
            (
                f"- {event['sequence']} {event.get('payload', {}).get('sender_player_id')}: "
                f"{event.get('payload', {}).get('body')}"
            )
            for event in messages
        )
    else:
        lines.append("- no visible messages")
    return RenderPacket(
        surface="thread",
        player_markdown="\n".join(lines),
        agent_context={
            "conversation_id": conversation_id,
            "message_count": len(messages),
            "messages": [
                _shape_chat_message(event.get("payload", {}), int(event["sequence"]))
                for event in messages
            ],
        },
        suggested_prompts=[
            "Reply using the CLI",
            "Review recent activity",
        ],
    )


def _render_deal_lines(deal: dict[str, Any]) -> list[str]:
    offered = _artifact_list(deal.get("offered_artifact_ids", []))
    requested = _artifact_list(deal.get("requested_artifact_ids", []))
    action = "offered" if deal.get("status") == "fulfilled" else "offers"
    lines = [
        (
            f"- {deal['deal_id']} {deal['status']}: "
            f"{deal['proposer_crew_id']} {action} {offered} for {requested}"
        )
    ]
    if deal.get("expires_phase"):
        lines.append(f"  Expires: {deal['expires_phase']}")
    for soft_term in deal.get("soft_terms", []):
        lines.append(f"  Soft term: {soft_term}")
    proposer_received = deal.get("proposer_received_artifact_ids", [])
    if proposer_received:
        lines.append(f"  Received by proposer: {_artifact_list(proposer_received)}")
    recipient_received = deal.get("recipient_received_artifact_ids", [])
    if recipient_received:
        lines.append(f"  Received by recipient: {_artifact_list(recipient_received)}")
    return lines


def _artifact_list(artifact_ids: list[str] | tuple[str, ...]) -> str:
    return ", ".join(artifact_ids) if artifact_ids else "nothing"


def _viewer_side(deal: dict[str, Any], viewer_crew_ids: list[str] | tuple[str, ...]) -> str:
    crews = set(viewer_crew_ids)
    if deal["recipient_crew_id"] in crews:
        return "recipient"
    if deal["proposer_crew_id"] in crews:
        return "proposer"
    return "observer"


def build_deals_packet(payload: dict[str, Any]) -> RenderPacket:
    deals = payload.get("deals", [])
    lines = ["Visible deals:"]
    if deals:
        for deal in deals:
            lines.extend(_render_deal_lines(deal))
    else:
        lines.append("- none")
    return RenderPacket(
        surface="deals",
        player_markdown="\n".join(lines),
        agent_context={
            "deals": [_shape_deal(deal) for deal in deals],
            "visible_deal_count": len(deals),
        },
        suggested_prompts=[
            "Preview deal acceptance",
            "Review crew board",
        ],
    )


def build_deal_acceptance_preview_packet(payload: dict[str, Any]) -> RenderPacket:
    deal = payload["deal"]
    viewer_crew_ids = payload.get("viewer_crew_ids", [])
    side = _viewer_side(deal, viewer_crew_ids)
    if side == "recipient":
        gives = deal.get("requested_artifact_ids", [])
        receives = deal.get("offered_artifact_ids", [])
    elif side == "proposer":
        gives = deal.get("offered_artifact_ids", [])
        receives = deal.get("requested_artifact_ids", [])
    else:
        gives = []
        receives = []

    lines = [
        f"Acceptance preview: {deal['deal_id']}",
        f"Status: {deal['status']}",
        f"Your side: {side}",
        f"Your crew gives: {_artifact_list(gives)}",
        f"Your crew receives: {_artifact_list(receives)}",
        "Concrete artifact terms are server-enforced as copy transfers.",
        "Soft terms are recorded but not enforced by the server.",
    ]
    for soft_term in deal.get("soft_terms", []):
        lines.append(f"Soft term: {soft_term}")
    lines.append("This preview does not accept the deal.")
    return RenderPacket(
        surface="deal_preview",
        player_markdown="\n".join(lines),
        agent_context={
            "deal": _shape_deal(deal),
            "viewer_crew_ids": list(viewer_crew_ids),
            "viewer_side": side,
            "gives_artifact_ids": list(gives),
            "receives_artifact_ids": list(receives),
            "mutation": False,
        },
        suggested_prompts=[
            "Review visible deals",
            "Open crew board",
        ],
    )


def _shape_crew(crew: dict[str, Any]) -> dict[str, Any]:
    return {
        key: crew[key]
        for key in (
            "crew_id",
            "name",
            "member_ids",
            "member_count",
            "ready_for_full_contracts",
            "readiness_warning",
        )
        if key in crew
    }


def _shape_dossier_contribution(contribution: dict[str, Any]) -> dict[str, Any]:
    return {
        key: contribution[key]
        for key in ("player_id", "note", "evidence_ids")
        if key in contribution
    }


def _shape_artifact_citation(citation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: citation[key]
        for key in ("player_id", "artifact_id", "claim", "quote")
        if key in citation
    }


def _shape_dossier(dossier: dict[str, Any]) -> dict[str, Any]:
    shaped = {
        key: dossier[key]
        for key in (
            "dossier_id",
            "crew_id",
            "packet_lead_player_id",
            "claim",
            "evidence_ids",
            "artifact_citations",
            "reasoning",
            "weaknesses",
            "provenance_concerns",
        )
        if key in dossier
    }
    shaped["member_contributions"] = [
        _shape_dossier_contribution(contribution)
        for contribution in dossier.get("member_contributions", [])
    ]
    shaped["artifact_citations"] = [
        _shape_artifact_citation(citation)
        for citation in dossier.get("artifact_citations", [])
    ]
    return shaped


def build_contract_board_packet(board: dict[str, Any]) -> RenderPacket:
    lines: list[str] = []
    campaign = board.get("campaign") or {}
    if campaign:
        lines.append(str(campaign["title"]))
        lines.append("")
    contracts = board.get("contracts", [])
    if not contracts:
        lines.append("No visible contracts.")
    for contract in contracts:
        phase = contract["phase"]
        lines.append(f"## {contract['title']}")
        lines.append(f"Phase: {phase['name']} ({phase.get('remaining_hours', 0)}h remaining)")
        lines.append(f"Crew Heat: {contract.get('crew_heat', 0)}")
        lines.append("Proof dossier needs:")
        lines.extend(f"- {need}" for need in contract.get("proof_dossier_needs", []))
        if "phase_result" in contract:
            lines.append("Phase result:")
            for standing in contract["phase_result"].get("standings", []):
                lines.append(
                    f"- {standing['crew_id']}: {standing['standing']} ({standing['score']})"
                )
        lines.append("")
    visible_artifacts = board.get("visible_artifacts", [])
    if visible_artifacts:
        lines.append("Visible artifacts:")
        lines.extend(
            f"- {artifact['artifact_id']}: {artifact['title']}"
            for artifact in visible_artifacts[:5]
        )
        lines.append("")
    return RenderPacket(
        surface="contract_board",
        player_markdown="\n".join(lines).strip(),
        agent_context={
            "campaign": _shape_campaign(campaign),
            "contracts": [_shape_contract(contract) for contract in contracts],
            "visible_artifacts": [
                _shape_artifact(artifact)
                for artifact in board.get("visible_artifacts", [])
            ],
            "visible_contract_count": len(contracts),
        },
        suggested_prompts=[
            "Open the contested contract",
            "Review crew packet status",
            "Draft a contract action",
        ],
        actions=[
            RenderAction(label="Review crew board", intent="render_crew_board"),
            RenderAction(label="Draft action", intent="draft_action", requires_confirmation=False),
        ],
    )


def build_crew_board_packet(board: dict[str, Any]) -> RenderPacket:
    crew = board["crew"]
    dossier = board["dossier"]
    active_contracts = board.get("active_contracts", [])
    lines = [
        f"Crew Board: {crew['name']}",
        f"Crew ID: {crew['crew_id']}",
        f"Member Count: {crew['member_count']}",
        f"Packet Lead: {dossier['packet_lead_player_id']}",
        "",
        "Active Contracts:",
    ]
    if active_contracts:
        lines.extend(f"- {contract['title']}" for contract in active_contracts)
    else:
        lines.append("- none")
    visible_artifacts = board.get("visible_artifacts", [])
    lines.extend(["", "Artifacts:"])
    if visible_artifacts:
        lines.extend(
            f"- {artifact['artifact_id']}: {artifact['title']}"
            for artifact in visible_artifacts
        )
    else:
        lines.append("- none")
    lines.extend(["", "Deals:"])
    deals = board.get("deals", [])
    if deals:
        for deal in deals:
            lines.extend(_render_deal_lines(deal))
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "Dossier:",
            f"Claim: {dossier.get('claim') or 'not set'}",
            "Evidence:",
        ]
    )
    evidence_ids = dossier.get("evidence_ids", [])
    if evidence_ids:
        lines.extend(f"- {evidence_id}" for evidence_id in evidence_ids)
    else:
        lines.append("- none")
    lines.append("Artifact citations:")
    artifact_citations = dossier.get("artifact_citations", [])
    if artifact_citations:
        for citation in artifact_citations:
            lines.append(f"- {citation['artifact_id']}: {citation['claim']}")
    else:
        lines.append("- none")
    lines.append("Contributions:")
    contributions = dossier.get("member_contributions", [])
    if contributions:
        for contribution in contributions:
            lines.append(f"- {contribution['player_id']}: {contribution['note']}")
    else:
        lines.append("- none")
    return RenderPacket(
        surface="crew_board",
        player_markdown="\n".join(lines),
        agent_context={
            "player_id": board["player_id"],
            "crew": _shape_crew(crew),
            "active_contracts": [
                _shape_contract(contract)
                for contract in active_contracts
            ],
            "dossier": _shape_dossier(dossier),
            "visible_artifacts": [
                _shape_artifact(artifact)
                for artifact in board.get("visible_artifacts", [])
            ],
            "deals": [_shape_deal(deal) for deal in board.get("deals", [])],
            "urgent_items": [],
        },
        suggested_prompts=[
            "Review the proof dossier",
            "Draft a crew action",
            "Vote on packet lead",
        ],
        actions=[
            RenderAction(label="Draft crew action", intent="draft_action"),
            RenderAction(
                label="Update dossier claim",
                intent="update_dossier",
                requires_confirmation=True,
            ),
            RenderAction(
                label="Vote packet lead",
                intent="vote_packet_lead",
                requires_confirmation=True,
            ),
        ],
    )


def build_inbox_packet(inbox: dict[str, Any]) -> RenderPacket:
    display_name = inbox.get("display_name") or inbox["player_id"]
    lines = [f"Inbox: {display_name}"]
    active_contracts = inbox.get("active_contracts", [])
    if active_contracts:
        lines.append("")
        lines.append("Active contracts:")
        for contract in active_contracts:
            lines.append(f"- {contract['title']} ({contract['phase']['name']})")
    fragments = inbox.get("incoming_proof_fragments", [])
    lines.append("")
    if fragments:
        lines.append("incoming proof fragments:")
        lines.extend(f"- {fragment['fragment_id']}: {fragment['summary']}" for fragment in fragments)
    else:
        lines.append("incoming proof fragments: none")
    deals = inbox.get("deals", [])
    lines.append("")
    lines.append("Incoming deals:")
    if deals:
        for deal in deals:
            lines.extend(_render_deal_lines(deal))
    else:
        lines.append("- none")
    artifacts = inbox.get("visible_artifacts", [])
    if artifacts:
        lines.append("")
        lines.append("visible artifacts:")
        lines.extend(
            f"- {artifact['artifact_id']}: {artifact['title']}"
            for artifact in artifacts[:5]
        )
    urgent_items = [
        {"kind": "proof_fragment", "fragment_id": fragment["fragment_id"]}
        for fragment in fragments
    ]
    agent_context: dict[str, Any] = {
        "player_id": inbox["player_id"],
        "active_contracts": [
            _shape_contract(contract)
            for contract in active_contracts
        ],
        "incoming_proof_fragments": [
            _shape_proof_fragment(fragment)
            for fragment in fragments
        ],
        "visible_artifacts": [
            _shape_artifact(artifact)
            for artifact in inbox.get("visible_artifacts", [])
        ],
        "deals": [_shape_deal(deal) for deal in inbox.get("deals", [])],
        "urgent_items": urgent_items,
    }
    if inbox.get("display_name"):
        agent_context["display_name"] = inbox["display_name"]
    return RenderPacket(
        surface="inbox",
        player_markdown="\n".join(lines),
        agent_context=agent_context,
        suggested_prompts=[
            "Open the contract board",
            "Review crew board",
        ],
    )
