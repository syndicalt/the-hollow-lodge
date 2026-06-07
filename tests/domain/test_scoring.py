from hollow_lodge.domain.scoring import AuctionPreviewScoreInput, score_auction_preview


def test_clean_provenance_contradiction_beats_uncorroborated_occult_clue():
    clean = score_auction_preview(
        AuctionPreviewScoreInput(
            crew_id="crew_any",
            claim="The relic is likely false.",
            evidence_ids=["fragment_starter_ledger"],
            exposed_assets=["fragment_starter_ledger"],
            reasoning="The ledger date contradicts the chapel timestamp.",
            weaknesses="No material confirmation.",
            provenance_concerns="Copied hand, ink after binding.",
            action_intents=[
                "Quietly compare the red ledger date to the chapel timestamp for a forged provenance contradiction.",
            ],
            crew_noise=1,
        )
    )
    occult = score_auction_preview(
        AuctionPreviewScoreInput(
            crew_id="crew_other",
            claim="The reliquary is occult but unstable.",
            evidence_ids=[],
            exposed_assets=["asset_door_omen"],
            reasoning="A moth jar door omen appears near the auction room.",
            weaknesses="Omen has no corroboration.",
            provenance_concerns="Ledger chain is contaminated.",
            action_intents=["Observe the sealed door omen and moth jar for occult resonance."],
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
        claim="The relic is likely false.",
        evidence_ids=["fragment_starter_ledger"],
        exposed_assets=["fragment_starter_ledger"],
        reasoning="The ledger contradicts the chapel timestamp.",
        weaknesses="No material confirmation.",
        provenance_concerns="Copied hand.",
        action_intents=["Inspect the ledger for forged provenance date correlation."],
        crew_noise=0,
    )
    renamed = base.model_copy(update={"crew_id": "crew_moth_choir"})

    assert score_auction_preview(base).total == score_auction_preview(renamed).total


def test_provenance_keywords_without_supporting_evidence_do_not_get_clean_clue():
    unsupported = score_auction_preview(
        AuctionPreviewScoreInput(
            crew_id="crew_any",
            claim="The relic is likely false.",
            evidence_ids=[],
            exposed_assets=[],
            reasoning="The ledger date is forged and contradicts the chapel timestamp.",
            action_intents=["Say ledger provenance date correlation repeatedly."],
            crew_noise=0,
        )
    )

    assert "clean provenance contradiction" not in unsupported.strengths
    assert unsupported.standing == "Weak"
