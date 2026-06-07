from __future__ import annotations

from hollow_lodge.domain.contracts import (
    Campaign,
    Contract,
    ContractPhase,
    EvidenceAsset,
    HiddenTruth,
)


STARTER_CAMPAIGN = Campaign(
    campaign_id="campaign_saints_ledgers",
    title="Saints & Ledgers",
)

STARTER_CONTRACT = Contract(
    contract_id="contract_false_finger",
    campaign_id=STARTER_CAMPAIGN.campaign_id,
    title="The Saint's False Finger",
    premise=(
        "A reliquary finger is moving through a sealed auction preview. "
        "Crews must prove what it is before the Lodge names a buyer."
    ),
    phase=ContractPhase(name="Auction Preview", remaining_hours=6),
    evidence_assets=(
        EvidenceAsset(
            asset_id="asset_lot_card",
            title="Auction lot card",
            public_summary="A vellum card attributes the finger to Saint Aint.",
        ),
        EvidenceAsset(
            asset_id="asset_ledger_rubric",
            title="Red ledger rubric",
            public_summary="A copied rubric marks prior ownership in an unfamiliar hand.",
        ),
    ),
    proof_dossier_needs=(
        "provenance chain",
        "material authenticity",
        "auction leverage",
    ),
    crew_heat=0,
)

STARTER_HIDDEN_TRUTH = HiddenTruth(
    truth_id="truth_false_finger_forgery",
    summary="The finger is a saint-bone forgery wrapped around a real debtor's omen.",
)
