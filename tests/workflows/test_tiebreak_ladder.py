from __future__ import annotations

from hollow_lodge.domain.scoring import RUBRIC_SCORING_MODE, RubricFact
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewPacket,
    AuctionPreviewCrewResult,
    AuctionPreviewOraclePacket,
    AuctionPreviewOracleResult,
    OracleProviderMetadata,
    validate_auction_preview_result,
)

FACT = RubricFact(
    fact_id="fact_key",
    points=20,
    required_artifact_ids=("artifact_hidden",),
)


def packet(crews: tuple[AuctionPreviewCrewPacket, ...]) -> AuctionPreviewOraclePacket:
    return AuctionPreviewOraclePacket(
        contract_id="contract_tied",
        phase="Preview",
        hidden_truth_summary="",
        crews=crews,
        scoring_mode=RUBRIC_SCORING_MODE,
        rubric_facts=(FACT,),
    )


def result_for(*crew_ids: str) -> AuctionPreviewOracleResult:
    return AuctionPreviewOracleResult(
        provider=OracleProviderMetadata(
            provider="deterministic",
            prompt_version="test",
        ),
        standings=tuple(
            AuctionPreviewCrewResult(
                crew_id=crew_id,
                score=50,
                standing="Viable",
            )
            for crew_id in crew_ids
        ),
    )


def crew(crew_id: str, **overrides) -> AuctionPreviewCrewPacket:
    defaults = dict(crew_id=crew_id, crew_noise=0, last_dossier_edit_sequence=0)
    defaults.update(overrides)
    return AuctionPreviewCrewPacket(**defaults)


def fact_claim() -> dict:
    return {
        "subject_id": "artifact_hidden",
        "predicate": "establishes",
        "citation_artifact_ids": ("artifact_hidden",),
    }


def test_score_tie_breaks_on_established_facts():
    validated = validate_auction_preview_result(
        packet=packet(
            (
                crew("crew_alpha"),
                crew("crew_beta", typed_claims=(fact_claim(),)),
            )
        ),
        result=result_for("crew_alpha", "crew_beta"),
    )

    assert [standing.crew_id for standing in validated.standings] == [
        "crew_beta",
        "crew_alpha",
    ]


def test_fact_tie_breaks_on_lower_noise():
    validated = validate_auction_preview_result(
        packet=packet(
            (
                crew("crew_alpha", crew_noise=3),
                crew("crew_beta", crew_noise=1),
            )
        ),
        result=result_for("crew_alpha", "crew_beta"),
    )

    assert [standing.crew_id for standing in validated.standings] == [
        "crew_beta",
        "crew_alpha",
    ]


def test_noise_tie_breaks_on_earlier_final_dossier_edit():
    validated = validate_auction_preview_result(
        packet=packet(
            (
                crew("crew_alpha", last_dossier_edit_sequence=90),
                crew("crew_beta", last_dossier_edit_sequence=40),
            )
        ),
        result=result_for("crew_alpha", "crew_beta"),
    )

    assert [standing.crew_id for standing in validated.standings] == [
        "crew_beta",
        "crew_alpha",
    ]


def test_legacy_packets_keep_score_then_crew_id_ordering():
    legacy_packet = AuctionPreviewOraclePacket(
        contract_id="contract_legacy",
        phase="Preview",
        hidden_truth_summary="",
        crews=(
            crew("crew_alpha", crew_noise=5),
            crew("crew_beta", crew_noise=0),
        ),
    )

    validated = validate_auction_preview_result(
        packet=legacy_packet,
        result=result_for("crew_beta", "crew_alpha"),
    )

    assert [standing.crew_id for standing in validated.standings] == [
        "crew_alpha",
        "crew_beta",
    ]
