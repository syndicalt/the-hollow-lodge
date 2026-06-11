"""Playability lint for packaged contract seeds.

These tests enforce the authoring invariants from docs/gm-guide.md:

- Every action-unlocked artifact must be reachable: at least one term in each
  of its term groups must appear verbatim in text a player can actually see
  before the unlock fires (contract premise, evidence asset summaries, public
  artifact text, or text revealed by an earlier reachable unlock).
- Every non-public artifact must have an unlock rule, or it is dead content.
- Every proof dossier need must have at least one supporting artifact.
- The hidden truth identifiers must not appear in any player-visible text.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hollow_lodge.domain.artifact_graph import ArtifactGraph
from hollow_lodge.domain.scoring import RubricFact

SEED_DIR = Path(__file__).resolve().parents[2] / "src" / "hollow_lodge" / "contract_seeds"
SEED_PATHS = sorted(SEED_DIR.glob("*.json"))

# Maps GM vocabulary used in proof_dossier_needs onto artifact proof lanes.
NEED_WORD_LANES = {
    "provenance": "provenance",
    "custody": "provenance",
    "chain": "provenance",
    "identity": "provenance",
    "material": "material",
    "residue": "material",
    "witness": "witness",
    "attendance": "witness",
    "testimony": "witness",
    "contradiction": "witness",
    "leverage": "leverage",
    "auction": "leverage",
    "pressure": "leverage",
    "ritual": "occult",
    "occult": "occult",
    "omen": "occult",
    "motive": "occult",
}


def seed_ids() -> list[str]:
    return [path.stem for path in SEED_PATHS]


@pytest.fixture(params=SEED_PATHS, ids=seed_ids())
def seed(request) -> dict:
    return json.loads(request.param.read_text(encoding="utf-8"))


def artifact_public_text(artifact: dict) -> str:
    return " ".join(
        (
            artifact.get("title", ""),
            artifact.get("public_summary", ""),
            artifact.get("full_text", ""),
        )
    ).casefold()


def contract_public_text(seed: dict) -> str:
    contract = seed["contract"]
    parts = [
        contract.get("title", ""),
        contract.get("premise", ""),
        contract.get("phase", {}).get("name", ""),
    ]
    parts.extend(contract.get("proof_dossier_needs", []))
    for asset in contract.get("evidence_assets", []):
        parts.append(asset.get("title", ""))
        parts.append(asset.get("public_summary", ""))
    return " ".join(parts).casefold()


def rule_term_groups(rule) -> list[tuple[str, ...]]:
    groups = [(term,) for term in rule.required_terms]
    groups.extend(tuple(group) for group in rule.required_term_groups)
    return groups


def test_seed_parses_into_domain_models(seed):
    graph = ArtifactGraph.model_validate(seed["artifact_graph"])
    assert graph.contract_id == seed["contract"]["contract_id"]


def test_every_unlock_is_reachable_from_public_text(seed):
    graph = ArtifactGraph.model_validate(seed["artifact_graph"])
    artifacts = {artifact.artifact_id: artifact for artifact in graph.artifacts}
    visible_ids = set(seed["public_artifact_ids"])
    reachable_text = contract_public_text(seed)
    for artifact_id in visible_ids:
        reachable_text += " " + artifact_public_text(
            artifacts[artifact_id].model_dump()
        )

    pending = [
        rule for rule in graph.unlock_rules if rule.trigger == "action_mentions_tag"
    ]
    progressed = True
    while pending and progressed:
        progressed = False
        still_pending = []
        for rule in pending:
            satisfied = all(
                any(term.casefold() in reachable_text for term in group)
                for group in rule_term_groups(rule)
            )
            if satisfied:
                visible_ids.add(rule.artifact_id)
                reachable_text += " " + artifact_public_text(
                    artifacts[rule.artifact_id].model_dump()
                )
                progressed = True
            else:
                still_pending.append(rule)
        pending = still_pending

    unreachable = {
        rule.rule_id: rule_term_groups(rule) for rule in pending
    }
    assert not unreachable, (
        "unlock rules whose terms never appear in player-reachable public text "
        f"(catch-22): {unreachable}"
    )


def test_every_hidden_artifact_has_an_unlock_rule(seed):
    graph = ArtifactGraph.model_validate(seed["artifact_graph"])
    public_ids = set(seed["public_artifact_ids"])
    unlockable_ids = {rule.artifact_id for rule in graph.unlock_rules}
    dead = [
        artifact.artifact_id
        for artifact in graph.artifacts
        if artifact.artifact_id not in public_ids
        and artifact.artifact_id not in unlockable_ids
    ]
    assert not dead, f"hidden artifacts with no unlock rule (dead content): {dead}"


def test_every_dossier_need_has_supporting_artifacts(seed):
    graph = ArtifactGraph.model_validate(seed["artifact_graph"])
    lanes = {lane for artifact in graph.artifacts for lane in artifact.proof_lanes}
    corpus = " ".join(
        artifact_public_text(artifact.model_dump()) for artifact in graph.artifacts
    )

    unsupported = []
    for need in seed["contract"]["proof_dossier_needs"]:
        words = [word.strip().casefold() for word in need.split()]
        lane_supported = any(
            NEED_WORD_LANES.get(word) in lanes for word in words
        )
        text_supported = any(
            len(word) >= 4 and word[:6] in corpus for word in words
        )
        if not (lane_supported or text_supported):
            unsupported.append(need)

    assert not unsupported, (
        "proof_dossier_needs with no supporting artifact lane or text: "
        f"{unsupported}"
    )


def test_rubric_facts_are_well_formed(seed):
    """Every packaged seed must carry scorable rubric facts.

    Facts are what differentiate competent crews at resolution; a seed
    without them scores on lane coverage alone and flattens the contest.
    """
    graph = ArtifactGraph.model_validate(seed["artifact_graph"])
    artifact_ids = {artifact.artifact_id for artifact in graph.artifacts}
    hints = seed.get("scoring_hints", {})
    allowed_reveals = set(hints.get("allowed_reveal_strings", ()))
    facts = [RubricFact.model_validate(fact) for fact in hints.get("rubric_facts", ())]

    assert facts, "seed has no rubric_facts in scoring_hints"
    seen_fact_ids: set[str] = set()
    for fact in facts:
        assert fact.fact_id not in seen_fact_ids, f"duplicate fact: {fact.fact_id}"
        seen_fact_ids.add(fact.fact_id)
        unknown = set(fact.required_artifact_ids) - artifact_ids
        assert not unknown, (
            f"fact {fact.fact_id} requires unknown artifacts: {sorted(unknown)}"
        )
        if fact.reveal:
            assert fact.reveal in allowed_reveals, (
                f"fact {fact.fact_id} reveal is not in allowed_reveal_strings: "
                f"{fact.reveal!r}"
            )


def test_hidden_truth_does_not_leak_into_public_text(seed):
    truth = seed["hidden_truth"]
    public_text = contract_public_text(seed)
    graph = ArtifactGraph.model_validate(seed["artifact_graph"])
    for artifact_id in seed["public_artifact_ids"]:
        artifact = next(
            a for a in graph.artifacts if a.artifact_id == artifact_id
        )
        public_text += " " + artifact_public_text(artifact.model_dump())

    assert truth["truth_id"].casefold() not in public_text
    assert truth["summary"].casefold() not in public_text
