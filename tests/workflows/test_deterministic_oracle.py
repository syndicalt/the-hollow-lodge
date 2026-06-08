from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewPacket,
    AuctionPreviewOraclePacket,
)


def test_deterministic_oracle_preserves_current_scoring_shape():
    packet = AuctionPreviewOraclePacket(
        contract_id="contract_false_finger",
        phase="Auction Preview",
        hidden_truth_summary="The finger is a saint-bone forgery.",
        allowed_reveal_strings=(
            "Auction house provenance is now suspect.",
            "Rival alternate clue paths remain open.",
            "auction-house provenance is now suspect",
            "sealed-door omen remains viable",
        ),
        rubric_hooks=("provenance quality",),
        crews=(
            AuctionPreviewCrewPacket(
                crew_id="crew_gilt",
                claim="The relic is likely false.",
                evidence_ids=("fragment_starter_ledger",),
                exposed_assets=("fragment_starter_ledger",),
                reasoning="The ledger date contradicts the chapel timestamp.",
                weaknesses="No material confirmation.",
                provenance_concerns="Copied hand.",
                action_intents=("Inspect the ledger for forged provenance.",),
                crew_noise=1,
            ),
            AuctionPreviewCrewPacket(
                crew_id="crew_moth",
                claim="The reliquary is occult but unstable.",
                evidence_ids=(),
                exposed_assets=("asset_door_omen",),
                reasoning="A moth jar door omen appears near the auction room.",
                weaknesses="Omen has no corroboration.",
                provenance_concerns="",
                action_intents=("Observe the sealed door omen for occult resonance.",),
                crew_noise=0,
            ),
        ),
        allowed_evidence_ids=("fragment_starter_ledger", "asset_door_omen"),
        score_min=0,
        score_max=100,
    )

    result = DeterministicResolutionOracle().resolve_auction_preview(packet)

    assert result.provider.provider == "deterministic"
    assert result.provider.model is None
    assert result.provider.prompt_version == "deterministic-v1"
    assert result.standings[0].crew_id == "crew_gilt"
    assert result.standings[0].standing == "Strong lead"
    assert "clean provenance contradiction" in result.standings[0].strengths
    assert result.standings[0].revealed_clues == (
        "auction-house provenance is now suspect",
    )
    assert result.standings[1].crew_id == "crew_moth"
    assert result.standings[1].standing == "Viable but unstable"
    assert "occult clue may unlock alternate lane" in result.standings[1].strengths
    assert result.standings[1].revealed_clues == (
        "sealed-door omen remains viable",
    )
    assert result.contract_state == (
        "Auction house provenance is now suspect.",
        "Rival alternate clue paths remain open.",
    )
