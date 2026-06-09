from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hollow_lodge.domain.artifact_graph import ArtifactGraph
from hollow_lodge.domain.contracts import Campaign, Contract, HiddenTruth


class PhaseReward(BaseModel):
    model_config = ConfigDict(frozen=True)

    phase: str = Field(min_length=1)
    trigger: Literal["phase_resolved"]
    award_to: Literal["standing_leader"]
    artifact_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class PhaseFollowUp(BaseModel):
    model_config = ConfigDict(frozen=True)

    phase: str = Field(min_length=1)
    trigger: Literal["phase_resolved"]
    seed: ContractSeed


class ContractUnlockRequirement(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: Literal["crew"]
    metric: Literal[
        "reputation",
        "favors",
        "deal_conduct_score",
        "completed_contract",
        "rumor_containment",
        "rumor_exploitation",
        "rumor_integration",
    ]
    required_contract_id: str | None = Field(default=None, min_length=1)
    minimum: int = Field(ge=0)
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_required_contract_target(self) -> ContractUnlockRequirement:
        if self.metric == "completed_contract":
            if self.required_contract_id is None:
                raise ValueError(
                    "completed_contract unlock requires required_contract_id"
                )
            if self.minimum < 1:
                raise ValueError(
                    "completed_contract unlock minimum must be at least 1"
                )
        elif self.required_contract_id is not None:
            raise ValueError(
                "required_contract_id only applies to completed_contract unlocks"
            )
        return self


class ContractSeed(BaseModel):
    model_config = ConfigDict(frozen=True)

    campaign: Campaign
    contract: Contract
    hidden_truth: HiddenTruth
    artifact_graph: ArtifactGraph
    public_artifact_ids: tuple[str, ...] = Field(default_factory=tuple)
    scoring_hints: dict[str, Any] = Field(default_factory=dict)
    phase_rewards: tuple[PhaseReward, ...] = Field(default_factory=tuple)
    phase_followups: tuple[PhaseFollowUp, ...] = Field(default_factory=tuple)
    unlock_requirements: tuple[ContractUnlockRequirement, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_seed_consistency(self) -> ContractSeed:
        if self.contract.campaign_id != self.campaign.campaign_id:
            raise ValueError("contract campaign mismatch")
        if self.artifact_graph.contract_id != self.contract.contract_id:
            raise ValueError("artifact graph contract mismatch")
        artifact_ids = {
            artifact.artifact_id
            for artifact in self.artifact_graph.artifacts
        }
        for artifact_id in self.public_artifact_ids:
            if artifact_id not in artifact_ids:
                raise ValueError(f"unknown public artifact: {artifact_id}")
        for reward in self.phase_rewards:
            if reward.artifact_id not in artifact_ids:
                raise ValueError(f"unknown phase reward artifact: {reward.artifact_id}")
            if reward.phase != self.contract.phase.name:
                raise ValueError(f"unknown phase reward phase: {reward.phase}")
        for follow_up in self.phase_followups:
            if follow_up.phase != self.contract.phase.name:
                raise ValueError(f"unknown phase follow-up phase: {follow_up.phase}")
            if follow_up.seed.contract.contract_id == self.contract.contract_id:
                raise ValueError("phase follow-up cannot reference parent contract")
            if follow_up.seed.contract.campaign_id != self.contract.campaign_id:
                raise ValueError("phase follow-up campaign mismatch")
            if (
                follow_up.seed.contract.arc is None
                or follow_up.seed.contract.arc.previous_contract_id
                != self.contract.contract_id
            ):
                raise ValueError(
                    "phase follow-up arc previous contract must reference parent contract"
                )
        return self


def load_contract_seed_file(path: str | Path) -> ContractSeed:
    with Path(path).open(encoding="utf-8") as handle:
        return ContractSeed.model_validate(json.load(handle))
