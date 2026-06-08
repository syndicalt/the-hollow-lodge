from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ArtifactKind = Literal[
    "lot_card",
    "ledger",
    "letter",
    "receipt",
    "witness_note",
    "rubbing",
    "omen",
    "catalogue",
    "other",
]
ProofLane = Literal["provenance", "material", "witness", "occult", "leverage"]
CopyPolicy = Literal["copyable", "excerpt_only", "sealed"]


class ArtifactNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    kind: ArtifactKind
    public_summary: str = Field(min_length=1)
    full_text: str = Field(min_length=1)
    source_chain: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    proof_lanes: tuple[ProofLane, ...] = ()
    phase_relevance: tuple[str, ...] = ()
    hidden_flags: tuple[str, ...] = ()
    visible_flags: tuple[str, ...] = ()
    copy_policy: CopyPolicy = "copyable"

    def surface_view(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "contract_id": self.contract_id,
            "title": self.title,
            "kind": self.kind,
            "public_summary": self.public_summary,
            "visible_flags": list(self.visible_flags),
            "proof_lanes": list(self.proof_lanes),
            "phase_relevance": list(self.phase_relevance),
            "copy_policy": self.copy_policy,
        }

    def inspection_view(self) -> dict:
        return {
            **self.surface_view(),
            "full_text": self.full_text,
            "source_chain": list(self.source_chain),
        }


class ArtifactCopy(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(min_length=1)
    source_artifact_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    public_summary: str = Field(min_length=1)
    source_chain: tuple[str, ...]
    visible_flags: tuple[str, ...] = ("copy",)
    contamination_flags: tuple[str, ...] = ()

    @classmethod
    def from_source(
        cls,
        *,
        source_artifact_id: str,
        copy_artifact_id: str,
        contract_id: str,
        sender_player_id: str,
        recipient_player_id: str,
        title: str,
        public_summary: str,
    ) -> ArtifactCopy:
        return cls(
            artifact_id=copy_artifact_id,
            source_artifact_id=source_artifact_id,
            contract_id=contract_id,
            title=title,
            public_summary=public_summary,
            source_chain=(
                f"artifact:{source_artifact_id}",
                f"transfer:{sender_player_id}->{recipient_player_id}",
            ),
        )

    def surface_view(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "source_artifact_id": self.source_artifact_id,
            "contract_id": self.contract_id,
            "title": self.title,
            "public_summary": self.public_summary,
            "visible_flags": list(self.visible_flags),
            "contamination_flags": list(self.contamination_flags),
            "is_copy": True,
        }
