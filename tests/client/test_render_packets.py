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
