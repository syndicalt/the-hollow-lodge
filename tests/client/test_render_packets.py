from hollow_lodge.client import render_packets
from hollow_lodge.client.render_packets import (
    build_contract_board_packet,
    build_crew_board_packet,
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
    "visible_artifacts": [
        {
            "artifact_id": "artifact_lot_card",
            "title": "Auction Lot Card",
            "kind": "lot_card",
            "public_summary": "A vellum card attributes the reliquary finger.",
            "hidden_note": "server-only",
        }
    ],
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
    assert "visible artifacts:" in packet.player_markdown
    assert "- artifact_lot_card: Auction Lot Card" in packet.player_markdown
    assert packet.agent_context["player_id"] == "player_0001"
    assert packet.agent_context["visible_artifacts"] == [
        {
            "artifact_id": "artifact_lot_card",
            "title": "Auction Lot Card",
            "kind": "lot_card",
            "public_summary": "A vellum card attributes the reliquary finger.",
        }
    ]
    assert packet.agent_context["urgent_items"] == []
    assert packet.suggested_prompts == [
        "Open the contract board",
        "Review crew board",
    ]


def test_inbox_packet_uses_display_name_without_losing_player_id():
    packet = build_inbox_packet({**INBOX, "display_name": "corelumen"})

    assert "Inbox: corelumen" in packet.player_markdown
    assert packet.agent_context["display_name"] == "corelumen"
    assert packet.agent_context["player_id"] == "player_0001"


def test_crew_board_packet_shows_packet_lead_and_dossier_status():
    packet = build_crew_board_packet(
        {
            "player_id": "player_0001",
            "crew": {
                "crew_id": "crew_0001",
                "name": "The Gilt Knives",
                "member_ids": ["player_0001", "player_0002"],
                "member_count": 2,
                "ready_for_full_contracts": False,
                "readiness_warning": "Crews should have 3-5 players for full contracts.",
                "join_code": "hidden",
            },
            "active_contracts": [
                {
                    **BOARD["contracts"][0],
                    "hidden_truth": "saint-bone forgery",
                }
            ],
            "dossier": {
                "dossier_id": "dossier_crew_0001",
                "crew_id": "crew_0001",
                "packet_lead_player_id": "player_0001",
                "claim": "",
                "evidence_ids": [],
                "artifact_citations": [
                    {
                        "player_id": "player_0001",
                        "artifact_id": "artifact_ledger_rubric",
                        "claim": "The ledger contradicts the public lot card.",
                        "quote": "The last hand is redder and later than the binding.",
                        "hidden_note": "server-only",
                    }
                ],
                "member_contributions": [],
                "server_notes": "hidden",
            },
            "visible_artifacts": [
                {
                    "artifact_id": "artifact_lot_card",
                    "title": "Auction Lot Card",
                    "kind": "lot_card",
                    "public_summary": "A vellum card attributes the reliquary finger.",
                    "hidden_note": "server-only",
                }
            ],
        }
    )

    assert packet.surface == "crew_board"
    assert "Crew Board: The Gilt Knives" in packet.player_markdown
    assert "Packet Lead: player_0001" in packet.player_markdown
    assert "Artifact citations:" in packet.player_markdown
    assert "- artifact_ledger_rubric: The ledger contradicts the public lot card." in packet.player_markdown
    assert "Artifacts:" in packet.player_markdown
    assert "- artifact_lot_card: Auction Lot Card" in packet.player_markdown
    assert "hidden" not in packet.player_markdown
    assert "hidden_truth" not in packet.player_markdown
    assert "server_notes" not in packet.player_markdown
    assert packet.agent_context["crew"]["crew_id"] == "crew_0001"
    assert "join_code" not in packet.agent_context["crew"]
    assert "hidden_truth" not in packet.agent_context["active_contracts"][0]
    assert "server_notes" not in packet.agent_context["dossier"]
    assert packet.agent_context["dossier"]["artifact_citations"] == [
        {
            "player_id": "player_0001",
            "artifact_id": "artifact_ledger_rubric",
            "claim": "The ledger contradicts the public lot card.",
            "quote": "The last hand is redder and later than the binding.",
        }
    ]
    assert packet.agent_context["visible_artifacts"] == [
        {
            "artifact_id": "artifact_lot_card",
            "title": "Auction Lot Card",
            "kind": "lot_card",
            "public_summary": "A vellum card attributes the reliquary finger.",
        }
    ]


def test_contract_board_agent_context_omits_hidden_upstream_fields():
    board = {
        "campaign": {
            "campaign_id": "campaign_saints_ledgers",
            "title": "Saints & Ledgers",
            "hidden_truth": "auction house is compromised",
        },
        "contracts": [
            {
                "contract_id": "contract_false_finger",
                "title": "The Saint's False Finger",
                "phase": {
                    "name": "Auction Preview",
                    "remaining_hours": 6,
                    "hidden_timer_seed": "server-only",
                },
                "crew_heat": 0,
                "proof_dossier_needs": ["provenance chain"],
                "phase_result": {
                    "standings": [
                        {
                            "crew_id": "crew_0001",
                            "standing": "Strong lead",
                            "score": 82,
                            "hidden_tiebreaker": 17,
                        }
                    ],
                    "hidden_truth": "saint-bone forgery",
                },
                "hidden_truth": "saint-bone forgery",
                "server_notes": "do not render",
            }
        ],
        "server_notes": "internal campaign notes",
    }

    packet = build_contract_board_packet(board)

    assert packet.agent_context == {
        "campaign": {
            "campaign_id": "campaign_saints_ledgers",
            "title": "Saints & Ledgers",
        },
        "contracts": [
            {
                "contract_id": "contract_false_finger",
                "title": "The Saint's False Finger",
                "phase": {"name": "Auction Preview", "remaining_hours": 6},
                "crew_heat": 0,
                "proof_dossier_needs": ["provenance chain"],
                "phase_result": {
                    "standings": [
                        {
                            "crew_id": "crew_0001",
                            "standing": "Strong lead",
                            "score": 82,
                        }
                    ]
                },
            }
        ],
        "visible_artifacts": [],
        "visible_contract_count": 1,
    }


def test_inbox_agent_context_omits_hidden_upstream_fields_and_serializes_actions():
    inbox = {
        "player_id": "player_0001",
        "active_contracts": [
            {
                "contract_id": "contract_false_finger",
                "title": "The Saint's False Finger",
                "phase": {
                    "name": "Auction Preview",
                    "remaining_hours": 6,
                    "hidden_timer_seed": "server-only",
                },
                "crew_heat": 0,
                "proof_dossier_needs": ["provenance chain"],
                "hidden_truth": "saint-bone forgery",
            }
        ],
        "incoming_proof_fragments": [
            {
                "fragment_id": "fragment_0001",
                "summary": "A chipped reliquary seal.",
                "hidden_source": "server-only witness",
            }
        ],
        "server_notes": "internal inbox notes",
    }

    packet = build_inbox_packet(inbox)

    assert packet.model_dump() == {
        "surface": "inbox",
        "player_markdown": (
            "Inbox: player_0001\n\n"
            "Active contracts:\n"
            "- The Saint's False Finger (Auction Preview)\n\n"
            "incoming proof fragments:\n"
            "- fragment_0001: A chipped reliquary seal.\n\n"
            "Incoming deals:\n"
            "- none"
        ),
        "agent_context": {
            "player_id": "player_0001",
            "active_contracts": [
                {
                    "contract_id": "contract_false_finger",
                    "title": "The Saint's False Finger",
                    "phase": {"name": "Auction Preview", "remaining_hours": 6},
                    "crew_heat": 0,
                    "proof_dossier_needs": ["provenance chain"],
                }
            ],
            "incoming_proof_fragments": [
                {
                    "fragment_id": "fragment_0001",
                    "summary": "A chipped reliquary seal.",
                }
            ],
            "visible_artifacts": [],
            "deals": [],
            "urgent_items": [{"kind": "proof_fragment", "fragment_id": "fragment_0001"}],
        },
        "suggested_prompts": [
            "Open the contract board",
            "Review crew board",
        ],
        "actions": [],
    }


def test_activity_summary_packet_shapes_visible_events_without_server_only_fields():
    assert hasattr(render_packets, "build_activity_summary_packet")
    packet = render_packets.build_activity_summary_packet(
        [
            {
                "origin": "server",
                "event_id": "evt_1",
                "sequence": 1,
                "type": "chat.message.created",
                "event_hash": "server-only-hash",
                "visibility": {"principals": [{"kind": "server"}]},
                "payload": {
                    "message_id": "msg_1",
                    "sender_player_id": "player_0002",
                    "sender_crew_id": "crew_a",
                    "recipient_crew_id": "crew_b",
                    "body": "No public claims until lock.",
                    "artifact_ids": ["artifact_1"],
                    "server_only_note": "hidden",
                },
            },
            {
                "origin": "server",
                "event_id": "evt_2",
                "sequence": 2,
                "type": "proof.fragment.transferred",
                "payload": {
                    "surface": {
                        "fragment_id": "fragment_1",
                        "content_summary": "A chipped reliquary seal.",
                        "hidden_source": "server-only witness",
                    },
                    "server_notes": "hidden",
                },
            },
        ]
    )

    assert packet.surface == "activity"
    assert "Recent visible activity:" in packet.player_markdown
    assert "1 chat player_0002: No public claims until lock." in packet.player_markdown
    assert "2 proof fragment fragment_1: A chipped reliquary seal." in packet.player_markdown
    assert "server-only" not in packet.player_markdown
    assert "hidden" not in packet.player_markdown
    assert packet.agent_context == {
        "visible_event_count": 2,
        "event_type_counts": {
            "chat.message.created": 1,
            "proof.fragment.transferred": 1,
        },
        "recent_events": [
            {
                "sequence": 1,
                "type": "chat.message.created",
                "message": {
                    "message_id": "msg_1",
                    "sender_player_id": "player_0002",
                    "sender_crew_id": "crew_a",
                    "recipient_crew_id": "crew_b",
                    "body": "No public claims until lock.",
                    "artifact_ids": ["artifact_1"],
                },
            },
            {
                "sequence": 2,
                "type": "proof.fragment.transferred",
                "proof_fragment": {
                    "fragment_id": "fragment_1",
                    "content_summary": "A chipped reliquary seal.",
                },
            },
        ],
    }
    assert packet.suggested_prompts == [
        "Open a conversation thread",
        "Review inbox",
        "Open the contract board",
    ]


def test_thread_packet_matches_cli_conversation_logic_and_omits_hidden_fields():
    events = [
        {
            "sequence": 1,
            "type": "chat.message.created",
            "payload": {
                "message_id": "msg_1",
                "sender_player_id": "player_0002",
                "sender_crew_id": "crew_a",
                "recipient_crew_id": "crew_b",
                "body": "No public claims until lock.",
                "server_only_note": "hidden",
            },
        },
        {
            "sequence": 2,
            "type": "chat.message.created",
            "payload": {
                "message_id": "msg_2",
                "sender_player_id": "player_0003",
                "sender_crew_id": "crew_b",
                "recipient_crew_id": "crew_a",
                "body": "Agreed.",
            },
        },
        {
            "sequence": 3,
            "type": "chat.message.created",
            "payload": {
                "message_id": "msg_3",
                "sender_player_id": "player_0004",
                "sender_crew_id": "crew_c",
                "recipient_crew_id": "crew_d",
                "body": "Not this thread.",
            },
        },
    ]

    assert hasattr(render_packets, "build_thread_packet")
    packet = render_packets.build_thread_packet(events, conversation_id="crew_a:crew_b")

    assert packet.surface == "thread"
    assert "Conversation: crew_a:crew_b" in packet.player_markdown
    assert "1 player_0002: No public claims until lock." in packet.player_markdown
    assert "2 player_0003: Agreed." in packet.player_markdown
    assert "Not this thread" not in packet.player_markdown
    assert "hidden" not in packet.player_markdown
    assert packet.agent_context == {
        "conversation_id": "crew_a:crew_b",
        "message_count": 2,
        "messages": [
            {
                "sequence": 1,
                "message_id": "msg_1",
                "sender_player_id": "player_0002",
                "sender_crew_id": "crew_a",
                "recipient_crew_id": "crew_b",
                "body": "No public claims until lock.",
                "artifact_ids": [],
            },
            {
                "sequence": 2,
                "message_id": "msg_2",
                "sender_player_id": "player_0003",
                "sender_crew_id": "crew_b",
                "recipient_crew_id": "crew_a",
                "body": "Agreed.",
                "artifact_ids": [],
            },
        ],
    }
    assert packet.suggested_prompts == [
        "Reply using the CLI",
        "Review recent activity",
    ]
