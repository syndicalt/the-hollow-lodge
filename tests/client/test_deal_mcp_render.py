from hollow_lodge.client.render_packets import (
    build_deal_acceptance_preview_packet,
    build_deals_packet,
)


def deal_row(status: str = "proposed") -> dict:
    return {
        "deal_id": "deal_000001",
        "contract_id": "contract_false_finger",
        "proposer_crew_id": "crew_0001",
        "recipient_crew_id": "crew_0002",
        "status": status,
        "offered_artifact_ids": ["artifact_ledger_rubric"],
        "requested_artifact_ids": ["artifact_chapel_debt_mark"],
        "soft_terms": ["Do not cite our crew as source until Auction Lock."],
        "expires_phase": "Auction Preview",
        "proposer_received_artifact_ids": [],
        "recipient_received_artifact_ids": [],
    }


def test_deals_packet_renders_visible_deals_for_codex():
    packet = build_deals_packet({"deals": [deal_row()]})

    assert packet.surface == "deals"
    assert "Visible deals:" in packet.player_markdown
    assert (
        "- deal_000001 proposed: crew_0001 offers artifact_ledger_rubric "
        "for artifact_chapel_debt_mark"
    ) in packet.player_markdown
    assert "Soft term: Do not cite our crew as source until Auction Lock." in packet.player_markdown
    assert packet.agent_context["deals"][0]["deal_id"] == "deal_000001"
    assert "Preview deal acceptance" in packet.suggested_prompts


def test_deal_acceptance_preview_clarifies_consequences_without_strategy():
    packet = build_deal_acceptance_preview_packet(
        {
            "deal": deal_row(),
            "viewer_crew_ids": ["crew_0002"],
        }
    )

    assert packet.surface == "deal_preview"
    assert "Acceptance preview: deal_000001" in packet.player_markdown
    assert "Your crew gives: artifact_chapel_debt_mark" in packet.player_markdown
    assert "Your crew receives: artifact_ledger_rubric" in packet.player_markdown
    assert "Soft terms are recorded but not enforced by the server." in packet.player_markdown
    assert "This preview does not accept the deal." in packet.player_markdown
    assert packet.agent_context["deal"]["deal_id"] == "deal_000001"
    assert packet.agent_context["viewer_side"] == "recipient"
