from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


RUBRIC_SCORING_MODE = "rubric-v1"
LEGACY_SCORING_MODE = "legacy"

LANE_BASE_POINTS = 12
TWO_LANE_BONUS = 10
THREE_LANE_BONUS = 18
HIDDEN_CITATION_POINTS = 8
HIDDEN_CITATION_CAP = 24
EDGE_POINTS = 3
EDGE_CAP = 9
TYPED_CLAIM_POINTS = 2
TYPED_CLAIM_CAP = 6
CONTAMINATION_PENALTY = 5
NOISE_PENALTY_PER_POINT = 4


class RubricFact(BaseModel):
    """A hidden, seed-authored key fact worth points when a crew establishes it.

    A fact is established by a typed claim whose citations include every
    required artifact (and whose predicate matches, when one is specified).
    `reveal` must be one of the contract's allowed_reveal_strings; it is the
    only part of the fact that ever reaches players.
    """

    model_config = ConfigDict(frozen=True)

    fact_id: str = Field(min_length=1)
    points: int = Field(ge=1, le=40)
    required_artifact_ids: tuple[str, ...] = Field(min_length=1)
    required_predicate: str | None = Field(default=None, min_length=1)
    reveal: str = ""


class ArtifactScoreContext(BaseModel):
    """Per-artifact scoring metadata derived from the contract's seed graph."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(min_length=1)
    proof_lanes: tuple[str, ...] = ()
    hidden: bool = False


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


def _claim_field(claim: Any, field: str) -> Any:
    if isinstance(claim, dict):
        return claim.get(field)
    return getattr(claim, field, None)


def established_fact_ids(
    facts: tuple[RubricFact, ...] | list[RubricFact],
    typed_claims: tuple[Any, ...] | list[Any],
) -> tuple[str, ...]:
    """Which rubric facts the crew's typed claims establish.

    Pure and packet-derivable: both the scorer and the result validator use
    this, so standings and tiebreaks agree regardless of oracle provider.
    """
    established: list[str] = []
    for fact in facts:
        required = set(fact.required_artifact_ids)
        for claim in typed_claims:
            citations = set(_claim_field(claim, "citation_artifact_ids") or ())
            if not required.issubset(citations):
                continue
            if (
                fact.required_predicate is not None
                and _claim_field(claim, "predicate") != fact.required_predicate
            ):
                continue
            established.append(fact.fact_id)
            break
    return tuple(established)


def score_rubric_contract(
    score_input: AuctionPreviewScoreInput,
    *,
    artifact_contexts: tuple[ArtifactScoreContext, ...] | list[ArtifactScoreContext],
    rubric_facts: tuple[RubricFact, ...] | list[RubricFact] = (),
) -> AuctionPreviewScore:
    """Seed-driven scoring: lanes, corroboration, discovery depth, key facts.

    Only material belonging to this contract counts — citations, edges, and
    claims referencing other contracts' artifacts are ignored, so a crew's
    dossier history cannot leak points across contracts.
    """
    contexts = {context.artifact_id: context for context in artifact_contexts}
    strengths: list[str] = []
    weaknesses: list[str] = []
    penalties: list[str] = []
    revealed_clues: list[str] = []
    total = 0

    cited_ids = dict.fromkeys(
        citation["artifact_id"] if isinstance(citation, dict) else citation.artifact_id
        for citation in score_input.artifact_citations
    )
    for evidence_id in score_input.evidence_ids:
        if evidence_id in contexts:
            cited_ids.setdefault(evidence_id, None)
    cited_in_contract = [
        artifact_id for artifact_id in cited_ids if artifact_id in contexts
    ]

    lanes = sorted(
        {
            lane
            for artifact_id in cited_in_contract
            for lane in contexts[artifact_id].proof_lanes
        }
    )
    total += LANE_BASE_POINTS * len(lanes)
    strengths.extend(f"proved {lane} lane" for lane in lanes)
    if len(lanes) >= 3:
        total += THREE_LANE_BONUS
        strengths.append("corroborated across three lanes")
    elif len(lanes) == 2:
        total += TWO_LANE_BONUS
        strengths.append("corroborated across two lanes")

    hidden_cited = [
        artifact_id
        for artifact_id in cited_in_contract
        if contexts[artifact_id].hidden
    ]
    if hidden_cited:
        total += min(HIDDEN_CITATION_CAP, HIDDEN_CITATION_POINTS * len(hidden_cited))
        strengths.append("cited unlocked source material")

    contract_claims = [
        claim
        for claim in score_input.typed_claims
        if any(
            artifact_id in contexts
            for artifact_id in (_claim_field(claim, "citation_artifact_ids") or ())
        )
    ]
    established = established_fact_ids(tuple(rubric_facts), tuple(contract_claims))
    established_set = set(established)
    for fact in rubric_facts:
        if fact.fact_id in established_set:
            total += fact.points
            if fact.reveal:
                revealed_clues.append(fact.reveal)
    if established:
        plural = "s" if len(established) > 1 else ""
        strengths.append(f"established {len(established)} key fact{plural}")

    contract_edges = [
        edge
        for edge in score_input.known_edges
        if isinstance(edge, dict)
        and edge.get("source_id") in contexts
        and edge.get("target_id") in contexts
    ]
    if contract_edges:
        total += min(EDGE_CAP, EDGE_POINTS * len(contract_edges))
    if contract_claims:
        total += min(TYPED_CLAIM_CAP, TYPED_CLAIM_POINTS * len(contract_claims))

    if not lanes:
        weaknesses.append("no proof lane covered")
    elif len(lanes) == 1:
        weaknesses.append("single-lane proof")
    if not hidden_cited:
        weaknesses.append("only public source material")
    if rubric_facts and not established:
        weaknesses.append("no key facts established")

    if any(edge.get("relation") == "contaminates" for edge in contract_edges):
        penalties.append("contaminated ledger chain")
        total = max(0, total - CONTAMINATION_PENALTY)
    if score_input.crew_noise:
        penalties.append("minor heat trace")
        total = max(0, total - score_input.crew_noise * NOISE_PENALTY_PER_POINT)

    if total >= 70:
        standing = "Strong lead"
    elif total >= 40:
        standing = "Viable"
    else:
        standing = "Weak"
    return AuctionPreviewScore(
        crew_id=score_input.crew_id,
        total=total,
        standing=standing,
        strengths=tuple(dict.fromkeys(strengths)),
        weaknesses=tuple(dict.fromkeys(weaknesses)),
        penalties=tuple(penalties),
        revealed_clues=tuple(dict.fromkeys(revealed_clues)),
    )
