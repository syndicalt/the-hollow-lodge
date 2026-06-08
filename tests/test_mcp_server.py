import asyncio

from mcp.types import CallToolResult

from hollow_lodge import mcp_server
from hollow_lodge.mcp_server import packet_response
from hollow_lodge.client.render_packets import RenderPacket


def test_packet_response_returns_markdown_and_structured_content():
    packet = RenderPacket(
        surface="inbox",
        player_markdown="Inbox: player_0001",
        agent_context={"player_id": "player_0001"},
        suggested_prompts=["Open the contract board"],
    )

    response = packet_response(packet)

    assert isinstance(response, CallToolResult)
    assert response.content[0].type == "text"
    assert response.content[0].text == "Inbox: player_0001"
    assert response.structuredContent["surface"] == "inbox"
    assert response.structuredContent["agent_context"]["player_id"] == "player_0001"


def test_render_inbox_mcp_call_returns_text_and_structured_packet(monkeypatch):
    packet = RenderPacket(
        surface="inbox",
        player_markdown="Inbox: player_0001",
        agent_context={"player_id": "player_0001"},
        suggested_prompts=["Open the contract board"],
    )

    class StubSession:
        def render_inbox(self) -> RenderPacket:
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(mcp_server.mcp.call_tool("render_inbox", {}))

    assert isinstance(result, CallToolResult)
    assert result.content[0].type == "text"
    assert result.content[0].text == "Inbox: player_0001"
    assert not result.content[0].text.startswith("{")
    assert result.structuredContent["surface"] == "inbox"
    assert result.structuredContent["agent_context"]["player_id"] == "player_0001"
    assert result.structuredContent["suggested_prompts"] == ["Open the contract board"]


def test_public_mcp_tools_do_not_expose_local_path_overrides():
    tools = {tool.name: tool for tool in asyncio.run(mcp_server.mcp.list_tools())}

    for tool_name in ("render_inbox", "render_contract_board", "render_crew_board"):
        properties = tools[tool_name].inputSchema["properties"]
        assert "config_path" not in properties
        assert "local_log_path" not in properties
