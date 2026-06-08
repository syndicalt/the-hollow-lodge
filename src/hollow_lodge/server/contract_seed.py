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


class ContractSeed(BaseModel):
    model_config = ConfigDict(frozen=True)

    campaign: Campaign
    contract: Contract
    hidden_truth: HiddenTruth
    artifact_graph: ArtifactGraph
    public_artifact_ids: tuple[str, ...] = Field(default_factory=tuple)
    scoring_hints: dict[str, Any] = Field(default_factory=dict)
    phase_rewards: tuple[PhaseReward, ...] = Field(default_factory=tuple)

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
        return self


def load_contract_seed_file(path: str | Path) -> ContractSeed:
    with Path(path).open(encoding="utf-8") as handle:
        return ContractSeed.model_validate(json.load(handle))
