from hollow_lodge.domain.artifact_graph import (
    ArtifactGraph,
    ArtifactNode,
    ArtifactUnlockRule,
)
from hollow_lodge.server.artifact_seed import STARTER_ARTIFACT_GRAPH
from hollow_lodge.server.artifact_unlocks import action_unlock_candidates


def test_action_mentions_tag_unlocks_matching_artifact_rule():
    candidates = action_unlock_candidates(
        graph=STARTER_ARTIFACT_GRAPH,
        contract_id="contract_false_finger",
        phase="Auction Preview",
        matched_terms=("chapel",),
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
        matched_terms=("chapel",),
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
        matched_terms=("clerk",),
        exposed_assets=(),
        already_visible_artifact_ids={"artifact_lot_card", "artifact_ledger_rubric"},
    )
    complete_candidates = action_unlock_candidates(
        graph=STARTER_ARTIFACT_GRAPH,
        contract_id="contract_false_finger",
        phase="Auction Preview",
        matched_terms=("clerk", "catalogue"),
        exposed_assets=(),
        already_visible_artifact_ids={"artifact_lot_card", "artifact_ledger_rubric"},
    )

    assert "artifact_clerk_pencil_note" not in [
        candidate.artifact_id for candidate in partial_candidates
    ]
    assert [candidate.artifact_id for candidate in complete_candidates] == [
        "artifact_clerk_pencil_note"
    ]


def _synonym_graph() -> ArtifactGraph:
    return ArtifactGraph(
        contract_id="contract_synonyms",
        artifacts=(
            ArtifactNode(
                artifact_id="artifact_hidden_sample",
                contract_id="contract_synonyms",
                title="Hidden Sample",
                kind="ledger",
                public_summary="A sample.",
                full_text="A sample.",
            ),
        ),
        unlock_rules=(
            ArtifactUnlockRule(
                rule_id="unlock-sample",
                artifact_id="artifact_hidden_sample",
                contract_id="contract_synonyms",
                phase="Preview",
                trigger="action_mentions_tag",
                required_term_groups=(("soot", "ash", "residue"),),
                award_scope="crew",
                award_reason="Followed the residue.",
            ),
        ),
    )


def test_required_term_group_matches_any_synonym():
    for synonym in ("soot", "ash", "residue"):
        candidates = action_unlock_candidates(
            graph=_synonym_graph(),
            contract_id="contract_synonyms",
            phase="Preview",
            matched_terms=(synonym,),
            exposed_assets=(),
            already_visible_artifact_ids=set(),
        )
        assert [candidate.artifact_id for candidate in candidates] == [
            "artifact_hidden_sample"
        ], synonym


def test_required_term_group_rejects_unrelated_terms():
    candidates = action_unlock_candidates(
        graph=_synonym_graph(),
        contract_id="contract_synonyms",
        phase="Preview",
        matched_terms=("ledger",),
        exposed_assets=(),
        already_visible_artifact_ids=set(),
    )

    assert candidates == []
