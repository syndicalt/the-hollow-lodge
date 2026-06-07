from hollow_lodge.domain.actions import NormalizedAction


def test_prose_action_normalizes_into_expected_frame():
    frame = NormalizedAction.from_intent(
        intent="I inspect the red ledger rubric quietly for provenance gaps.",
        actor_player_id="player_0001",
        crew_id="crew_0001",
    )

    assert frame.intent == "I inspect the red ledger rubric quietly for provenance gaps."
    assert frame.scope == "proofwork"
    assert frame.approach == "quiet inspection"
    assert frame.risk_posture == "careful"
    assert frame.exposed_assets == ["fragment_starter_ledger"]
    assert frame.crew_noise_impact == 0


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
