from __future__ import annotations

from typing import Any

import pytest

from hollow_lodge.workflows.openai_oracle import (
    OpenAIAuctionPreviewResolution,
    OpenAIResolutionOracle,
)
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewPacket,
    AuctionPreviewOraclePacket,
    MAX_ORACLE_RESULT_LINES,
    MAX_ORACLE_TEXT_CHARS,
)


class FakeResponses:
    def __init__(self, parsed_output: Any):
        self._parsed_output = parsed_output
        self.parse_calls: list[dict] = []

    def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        return FakeParsedResponse(self._parsed_output)


class FakeParsedResponse:
    def __init__(self, parsed_output: Any):
        self.output_parsed = parsed_output


class FakeClient:
    def __init__(self, parsed_output: Any):
        self.responses = FakeResponses(parsed_output)


def auction_preview_packet() -> AuctionPreviewOraclePacket:
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
        ),
        allowed_evidence_ids=("fragment_starter_ledger", "asset_door_omen"),
        score_min=0,
        score_max=100,
    )


def parsed_output() -> dict:
    return {
        "standings": [
            {
                "crew_id": "crew_gilt",
                "score": 76,
                "standing": "Strong lead",
                "strengths": ["clean provenance contradiction"],
                "weaknesses": ["no material confirmation"],
                "penalties": ["minor heat trace"],
                "revealed_clues": ["Auction house provenance is now suspect."],
            }
        ],
        "contract_state": ["Auction house provenance is now suspect."],
        "narration": "The Gilt packet leads on provenance without settling material truth.",
        "validation_warnings": [],
    }


def test_openai_oracle_uses_structured_outputs_parse_contract():
    client = FakeClient(parsed_output())
    oracle = OpenAIResolutionOracle(
        client=client,
        model="gpt-test",
        timeout_seconds=7.5,
    )

    result = oracle.resolve_auction_preview(auction_preview_packet())

    assert result.provider.provider == "openai"
    assert result.provider.model == "gpt-test"
    assert result.provider.prompt_version == "auction-preview-resolution-v2"
    assert result.standings[0].score != 76
    assert result.narration == "The Gilt packet leads on provenance without settling material truth."

    assert len(client.responses.parse_calls) == 1
    parse_call = client.responses.parse_calls[0]
    assert parse_call["model"] == "gpt-test"
    assert parse_call["timeout"] == 7.5
    assert parse_call["store"] is False
    assert parse_call["text_format"] is OpenAIAuctionPreviewResolution
    assert "text" not in parse_call
    assert parse_call["input"][1]["content"]["packet"]["contract_id"] == "contract_false_finger"
    assert "Deterministic standings are authoritative" in parse_call["input"][0]["content"]
    assert "raw action prose" not in str(parse_call["input"])


def test_openai_oracle_does_not_require_real_api_when_client_injected():
    client = FakeClient(parsed_output())
    oracle = OpenAIResolutionOracle(
        client=client,
        model="gpt-test",
        timeout_seconds=20,
    )

    result = oracle.resolve_auction_preview(auction_preview_packet())

    assert result.standings[0].crew_id == "crew_gilt"
    assert len(client.responses.parse_calls) == 1


def test_openai_oracle_rejects_missing_parsed_output():
    client = FakeClient(None)
    oracle = OpenAIResolutionOracle(
        client=client,
        model="gpt-test",
        timeout_seconds=20,
    )

    with pytest.raises(ValueError, match="parsed output"):
        oracle.resolve_auction_preview(auction_preview_packet())


def test_openai_oracle_rejects_non_object_parsed_output():
    client = FakeClient("not an object")
    oracle = OpenAIResolutionOracle(
        client=client,
        model="gpt-test",
        timeout_seconds=20,
    )

    with pytest.raises(ValueError, match="parsed output"):
        oracle.resolve_auction_preview(auction_preview_packet())


def test_openai_oracle_rejects_schema_invalid_parsed_dict():
    invalid_output = parsed_output()
    invalid_output["standings"][0].pop("crew_id")
    client = FakeClient(invalid_output)
    oracle = OpenAIResolutionOracle(
        client=client,
        model="gpt-test",
        timeout_seconds=20,
    )

    with pytest.raises(Exception):
        oracle.resolve_auction_preview(auction_preview_packet())


def test_openai_oracle_rejects_unbounded_parsed_output():
    invalid_output = parsed_output()
    invalid_output["narration"] = "x" * (MAX_ORACLE_TEXT_CHARS + 1)
    invalid_output["standings"][0]["strengths"] = [
        f"strength {index}"
        for index in range(MAX_ORACLE_RESULT_LINES + 1)
    ]
    client = FakeClient(invalid_output)
    oracle = OpenAIResolutionOracle(
        client=client,
        model="gpt-test",
        timeout_seconds=20,
    )

    with pytest.raises(Exception):
        oracle.resolve_auction_preview(auction_preview_packet())
