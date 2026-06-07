from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Campaign(BaseModel):
    model_config = ConfigDict(frozen=True)

    campaign_id: str = Field(min_length=1)
    title: str = Field(min_length=1)


class ContractPhase(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    remaining_hours: int = Field(ge=0)


class EvidenceAsset(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    public_summary: str = Field(min_length=1)


class HiddenTruth(BaseModel):
    model_config = ConfigDict(frozen=True)

    truth_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    premise: str = Field(min_length=1)
    phase: ContractPhase
    evidence_assets: tuple[EvidenceAsset, ...]
    proof_dossier_needs: tuple[str, ...]
    crew_heat: int = Field(ge=0)
