from __future__ import annotations

from typing import Any

from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewOraclePacket,
    AuctionPreviewOracleResult,
    OracleProviderMetadata,
)


_PROMPT_VERSION = "auction-preview-resolution-v1"


class OpenAIResolutionOracle:
    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str,
        timeout_seconds: float,
    ) -> None:
        if client is None:
            from openai import OpenAI

            client = OpenAI()
        self._client = client
        self._model = model
        self._timeout_seconds = timeout_seconds

    def resolve_auction_preview(
        self,
        packet: AuctionPreviewOraclePacket,
    ) -> AuctionPreviewOracleResult:
        response = self._client.responses.parse(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": _system_prompt(),
                },
                {
                    "role": "user",
                    "content": packet.model_dump_json(),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "auction_preview_resolution",
                    "strict": True,
                    "schema": _schema(),
                }
            },
            timeout=self._timeout_seconds,
        )
        parsed = response.output_parsed
        if not isinstance(parsed, dict):
            raise ValueError("OpenAI oracle returned non-object parsed output")
        return AuctionPreviewOracleResult(
            provider=OracleProviderMetadata(
                provider="openai",
                model=self._model,
                prompt_version=_PROMPT_VERSION,
            ),
            **parsed,
        )


def _system_prompt() -> str:
    return (
        "Resolve Hollow Lodge Auction Preview packets into the requested JSON "
        "schema. Preserve the hidden truth: never reveal, paraphrase, or confirm "
        "hidden_truth_summary content. Public clue output in contract_state and "
        "revealed_clues must use only exact strings from allowed_reveal_strings. "
        "Score each crew from the packet evidence, rubric hooks, and noise fields."
    )


def _schema() -> dict[str, Any]:
    string_array = {
        "type": "array",
        "items": {"type": "string"},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "standings",
            "contract_state",
            "narration",
            "validation_warnings",
        ],
        "properties": {
            "standings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "crew_id",
                        "score",
                        "standing",
                        "strengths",
                        "weaknesses",
                        "penalties",
                        "revealed_clues",
                    ],
                    "properties": {
                        "crew_id": {"type": "string"},
                        "score": {"type": "integer", "minimum": 0},
                        "standing": {"type": "string"},
                        "strengths": string_array,
                        "weaknesses": string_array,
                        "penalties": string_array,
                        "revealed_clues": string_array,
                    },
                },
            },
            "contract_state": string_array,
            "narration": {"type": "string"},
            "validation_warnings": string_array,
        },
    }
