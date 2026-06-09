from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from hollow_lodge.client.paths import DEFAULT_CONFIG_PATH, DEFAULT_LOCAL_LOG_PATH
from hollow_lodge.client.codex_session import CodexGameSession
from hollow_lodge.client.render_packets import RenderPacket


mcp = FastMCP(
    "the-hollow-lodge",
    instructions=(
        "Render The Hollow Lodge game state for Codex. Show player_markdown to the "
        "player. Use agent_context for reasoning. Clarify consequences and translate "
        "intent; do not choose player strategy by default."
    ),
)


def packet_response(packet: RenderPacket) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=packet.player_markdown)],
        structuredContent=packet.model_dump(mode="json"),
    )


def _session(
    *,
    config_path: str | None = None,
    local_log_path: str | None = None,
) -> CodexGameSession:
    return CodexGameSession(
        config_path=Path(config_path) if config_path else DEFAULT_CONFIG_PATH,
        local_log_path=Path(local_log_path) if local_log_path else DEFAULT_LOCAL_LOG_PATH,
    )


@mcp.tool()
def render_inbox() -> CallToolResult:
    return packet_response(_session().render_inbox())


@mcp.tool()
def render_what_now() -> CallToolResult:
    return packet_response(_session().render_what_now())


@mcp.tool()
def render_profile() -> CallToolResult:
    return packet_response(_session().render_profile())


@mcp.tool()
def render_contract_board() -> CallToolResult:
    return packet_response(_session().render_contract_board())


@mcp.tool()
def render_crew_board(
    crew_id: str | None = None,
) -> CallToolResult:
    return packet_response(
        _session().render_crew_board(crew_id=crew_id)
    )


@mcp.tool()
def render_dossier(
    crew_id: str | None = None,
) -> CallToolResult:
    return packet_response(
        _session().render_dossier(crew_id=crew_id)
    )


@mcp.tool()
def render_artifacts() -> CallToolResult:
    return packet_response(_session().render_artifacts())


@mcp.tool()
def render_artifact(artifact_id: str) -> CallToolResult:
    return packet_response(_session().render_artifact(artifact_id))


@mcp.tool()
def render_deals() -> CallToolResult:
    return packet_response(_session().render_deals())


@mcp.tool()
def render_activity() -> CallToolResult:
    return packet_response(_session().render_activity())


@mcp.tool()
def render_crew_activity(
    crew_id: str | None = None,
) -> CallToolResult:
    return packet_response(_session().render_crew_activity(crew_id=crew_id))


@mcp.tool()
def render_thread(conversation_id: str) -> CallToolResult:
    return packet_response(_session().render_thread(conversation_id))


@mcp.tool()
def preview_deal_acceptance(deal_id: str) -> CallToolResult:
    return packet_response(_session().preview_deal_acceptance(deal_id))


@mcp.tool()
def submit_action(
    intent: str,
    confirm: bool,
    crew_id: str | None = None,
    rumor_id: str | None = None,
    rumor_response_mode: str | None = None,
    responds_to_rumor_escalation: bool = False,
    rumor_escalation_mode: str | None = None,
) -> CallToolResult:
    return packet_response(
        _session().submit_action(
            intent=intent,
            confirm=confirm,
            crew_id=crew_id,
            rumor_id=rumor_id,
            rumor_response_mode=rumor_response_mode,
            responds_to_rumor_escalation=responds_to_rumor_escalation,
            rumor_escalation_mode=rumor_escalation_mode,
        )
    )


@mcp.tool()
def dossier_contribute(
    note: str,
    evidence_ids: list[str],
    confirm: bool,
    crew_id: str | None = None,
) -> CallToolResult:
    return packet_response(
        _session().dossier_contribute(
            note=note,
            evidence_ids=evidence_ids,
            confirm=confirm,
            crew_id=crew_id,
        )
    )


@mcp.tool()
def dossier_cite_artifact(
    artifact_id: str,
    claim: str,
    quote: str,
    confirm: bool,
    crew_id: str | None = None,
) -> CallToolResult:
    return packet_response(
        _session().dossier_cite_artifact(
            artifact_id=artifact_id,
            claim=claim,
            quote=quote,
            confirm=confirm,
            crew_id=crew_id,
        )
    )


@mcp.tool()
def propose_deal(
    recipient_crew_id: str,
    offered_artifact_ids: list[str],
    requested_artifact_ids: list[str],
    confirm: bool,
    proposer_crew_id: str | None = None,
    contract_id: str = "contract_false_finger",
    soft_terms: list[str] | None = None,
    expires_phase: str | None = None,
) -> CallToolResult:
    return packet_response(
        _session().propose_deal(
            recipient_crew_id=recipient_crew_id,
            offered_artifact_ids=offered_artifact_ids,
            requested_artifact_ids=requested_artifact_ids,
            confirm=confirm,
            proposer_crew_id=proposer_crew_id,
            contract_id=contract_id,
            soft_terms=soft_terms,
            expires_phase=expires_phase,
        )
    )


@mcp.tool()
def accept_deal(deal_id: str, confirm: bool) -> CallToolResult:
    return packet_response(_session().accept_deal(deal_id=deal_id, confirm=confirm))


@mcp.tool()
def transfer_artifact(
    artifact_id: str,
    recipient_player_id: str,
    confirm: bool,
) -> CallToolResult:
    return packet_response(
        _session().transfer_artifact(
            artifact_id=artifact_id,
            recipient_player_id=recipient_player_id,
            confirm=confirm,
        )
    )


@mcp.tool()
def vote_packet_lead(
    player_id: str,
    confirm: bool,
    crew_id: str | None = None,
) -> CallToolResult:
    return packet_response(
        _session().vote_packet_lead(
            player_id=player_id,
            confirm=confirm,
            crew_id=crew_id,
        )
    )


def main() -> None:
    mcp.run()
