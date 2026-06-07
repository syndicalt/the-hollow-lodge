from hollow_lodge.client.render import render_contract_board


def test_contract_board_renders_resolved_score_reveal_without_hidden_truth():
    rendered = render_contract_board(
        {
            "campaign": {"title": "Saints & Ledgers"},
            "contracts": [
                {
                    "title": "The Saint's False Finger",
                    "phase": {"name": "Auction Preview", "remaining_hours": 0, "status": "resolved"},
                    "crew_heat": 1,
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
        }
    )

    assert "Phase result:" in rendered
    assert "crew_0001: Strong lead (82)" in rendered
    assert "saint-bone forgery" not in rendered
