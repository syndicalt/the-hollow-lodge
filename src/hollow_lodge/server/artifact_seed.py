from __future__ import annotations

from hollow_lodge.domain.artifact_graph import (
    ArtifactEdge,
    ArtifactGraph,
    ArtifactUnlockRule,
)
from hollow_lodge.domain.artifacts import ArtifactNode


CONTRACT_FALSE_FINGER = "contract_false_finger"

STARTER_PUBLIC_ARTIFACT_IDS = ("artifact_lot_card", "artifact_ledger_rubric")

STARTER_ARTIFACT_GRAPH = ArtifactGraph(
    contract_id=CONTRACT_FALSE_FINGER,
    artifacts=(
        ArtifactNode(
            artifact_id="artifact_lot_card",
            contract_id=CONTRACT_FALSE_FINGER,
            kind="lot_card",
            title="Auction Lot Card",
            public_summary=(
                "A vellum card attributes the reliquary finger to Saint Aint."
            ),
            full_text=(
                "Lot 19. Reliquary finger of Saint Aint. Held under sealed "
                "preview by Venn & Bell, with chapel seal affixed."
            ),
            tags=("auction", "lot", "chapel", "saint-aint"),
            proof_lanes=("provenance", "leverage"),
            phase_relevance=("Auction Preview",),
            visible_flags=("public-lot",),
        ),
        ArtifactNode(
            artifact_id="artifact_ledger_rubric",
            contract_id=CONTRACT_FALSE_FINGER,
            kind="ledger",
            title="Red Ledger Rubric",
            public_summary=(
                "A copied rubric marks three prior owners in an unfamiliar hand."
            ),
            full_text=(
                "Rubric copy: Armitage, then Venn, then a chapel debt mark. "
                "The last hand is redder and later than the binding."
            ),
            source_chain=("archive:lot-card",),
            tags=("ledger", "rubric", "ownership", "red-hand"),
            proof_lanes=("provenance", "material"),
            phase_relevance=("Auction Preview",),
            hidden_flags=("ink-after-binding",),
            visible_flags=("copied-hand",),
        ),
        ArtifactNode(
            artifact_id="artifact_chapel_debt_mark",
            contract_id=CONTRACT_FALSE_FINGER,
            kind="rubbing",
            title="Chapel Debt Mark Rubbing",
            public_summary=(
                "A charcoal rubbing of a chapel debt mark tied to the reliquary "
                "case."
            ),
            full_text=(
                "The rubbing shows the same chapel mark named in the ledger, "
                "but it is a debt sign rather than a saintly custody seal."
            ),
            tags=("chapel", "debt", "mark", "omen"),
            proof_lanes=("occult", "provenance"),
            phase_relevance=("Auction Preview", "Access"),
            hidden_flags=("debtor-omen",),
        ),
        ArtifactNode(
            artifact_id="artifact_clerk_pencil_note",
            contract_id=CONTRACT_FALSE_FINGER,
            kind="witness_note",
            title="Clerk's Pencil Correction",
            public_summary="A clerk's correction questions the lot's ownership date.",
            full_text=(
                "Pencil note: 'Do not read the chapel mark as custody. Date "
                "was corrected after the preview catalogue was copied.'"
            ),
            tags=("clerk", "pencil", "catalogue", "date"),
            proof_lanes=("witness", "provenance", "leverage"),
            phase_relevance=("Auction Preview",),
        ),
    ),
    edges=(
        ArtifactEdge(
            source_id="artifact_lot_card",
            target_id="artifact_ledger_rubric",
            relation="contradicts",
            public_summary=(
                "The public lot card and copied ledger disagree on custody."
            ),
        ),
        ArtifactEdge(
            source_id="artifact_ledger_rubric",
            target_id="artifact_chapel_debt_mark",
            relation="points_to",
            public_summary="The ledger's chapel mark points toward a debt record.",
        ),
        ArtifactEdge(
            source_id="artifact_clerk_pencil_note",
            target_id="artifact_lot_card",
            relation="contradicts",
            public_summary="The clerk questions the lot card's copied date.",
        ),
    ),
    unlock_rules=(
        ArtifactUnlockRule(
            rule_id="unlock-chapel-debt-mark",
            artifact_id="artifact_chapel_debt_mark",
            contract_id=CONTRACT_FALSE_FINGER,
            phase="Auction Preview",
            trigger="action_mentions_tag",
            required_terms=("chapel",),
            award_scope="crew",
            award_reason="Followed the chapel mark from the ledger.",
        ),
        ArtifactUnlockRule(
            rule_id="unlock-clerk-pencil-note",
            artifact_id="artifact_clerk_pencil_note",
            contract_id=CONTRACT_FALSE_FINGER,
            phase="Auction Preview",
            trigger="action_mentions_tag",
            required_terms=("clerk", "catalogue"),
            award_scope="crew",
            award_reason="Pressed the auction clerk on the catalogue correction.",
        ),
    ),
)
