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
        "what_now",
        "profile",
        "contract_board",
        "crew_board",
        "dossier",
        "deals",
        "deal_preview",
        "artifact",
        "artifact_graph",
        "activity",
        "activity_delta",
        "crew_activity",
        "conversations",
        "thread",
        "mutation",
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
    shaped = {
        "standings": [
            _shape_phase_standing(standing)
            for standing in phase_result.get("standings", [])
        ]
    }
    if "contract_state" in phase_result:
        shaped["contract_state"] = list(phase_result["contract_state"])
    return shaped


def _shape_phase_standing(standing: dict[str, Any]) -> dict[str, Any]:
    shaped = {
        key: standing[key]
        for key in ("crew_id", "standing", "score")
        if key in standing
    }
    reasoning = {
        key: list(standing.get(key, []))
        for key in ("strengths", "weaknesses", "penalties", "revealed_clues")
    }
    shaped["score_reasoning"] = reasoning
    return shaped


def _shape_modifier(modifier: dict[str, Any]) -> dict[str, Any]:
    return {
        key: modifier[key]
        for key in ("kind", "label", "description", "value")
        if key in modifier
    }


def _shape_unlock_status(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": status.get("state", "unlocked"),
        "requirements": [
            {
                key: requirement[key]
                for key in (
                    "scope",
                    "metric",
                    "required_contract_id",
                    "minimum",
                    "current",
                    "label",
                    "description",
                    "satisfied",
                )
                if key in requirement
            }
            for requirement in status.get("requirements", [])
        ],
    }


def _shape_arc(arc: dict[str, Any]) -> dict[str, Any]:
    return {
        key: arc[key]
        for key in (
            "arc_id",
            "title",
            "chapter",
            "sequence",
            "public_summary",
            "previous_contract_id",
            "next_contract_hint",
        )
        if key in arc
    }


def _shape_contract(contract: dict[str, Any]) -> dict[str, Any]:
    shaped = {
        key: contract[key]
        for key in (
            "contract_id",
            "title",
            "crew_heat",
            "proof_dossier_needs",
            "lifecycle_status",
        )
        if key in contract
    }
    shaped["phase"] = _shape_phase(contract["phase"])
    if "phase_result" in contract:
        shaped["phase_result"] = _shape_phase_result(contract["phase_result"])
    if "crew_modifiers" in contract:
        shaped["crew_modifiers"] = [
            _shape_modifier(modifier)
            for modifier in contract["crew_modifiers"]
        ]
    if "unlock_status" in contract:
        shaped["unlock_status"] = _shape_unlock_status(contract["unlock_status"])
    if contract.get("arc"):
        shaped["arc"] = _shape_arc(contract["arc"])
    return shaped


def _contract_arc_status(contract: dict[str, Any]) -> str:
    if contract.get("lifecycle_status") == "archived":
        return "archived"
    if (
        contract.get("unlock_status", {}).get("state") == "locked"
        or contract.get("phase", {}).get("status") == "locked"
    ):
        return "locked"
    if contract.get("phase_result") or contract.get("phase", {}).get("status") == "resolved":
        return "resolved"
    return "active"


def _shape_arc_progress(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    arcs: dict[str, dict[str, Any]] = {}
    for contract in contracts:
        if not contract.get("arc"):
            continue
        arc = _shape_arc(contract["arc"])
        arc_id = arc["arc_id"]
        progress = arcs.setdefault(
            arc_id,
            {
                "arc_id": arc_id,
                "title": arc["title"],
                "total_contracts": 0,
                "resolved_count": 0,
                "active_count": 0,
                "locked_count": 0,
                "archived_count": 0,
                "chapters": [],
            },
        )
        status = _contract_arc_status(contract)
        progress["total_contracts"] += 1
        progress[f"{status}_count"] += 1
        progress["chapters"].append(
            {
                "contract_id": contract["contract_id"],
                "title": contract["title"],
                "chapter": arc["chapter"],
                "sequence": arc["sequence"],
                "status": status,
            }
        )
    progress_rows = sorted(
        arcs.values(),
        key=lambda progress: (
            min(chapter["sequence"] for chapter in progress["chapters"]),
            progress["title"],
            progress["arc_id"],
        ),
    )
    for progress in progress_rows:
        progress["chapters"].sort(
            key=lambda chapter: (
                chapter["sequence"],
                chapter["chapter"],
                chapter["title"],
                chapter["contract_id"],
            )
        )
    return progress_rows


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


def _shape_crew_legacy(legacy: dict[str, Any]) -> dict[str, Any]:
    return {
        "reputation": legacy.get("reputation", 0),
        "heat": legacy.get("heat", 0),
        "favors": legacy.get("favors", 0),
        "debts": legacy.get("debts", 0),
        "scars": list(legacy.get("scars", [])),
        "deal_conduct": _shape_deal_conduct(legacy.get("deal_conduct", {})),
        "counterintelligence": _shape_counterintelligence(
            legacy.get("counterintelligence", {})
        ),
        "rumor_memory": _shape_rumor_memory(legacy.get("rumor_memory", {})),
        "rumor_escalation": _shape_rumor_escalation_legacy(
            legacy.get("rumor_escalation", {})
        ),
        "completed_contracts": [
            {
                key: contract[key]
                for key in ("contract_id", "title", "phase", "standing", "score", "outcome")
                if key in contract
            }
            for contract in legacy.get("completed_contracts", [])
        ],
        "future_opportunities": [
            {
                "contract_id": opportunity["contract_id"],
                "title": opportunity["title"],
                "modifiers": [
                    _shape_modifier(modifier)
                    for modifier in opportunity.get("modifiers", [])
                ],
            }
            for opportunity in legacy.get("future_opportunities", [])
        ],
    }


def _shape_deal_conduct(conduct: dict[str, Any]) -> dict[str, Any]:
    return {
        "score": conduct.get("score", 0),
        "fulfilled_count": conduct.get("fulfilled_count", 0),
        "canceled_count": conduct.get("canceled_count", 0),
        "declined_count": conduct.get("declined_count", 0),
        "open_count": conduct.get("open_count", 0),
        "reliability": conduct.get("reliability", "unproven"),
    }


def _shape_counterintelligence(counterintelligence: dict[str, Any]) -> dict[str, int]:
    return {
        "investigations_started": int(
            counterintelligence.get("investigations_started", 0)
        ),
        "containments_started": int(
            counterintelligence.get("containments_started", 0)
        ),
        "heat_from_containment": int(
            counterintelligence.get("heat_from_containment", 0)
        ),
    }


def _shape_rumor_memory(memory: dict[str, Any]) -> dict[str, Any]:
    return {
        "verified_count": int(memory.get("verified_count", 0)),
        "assessment_counts": {
            str(assessment): int(count)
            for assessment, count in sorted(
                dict(memory.get("assessment_counts", {})).items()
            )
        },
        "recent": [
            {
                key: item[key]
                for key in (
                    "rumor_id",
                    "contract_id",
                    "pressure",
                    "assessment",
                    "confidence",
                    "summary",
                )
                if key in item
            }
            for item in memory.get("recent", [])
        ][:5],
    }


def _shape_rumor_escalation_legacy(escalation: dict[str, Any]) -> dict[str, int]:
    return {
        "contain_count": int(escalation.get("contain_count", 0)),
        "exploit_count": int(escalation.get("exploit_count", 0)),
        "integrate_count": int(escalation.get("integrate_count", 0)),
        "credible_count_total": int(escalation.get("credible_count_total", 0)),
    }


def _shape_legacy_delta(payload: dict[str, Any]) -> dict[str, Any]:
    deltas = payload.get("deltas", {})
    return {
        "schema_version": int(payload.get("schema_version", 1)),
        "crew_id": payload.get("crew_id"),
        "contract_id": payload.get("contract_id"),
        "contract_title": payload.get("contract_title"),
        "phase": payload.get("phase"),
        "standing": payload.get("standing"),
        "score": int(payload.get("score", 0)),
        "outcome": payload.get("outcome"),
        "deltas": {
            "reputation": int(deltas.get("reputation", 0)),
            "heat": int(deltas.get("heat", 0)),
            "favors": int(deltas.get("favors", 0)),
            "debts": int(deltas.get("debts", 0)),
            "scars": [str(scar) for scar in deltas.get("scars", [])],
        },
        "summary": payload.get("summary", ""),
    }


def _shape_pending_decision(decision: dict[str, Any]) -> dict[str, Any]:
    shaped = {
        key: decision[key]
        for key in (
            "kind",
            "label",
            "description",
            "crew_id",
            "contract_id",
            "deal_id",
            "rumor_id",
            "source_type",
            "source_id",
            "pressure",
            "leak_vector",
            "candidate_player_id",
            "missing_need",
            "action",
            "action_ids",
            "credible_count",
            "assessment_counts",
        )
        if key in decision
    }
    if shaped.get("kind") == "rumor_escalation":
        shaped.pop("rumor_id", None)
        shaped.pop("source_type", None)
        shaped.pop("source_id", None)
        shaped.pop("pressure", None)
        shaped["credible_count"] = int(shaped.get("credible_count", 0))
        shaped["assessment_counts"] = {
            str(assessment): int(count)
            for assessment, count in sorted(
                dict(shaped.get("assessment_counts", {})).items()
            )
        }
    return shaped


def _render_pending_decisions(decisions: list[dict[str, Any]]) -> list[str]:
    lines = ["Pending decisions:"]
    if decisions:
        lines.extend(
            f"- {decision['label']}: {decision['description']}"
            for decision in decisions
        )
    else:
        lines.append("- none")
    return lines


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


def _shape_rumor(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: payload[key]
        for key in (
            "rumor_id",
            "source_type",
            "source_id",
            "conversation_scope",
            "contract_id",
            "suspected_crew_ids",
            "summary",
            "pressure",
            "leak_vector",
        )
        if key in payload
    }


def _shape_rumor_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: payload[key]
        for key in (
            "rumor_id",
            "action_id",
            "crew_id",
            "source_type",
            "source_id",
            "contract_id",
            "pressure",
            "leak_vector",
            "mode",
            "outcome",
            "heat_delta",
            "summary",
        )
        if key in payload
    }


def _shape_rumor_verification(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: payload[key]
        for key in (
            "schema_version",
            "rumor_id",
            "action_id",
            "crew_id",
            "source_type",
            "source_id",
            "contract_id",
            "pressure",
            "leak_vector",
            "assessment",
            "confidence",
            "summary",
        )
        if key in payload
    }


def _shape_rumor_escalation(payload: dict[str, Any]) -> dict[str, Any]:
    shaped = {
        key: payload[key]
        for key in (
            "schema_version",
            "action_id",
            "crew_id",
            "mode",
            "credible_count",
            "assessment_counts",
            "summary",
        )
        if key in payload
    }
    if "credible_count" in shaped:
        shaped["credible_count"] = int(shaped["credible_count"])
    if "assessment_counts" in shaped:
        shaped["assessment_counts"] = {
            str(assessment): int(count)
            for assessment, count in sorted(
                dict(shaped["assessment_counts"]).items()
            )
        }
    return shaped


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
            for key in (
                "action_id",
                "crew_id",
                "intent",
                "responds_to_rumor_id",
                "rumor_response_mode",
                "responds_to_rumor_escalation",
                "rumor_escalation_mode",
            )
            if key in action
        }
    elif event_type == "contract.phase.resolved":
        reveal = payload.get("reveal", {})
        shaped["phase_result"] = _shape_phase_result(reveal)
    elif event_type == "contract.rumor.leaked":
        shaped["rumor"] = _shape_rumor(payload)
    elif event_type == "contract.rumor.responded":
        shaped["rumor_response"] = _shape_rumor_response(payload)
    elif event_type == "contract.rumor.verified":
        shaped["rumor_verification"] = _shape_rumor_verification(payload)
    elif event_type == "contract.rumor.escalated":
        shaped["rumor_escalation"] = _shape_rumor_escalation(payload)
    elif event_type == "crew.legacy.delta.recorded":
        shaped["legacy_delta"] = _shape_legacy_delta(payload)
    return shaped


def _shape_mutation_result(operation: str, result: dict[str, Any]) -> dict[str, Any]:
    if operation == "submit_action":
        return {
            key: result[key]
            for key in (
                "action_id",
                "crew_id",
                "intent",
                "responds_to_rumor_id",
                "rumor_response_mode",
                "responds_to_rumor_escalation",
                "rumor_escalation_mode",
            )
            if key in result
        }
    if operation in {
        "dossier_contribute",
        "dossier_cite_artifact",
        "vote_packet_lead",
    }:
        return _shape_dossier(result)
    if operation in {"propose_deal", "accept_deal"}:
        return _shape_deal(result)
    if operation == "transfer_artifact":
        return _shape_artifact(result)
    return {}


def _mutation_result_label(operation: str, result: dict[str, Any]) -> str:
    for key in ("action_id", "deal_id", "artifact_id", "dossier_id"):
        if key in result:
            return str(result[key])
    return "accepted"


def build_mutation_result_packet(
    *,
    operation: str,
    confirmed: bool,
    preview_fields: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> RenderPacket:
    if not confirmed:
        preview = dict(preview_fields or {})
        lines = [
            f"Preview: {operation}",
            "No server mutation was submitted.",
        ]
        for key, value in preview.items():
            lines.append(f"- {key}: {value}")
        return RenderPacket(
            surface="mutation",
            player_markdown="\n".join(lines),
            agent_context={
                "operation": operation,
                "mutation": False,
                "confirmed": False,
                "preview": preview,
            },
        )

    shaped_result = _shape_mutation_result(operation, result or {})
    lines = [
        f"Submitted: {operation}",
        f"Result: {_mutation_result_label(operation, shaped_result)}",
    ]
    if operation in {"propose_deal", "accept_deal"} and shaped_result:
        lines.extend(_render_deal_lines(shaped_result))
    return RenderPacket(
        surface="mutation",
        player_markdown="\n".join(lines),
        agent_context={
            "operation": operation,
            "mutation": True,
            "confirmed": True,
            "result": shaped_result,
        },
        suggested_prompts=[
            "Review recent activity",
            "Open crew board",
        ],
    )


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
    if event_type == "contract.rumor.leaked":
        return f"{sequence} rumor: {payload.get('summary')}"
    if event_type == "contract.rumor.responded":
        return (
            f"{sequence} rumor response {payload.get('action_id')}: "
            f"{payload.get('summary')}"
        )
    if event_type == "contract.rumor.verified":
        return (
            f"{sequence} rumor verification {payload.get('action_id')}: "
            f"{payload.get('summary')}"
        )
    if event_type == "contract.rumor.escalated":
        return (
            f"{sequence} rumor escalation {payload.get('action_id')}: "
            f"{payload.get('summary')}"
        )
    if event_type == "crew.legacy.delta.recorded":
        return f"{sequence} legacy {payload.get('crew_id')}: {payload.get('summary')}"
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


def _conversation_key_and_id(payload: dict[str, Any]) -> tuple[str, str] | None:
    sender_crew_id = payload.get("sender_crew_id")
    recipient_crew_id = payload.get("recipient_crew_id")
    if sender_crew_id and recipient_crew_id:
        participants = sorted((sender_crew_id, recipient_crew_id))
        conversation_id = f"{participants[0]}:{participants[1]}"
        return f"crew_pair:{conversation_id}", conversation_id
    if sender_crew_id:
        return f"crew:{sender_crew_id}", sender_crew_id
    message_id = payload.get("message_id")
    if message_id:
        return f"direct:{message_id}", message_id
    return None


def _shape_conversation_summary(
    *,
    conversation_id: str,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    sorted_events = sorted(events, key=lambda event: int(event["sequence"]))
    last_event = sorted_events[-1]
    last_payload = last_event.get("payload", {})
    participant_ids = sorted(
        {
            value
            for event in sorted_events
            for value in (
                event.get("payload", {}).get("sender_player_id"),
                event.get("payload", {}).get("recipient_player_id"),
                event.get("payload", {}).get("sender_crew_id"),
                event.get("payload", {}).get("recipient_crew_id"),
            )
            if value
        }
    )
    artifact_reference_count = sum(
        len(event.get("payload", {}).get("artifact_ids", []))
        for event in sorted_events
    )
    return {
        "conversation_id": conversation_id,
        "message_count": len(sorted_events),
        "first_sequence": int(sorted_events[0]["sequence"]),
        "last_sequence": int(last_event["sequence"]),
        "last_sender_player_id": last_payload.get("sender_player_id"),
        "last_body": last_payload.get("body"),
        "participant_ids": participant_ids,
        "artifact_reference_count": artifact_reference_count,
    }


def build_conversations_packet(
    events: list[dict[str, Any]],
    *,
    recent_limit: int = 10,
) -> RenderPacket:
    grouped: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for event in sorted(events, key=lambda candidate: int(candidate["sequence"])):
        if event.get("type") != "chat.message.created":
            continue
        conversation = _conversation_key_and_id(event.get("payload", {}))
        if conversation is None:
            continue
        key, conversation_id = conversation
        grouped.setdefault(key, (conversation_id, []))[1].append(event)
    summaries = [
        _shape_conversation_summary(conversation_id=conversation_id, events=messages)
        for conversation_id, messages in grouped.values()
    ]
    summaries.sort(key=lambda summary: int(summary["last_sequence"]), reverse=True)
    recent = summaries[:recent_limit]
    lines = ["Visible conversations:"]
    if recent:
        for summary in recent:
            lines.append(
                f"- {summary['conversation_id']} ({summary['message_count']} messages, "
                f"last {summary['last_sequence']}): "
                f"{summary.get('last_sender_player_id')}: {summary.get('last_body')}"
            )
    else:
        lines.append("- none")
    return RenderPacket(
        surface="conversations",
        player_markdown="\n".join(lines),
        agent_context={
            "conversation_count": len(summaries),
            "conversations": recent,
            "mutation": False,
        },
        suggested_prompts=[
            "Open a conversation thread",
            "Review recent activity",
            "Review inbox",
        ],
        actions=[
            RenderAction(label="Review recent activity", intent="render_activity"),
            RenderAction(label="Review inbox", intent="render_inbox"),
        ],
    )


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


def build_activity_delta_packet(
    events: list[dict[str, Any]],
    *,
    checkpoint_sequence: int,
    crew_id: str | None = None,
    recent_limit: int = 10,
) -> RenderPacket:
    visible_events = sorted(events, key=lambda event: int(event["sequence"]))
    if crew_id is None:
        activity_events = visible_events
        lines = [f"What changed since sequence {checkpoint_sequence}:"]
    else:
        activity_events = [
            event
            for event in visible_events
            if event_matches_crew_activity(event, crew_id)
        ]
        lines = [
            f"Crew changes since sequence {checkpoint_sequence}: {crew_id}",
        ]
    recent_events = activity_events[-recent_limit:]
    if recent_events:
        lines.extend(f"- {_render_activity_event(event)}" for event in recent_events)
    else:
        lines.append("- no new visible activity")
    max_sequence = max(
        (int(event["sequence"]) for event in visible_events),
        default=checkpoint_sequence,
    )
    agent_context = {
        "checkpoint_sequence": checkpoint_sequence,
        "max_sequence": max_sequence,
        "synced_event_count": len(visible_events),
        "activity_event_count": len(activity_events),
        "event_type_counts": dict(Counter(event["type"] for event in activity_events)),
        "recent_events": [
            _shape_activity_event(event)
            for event in recent_events
        ],
        "mutation": False,
    }
    if crew_id is not None:
        agent_context["crew_id"] = crew_id
        agent_context["skipped_visible_event_count"] = (
            len(visible_events) - len(activity_events)
        )
    return RenderPacket(
        surface="activity_delta",
        player_markdown="\n".join(lines),
        agent_context=agent_context,
        suggested_prompts=[
            "Open inbox",
            "Open crew board",
            "Review recent activity",
        ],
        actions=[
            RenderAction(label="Open inbox", intent="render_inbox"),
            RenderAction(label="Open crew board", intent="render_crew_board"),
            RenderAction(label="Review recent activity", intent="render_activity"),
        ],
    )


def _payload_mentions_crew(payload: dict[str, Any], crew_id: str) -> bool:
    for key in (
        "crew_id",
        "sender_crew_id",
        "recipient_crew_id",
        "proposer_crew_id",
        "candidate_crew_id",
    ):
        if payload.get(key) == crew_id:
            return True
    for key in (
        "crew_ids",
        "recipient_crew_ids",
        "suspected_crew_ids",
        "affected_crew_ids",
    ):
        if crew_id in payload.get(key, []):
            return True
    for key in ("action", "deal", "dossier", "surface", "result"):
        value = payload.get(key)
        if isinstance(value, dict) and _payload_mentions_crew(value, crew_id):
            return True
    reveal = payload.get("reveal", {})
    if isinstance(reveal, dict):
        for standing in reveal.get("standings", []):
            if isinstance(standing, dict) and standing.get("crew_id") == crew_id:
                return True
    return False


def _event_visibility_mentions_crew(event: dict[str, Any], crew_id: str) -> bool:
    for principal in event.get("visibility", {}).get("principals", []):
        if principal.get("kind") == "crew" and principal.get("id") == crew_id:
            return True
        if principal.get("kind") == "crew" and principal.get("crew_id") == crew_id:
            return True
    return False


def event_matches_crew_activity(event: dict[str, Any], crew_id: str) -> bool:
    return _payload_mentions_crew(
        event.get("payload", {}),
        crew_id,
    ) or _event_visibility_mentions_crew(event, crew_id)


def build_crew_activity_packet(
    events: list[dict[str, Any]],
    *,
    crew_id: str,
    recent_limit: int = 10,
) -> RenderPacket:
    visible_events = sorted(events, key=lambda event: int(event["sequence"]))
    crew_events = [
        event
        for event in visible_events
        if event_matches_crew_activity(event, crew_id)
    ]
    recent_events = crew_events[-recent_limit:]
    lines = [f"Crew activity: {crew_id}"]
    if recent_events:
        lines.extend(f"- {_render_activity_event(event)}" for event in recent_events)
    else:
        lines.append("- no visible crew activity")
    return RenderPacket(
        surface="crew_activity",
        player_markdown="\n".join(lines),
        agent_context={
            "crew_id": crew_id,
            "visible_event_count": len(visible_events),
            "crew_event_count": len(crew_events),
            "skipped_visible_event_count": len(visible_events) - len(crew_events),
            "event_type_counts": dict(Counter(event["type"] for event in crew_events)),
            "recent_events": [
                _shape_activity_event(event)
                for event in recent_events
            ],
            "mutation": False,
        },
        suggested_prompts=[
            "Open crew board",
            "Review inbox",
            "Open a conversation thread",
        ],
        actions=[
            RenderAction(label="Open crew board", intent="render_crew_board"),
            RenderAction(label="Review inbox", intent="render_inbox"),
            RenderAction(label="Review recent activity", intent="render_activity"),
        ],
    )


def build_what_now_packet(payload: dict[str, Any]) -> RenderPacket:
    profile = payload.get("profile", {})
    inbox = dict(payload.get("inbox", {}))
    if profile.get("display_name"):
        inbox.setdefault("display_name", profile["display_name"])
    deals_payload = payload.get("deals", {})
    events = payload.get("events", [])
    active_crew_id = payload.get("active_crew_id")

    display_name = (
        inbox.get("display_name")
        or profile.get("display_name")
        or inbox["player_id"]
    )
    active_contracts = inbox.get("active_contracts", [])
    pending_decisions = [
        _shape_pending_decision(decision)
        for decision in inbox.get("pending_decisions", [])
    ]
    fragments = inbox.get("incoming_proof_fragments", [])
    visible_artifacts = inbox.get("visible_artifacts", [])
    visible_deals = deals_payload.get("deals", [])
    open_deals = [
        deal
        for deal in visible_deals
        if deal.get("status") not in {"fulfilled", "declined", "canceled", "expired"}
    ]
    visible_events = sorted(events, key=lambda event: int(event["sequence"]))
    recent_events = visible_events[-3:]

    lines = [
        f"What Now: {display_name}",
        f"Player ID: {inbox['player_id']}",
    ]
    if active_crew_id:
        lines.append(f"Active crew: {active_crew_id}")
    lines.extend(
        [
            "",
            "Snapshot:",
            f"- active contracts: {len(active_contracts)}",
            f"- pending decisions: {len(pending_decisions)}",
            f"- incoming fragments: {len(fragments)}",
            f"- visible artifacts: {len(visible_artifacts)}",
            f"- open deals: {len(open_deals)}",
            f"- recent visible events: {len(recent_events)}",
            "",
            "Priority:",
        ]
    )
    if pending_decisions:
        for decision in pending_decisions[:3]:
            lines.append(
                f"- decision: {decision['label']} - {decision['description']}"
            )
    elif fragments:
        for fragment in fragments[:3]:
            lines.append(
                f"- fragment: {fragment['fragment_id']} - {fragment['summary']}"
            )
    elif open_deals:
        for deal in open_deals[:3]:
            lines.append(
                f"- deal: {deal['deal_id']} {deal['status']} from "
                f"{deal['proposer_crew_id']} to {deal['recipient_crew_id']}"
            )
    elif active_contracts:
        for contract in active_contracts[:3]:
            lines.append(
                f"- contract: {contract['title']} ({contract['phase']['name']})"
            )
    else:
        lines.append("- no urgent visible items")

    lines.append("")
    lines.append("Recent activity:")
    if recent_events:
        lines.extend(f"- {_render_activity_event(event)}" for event in recent_events)
    else:
        lines.append("- none")

    agent_context = {
        "player": {
            "player_id": inbox["player_id"],
            "display_name": display_name,
            "active_crew_id": active_crew_id,
            "crews": [
                _shape_profile_crew(crew)
                for crew in profile.get("crews", [])
            ],
        },
        "summary_counts": {
            "active_contracts": len(active_contracts),
            "pending_decisions": len(pending_decisions),
            "incoming_fragments": len(fragments),
            "visible_artifacts": len(visible_artifacts),
            "visible_deals": len(visible_deals),
            "open_deals": len(open_deals),
            "visible_events": len(visible_events),
        },
        "active_contracts": [
            _shape_contract(contract)
            for contract in active_contracts
        ],
        "pending_decisions": pending_decisions,
        "incoming_proof_fragments": [
            _shape_proof_fragment(fragment)
            for fragment in fragments
        ],
        "visible_artifacts": [
            _shape_artifact(artifact)
            for artifact in visible_artifacts
        ],
        "open_deals": [_shape_deal(deal) for deal in open_deals],
        "recent_events": [
            _shape_activity_event(event)
            for event in recent_events
        ],
        "mutation": False,
    }
    return RenderPacket(
        surface="what_now",
        player_markdown="\n".join(lines),
        agent_context=agent_context,
        suggested_prompts=[
            "Open inbox",
            "Review crew board",
            "Review visible deals",
            "Review recent activity",
        ],
        actions=[
            RenderAction(label="Open inbox", intent="render_inbox"),
            RenderAction(label="Review crew board", intent="render_crew_board"),
            RenderAction(label="Review visible deals", intent="render_deals"),
            RenderAction(label="Review recent activity", intent="render_activity"),
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


def _render_modifiers(modifiers: list[dict[str, Any]]) -> str:
    if not modifiers:
        return "none"
    return "; ".join(
        f"{modifier['label']} +{modifier['value']}"
        for modifier in modifiers
    )


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


def _shape_profile_crew(crew: dict[str, Any]) -> dict[str, Any]:
    shaped = {
        key: crew[key]
        for key in (
            "crew_id",
            "name",
            "member_count",
            "ready_for_full_contracts",
        )
        if key in crew
    }
    if "legacy" in crew:
        shaped["legacy"] = _shape_crew_legacy(crew["legacy"])
    return shaped


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


def _shape_packet_lead_vote(vote: dict[str, Any]) -> dict[str, Any]:
    return {
        key: vote[key]
        for key in ("sequence", "voter_player_id", "candidate_player_id")
        if key in vote
    }


def _shape_packet_lead_replacement(replacement: dict[str, Any]) -> dict[str, Any]:
    return {
        key: replacement[key]
        for key in (
            "sequence",
            "previous_packet_lead_player_id",
            "packet_lead_player_id",
        )
        if key in replacement
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
    packet_lead_votes = [
        _shape_packet_lead_vote(vote)
        for vote in dossier.get("packet_lead_votes", [])
    ]
    if packet_lead_votes:
        shaped["packet_lead_votes"] = packet_lead_votes
    packet_lead_replacements = [
        _shape_packet_lead_replacement(replacement)
        for replacement in dossier.get("packet_lead_replacements", [])
    ]
    if packet_lead_replacements:
        shaped["packet_lead_replacements"] = packet_lead_replacements
    return shaped


def _render_packet_lead_history_lines(dossier: dict[str, Any]) -> list[str]:
    if (
        not dossier.get("packet_lead_votes")
        and not dossier.get("packet_lead_replacements")
    ):
        return []
    lines = ["Packet Lead votes:"]
    votes = dossier.get("packet_lead_votes", [])
    if votes:
        lines.extend(
            (
                f"- {vote.get('sequence')} {vote.get('voter_player_id')} -> "
                f"{vote.get('candidate_player_id')}"
            )
            for vote in votes
        )
    else:
        lines.append("- none")
    lines.append("Packet Lead replacements:")
    replacements = dossier.get("packet_lead_replacements", [])
    if replacements:
        lines.extend(
            (
                f"- {replacement.get('sequence')} "
                f"{replacement.get('previous_packet_lead_player_id')} -> "
                f"{replacement.get('packet_lead_player_id')}"
            )
            for replacement in replacements
        )
    else:
        lines.append("- none")
    return lines


def build_dossier_packet(dossier: dict[str, Any]) -> RenderPacket:
    shaped = _shape_dossier(dossier)
    lines = [
        f"Proof Dossier: {shaped['crew_id']}",
        f"Dossier ID: {shaped['dossier_id']}",
        f"Packet Lead: {shaped['packet_lead_player_id']}",
        f"Claim: {shaped.get('claim') or 'not set'}",
        "",
        *_render_packet_lead_history_lines(shaped),
        "",
        "Evidence:",
    ]
    evidence_ids = shaped.get("evidence_ids", [])
    if evidence_ids:
        lines.extend(f"- {evidence_id}" for evidence_id in evidence_ids)
    else:
        lines.append("- none")

    lines.append("Artifact citations:")
    artifact_citations = shaped.get("artifact_citations", [])
    if artifact_citations:
        for citation in artifact_citations:
            lines.append(f"- {citation['artifact_id']}: {citation['claim']}")
    else:
        lines.append("- none")

    lines.append("Contributions:")
    contributions = shaped.get("member_contributions", [])
    if contributions:
        for contribution in contributions:
            lines.append(f"- {contribution['player_id']}: {contribution['note']}")
    else:
        lines.append("- none")

    if shaped.get("reasoning"):
        lines.extend(["", f"Reasoning: {shaped['reasoning']}"])

    weaknesses = [str(weakness) for weakness in shaped.get("weaknesses", []) if str(weakness)]
    if weaknesses:
        lines.extend(["", "Weaknesses:"])
        lines.extend(f"- {weakness}" for weakness in weaknesses)

    concerns = [
        str(concern)
        for concern in shaped.get("provenance_concerns", [])
        if str(concern)
    ]
    if concerns:
        lines.extend(["", "Provenance concerns:"])
        lines.extend(f"- {concern}" for concern in concerns)

    return RenderPacket(
        surface="dossier",
        player_markdown="\n".join(lines),
        agent_context={
            "dossier": shaped,
            "evidence_count": len(evidence_ids),
            "artifact_citation_count": len(artifact_citations),
            "contribution_count": len(contributions),
            "mutation": False,
        },
        suggested_prompts=[
            "Contribute to dossier",
            "Cite an artifact",
            "Open crew board",
        ],
        actions=[
            RenderAction(label="Contribute to dossier", intent="dossier_contribute"),
            RenderAction(label="Cite an artifact", intent="dossier_cite_artifact"),
            RenderAction(label="Open crew board", intent="render_crew_board"),
        ],
    )


def build_contract_board_packet(board: dict[str, Any]) -> RenderPacket:
    lines: list[str] = []
    campaign = board.get("campaign") or {}
    if campaign:
        lines.append(str(campaign["title"]))
        lines.append("")
    contracts = board.get("contracts", [])
    if not contracts:
        lines.append("No visible contracts.")
    arc_progress = _shape_arc_progress(contracts)
    if arc_progress:
        lines.append("Campaign arcs:")
        for progress in arc_progress:
            lines.append(
                f"- {progress['title']}: {progress['total_contracts']} contracts; "
                f"resolved {progress['resolved_count']}; "
                f"active {progress['active_count']}; "
                f"locked {progress['locked_count']}; "
                f"archived {progress['archived_count']}"
            )
            lines.extend(
                (
                    f"  - Chapter {chapter['chapter']}: {chapter['title']} "
                    f"({chapter['status']})"
                )
                for chapter in progress["chapters"]
            )
        lines.append("")
    for contract in contracts:
        phase = contract["phase"]
        lines.append(f"## {contract['title']}")
        if contract.get("arc"):
            arc = _shape_arc(contract["arc"])
            lines.append(f"Arc: {arc['title']}, chapter {arc['chapter']}")
            lines.append(str(arc["public_summary"]))
            if "previous_contract_id" in arc:
                lines.append(f"Previous: {arc['previous_contract_id']}")
            if "next_contract_hint" in arc:
                lines.append(f"Next hint: {arc['next_contract_hint']}")
        if "lifecycle_status" in contract:
            lines.append(f"Status: {contract['lifecycle_status']}")
        if "unlock_status" in contract:
            unlock_status = _shape_unlock_status(contract["unlock_status"])
            lines.append(f"Unlock: {unlock_status['state']}")
            for requirement in unlock_status["requirements"]:
                lines.append(
                    f"- {requirement.get('label', requirement.get('metric', 'Requirement'))}: "
                    f"{requirement.get('current', 0)}/{requirement.get('minimum', 0)}"
                )
        lines.append(f"Phase: {phase['name']} ({phase.get('remaining_hours', 0)}h remaining)")
        lines.append(f"Crew Heat: {contract.get('crew_heat', 0)}")
        lines.append("Proof dossier needs:")
        lines.extend(f"- {need}" for need in contract.get("proof_dossier_needs", []))
        if "phase_result" in contract:
            lines.append("Phase result:")
            for state in contract["phase_result"].get("contract_state", []):
                lines.append(f"- {state}")
            for standing in contract["phase_result"].get("standings", []):
                lines.append(
                    f"- {standing['crew_id']}: {standing['standing']} ({standing['score']})"
                )
                reasoning_lines = _render_standing_reasoning_lines(standing)
                if reasoning_lines:
                    lines.append("  Reasoning:")
                    lines.extend(f"  - {line}" for line in reasoning_lines)
        lines.append("")
    visible_artifacts = board.get("visible_artifacts", [])
    if visible_artifacts:
        lines.append("Visible artifacts:")
        lines.extend(
            f"- {artifact['artifact_id']}: {artifact['title']}"
            for artifact in visible_artifacts[:5]
        )
        lines.append("")
    agent_context = {
        "campaign": _shape_campaign(campaign),
        "contracts": [_shape_contract(contract) for contract in contracts],
        "visible_artifacts": [
            _shape_artifact(artifact)
            for artifact in board.get("visible_artifacts", [])
        ],
        "visible_contract_count": len(contracts),
    }
    if arc_progress:
        agent_context["arc_progress"] = arc_progress
    return RenderPacket(
        surface="contract_board",
        player_markdown="\n".join(lines).strip(),
        agent_context=agent_context,
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


def build_profile_packet(profile: dict[str, Any]) -> RenderPacket:
    crews = [_shape_profile_crew(crew) for crew in profile.get("crews", [])]
    lines = [
        f"Profile: {profile['display_name']}",
        f"Player ID: {profile['player_id']}",
        f"Crew Count: {profile.get('crew_count', len(crews))}",
        "",
        "Crews:",
    ]
    if crews:
        for crew in crews:
            readiness = (
                "full-contract-ready"
                if crew.get("ready_for_full_contracts")
                else "starter-ready"
            )
            member_label = "member" if crew.get("member_count") == 1 else "members"
            lines.append(
                f"- {crew['name']} ({crew['crew_id']}): "
                f"{crew['member_count']} {member_label}; {readiness}"
            )
            legacy = crew.get("legacy")
            if legacy:
                lines.append(
                    "  Legacy: "
                    f"reputation {legacy['reputation']}; "
                    f"heat {legacy['heat']}; "
                    f"favors {legacy['favors']}; "
                    f"debts {legacy['debts']}"
                )
                if legacy["completed_contracts"]:
                    lines.extend(
                        [
                            f"  - {contract['title']}: "
                            f"{contract['standing']} ({contract['score']})"
                            for contract in legacy["completed_contracts"]
                        ]
                    )
    else:
        lines.append("- none")

    return RenderPacket(
        surface="profile",
        player_markdown="\n".join(lines),
        agent_context={
            "player_id": profile["player_id"],
            "display_name": profile["display_name"],
            "crew_count": profile.get("crew_count", len(crews)),
            "crews": crews,
        },
        suggested_prompts=[
            "Open inbox",
            "Review crew board",
            "Review recent activity",
        ],
        actions=[
            RenderAction(label="Open inbox", intent="render_inbox"),
            RenderAction(label="Review crew board", intent="render_crew_board"),
            RenderAction(label="Review recent activity", intent="render_activity"),
        ],
    )


def _render_standing_reasoning_lines(standing: dict[str, Any]) -> list[str]:
    rendered: list[str] = []
    for source_key, label in (
        ("strengths", "strengths"),
        ("weaknesses", "weaknesses"),
        ("penalties", "penalties"),
        ("revealed_clues", "clues"),
    ):
        values = [str(value) for value in standing.get(source_key, []) if str(value)]
        if values:
            rendered.append(f"{label}: {', '.join(values)}")
    return rendered


def build_crew_board_packet(board: dict[str, Any]) -> RenderPacket:
    crew = board["crew"]
    dossier = board["dossier"]
    active_contracts = board.get("active_contracts", [])
    legacy = _shape_crew_legacy(board.get("legacy", {}))
    pending_decisions = [
        _shape_pending_decision(decision)
        for decision in board.get("pending_decisions", [])
    ]
    lines = [
        f"Crew Board: {crew['name']}",
        f"Crew ID: {crew['crew_id']}",
        f"Member Count: {crew['member_count']}",
        f"Packet Lead: {dossier['packet_lead_player_id']}",
        *_render_packet_lead_history_lines(_shape_dossier(dossier)),
        "",
        *_render_pending_decisions(pending_decisions),
        "",
        "Legacy:",
        f"Reputation: {legacy['reputation']}",
        f"Heat: {legacy['heat']}",
        f"Favors: {legacy['favors']}",
        f"Debts: {legacy['debts']}",
        "Deal conduct:",
        f"Conduct score: {legacy['deal_conduct']['score']}",
        f"Reliability: {legacy['deal_conduct']['reliability']}",
        (
            f"Fulfilled: {legacy['deal_conduct']['fulfilled_count']}; "
            f"Canceled: {legacy['deal_conduct']['canceled_count']}; "
            f"Declined: {legacy['deal_conduct']['declined_count']}; "
            f"Open: {legacy['deal_conduct']['open_count']}"
        ),
        "Counterintelligence:",
        (
            f"Investigations: {legacy['counterintelligence']['investigations_started']}; "
            f"Containments: {legacy['counterintelligence']['containments_started']}; "
            "Heat from containment: "
            f"{legacy['counterintelligence']['heat_from_containment']}"
        ),
        "Rumor memory:",
        f"Verified rumors: {legacy['rumor_memory']['verified_count']}",
        f"Assessments: {_render_assessment_counts(legacy['rumor_memory']['assessment_counts'])}",
        "Rumor escalation:",
        (
            f"Contain: {legacy['rumor_escalation']['contain_count']}; "
            f"Exploit: {legacy['rumor_escalation']['exploit_count']}; "
            f"Integrate: {legacy['rumor_escalation']['integrate_count']}; "
            "Credible signal weight: "
            f"{legacy['rumor_escalation']['credible_count_total']}"
        ),
        "Recent rumor checks:",
        *(
            [_render_rumor_memory_item(item) for item in legacy["rumor_memory"]["recent"]]
            if legacy["rumor_memory"]["recent"]
            else ["- none"]
        ),
        "Scars:",
        *(
            [f"- {scar}" for scar in legacy["scars"]]
            if legacy["scars"]
            else ["- none"]
        ),
        "Completed contracts:",
    ]
    if legacy["completed_contracts"]:
        lines.extend(
            f"- {contract['title']}: {contract['standing']} ({contract['score']})"
            for contract in legacy["completed_contracts"]
        )
    else:
        lines.append("- none")
    lines.append("Future modifiers:")
    if legacy["future_opportunities"]:
        lines.extend(
            f"- {opportunity['title']}: {_render_modifiers(opportunity['modifiers'])}"
            for opportunity in legacy["future_opportunities"]
        )
    else:
        lines.append("- none")
    lines.extend([
        "",
        "Active Contracts:",
    ])
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
    lines.extend(["", "Rumors:"])
    rumors = [_shape_rumor(rumor) for rumor in board.get("rumors", [])]
    if rumors:
        lines.extend(
            f"- {rumor['rumor_id']}: {rumor['summary']}"
            for rumor in rumors
        )
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
            "legacy": legacy,
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
            "rumors": rumors,
            "pending_decisions": pending_decisions,
            "urgent_items": pending_decisions,
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


def _render_assessment_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return "; ".join(
        f"{assessment} {count}"
        for assessment, count in counts.items()
    )


def _render_rumor_memory_item(item: dict[str, Any]) -> str:
    confidence = item.get("confidence") or "unknown"
    return (
        f"- {item.get('rumor_id', '')}: {item.get('assessment', '')} "
        f"({confidence}) - {item.get('summary', '')}"
    )


def build_inbox_packet(inbox: dict[str, Any]) -> RenderPacket:
    display_name = inbox.get("display_name") or inbox["player_id"]
    lines = [f"Inbox: {display_name}"]
    pending_decisions = [
        _shape_pending_decision(decision)
        for decision in inbox.get("pending_decisions", [])
    ]
    lines.append("")
    lines.extend(_render_pending_decisions(pending_decisions))
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
    urgent_items = pending_decisions + urgent_items
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
        "pending_decisions": pending_decisions,
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
