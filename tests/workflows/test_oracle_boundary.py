import pytest

from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewPacket,
    AuctionPreviewCrewResult,
    AuctionPreviewOraclePacket,
    AuctionPreviewOracleResult,
    OracleProviderMetadata,
    validate_auction_preview_result,
)


def valid_packet() -> AuctionPreviewOraclePacket:
    return AuctionPreviewOraclePacket(
        contract_id="contract_false_finger",
        phase="Auction Preview",
        hidden_truth_summary="The finger is a saint-bone forgery.",
        allowed_reveal_strings=(
            "Auction house provenance is now suspect.",
            "Rival alternate clue paths remain open.",
        ),
        rubric_hooks=("provenance quality", "corroboration", "heat/noise penalties"),
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
        ),
        allowed_evidence_ids=("fragment_starter_ledger", "asset_door_omen"),
        score_min=0,
        score_max=100,
    )


def valid_result() -> AuctionPreviewOracleResult:
    return AuctionPreviewOracleResult(
        provider=OracleProviderMetadata(
            provider="deterministic",
            model=None,
            prompt_version="deterministic-v1",
        ),
        standings=(
            AuctionPreviewCrewResult(
                crew_id="crew_gilt",
                score=76,
                standing="Strong lead",
                strengths=("clean provenance contradiction",),
                weaknesses=("no material confirmation",),
                penalties=("minor heat trace",),
                revealed_clues=("Auction house provenance is now suspect.",),
            ),
        ),
        contract_state=("Auction house provenance is now suspect.",),
        narration="The Gilt packet leads on provenance without settling material truth.",
        validation_warnings=(),
    )


def test_validate_accepts_known_crews_and_safe_reveal_strings():
    accepted = validate_auction_preview_result(
        packet=valid_packet(),
        result=valid_result(),
    )

    assert accepted.standings[0].crew_id == "crew_gilt"
    assert accepted.standings[0].score == 76
    assert accepted.contract_state == ("Auction house provenance is now suspect.",)


def test_validate_rejects_unknown_crew_id():
    result = valid_result().model_copy(
        update={
            "standings": (
                valid_result()
                .standings[0]
                .model_copy(update={"crew_id": "crew_unknown"}),
            )
        }
    )

    with pytest.raises(ValueError, match="unknown crew id"):
        validate_auction_preview_result(packet=valid_packet(), result=result)


def test_validate_clamps_scores_to_packet_bounds():
    result = valid_result().model_copy(
        update={
            "standings": (
                valid_result().standings[0].model_copy(update={"score": 500}),
            )
        }
    )

    accepted = validate_auction_preview_result(packet=valid_packet(), result=result)

    assert accepted.standings[0].score == 100


def test_validate_rejects_hidden_truth_leakage():
    result = valid_result().model_copy(
        update={"narration": "The finger is a saint-bone forgery."}
    )

    with pytest.raises(ValueError, match="hidden truth leak"):
        validate_auction_preview_result(packet=valid_packet(), result=result)


def test_validate_rejects_unknown_revealed_clue():
    result = valid_result().model_copy(
        update={
            "standings": (
                valid_result().standings[0].model_copy(
                    update={"revealed_clues": ("The debtor omen is real.",)}
                ),
            )
        }
    )

    with pytest.raises(ValueError, match="unsafe reveal"):
        validate_auction_preview_result(packet=valid_packet(), result=result)
