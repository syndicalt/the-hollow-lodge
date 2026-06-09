from hollow_lodge.domain.scoring import AuctionPreviewScoreInput, score_auction_preview


def test_clean_provenance_contradiction_beats_uncorroborated_occult_clue():
    clean = score_auction_preview(
        AuctionPreviewScoreInput(
            crew_id="crew_any",
            evidence_ids=["fragment_starter_ledger"],
            exposed_assets=["fragment_starter_ledger"],
            compiled_actions=[
                {
                    "approach": "provenance_research",
                    "scope": "proofwork",
                    "risk_posture": "careful",
                },
            ],
            crew_noise=1,
        )
    )
    occult = score_auction_preview(
        AuctionPreviewScoreInput(
            crew_id="crew_other",
            evidence_ids=[],
            exposed_assets=["asset_door_omen"],
            compiled_actions=[
                {
                    "approach": "occult_analysis",
                    "scope": "proofwork",
                    "risk_posture": "balanced",
                },
            ],
            crew_noise=0,
        )
    )

    assert clean.total > occult.total
    assert "clean provenance contradiction" in clean.strengths
    assert "occult clue may unlock alternate lane" in occult.strengths
    assert "minor heat trace" in clean.penalties


def test_scoring_uses_evidence_and_actions_not_crew_names():
    base = AuctionPreviewScoreInput(
        crew_id="crew_gilt_knives",
        evidence_ids=["fragment_starter_ledger"],
        exposed_assets=["fragment_starter_ledger"],
        compiled_actions=[
            {
                "approach": "provenance_research",
                "scope": "proofwork",
                "risk_posture": "careful",
            },
        ],
        crew_noise=0,
    )
    renamed = base.model_copy(update={"crew_id": "crew_moth_choir"})

    assert score_auction_preview(base).total == score_auction_preview(renamed).total


def test_provenance_keywords_without_supporting_evidence_do_not_get_clean_clue():
    unsupported = score_auction_preview(
        AuctionPreviewScoreInput(
            crew_id="crew_any",
            evidence_ids=[],
            exposed_assets=[],
            compiled_actions=[
                {
                    "approach": "provenance_research",
                    "scope": "proofwork",
                    "risk_posture": "careful",
                },
            ],
            crew_noise=0,
        )
    )

    assert "clean provenance contradiction" not in unsupported.strengths
    assert unsupported.standing == "Weak"


def test_score_input_has_no_raw_prose_fields():
    forbidden = {
        "claim",
        "reasoning",
        "weaknesses",
        "provenance_concerns",
        "action_intents",
    }

    assert forbidden.isdisjoint(AuctionPreviewScoreInput.model_fields)
