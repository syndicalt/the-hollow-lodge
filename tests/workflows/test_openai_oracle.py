from __future__ import annotations

from hollow_lodge.workflows.openai_oracle import OpenAIResolutionOracle
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewPacket,
    AuctionPreviewOraclePacket,
)


class FakeResponses:
    def __init__(self, parsed_output: dict):
        self._parsed_output = parsed_output
        self.parse_calls: list[dict] = []

    def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        return FakeParsedResponse(self._parsed_output)


class FakeParsedResponse:
    def __init__(self, parsed_output: dict):
        self.output_parsed = parsed_output


class FakeClient:
    def __init__(self, parsed_output: dict):
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
    assert result.provider.prompt_version == "auction-preview-resolution-v1"
    assert result.standings[0].score == 76

    assert len(client.responses.parse_calls) == 1
    parse_call = client.responses.parse_calls[0]
    assert parse_call["model"] == "gpt-test"
    assert parse_call["timeout"] == 7.5
    assert parse_call["text"]["format"]["type"] == "json_schema"
    assert parse_call["text"]["format"]["name"] == "auction_preview_resolution"
    assert parse_call["text"]["format"]["strict"] is True
    assert "schema" in parse_call["text"]["format"]
    assert "contract_false_finger" in str(parse_call["input"])


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
