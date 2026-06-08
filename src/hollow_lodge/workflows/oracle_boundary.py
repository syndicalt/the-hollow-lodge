from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AuctionPreviewCrewPacket(BaseModel):
    model_config = ConfigDict(frozen=True)

    crew_id: str = Field(min_length=1)
    claim: str = ""
    reasoning: str = ""
    weaknesses: str = ""
    provenance_concerns: str = ""
    evidence_ids: tuple[str, ...] = ()
    exposed_assets: tuple[str, ...] = ()
    action_intents: tuple[str, ...] = ()
    crew_noise: int = Field(ge=0)


class AuctionPreviewOraclePacket(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    hidden_truth_summary: str = ""
    allowed_reveal_strings: tuple[str, ...] = ()
    rubric_hooks: tuple[str, ...] = ()
    crews: tuple[AuctionPreviewCrewPacket, ...]
    allowed_evidence_ids: tuple[str, ...] = ()
    score_min: int = Field(default=0, ge=0)
    score_max: int = Field(default=100, ge=1)

    @model_validator(mode="after")
    def validate_score_bounds(self) -> Self:
        if self.score_max < self.score_min:
            raise ValueError("score_max must be greater than or equal to score_min")
        return self


class OracleProviderMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)
    model: str | None = None
    prompt_version: str = Field(min_length=1)


class AuctionPreviewCrewResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    crew_id: str = Field(min_length=1)
    score: int = Field(ge=0)
    standing: str = Field(min_length=1)
    strengths: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    penalties: tuple[str, ...] = ()
    revealed_clues: tuple[str, ...] = ()


class AuctionPreviewOracleResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: OracleProviderMetadata
    standings: tuple[AuctionPreviewCrewResult, ...]
    contract_state: tuple[str, ...] = ()
    narration: str = ""
    validation_warnings: tuple[str, ...] = ()


class ResolutionOracle(Protocol):
    def resolve_auction_preview(
        self,
        packet: AuctionPreviewOraclePacket,
    ) -> AuctionPreviewOracleResult:
        """Resolve an Auction Preview packet into a candidate oracle result."""


_HIDDEN_TRUTH_PHRASES = (
    "saint-bone forgery",
    "real debtor's omen",
    "truth_false_finger_forgery",
)


def validate_auction_preview_result(
    *,
    packet: AuctionPreviewOraclePacket,
    result: AuctionPreviewOracleResult,
) -> AuctionPreviewOracleResult:
    """Accept, normalize, or reject an Auction Preview oracle candidate."""
    packet_crew_ids = _unique_crew_ids(crew.crew_id for crew in packet.crews)
    seen_result_crew_ids: set[str] = set()
    accepted_standings: list[AuctionPreviewCrewResult] = []

    for standing in result.standings:
        if standing.crew_id in seen_result_crew_ids:
            raise ValueError(f"duplicate crew id: {standing.crew_id}")
        seen_result_crew_ids.add(standing.crew_id)

        if standing.crew_id not in packet_crew_ids:
            raise ValueError(f"unknown crew id: {standing.crew_id}")

        _reject_unsafe_reveals(packet=packet, lines=standing.revealed_clues)
        accepted_standings.append(
            standing.model_copy(
                update={
                    "score": _clamp_score(
                        score=standing.score,
                        score_min=packet.score_min,
                        score_max=packet.score_max,
                    )
                }
            )
        )

    _reject_unsafe_reveals(packet=packet, lines=result.contract_state)
    _reject_hidden_truth_leak(packet=packet, result=result)

    ordered_standings = tuple(
        sorted(
            accepted_standings,
            key=lambda standing: (-standing.score, standing.crew_id),
        )
    )
    return result.model_copy(update={"standings": ordered_standings})


def _unique_crew_ids(crew_ids: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    for crew_id in crew_ids:
        if crew_id in seen:
            raise ValueError(f"duplicate crew id: {crew_id}")
        seen.add(crew_id)
    return seen


def _clamp_score(*, score: int, score_min: int, score_max: int) -> int:
    return max(score_min, min(score, score_max))


def _reject_unsafe_reveals(
    *,
    packet: AuctionPreviewOraclePacket,
    lines: tuple[str, ...],
) -> None:
    allowed_reveals = set(packet.allowed_reveal_strings)
    for line in lines:
        if line not in allowed_reveals:
            raise ValueError(f"unsafe reveal: {line}")


def _reject_hidden_truth_leak(
    *,
    packet: AuctionPreviewOraclePacket,
    result: AuctionPreviewOracleResult,
) -> None:
    hidden_truth = packet.hidden_truth_summary.casefold()
    phrases = [phrase for phrase in _HIDDEN_TRUTH_PHRASES if phrase in hidden_truth]
    if hidden_truth.strip():
        phrases.append(hidden_truth.strip())

    if not phrases:
        return

    searchable_text = "\n".join(_result_text_lines(result)).casefold()
    for phrase in phrases:
        if phrase and phrase in searchable_text:
            raise ValueError(f"hidden truth leak: {phrase}")


def _result_text_lines(result: AuctionPreviewOracleResult) -> tuple[str, ...]:
    lines: list[str] = [
        result.provider.provider,
        result.provider.model or "",
        result.provider.prompt_version,
        result.narration,
        *result.contract_state,
        *result.validation_warnings,
    ]
    for standing in result.standings:
        lines.extend(
            (
                standing.crew_id,
                standing.standing,
                *standing.strengths,
                *standing.weaknesses,
                *standing.penalties,
                *standing.revealed_clues,
            )
        )
    return tuple(lines)
