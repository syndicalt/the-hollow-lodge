from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewOraclePacket,
    AuctionPreviewOracleResult,
    BoundedOracleText,
    MAX_ORACLE_RESULT_LINES,
    OracleProviderMetadata,
)


_PROMPT_VERSION = "auction-preview-resolution-v2"


class OpenAICrewStanding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crew_id: str = Field(min_length=1)
    score: int = Field(ge=0)
    standing: BoundedOracleText = Field(min_length=1)
    strengths: list[BoundedOracleText] = Field(
        default_factory=list,
        max_length=MAX_ORACLE_RESULT_LINES,
    )
    weaknesses: list[BoundedOracleText] = Field(
        default_factory=list,
        max_length=MAX_ORACLE_RESULT_LINES,
    )
    penalties: list[BoundedOracleText] = Field(
        default_factory=list,
        max_length=MAX_ORACLE_RESULT_LINES,
    )
    revealed_clues: list[BoundedOracleText] = Field(
        default_factory=list,
        max_length=MAX_ORACLE_RESULT_LINES,
    )


class OpenAIAuctionPreviewResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standings: list[OpenAICrewStanding]
    contract_state: list[BoundedOracleText] = Field(
        default_factory=list,
        max_length=MAX_ORACLE_RESULT_LINES,
    )
    narration: BoundedOracleText = ""
    validation_warnings: list[BoundedOracleText] = Field(
        default_factory=list,
        max_length=MAX_ORACLE_RESULT_LINES,
    )


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

    def runtime_metadata(self) -> OracleProviderMetadata:
        return OracleProviderMetadata(
            provider="openai",
            model=self._model,
            prompt_version=_PROMPT_VERSION,
        )

    def resolve_auction_preview(
        self,
        packet: AuctionPreviewOraclePacket,
    ) -> AuctionPreviewOracleResult:
        deterministic = DeterministicResolutionOracle().resolve_auction_preview(packet)
        response = self._client.responses.parse(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": _system_prompt(),
                },
                {
                    "role": "user",
                    "content": {
                        "packet": packet.model_dump(mode="json"),
                        "deterministic_result": deterministic.model_dump(mode="json"),
                    },
                },
            ],
            text_format=OpenAIAuctionPreviewResolution,
            store=False,
            timeout=self._timeout_seconds,
        )
        parsed = _parse_openai_output(response.output_parsed)
        return deterministic.model_copy(
            update={
                "provider": self.runtime_metadata(),
                "narration": parsed.narration,
                "validation_warnings": tuple(parsed.validation_warnings),
            }
        )


def _system_prompt() -> str:
    return (
        "Resolve Hollow Lodge Auction Preview packets into the requested JSON "
        "schema. Deterministic standings are authoritative; do not change crew "
        "scores, standing order, strengths, penalties, or revealed clues. "
        "Preserve the hidden truth: never reveal, paraphrase, or confirm "
        "hidden_truth_summary content. Public clue output in contract_state and "
        "revealed_clues must use only exact strings from allowed_reveal_strings. "
        "Use the structured packet and deterministic result only to write concise "
        "narration and validation warnings. Do not reveal hidden graph nodes "
        "unless they are in allowed reveal strings."
    )


def _parse_openai_output(parsed: Any) -> OpenAIAuctionPreviewResolution:
    if parsed is None:
        raise ValueError("OpenAI oracle returned no parsed output")
    if isinstance(parsed, OpenAIAuctionPreviewResolution):
        return parsed
    if isinstance(parsed, dict):
        return OpenAIAuctionPreviewResolution.model_validate(parsed)
    raise ValueError("OpenAI oracle returned invalid parsed output")
