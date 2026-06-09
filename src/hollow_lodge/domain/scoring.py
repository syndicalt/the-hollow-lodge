from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AuctionPreviewScoreInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    crew_id: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] | list[str] = ()
    artifact_citations: tuple[dict, ...] | list[dict] = ()
    known_edges: tuple[dict, ...] | list[dict] = ()
    exposed_assets: tuple[str, ...] | list[str] = ()
    compiled_actions: tuple[dict, ...] | list[dict] = ()
    typed_claims: tuple[dict, ...] | list[dict] = ()
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
    evidence_ids = tuple(dict.fromkeys(score_input.evidence_ids))
    exposed_assets = tuple(dict.fromkeys(score_input.exposed_assets))
    compiled_actions = tuple(score_input.compiled_actions)
    known_edges = tuple(score_input.known_edges)
    typed_claims = tuple(score_input.typed_claims)
    strengths: list[str] = []
    weaknesses: list[str] = []
    penalties: list[str] = []
    revealed_clues: list[str] = []
    total = 0

    evidence_set = set(evidence_ids) | set(exposed_assets)
    action_approaches = {
        str(action.get("approach", ""))
        for action in compiled_actions
        if isinstance(action, dict)
    }
    has_ledger = (
        "fragment_starter_ledger" in evidence_set
        or "artifact_ledger_rubric" in evidence_set
    )
    has_provenance_work = bool(
        action_approaches
        & {
            "provenance_research",
            "forgery_analysis",
            "surveillance",
        }
    ) or any(
        isinstance(edge, dict)
        and edge.get("relation") in {"contradicts", "copies", "points_to"}
        for edge in known_edges
    )
    if has_ledger and has_provenance_work:
        total += 70
        strengths.append("clean provenance contradiction")
        weaknesses.append("no material confirmation")
        revealed_clues.append("auction-house provenance is now suspect")

    has_occult_observation = "occult_analysis" in action_approaches
    has_occult_support = "asset_door_omen" in evidence_set
    if has_occult_observation and has_occult_support:
        total += 43
        strengths.append("occult clue may unlock alternate lane")
        weaknesses.append("uncorroborated omen")
        revealed_clues.append("sealed-door omen remains viable")

    if typed_claims:
        total += min(12, 4 * len(typed_claims))
    if score_input.artifact_citations:
        total += min(12, 4 * len(score_input.artifact_citations))
    if known_edges:
        total += min(8, 4 * len(known_edges))
    if not evidence_ids and has_occult_observation:
        total += 3
    if not strengths:
        weaknesses.append("no resolved proof lane")

    if any(
        isinstance(edge, dict) and edge.get("relation") == "contaminates"
        for edge in known_edges
    ):
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


def _standing(*, total: int, strengths: list[str]) -> str:
    if total >= 70:
        return "Strong lead"
    if "occult clue may unlock alternate lane" in strengths:
        return "Viable but unstable"
    if total >= 40:
        return "Viable"
    return "Weak"
