from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewOraclePacket,
    AuctionPreviewOracleResult,
    BoundedOracleText,
    MAX_ORACLE_RESULT_LINES,
    OracleProviderMetadata,
)


_PROMPT_VERSION = "auction-preview-resolution-v1"


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
            provider=self.runtime_metadata(),
            **parsed.model_dump(),
        )


def _system_prompt() -> str:
    return (
        "Resolve Hollow Lodge Auction Preview packets into the requested JSON "
        "schema. Preserve the hidden truth: never reveal, paraphrase, or confirm "
        "hidden_truth_summary content. Public clue output in contract_state and "
        "revealed_clues must use only exact strings from allowed_reveal_strings. "
        "Score each crew from the packet evidence, rubric hooks, and noise fields. "
        "Reward cited artifacts, direct quotes, and graph contradictions. "
        "Penalize claims that lack artifact citations or rely only on broad action prose. "
        "Do not reveal hidden graph nodes unless they are in allowed reveal strings."
    )


def _parse_openai_output(parsed: Any) -> OpenAIAuctionPreviewResolution:
    if parsed is None:
        raise ValueError("OpenAI oracle returned no parsed output")
    if isinstance(parsed, OpenAIAuctionPreviewResolution):
        return parsed
    if isinstance(parsed, dict):
        return OpenAIAuctionPreviewResolution.model_validate(parsed)
    raise ValueError("OpenAI oracle returned invalid parsed output")
