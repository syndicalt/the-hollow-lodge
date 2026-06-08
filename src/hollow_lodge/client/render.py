from __future__ import annotations

from typing import Any

from hollow_lodge.client.render_packets import build_crew_board_packet


def render_contract_board(board: dict[str, Any]) -> str:
    lines: list[str] = []
    campaign = board.get("campaign")
    if campaign:
        lines.append(campaign["title"])
    for contract in board.get("contracts", []):
        lines.append(contract["title"])
        phase = contract["phase"]
        lines.append(f"Phase: {phase['name']} ({phase['remaining_hours']}h remaining)")
        lines.append(f"Crew Heat: {contract['crew_heat']}")
        lines.append("Proof dossier needs:")
        lines.extend(f"- {need}" for need in contract.get("proof_dossier_needs", []))
        if "phase_result" in contract:
            lines.append("Phase result:")
            for state in contract["phase_result"].get("contract_state", []):
                lines.append(f"- {state}")
            for standing in contract["phase_result"].get("standings", []):
                lines.append(f"- {standing['crew_id']}: {standing['standing']} ({standing['score']})")
    return "\n".join(lines)


def render_crew_board(board: dict[str, Any]) -> str:
    return build_crew_board_packet(board).player_markdown


def render_inbox(inbox: dict[str, Any]) -> str:
    display_name = inbox.get("display_name") or inbox["player_id"]
    lines = [f"Inbox: {display_name}"]
    for contract in inbox.get("active_contracts", []):
        lines.append(contract["title"])
        lines.append(f"Phase: {contract['phase']['name']}")
    fragments = inbox.get("incoming_proof_fragments", [])
    if fragments:
        lines.append("incoming proof fragments:")
        lines.extend(f"- {fragment['fragment_id']}: {fragment['summary']}" for fragment in fragments)
    else:
        lines.append("incoming proof fragments: none")
    return "\n".join(lines)
