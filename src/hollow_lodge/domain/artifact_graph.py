from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hollow_lodge.domain.artifacts import ArtifactNode


ArtifactRelation = Literal[
    "supports",
    "contradicts",
    "mentions",
    "copies",
    "unlocks",
    "requires",
    "contaminates",
    "points_to",
]
ArtifactVisibility = Literal["server_only", "when_both_visible", "public"]
ArtifactUnlockTrigger = Literal[
    "action_exposes_asset",
    "action_mentions_tag",
    "provenance_checked",
    "dossier_cites",
    "phase_resolved",
    "manual_award",
]
ArtifactAwardScope = Literal["player", "crew"]


class ArtifactEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    relation: ArtifactRelation
    visibility: ArtifactVisibility = "when_both_visible"
    public_summary: str = ""

    def surface_view(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "public_summary": self.public_summary,
        }


class ArtifactUnlockRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    trigger: ArtifactUnlockTrigger
    required_terms: tuple[str, ...] = ()
    required_artifact_ids: tuple[str, ...] = ()
    award_scope: ArtifactAwardScope = "crew"
    award_reason: str = Field(min_length=1)


class ArtifactGraph(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_id: str = Field(min_length=1)
    artifacts: tuple[ArtifactNode, ...]
    edges: tuple[ArtifactEdge, ...] = ()
    unlock_rules: tuple[ArtifactUnlockRule, ...] = ()

    @model_validator(mode="after")
    def validate_references(self) -> ArtifactGraph:
        artifact_ids: set[str] = set()
        for artifact in self.artifacts:
            if artifact.artifact_id in artifact_ids:
                raise ValueError(f"duplicate artifact id: {artifact.artifact_id}")
            if artifact.contract_id != self.contract_id:
                raise ValueError(f"artifact contract mismatch: {artifact.artifact_id}")
            artifact_ids.add(artifact.artifact_id)

        for rule in self.unlock_rules:
            if rule.contract_id != self.contract_id:
                raise ValueError(f"unlock contract mismatch: {rule.rule_id}")

        for edge in self.edges:
            if edge.source_id not in artifact_ids:
                raise ValueError(f"unknown edge source: {edge.source_id}")
            if edge.target_id not in artifact_ids:
                raise ValueError(f"unknown edge target: {edge.target_id}")

        for rule in self.unlock_rules:
            if rule.artifact_id not in artifact_ids:
                raise ValueError(f"unknown unlock artifact: {rule.artifact_id}")
            for artifact_id in rule.required_artifact_ids:
                if artifact_id not in artifact_ids:
                    raise ValueError(f"unknown required artifact: {artifact_id}")

        return self

    def artifact_by_id(self, artifact_id: str) -> ArtifactNode:
        for artifact in self.artifacts:
            if artifact.artifact_id == artifact_id:
                return artifact
        raise KeyError(artifact_id)

    def visible_slice(self, visible_artifact_ids: set[str]) -> dict:
        visible_artifacts = [
            artifact
            for artifact in self.artifacts
            if artifact.artifact_id in visible_artifact_ids
        ]
        visible_edges = [
            edge
            for edge in self.edges
            if edge.visibility != "server_only"
            and edge.source_id in visible_artifact_ids
            and edge.target_id in visible_artifact_ids
        ]

        return {
            "contract_id": self.contract_id,
            "artifacts": [artifact.surface_view() for artifact in visible_artifacts],
            "edges": [edge.surface_view() for edge in visible_edges],
        }
