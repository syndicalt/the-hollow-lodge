from hollow_lodge.domain.proofs import ProofFragment


def test_copied_fragments_preserve_source_chain_internally():
    original = ProofFragment(
        fragment_id="fragment_starter_ledger",
        content_summary="A red ledger rubric names three prior owners.",
        source_chain=("archive:lot-card",),
        provenance_flags=("copied-hand", "ink-after-binding"),
    )

    copied = original.copy_for_transfer(
        new_fragment_id="fragment_copy_1",
        sender_player_id="player_0001",
        recipient_player_id="player_0002",
    )

    assert copied.source_chain == (
        "archive:lot-card",
        "transfer:player_0001->player_0002",
    )
    assert copied.provenance_flags == original.provenance_flags
    assert copied.surface_view() == {
        "fragment_id": "fragment_copy_1",
        "content_summary": "A red ledger rubric names three prior owners.",
        "source_chain": ["archive:lot-card", "transfer:player_0001->player_0002"],
        "provenance_checked": False,
    }
