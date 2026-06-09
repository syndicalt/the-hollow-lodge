from hollow_lodge.domain.actions import NormalizedAction, compile_action_intent


def test_prose_action_normalizes_into_expected_frame():
    frame = NormalizedAction.from_intent(
        intent="I inspect the red ledger rubric quietly for provenance gaps.",
        actor_player_id="player_0001",
        crew_id="crew_0001",
    )

    assert frame.intent == "I inspect the red ledger rubric quietly for provenance gaps."
    assert frame.scope == "proofwork"
    assert frame.approach == "provenance_research"
    assert frame.risk_posture == "careful"
    assert frame.exposed_assets == ["fragment_starter_ledger", "artifact_ledger_rubric"]
    assert frame.crew_noise_impact == 0
    assert frame.compiled_intent is not None
    assert frame.compile_hash == frame.compiled_intent.compile_hash


def test_second_full_action_in_phase_increases_noise_risk():
    first = NormalizedAction.from_intent(
        intent="I inspect the red ledger rubric quietly.",
        actor_player_id="player_0001",
        crew_id="crew_0001",
        action_number=1,
    )
    second = NormalizedAction.from_intent(
        intent="I pressure the auction clerk for names.",
        actor_player_id="player_0001",
        crew_id="crew_0001",
        action_number=2,
    )

    assert first.crew_noise_impact == 0
    assert second.crew_noise_impact == 1


def test_compiled_action_filters_invisible_targets_and_assets():
    compiled = compile_action_intent(
        intent="Inspect the ledger and follow the chapel mark.",
        allowed_target_ids={"artifact_lot_card"},
        allowed_asset_ids={"artifact_lot_card"},
        contract_terms={"chapel"},
    )

    assert compiled.target_ids == ()
    assert compiled.assets_staked == ()
    assert compiled.matched_terms == ("chapel",)
