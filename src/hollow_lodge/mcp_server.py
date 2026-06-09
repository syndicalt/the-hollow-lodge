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
def render_proof_fragment(fragment_id: str) -> CallToolResult:
    return packet_response(_session().render_proof_fragment(fragment_id))


@mcp.tool()
def inspect_artifact(artifact_id: str, confirm: bool) -> CallToolResult:
    return packet_response(
        _session().inspect_artifact(
            artifact_id=artifact_id,
            confirm=confirm,
        )
    )


@mcp.tool()
def render_deals() -> CallToolResult:
    return packet_response(_session().render_deals())


@mcp.tool()
def render_activity() -> CallToolResult:
    return packet_response(_session().render_activity())


@mcp.tool()
def render_activity_delta() -> CallToolResult:
    return packet_response(_session().render_activity_delta())


@mcp.tool()
def render_crew_activity(
    crew_id: str | None = None,
) -> CallToolResult:
    return packet_response(_session().render_crew_activity(crew_id=crew_id))


@mcp.tool()
def render_crew_activity_delta(
    crew_id: str | None = None,
) -> CallToolResult:
    return packet_response(_session().render_crew_activity_delta(crew_id=crew_id))


@mcp.tool()
def render_conversations() -> CallToolResult:
    return packet_response(_session().render_conversations())


@mcp.tool()
def render_thread(conversation_id: str) -> CallToolResult:
    return packet_response(_session().render_thread(conversation_id))


@mcp.tool()
def render_backend_status() -> CallToolResult:
    return packet_response(_session().render_backend_status())


@mcp.tool()
def check_backend_readiness(
    production_postgres: bool = True,
    expected_backend: str | None = None,
    expected_event_backend: str | None = None,
    expected_operational_backend: str | None = None,
    require_production_postgres_preset: bool = False,
    require_maintenance_read_only: bool = False,
) -> CallToolResult:
    return packet_response(
        _session().check_backend_readiness(
            production_postgres=production_postgres,
            expected_backend=expected_backend,
            expected_event_backend=expected_event_backend,
            expected_operational_backend=expected_operational_backend,
            require_production_postgres_preset=require_production_postgres_preset,
            require_maintenance_read_only=require_maintenance_read_only,
        )
    )


@mcp.tool()
def send_message(
    scope: str,
    body: str,
    confirm: bool,
    recipient_player_id: str | None = None,
    crew_id: str | None = None,
    recipient_crew_id: str | None = None,
    sender_crew_id: str | None = None,
    artifact_ids: list[str] | None = None,
) -> CallToolResult:
    return packet_response(
        _session().send_message(
            scope=scope,
            body=body,
            confirm=confirm,
            recipient_player_id=recipient_player_id,
            crew_id=crew_id,
            recipient_crew_id=recipient_crew_id,
            sender_crew_id=sender_crew_id,
            artifact_ids=artifact_ids,
        )
    )


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
def edit_action(
    action_id: str,
    intent: str,
    confirm: bool,
) -> CallToolResult:
    return packet_response(
        _session().edit_action(
            action_id=action_id,
            intent=intent,
            confirm=confirm,
        )
    )


@mcp.tool()
def cancel_action(
    action_id: str,
    confirm: bool,
) -> CallToolResult:
    return packet_response(
        _session().cancel_action(
            action_id=action_id,
            confirm=confirm,
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
def dossier_update_framing(
    confirm: bool,
    crew_id: str | None = None,
    claim: str | None = None,
    evidence_ids: list[str] | None = None,
    reasoning: str | None = None,
    weaknesses: str | None = None,
    provenance_concerns: str | None = None,
) -> CallToolResult:
    return packet_response(
        _session().dossier_update_framing(
            confirm=confirm,
            crew_id=crew_id,
            claim=claim,
            evidence_ids=evidence_ids,
            reasoning=reasoning,
            weaknesses=weaknesses,
            provenance_concerns=provenance_concerns,
        )
    )


@mcp.tool()
def dossier_add_typed_claim(
    subject_id: str,
    predicate: str,
    confirm: bool,
    crew_id: str | None = None,
    object_id: str | None = None,
    value: str | None = None,
    citation_artifact_ids: list[str] | None = None,
) -> CallToolResult:
    return packet_response(
        _session().dossier_add_typed_claim(
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            value=value,
            citation_artifact_ids=citation_artifact_ids or [],
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
def decline_deal(deal_id: str, confirm: bool) -> CallToolResult:
    return packet_response(_session().decline_deal(deal_id=deal_id, confirm=confirm))


@mcp.tool()
def cancel_deal(deal_id: str, confirm: bool) -> CallToolResult:
    return packet_response(_session().cancel_deal(deal_id=deal_id, confirm=confirm))


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
def transfer_proof_fragment(
    fragment_id: str,
    recipient_player_id: str,
    confirm: bool,
) -> CallToolResult:
    return packet_response(
        _session().transfer_proof_fragment(
            fragment_id=fragment_id,
            recipient_player_id=recipient_player_id,
            confirm=confirm,
        )
    )


@mcp.tool()
def check_provenance(
    fragment_id: str,
    confirm: bool,
) -> CallToolResult:
    return packet_response(
        _session().check_provenance(
            fragment_id=fragment_id,
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


@mcp.tool()
def phase_lock(
    confirm: bool,
    contract_id: str = "contract_false_finger",
    hours_elapsed: int = 6,
) -> CallToolResult:
    return packet_response(
        _session().phase_lock(
            contract_id=contract_id,
            hours_elapsed=hours_elapsed,
            confirm=confirm,
        )
    )


def main() -> None:
    mcp.run()
