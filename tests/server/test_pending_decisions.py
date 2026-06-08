from hollow_lodge.server.pending_decisions import pending_decisions_for_player


def test_repeated_credible_rumor_memory_creates_escalation_decision():
    decisions = pending_decisions_for_player(
        player_id="player_0001",
        crew_ids=["crew_0001"],
        active_contracts=[],
        deals=[],
        crew_summaries={"crew_0001": {"member_ids": ["player_0001"]}},
        dossiers={"crew_0001": {"packet_lead_player_id": "player_0001"}},
        crew_legacies={
            "crew_0001": {
                "rumor_memory": {
                    "verified_count": 3,
                    "assessment_counts": {
                        "credible_artifact_signal": 2,
                        "inconclusive_signal": 1,
                    },
                    "recent": [
                        {
                            "rumor_id": "rumor_msg_000001",
                            "source_id": "msg_private_000001",
                            "assessment": "credible_artifact_signal",
                            "summary": "safe summary",
                        }
                    ],
                }
            }
        },
    )

    assert decisions == [
        {
            "kind": "rumor_escalation",
            "label": "Repeated credible rumor signals",
            "description": (
                "Crew crew_0001 has 2 credible rumor verifications. Decide "
                "whether to contain, exploit, or fold them into contract strategy."
            ),
            "crew_id": "crew_0001",
            "action": "review_rumor_escalation",
            "credible_count": 2,
            "assessment_counts": {
                "credible_artifact_signal": 2,
                "inconclusive_signal": 1,
            },
        }
    ]
    assert "msg_private_000001" not in str(decisions)


def test_submitted_rumor_escalation_action_clears_escalation_decision():
    base_kwargs = {
        "player_id": "player_0001",
        "crew_ids": ["crew_0001"],
        "active_contracts": [],
        "deals": [],
        "crew_summaries": {"crew_0001": {"member_ids": ["player_0001"]}},
        "dossiers": {"crew_0001": {"packet_lead_player_id": "player_0001"}},
        "crew_legacies": {
            "crew_0001": {
                "rumor_memory": {
                    "verified_count": 2,
                    "assessment_counts": {"credible_artifact_signal": 2},
                    "recent": [],
                }
            }
        },
    }

    cleared = pending_decisions_for_player(
        **base_kwargs,
        actions_by_crew={
            "crew_0001": [
                {
                    "action_id": "action_000001",
                    "status": "submitted",
                    "responds_to_rumor_escalation": True,
                }
            ]
        },
    )
    reopened = pending_decisions_for_player(
        **base_kwargs,
        actions_by_crew={
            "crew_0001": [
                {
                    "action_id": "action_000001",
                    "status": "canceled",
                    "responds_to_rumor_escalation": True,
                }
            ]
        },
    )

    assert not any(decision["kind"] == "rumor_escalation" for decision in cleared)
    assert any(decision["kind"] == "rumor_escalation" for decision in reopened)
