from hollow_lodge.client.render_packets import build_crew_board_packet, build_inbox_packet


def deal_row(status: str = "proposed") -> dict:
    return {
        "deal_id": "deal_000001",
        "contract_id": "contract_false_finger",
        "proposer_crew_id": "crew_0001",
        "recipient_crew_id": "crew_0002",
        "status": status,
        "offered_artifact_ids": ["artifact_ledger_rubric"],
        "requested_artifact_ids": ["artifact_chapel_debt_mark"],
        "soft_terms": ["Do not cite us."],
        "expires_phase": "Auction Preview",
        "proposer_player_id": "player_0001",
        "accepted_by_player_id": None,
        "proposer_received_artifact_ids": [],
        "recipient_received_artifact_ids": [],
    }


def test_inbox_renders_incoming_deal():
    packet = build_inbox_packet(
        {
            "player_id": "player_0002",
            "active_contracts": [],
            "incoming_proof_fragments": [],
            "visible_artifacts": [],
            "deals": [deal_row()],
        }
    )

    assert "Incoming deals:" in packet.player_markdown
    assert "deal_000001 proposed" in packet.player_markdown
    assert packet.agent_context["deals"][0]["soft_terms"] == ["Do not cite us."]


def test_crew_board_renders_deals():
    packet = build_crew_board_packet(
        {
            "player_id": "player_0001",
            "crew": {
                "crew_id": "crew_0001",
                "name": "Gilt Knives",
                "member_ids": ["player_0001"],
                "member_count": 1,
                "ready_for_full_contracts": False,
                "readiness_warning": "Needs 3-5 players for full contracts.",
            },
            "active_contracts": [],
            "visible_artifacts": [],
            "deals": [deal_row("fulfilled")],
            "dossier": {
                "dossier_id": "dossier_crew_0001",
                "crew_id": "crew_0001",
                "packet_lead_player_id": "player_0001",
                "claim": None,
                "evidence_ids": [],
                "artifact_citations": [],
                "member_contributions": [],
            },
        }
    )

    assert "Deals:" in packet.player_markdown
    assert "deal_000001 fulfilled" in packet.player_markdown
    assert packet.agent_context["deals"][0]["status"] == "fulfilled"
