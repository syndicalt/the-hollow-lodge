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

    assert response["content"][0]["type"] == "text"
    assert response["content"][0]["text"] == "Inbox: player_0001"
    assert response["structuredContent"]["surface"] == "inbox"
    assert response["structuredContent"]["agent_context"]["player_id"] == "player_0001"
