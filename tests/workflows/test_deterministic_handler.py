from hollow_lodge.workflows.deterministic_handler import (
    deterministic_provenance_read,
    handler_provenance_summary,
    normalize_action_intent,
)
from hollow_lodge.workflows.llmff_boundary import HandlerNormalizer


def test_deterministic_shallow_provenance_read_for_starter_ledger():
    result = deterministic_provenance_read("fragment_starter_ledger")

    assert result["fragment_id"] == "fragment_starter_ledger"
    assert result["authority"] == "local-guidance"
    assert "provenance_flags" not in result
    assert "spend a side action" in result["guidance"]


def test_handler_summary_is_not_an_official_provenance_event():
    summary = handler_provenance_summary("fragment_starter_ledger")

    assert summary["origin"] == "handler"
    assert summary["type"] == "handler.provenance_summary"
    assert summary["type"] != "proof.provenance.checked"


def test_deterministic_action_normalizer_returns_local_frame_not_submission():
    frame = normalize_action_intent(
        "I inspect the red ledger rubric quietly.",
        actor_player_id="player_0001",
        crew_id="crew_0001",
    )

    assert frame.origin == "handler"
    assert frame.type == "action.draft.normalized"
    assert frame.normalized.scope == "proofwork"


def test_handler_normalizer_protocol_uses_typed_frame():
    normalizer: HandlerNormalizer = normalize_action_intent

    frame = normalizer(
        "I inspect the red ledger rubric quietly.",
        actor_player_id="player_0001",
        crew_id="crew_0001",
    )

    assert frame.normalized.crew_id == "crew_0001"
