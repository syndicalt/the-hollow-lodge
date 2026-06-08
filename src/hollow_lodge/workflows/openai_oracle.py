from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewOraclePacket,
    AuctionPreviewOracleResult,
    OracleProviderMetadata,
)


_PROMPT_VERSION = "auction-preview-resolution-v1"


class OpenAICrewStanding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crew_id: str = Field(min_length=1)
    score: int = Field(ge=0)
    standing: str = Field(min_length=1)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)
    revealed_clues: list[str] = Field(default_factory=list)


class OpenAIAuctionPreviewResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standings: list[OpenAICrewStanding]
    contract_state: list[str] = Field(default_factory=list)
    narration: str = ""
    validation_warnings: list[str] = Field(default_factory=list)


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
            text_format=OpenAIAuctionPreviewResolution,
            store=False,
            timeout=self._timeout_seconds,
        )
        parsed = _parse_openai_output(response.output_parsed)
        return AuctionPreviewOracleResult(
            provider=OracleProviderMetadata(
                provider="openai",
                model=self._model,
                prompt_version=_PROMPT_VERSION,
            ),
            **parsed.model_dump(),
        )


def _system_prompt() -> str:
    return (
        "Resolve Hollow Lodge Auction Preview packets into the requested JSON "
        "schema. Preserve the hidden truth: never reveal, paraphrase, or confirm "
        "hidden_truth_summary content. Public clue output in contract_state and "
        "revealed_clues must use only exact strings from allowed_reveal_strings. "
        "Score each crew from the packet evidence, rubric hooks, and noise fields."
    )


def _parse_openai_output(parsed: Any) -> OpenAIAuctionPreviewResolution:
    if parsed is None:
        raise ValueError("OpenAI oracle returned no parsed output")
    if isinstance(parsed, OpenAIAuctionPreviewResolution):
        return parsed
    if isinstance(parsed, dict):
        return OpenAIAuctionPreviewResolution.model_validate(parsed)
    raise ValueError("OpenAI oracle returned invalid parsed output")
