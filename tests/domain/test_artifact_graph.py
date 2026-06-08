import pytest

from hollow_lodge.domain.artifact_graph import ArtifactEdge, ArtifactGraph
from hollow_lodge.domain.artifacts import ArtifactNode


def _artifact(artifact_id: str) -> ArtifactNode:
    return ArtifactNode(
        artifact_id=artifact_id,
        contract_id="contract_false_finger",
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
