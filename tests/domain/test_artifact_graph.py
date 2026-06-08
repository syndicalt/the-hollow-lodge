import pytest

from hollow_lodge.domain.artifact_graph import ArtifactEdge, ArtifactGraph, ArtifactUnlockRule
from hollow_lodge.domain.artifacts import ArtifactNode


def _artifact(
    artifact_id: str,
    *,
    contract_id: str = "contract_false_finger",
) -> ArtifactNode:
    return ArtifactNode(
        artifact_id=artifact_id,
        contract_id=contract_id,
        title=artifact_id,
        kind="other",
        public_summary=f"Summary for {artifact_id}.",
        full_text=f"Full text for {artifact_id}.",
    )


def test_graph_rejects_edge_target_unknown_artifact():
    with pytest.raises(ValueError, match="unknown edge target"):
        ArtifactGraph(
            contract_id="contract_false_finger",
            artifacts=(_artifact("artifact_lot_card"),),
            edges=(
                ArtifactEdge(
                    source_id="artifact_lot_card",
                    target_id="artifact_ledger_rubric",
                    relation="contradicts",
                ),
            ),
        )


def test_graph_rejects_duplicate_artifact_ids():
    with pytest.raises(ValueError, match="duplicate artifact id"):
        ArtifactGraph(
            contract_id="contract_false_finger",
            artifacts=(
                _artifact("artifact_lot_card"),
                _artifact("artifact_lot_card"),
            ),
        )


def test_graph_rejects_artifact_contract_mismatch():
    with pytest.raises(ValueError, match="artifact contract mismatch"):
        ArtifactGraph(
            contract_id="contract_false_finger",
            artifacts=(
                _artifact(
                    "artifact_lot_card",
                    contract_id="contract_different",
                ),
            ),
        )


def test_graph_rejects_unlock_contract_mismatch():
    with pytest.raises(ValueError, match="unlock contract mismatch"):
        ArtifactGraph(
            contract_id="contract_false_finger",
            artifacts=(_artifact("artifact_lot_card"),),
            unlock_rules=(
                ArtifactUnlockRule(
                    rule_id="unlock_lot_card",
                    artifact_id="artifact_lot_card",
                    contract_id="contract_different",
                    phase="Auction Preview",
                    trigger="manual_award",
                    award_reason="Seed artifact.",
                ),
            ),
        )


def test_visible_slice_with_one_artifact_returns_no_edges():
    graph = ArtifactGraph(
        contract_id="contract_false_finger",
        artifacts=(
            _artifact("artifact_lot_card"),
            _artifact("artifact_ledger_rubric"),
        ),
        edges=(
            ArtifactEdge(
                source_id="artifact_lot_card",
                target_id="artifact_ledger_rubric",
                relation="contradicts",
                visibility="public",
                public_summary="The dates do not agree.",
            ),
        ),
    )

    visible = graph.visible_slice({"artifact_lot_card"})

    assert visible["edges"] == []


def test_visible_slice_with_both_artifacts_returns_public_edge():
    graph = ArtifactGraph(
        contract_id="contract_false_finger",
        artifacts=(
            _artifact("artifact_lot_card"),
            _artifact("artifact_ledger_rubric"),
        ),
        edges=(
            ArtifactEdge(
                source_id="artifact_lot_card",
                target_id="artifact_ledger_rubric",
                relation="contradicts",
                visibility="public",
                public_summary="The dates do not agree.",
            ),
        ),
    )

    visible = graph.visible_slice({"artifact_lot_card", "artifact_ledger_rubric"})

    assert visible["edges"] == [
        {
            "source_id": "artifact_lot_card",
            "target_id": "artifact_ledger_rubric",
            "relation": "contradicts",
            "public_summary": "The dates do not agree.",
        }
    ]
