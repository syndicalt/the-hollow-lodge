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


def test_render_deals_mcp_call_returns_text_and_structured_packet(monkeypatch):
    packet = RenderPacket(
        surface="deals",
        player_markdown="Visible deals:\n- deal_000001 proposed",
        agent_context={"deals": [{"deal_id": "deal_000001"}]},
    )

    class StubSession:
        def render_deals(self) -> RenderPacket:
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(mcp_server.mcp.call_tool("render_deals", {}))

    assert isinstance(result, CallToolResult)
    assert result.content[0].text == packet.player_markdown
    assert result.structuredContent["surface"] == "deals"
    assert result.structuredContent["agent_context"]["deals"][0]["deal_id"] == "deal_000001"


def test_render_activity_mcp_call_returns_text_and_structured_packet(monkeypatch):
    packet = RenderPacket(
        surface="activity",
        player_markdown="Recent visible activity:\n- 1 chat player_0002: The bell moved.",
        agent_context={"visible_event_count": 1, "recent_events": []},
    )

    class StubSession:
        def render_activity(self) -> RenderPacket:
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(mcp_server.mcp.call_tool("render_activity", {}))

    assert isinstance(result, CallToolResult)
    assert result.content[0].text == packet.player_markdown
    assert result.structuredContent["surface"] == "activity"
    assert result.structuredContent["agent_context"]["visible_event_count"] == 1


def test_render_thread_mcp_call_returns_matching_thread_packet(monkeypatch):
    packet = RenderPacket(
        surface="thread",
        player_markdown="Conversation: crew_a:crew_b\n- 1 player_0002: No public claims.",
        agent_context={"conversation_id": "crew_a:crew_b", "messages": []},
    )

    class StubSession:
        def render_thread(self, conversation_id: str) -> RenderPacket:
            assert conversation_id == "crew_a:crew_b"
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(
        mcp_server.mcp.call_tool(
            "render_thread",
            {"conversation_id": "crew_a:crew_b"},
        )
    )

    assert result.content[0].text == packet.player_markdown
    assert result.structuredContent["surface"] == "thread"
    assert result.structuredContent["agent_context"]["conversation_id"] == "crew_a:crew_b"


def test_preview_deal_acceptance_mcp_call_is_read_only(monkeypatch):
    packet = RenderPacket(
        surface="deal_preview",
        player_markdown="Acceptance preview: deal_000001\nThis preview does not accept the deal.",
        agent_context={"deal": {"deal_id": "deal_000001"}},
    )

    class StubSession:
        def preview_deal_acceptance(self, deal_id: str) -> RenderPacket:
            assert deal_id == "deal_000001"
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(
        mcp_server.mcp.call_tool(
            "preview_deal_acceptance",
            {"deal_id": "deal_000001"},
        )
    )

    assert result.content[0].text == packet.player_markdown
    assert result.structuredContent["surface"] == "deal_preview"


def test_submit_action_mcp_call_passes_confirmation_to_session(monkeypatch):
    packet = RenderPacket(
        surface="mutation",
        player_markdown="Preview: submit_action\nNo server mutation was submitted.",
        agent_context={"operation": "submit_action", "mutation": False},
    )

    class StubSession:
        def submit_action(
            self,
            *,
            intent: str,
            confirm: bool,
            crew_id: str | None = None,
        ) -> RenderPacket:
            assert intent == "Inspect the ledger."
            assert confirm is False
            assert crew_id is None
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(
        mcp_server.mcp.call_tool(
            "submit_action",
            {"intent": "Inspect the ledger.", "confirm": False},
        )
    )

    assert result.content[0].text == packet.player_markdown
    assert result.structuredContent["agent_context"]["mutation"] is False


def test_dossier_contribute_mcp_call_passes_note_evidence_and_confirmation(monkeypatch):
    packet = RenderPacket(
        surface="mutation",
        player_markdown="Preview: dossier_contribute\nNo server mutation was submitted.",
        agent_context={"operation": "dossier_contribute", "mutation": False},
    )

    class StubSession:
        def dossier_contribute(
            self,
            *,
            note: str,
            evidence_ids: list[str],
            confirm: bool,
            crew_id: str | None = None,
        ) -> RenderPacket:
            assert note == "The ledger hand changes after the chapel seal."
            assert evidence_ids == ["fragment_1", "artifact_ledger_rubric"]
            assert confirm is False
            assert crew_id == "crew_0001"
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(
        mcp_server.mcp.call_tool(
            "dossier_contribute",
            {
                "note": "The ledger hand changes after the chapel seal.",
                "evidence_ids": ["fragment_1", "artifact_ledger_rubric"],
                "confirm": False,
                "crew_id": "crew_0001",
            },
        )
    )

    assert result.content[0].text == packet.player_markdown
    assert result.structuredContent["agent_context"]["mutation"] is False


def test_public_mcp_tools_do_not_expose_local_path_overrides():
    tools = {tool.name: tool for tool in asyncio.run(mcp_server.mcp.list_tools())}

    for tool_name in (
        "render_inbox",
        "render_contract_board",
        "render_crew_board",
        "render_activity",
        "render_thread",
        "render_deals",
        "preview_deal_acceptance",
        "submit_action",
        "dossier_contribute",
        "dossier_cite_artifact",
        "propose_deal",
        "accept_deal",
        "transfer_artifact",
        "vote_packet_lead",
    ):
        properties = tools[tool_name].inputSchema["properties"]
        assert "config_path" not in properties
        assert "local_log_path" not in properties

    assert "send_message" not in tools


def test_mutating_mcp_tools_require_confirm_argument():
    tools = {tool.name: tool for tool in asyncio.run(mcp_server.mcp.list_tools())}

    for tool_name in (
        "submit_action",
        "dossier_contribute",
        "dossier_cite_artifact",
        "propose_deal",
        "accept_deal",
        "transfer_artifact",
        "vote_packet_lead",
    ):
        schema = tools[tool_name].inputSchema
        assert schema["properties"]["confirm"]["type"] == "boolean"
        assert "confirm" in schema["required"]

    assert "note" in tools["dossier_contribute"].inputSchema["required"]
    assert "evidence_ids" in tools["dossier_contribute"].inputSchema["required"]
