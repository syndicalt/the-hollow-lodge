from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

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


def packet_response(packet: RenderPacket) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": packet.player_markdown}],
        "structuredContent": packet.model_dump(mode="json"),
    }


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
def render_inbox(config_path: str | None = None, local_log_path: str | None = None) -> dict[str, Any]:
    return packet_response(
        _session(config_path=config_path, local_log_path=local_log_path).render_inbox()
    )


@mcp.tool()
def render_contract_board(
    config_path: str | None = None,
    local_log_path: str | None = None,
) -> dict[str, Any]:
    return packet_response(
        _session(config_path=config_path, local_log_path=local_log_path).render_contract_board()
    )


@mcp.tool()
def render_crew_board(
    crew_id: str | None = None,
    config_path: str | None = None,
    local_log_path: str | None = None,
) -> dict[str, Any]:
    return packet_response(
        _session(config_path=config_path, local_log_path=local_log_path).render_crew_board(
            crew_id=crew_id
        )
    )


def main() -> None:
    mcp.run()
