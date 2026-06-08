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
def render_artifacts() -> CallToolResult:
    return packet_response(_session().render_artifacts())


@mcp.tool()
def render_artifact(artifact_id: str) -> CallToolResult:
    return packet_response(_session().render_artifact(artifact_id))


@mcp.tool()
def render_deals() -> CallToolResult:
    return packet_response(_session().render_deals())


@mcp.tool()
def preview_deal_acceptance(deal_id: str) -> CallToolResult:
    return packet_response(_session().preview_deal_acceptance(deal_id))


def main() -> None:
    mcp.run()
