from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AuctionPreviewScoreInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    crew_id: str = Field(min_length=1)
    claim: str = ""
    evidence_ids: tuple[str, ...] | list[str] = ()
    exposed_assets: tuple[str, ...] | list[str] = ()
    reasoning: str = ""
    weaknesses: str = ""
    provenance_concerns: str = ""
    action_intents: tuple[str, ...] | list[str] = ()
    crew_noise: int = Field(ge=0)


class AuctionPreviewScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    crew_id: str = Field(min_length=1)
    total: int = Field(ge=0)
    standing: str = Field(min_length=1)
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]
    penalties: tuple[str, ...]
    revealed_clues: tuple[str, ...]


def score_auction_preview(score_input: AuctionPreviewScoreInput) -> AuctionPreviewScore:
    text = _combined_text(score_input)
    evidence_ids = tuple(dict.fromkeys(score_input.evidence_ids))
    exposed_assets = tuple(dict.fromkeys(score_input.exposed_assets))
    strengths: list[str] = []
    weaknesses: list[str] = []
    penalties: list[str] = []
    revealed_clues: list[str] = []
    total = 0

    has_ledger = (
        "fragment_starter_ledger" in evidence_ids
        or "fragment_starter_ledger" in exposed_assets
    )
    has_provenance_work = any(
        marker in text
        for marker in (
            "provenance",
            "forged",
            "forgery",
            "date",
            "timestamp",
            "copied",
            "ink",
        )
    )
    if has_ledger and has_provenance_work:
        total += 64
        strengths.append("clean provenance contradiction")
        weaknesses.append("no material confirmation")
        revealed_clues.append("auction-house provenance is now suspect")

    has_occult_observation = any(
        marker in text
        for marker in (
            "omen",
            "moth",
            "door",
            "occult",
            "resonance",
        )
    )
    has_occult_support = "asset_door_omen" in exposed_assets
    if has_occult_observation and has_occult_support:
        total += 43
        strengths.append("occult clue may unlock alternate lane")
        weaknesses.append("uncorroborated omen")
        revealed_clues.append("sealed-door omen remains viable")

    if score_input.claim:
        total += 6
    if score_input.reasoning:
        total += min(12, len(score_input.reasoning.split()) // 2)
    if score_input.provenance_concerns:
        total += 8
    if not evidence_ids and has_occult_observation:
        total += 3
    if not strengths:
        weaknesses.append("no resolved proof lane")

    if "contaminated" in text:
        penalties.append("contaminated ledger chain")
        total = max(0, total - 5)
    if score_input.crew_noise:
        penalties.append("minor heat trace")
        total = max(0, total - score_input.crew_noise * 4)

    return AuctionPreviewScore(
        crew_id=score_input.crew_id,
        total=total,
        standing=_standing(total=total, strengths=strengths),
        strengths=tuple(strengths),
        weaknesses=tuple(dict.fromkeys(weaknesses)),
        penalties=tuple(penalties),
        revealed_clues=tuple(revealed_clues),
    )


def _combined_text(score_input: AuctionPreviewScoreInput) -> str:
    return " ".join(
        (
            score_input.claim,
            score_input.reasoning,
            score_input.weaknesses,
            score_input.provenance_concerns,
            " ".join(score_input.action_intents),
        )
    ).lower()


def _standing(*, total: int, strengths: list[str]) -> str:
    if total >= 70:
        return "Strong lead"
    if "occult clue may unlock alternate lane" in strengths:
        return "Viable but unstable"
    if total >= 40:
        return "Viable"
    return "Weak"
