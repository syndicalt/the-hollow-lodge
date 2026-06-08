from hollow_lodge.client.render_packets import (
    build_contract_board_packet,
    build_inbox_packet,
)


BOARD = {
    "campaign": {"campaign_id": "campaign_saints_ledgers", "title": "Saints & Ledgers"},
    "contracts": [
        {
            "contract_id": "contract_false_finger",
            "title": "The Saint's False Finger",
            "phase": {"name": "Auction Preview", "remaining_hours": 6},
            "crew_heat": 0,
            "proof_dossier_needs": [
                "provenance chain",
                "material authenticity",
                "auction leverage",
            ],
        }
    ],
}


INBOX = {
    "player_id": "player_0001",
    "active_contracts": BOARD["contracts"],
    "incoming_proof_fragments": [],
}


def test_contract_board_packet_has_player_markdown_and_agent_context():
    packet = build_contract_board_packet(BOARD)

    assert packet.surface == "contract_board"
    assert "Saints & Ledgers" in packet.player_markdown
    assert "The Saint's False Finger" in packet.player_markdown
    assert packet.agent_context["contracts"][0]["contract_id"] == "contract_false_finger"
    assert packet.agent_context["contracts"][0]["phase"]["name"] == "Auction Preview"
    assert packet.suggested_prompts == [
        "Open the contested contract",
        "Review crew packet status",
        "Draft a contract action",
    ]


def test_inbox_packet_prioritizes_actionable_items_for_codex():
    packet = build_inbox_packet(INBOX)

    assert packet.surface == "inbox"
    assert "Inbox: player_0001" in packet.player_markdown
    assert "incoming proof fragments: none" in packet.player_markdown
    assert packet.agent_context["player_id"] == "player_0001"
    assert packet.agent_context["urgent_items"] == []
    assert packet.suggested_prompts == [
        "Open the contract board",
        "Review crew board",
    ]
