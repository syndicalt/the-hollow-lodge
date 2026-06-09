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


def test_render_what_now_mcp_call_returns_text_and_structured_packet(monkeypatch):
    packet = RenderPacket(
        surface="what_now",
        player_markdown="What Now: Ada\nSnapshot:\n- active contracts: 1",
        agent_context={"summary_counts": {"active_contracts": 1}, "mutation": False},
        suggested_prompts=["Open inbox"],
    )

    class StubSession:
        def render_what_now(self) -> RenderPacket:
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(mcp_server.mcp.call_tool("render_what_now", {}))

    assert isinstance(result, CallToolResult)
    assert result.content[0].text == packet.player_markdown
    assert result.structuredContent["surface"] == "what_now"
    assert result.structuredContent["agent_context"]["mutation"] is False
    assert result.structuredContent["suggested_prompts"] == ["Open inbox"]


def test_render_profile_mcp_call_returns_text_and_structured_packet(monkeypatch):
    packet = RenderPacket(
        surface="profile",
        player_markdown="Profile: Ada\nPlayer ID: player_0001",
        agent_context={"player_id": "player_0001", "crew_count": 1},
        suggested_prompts=["Open inbox"],
    )

    class StubSession:
        def render_profile(self) -> RenderPacket:
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(mcp_server.mcp.call_tool("render_profile", {}))

    assert isinstance(result, CallToolResult)
    assert result.content[0].text == packet.player_markdown
    assert result.structuredContent["surface"] == "profile"
    assert result.structuredContent["agent_context"]["player_id"] == "player_0001"
    assert result.structuredContent["suggested_prompts"] == ["Open inbox"]


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


def test_render_dossier_mcp_call_returns_text_and_structured_packet(monkeypatch):
    packet = RenderPacket(
        surface="dossier",
        player_markdown="Proof Dossier: crew_0001\nClaim: The finger is false.",
        agent_context={
            "dossier": {"crew_id": "crew_0001"},
            "artifact_citation_count": 1,
            "mutation": False,
        },
    )

    class StubSession:
        def render_dossier(self, crew_id: str | None = None) -> RenderPacket:
            assert crew_id == "crew_0001"
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(
        mcp_server.mcp.call_tool("render_dossier", {"crew_id": "crew_0001"})
    )

    assert isinstance(result, CallToolResult)
    assert result.content[0].text == packet.player_markdown
    assert result.structuredContent["surface"] == "dossier"
    assert result.structuredContent["agent_context"]["dossier"]["crew_id"] == "crew_0001"
    assert result.structuredContent["agent_context"]["mutation"] is False


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


def test_render_activity_delta_mcp_call_returns_text_and_structured_packet(monkeypatch):
    packet = RenderPacket(
        surface="activity_delta",
        player_markdown="What changed since sequence 5:\n- 6 chat player_0002: New.",
        agent_context={
            "checkpoint_sequence": 5,
            "synced_event_count": 1,
            "mutation": False,
        },
    )

    class StubSession:
        def render_activity_delta(self) -> RenderPacket:
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(mcp_server.mcp.call_tool("render_activity_delta", {}))

    assert isinstance(result, CallToolResult)
    assert result.content[0].text == packet.player_markdown
    assert result.structuredContent["surface"] == "activity_delta"
    assert result.structuredContent["agent_context"]["checkpoint_sequence"] == 5
    assert result.structuredContent["agent_context"]["mutation"] is False


def test_render_crew_activity_mcp_call_returns_text_and_structured_packet(monkeypatch):
    packet = RenderPacket(
        surface="crew_activity",
        player_markdown="Crew activity: crew_0001\n- 1 chat player_0002: The bell moved.",
        agent_context={"crew_id": "crew_0001", "crew_event_count": 1},
    )

    class StubSession:
        def render_crew_activity(self, crew_id: str | None = None) -> RenderPacket:
            assert crew_id == "crew_0001"
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(
        mcp_server.mcp.call_tool(
            "render_crew_activity",
            {"crew_id": "crew_0001"},
        )
    )

    assert isinstance(result, CallToolResult)
    assert result.content[0].text == packet.player_markdown
    assert result.structuredContent["surface"] == "crew_activity"
    assert result.structuredContent["agent_context"]["crew_id"] == "crew_0001"


def test_render_crew_activity_delta_mcp_call_returns_text_and_structured_packet(
    monkeypatch,
):
    packet = RenderPacket(
        surface="activity_delta",
        player_markdown="Crew changes since sequence 5: crew_0001\n- 6 chat player_0002: New.",
        agent_context={
            "crew_id": "crew_0001",
            "checkpoint_sequence": 5,
            "activity_event_count": 1,
            "mutation": False,
        },
    )

    class StubSession:
        def render_crew_activity_delta(self, crew_id: str | None = None) -> RenderPacket:
            assert crew_id == "crew_0001"
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(
        mcp_server.mcp.call_tool(
            "render_crew_activity_delta",
            {"crew_id": "crew_0001"},
        )
    )

    assert isinstance(result, CallToolResult)
    assert result.content[0].text == packet.player_markdown
    assert result.structuredContent["surface"] == "activity_delta"
    assert result.structuredContent["agent_context"]["crew_id"] == "crew_0001"
    assert result.structuredContent["agent_context"]["mutation"] is False


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


def test_render_conversations_mcp_call_returns_text_and_structured_packet(monkeypatch):
    packet = RenderPacket(
        surface="conversations",
        player_markdown="Visible conversations:\n- crew_a:crew_b (2 messages, last 4): player_2: Agreed.",
        agent_context={
            "conversation_count": 1,
            "conversations": [{"conversation_id": "crew_a:crew_b"}],
            "mutation": False,
        },
    )

    class StubSession:
        def render_conversations(self) -> RenderPacket:
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(mcp_server.mcp.call_tool("render_conversations", {}))

    assert result.content[0].text == packet.player_markdown
    assert result.structuredContent["surface"] == "conversations"
    assert result.structuredContent["agent_context"]["conversation_count"] == 1
    assert result.structuredContent["agent_context"]["mutation"] is False


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
            rumor_id: str | None = None,
            rumor_response_mode: str | None = None,
            responds_to_rumor_escalation: bool = False,
            rumor_escalation_mode: str | None = None,
        ) -> RenderPacket:
            assert intent == "Inspect the ledger."
            assert confirm is False
            assert crew_id is None
            assert rumor_id == "rumor_msg_000001"
            assert rumor_response_mode == "contain"
            assert responds_to_rumor_escalation is True
            assert rumor_escalation_mode == "exploit"
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(
        mcp_server.mcp.call_tool(
            "submit_action",
            {
                "intent": "Inspect the ledger.",
                "confirm": False,
                "rumor_id": "rumor_msg_000001",
                "rumor_response_mode": "contain",
                "responds_to_rumor_escalation": True,
                "rumor_escalation_mode": "exploit",
            },
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


def test_phase_lock_mcp_call_passes_confirmation_to_session(monkeypatch):
    packet = RenderPacket(
        surface="mutation",
        player_markdown="Preview: phase_lock\nNo server mutation was submitted.",
        agent_context={"operation": "phase_lock", "mutation": False},
    )

    class StubSession:
        def phase_lock(
            self,
            *,
            contract_id: str,
            hours_elapsed: int,
            confirm: bool,
        ) -> RenderPacket:
            assert contract_id == "contract_false_finger"
            assert hours_elapsed == 6
            assert confirm is False
            return packet

    monkeypatch.setattr(mcp_server, "_session", lambda: StubSession())

    result = asyncio.run(
        mcp_server.mcp.call_tool(
            "phase_lock",
            {
                "contract_id": "contract_false_finger",
                "hours_elapsed": 6,
                "confirm": False,
            },
        )
    )

    assert result.content[0].text == packet.player_markdown
    assert result.structuredContent["agent_context"]["mutation"] is False


def test_public_mcp_tools_do_not_expose_local_path_overrides():
    tools = {tool.name: tool for tool in asyncio.run(mcp_server.mcp.list_tools())}

    for tool_name in (
        "render_inbox",
        "render_what_now",
        "render_profile",
        "render_contract_board",
        "render_crew_board",
        "render_dossier",
        "render_activity",
        "render_activity_delta",
        "render_crew_activity",
        "render_crew_activity_delta",
        "render_conversations",
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
        "phase_lock",
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
        "phase_lock",
    ):
        schema = tools[tool_name].inputSchema
        assert schema["properties"]["confirm"]["type"] == "boolean"
        assert "confirm" in schema["required"]

    assert "note" in tools["dossier_contribute"].inputSchema["required"]
    assert "evidence_ids" in tools["dossier_contribute"].inputSchema["required"]
