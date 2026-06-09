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
        ),
        rubric_hooks=("provenance quality",),
        crews=(
            AuctionPreviewCrewPacket(
                crew_id="crew_gilt",
                evidence_ids=("fragment_starter_ledger",),
                exposed_assets=("fragment_starter_ledger",),
                compiled_actions=(
                    {
                        "version": "compiled-action-v1",
                        "approach": "provenance_research",
                        "scope": "proofwork",
                        "risk_posture": "careful",
                    },
                ),
                crew_noise=1,
            ),
            AuctionPreviewCrewPacket(
                crew_id="crew_moth",
                evidence_ids=(),
                exposed_assets=("asset_door_omen",),
                compiled_actions=(
                    {
                        "version": "compiled-action-v1",
                        "approach": "occult_analysis",
                        "scope": "proofwork",
                        "risk_posture": "balanced",
                    },
                ),
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
    assert result.standings[0].standing == "Viable"
    assert "clean provenance contradiction" in result.standings[0].strengths
    assert result.standings[0].revealed_clues == (
        "Auction house provenance is now suspect.",
    )
    assert result.standings[1].crew_id == "crew_moth"
    assert result.standings[1].standing == "Viable but unstable"
    assert "occult clue may unlock alternate lane" in result.standings[1].strengths
    assert result.standings[1].revealed_clues == (
        "Rival alternate clue paths remain open.",
    )
    assert result.contract_state == (
        "Auction house provenance is now suspect.",
        "Rival alternate clue paths remain open.",
    )


def test_deterministic_oracle_rewards_artifact_citations_and_known_edges():
    packet = AuctionPreviewOraclePacket(
        contract_id="contract_false_finger",
        phase="Auction Preview",
        hidden_truth_summary="The finger is a saint-bone forgery.",
        allowed_reveal_strings=(
            "Auction house provenance is now suspect.",
            "Rival alternate clue paths remain open.",
        ),
        rubric_hooks=("provenance quality",),
        crews=(
            AuctionPreviewCrewPacket(
                crew_id="crew_gilt",
                evidence_ids=("artifact_lot_card", "artifact_ledger_rubric"),
                artifact_citations=(
                    {
                        "artifact_id": "artifact_ledger_rubric",
                    },
                ),
                known_edges=(
                    {
                        "source_id": "artifact_lot_card",
                        "relation": "contradicts",
                        "target_id": "artifact_ledger_rubric",
                    },
                ),
            ),
        ),
        allowed_evidence_ids=("artifact_lot_card", "artifact_ledger_rubric"),
    )

    result = DeterministicResolutionOracle().resolve_auction_preview(packet)

    assert "cited artifact source material" in result.standings[0].strengths
    assert "mapped evidence contradiction" in result.standings[0].strengths
