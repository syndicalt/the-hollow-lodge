from __future__ import annotations

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
    ]
    player_markdown: str = Field(min_length=1)
    agent_context: dict[str, Any]
    suggested_prompts: list[str] = Field(default_factory=list)
    actions: list[RenderAction] = Field(default_factory=list)


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
    return RenderPacket(
        surface="contract_board",
        player_markdown="\n".join(lines).strip(),
        agent_context={
            "campaign": campaign or None,
            "contracts": contracts,
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


def build_inbox_packet(inbox: dict[str, Any]) -> RenderPacket:
    lines = [f"Inbox: {inbox['player_id']}"]
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
    urgent_items = [
        {"kind": "proof_fragment", "fragment_id": fragment["fragment_id"]}
        for fragment in fragments
    ]
    return RenderPacket(
        surface="inbox",
        player_markdown="\n".join(lines),
        agent_context={
            "player_id": inbox["player_id"],
            "active_contracts": active_contracts,
            "incoming_proof_fragments": fragments,
            "urgent_items": urgent_items,
        },
        suggested_prompts=[
            "Open the contract board",
            "Review crew board",
        ],
    )
