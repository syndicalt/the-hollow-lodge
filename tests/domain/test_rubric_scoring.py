from __future__ import annotations

from hollow_lodge.domain.scoring import (
    ArtifactScoreContext,
    AuctionPreviewScoreInput,
    RubricFact,
    established_fact_ids,
    score_rubric_contract,
)

CONTEXTS = (
    ArtifactScoreContext(
        artifact_id="artifact_public_card",
        proof_lanes=("provenance",),
        hidden=False,
    ),
    ArtifactScoreContext(
        artifact_id="artifact_public_ledger",
        proof_lanes=("provenance", "leverage"),
        hidden=False,
    ),
    ArtifactScoreContext(
        artifact_id="artifact_hidden_witness",
        proof_lanes=("witness",),
        hidden=True,
    ),
)

FACTS = (
    RubricFact(
        fact_id="fact_contradiction",
        points=20,
        required_artifact_ids=("artifact_public_ledger", "artifact_hidden_witness"),
        reveal="The ledger now has a witness contradiction.",
    ),
)


def crew_input(**overrides) -> AuctionPreviewScoreInput:
    defaults = dict(
        crew_id="crew_0001",
        evidence_ids=(),
        artifact_citations=(),
        known_edges=(),
        exposed_assets=(),
        compiled_actions=(),
        typed_claims=(),
        crew_noise=0,
    )
    defaults.update(overrides)
    return AuctionPreviewScoreInput(**defaults)


def test_lane_coverage_and_corroboration_score():
    public_only = score_rubric_contract(
        crew_input(
            artifact_citations=({"artifact_id": "artifact_public_card"},),
        ),
        artifact_contexts=CONTEXTS,
        rubric_facts=FACTS,
    )

    assert public_only.total == 12
    assert "proved provenance lane" in public_only.strengths
    assert "single-lane proof" in public_only.weaknesses
    assert "only public source material" in public_only.weaknesses
    assert public_only.standing == "Weak"


def test_hidden_citations_and_facts_beat_public_only_play():
    investigator = score_rubric_contract(
        crew_input(
            artifact_citations=(
                {"artifact_id": "artifact_public_ledger"},
                {"artifact_id": "artifact_hidden_witness"},
            ),
            typed_claims=(
                {
                    "subject_id": "artifact_public_ledger",
                    "predicate": "contradicted_by",
                    "object_id": "artifact_hidden_witness",
                    "citation_artifact_ids": (
                        "artifact_public_ledger",
                        "artifact_hidden_witness",
                    ),
                },
            ),
        ),
        artifact_contexts=CONTEXTS,
        rubric_facts=FACTS,
    )
    checklister = score_rubric_contract(
        crew_input(
            artifact_citations=(
                {"artifact_id": "artifact_public_card"},
                {"artifact_id": "artifact_public_ledger"},
            ),
            typed_claims=(
                {
                    "subject_id": "artifact_public_card",
                    "predicate": "relates_to",
                    "object_id": "artifact_public_ledger",
                    "citation_artifact_ids": ("artifact_public_card",),
                },
            ),
        ),
        artifact_contexts=CONTEXTS,
        rubric_facts=FACTS,
    )

    # 3 lanes (36) + three-lane bonus (18) + hidden (8) + fact (20) + claims (2)
    assert investigator.total == 84
    assert investigator.standing == "Strong lead"
    assert "established 1 key fact" in investigator.strengths
    assert "The ledger now has a witness contradiction." in investigator.revealed_clues
    # 2 lanes (24) + two-lane bonus (10) + claims (2); no hidden, no facts
    assert checklister.total == 36
    assert checklister.standing == "Weak"
    assert "no key facts established" in checklister.weaknesses
    assert investigator.total > checklister.total


def test_facts_require_all_cited_artifacts_and_predicate():
    partial_citation = established_fact_ids(
        FACTS,
        (
            {
                "predicate": "contradicted_by",
                "citation_artifact_ids": ("artifact_public_ledger",),
            },
        ),
    )
    predicate_fact = RubricFact(
        fact_id="fact_predicate",
        points=10,
        required_artifact_ids=("artifact_hidden_witness",),
        required_predicate="places_carrier_elsewhere",
    )
    wrong_predicate = established_fact_ids(
        (predicate_fact,),
        (
            {
                "predicate": "relates_to",
                "citation_artifact_ids": ("artifact_hidden_witness",),
            },
        ),
    )
    right_predicate = established_fact_ids(
        (predicate_fact,),
        (
            {
                "predicate": "places_carrier_elsewhere",
                "citation_artifact_ids": ("artifact_hidden_witness",),
            },
        ),
    )

    assert partial_citation == ()
    assert wrong_predicate == ()
    assert right_predicate == ("fact_predicate",)


def test_foreign_contract_material_scores_nothing():
    score = score_rubric_contract(
        crew_input(
            artifact_citations=({"artifact_id": "artifact_other_contract"},),
            known_edges=(
                {
                    "source_id": "artifact_other_contract",
                    "target_id": "artifact_other_two",
                    "relation": "contradicts",
                },
            ),
            typed_claims=(
                {
                    "subject_id": "artifact_other_contract",
                    "predicate": "contradicts",
                    "citation_artifact_ids": ("artifact_other_contract",),
                },
            ),
        ),
        artifact_contexts=CONTEXTS,
        rubric_facts=FACTS,
    )

    assert score.total == 0
    assert "no proof lane covered" in score.weaknesses


def test_noise_and_contamination_penalties_apply():
    score = score_rubric_contract(
        crew_input(
            artifact_citations=(
                {"artifact_id": "artifact_public_card"},
                {"artifact_id": "artifact_public_ledger"},
            ),
            known_edges=(
                {
                    "source_id": "artifact_public_card",
                    "target_id": "artifact_public_ledger",
                    "relation": "contaminates",
                },
            ),
            crew_noise=2,
        ),
        artifact_contexts=CONTEXTS,
        rubric_facts=FACTS,
    )

    # 2 lanes (24) + bonus (10) + edge (3) - contamination (5) - noise (8)
    assert score.total == 24
    assert "contaminated ledger chain" in score.penalties
    assert "minor heat trace" in score.penalties
