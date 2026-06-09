from __future__ import annotations

from hollow_lodge.domain.proofs import ProofFragment


STARTER_FRAGMENT = ProofFragment(
    fragment_id="fragment_starter_ledger",
    content_summary="A red ledger rubric names three prior owners.",
    source_chain=("archive:lot-card",),
    provenance_flags=("copied-hand", "ink-after-binding"),
)
