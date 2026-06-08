from hollow_lodge.server.artifact_seed import STARTER_ARTIFACT_GRAPH
from hollow_lodge.server.artifact_unlocks import action_unlock_candidates


def test_action_mentions_tag_unlocks_matching_artifact_rule():
    candidates = action_unlock_candidates(
        graph=STARTER_ARTIFACT_GRAPH,
        contract_id="contract_false_finger",
        phase="Auction Preview",
        intent="Question the chapel keeper about the debt mark.",
        exposed_assets=(),
        already_visible_artifact_ids={"artifact_lot_card", "artifact_ledger_rubric"},
    )

    assert [candidate.artifact_id for candidate in candidates] == [
        "artifact_chapel_debt_mark"
    ]


def test_unlock_candidates_skip_already_visible_artifacts():
    candidates = action_unlock_candidates(
        graph=STARTER_ARTIFACT_GRAPH,
        contract_id="contract_false_finger",
        phase="Auction Preview",
        intent="Question the chapel keeper about the debt mark.",
        exposed_assets=(),
        already_visible_artifact_ids={
            "artifact_lot_card",
            "artifact_ledger_rubric",
            "artifact_chapel_debt_mark",
        },
    )

    assert candidates == []


def test_action_mentions_tag_requires_all_terms():
    partial_candidates = action_unlock_candidates(
        graph=STARTER_ARTIFACT_GRAPH,
        contract_id="contract_false_finger",
        phase="Auction Preview",
        intent="Question the clerk.",
        exposed_assets=(),
        already_visible_artifact_ids={"artifact_lot_card", "artifact_ledger_rubric"},
    )
    complete_candidates = action_unlock_candidates(
        graph=STARTER_ARTIFACT_GRAPH,
        contract_id="contract_false_finger",
        phase="Auction Preview",
        intent="Question the clerk about the catalogue correction.",
        exposed_assets=(),
        already_visible_artifact_ids={"artifact_lot_card", "artifact_ledger_rubric"},
    )

    assert "artifact_clerk_pencil_note" not in [
        candidate.artifact_id for candidate in partial_candidates
    ]
    assert [candidate.artifact_id for candidate in complete_candidates] == [
        "artifact_clerk_pencil_note"
    ]
