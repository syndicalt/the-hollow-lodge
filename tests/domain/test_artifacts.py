from hollow_lodge.domain.artifacts import ArtifactCopy, ArtifactNode


def test_artifact_surface_view_hides_full_text_and_hidden_flags_by_default():
    artifact = ArtifactNode(
        artifact_id="artifact_ledger_rubric",
        contract_id="contract_false_finger",
        title="Red ledger rubric",
        kind="ledger",
        public_summary="A copied rubric marks prior ownership.",
        full_text="Lot 19 passed under chapel seal.",
        hidden_flags=("ink-after-binding",),
        visible_flags=("copied-hand",),
        proof_lanes=("provenance",),
        phase_relevance=("Auction Preview",),
    )

    assert artifact.surface_view() == {
        "artifact_id": "artifact_ledger_rubric",
        "contract_id": "contract_false_finger",
        "title": "Red ledger rubric",
        "kind": "ledger",
        "public_summary": "A copied rubric marks prior ownership.",
        "visible_flags": ["copied-hand"],
        "proof_lanes": ["provenance"],
        "phase_relevance": ["Auction Preview"],
        "copy_policy": "copyable",
    }


def test_artifact_copy_preserves_provenance_chain_and_marks_copy():
    copied = ArtifactCopy.from_source(
        source_artifact_id="artifact_ledger_rubric",
        copy_artifact_id="artifact_ledger_rubric.copy.player_0002.1",
        contract_id="contract_false_finger",
        sender_player_id="player_0001",
        recipient_player_id="player_0002",
        title="Red ledger rubric copy",
        public_summary="A copied rubric marks prior ownership.",
    )

    assert copied.source_artifact_id == "artifact_ledger_rubric"
    assert copied.source_chain == (
        "artifact:artifact_ledger_rubric",
        "transfer:player_0001->player_0002",
    )
    assert copied.surface_view()["is_copy"] is True
