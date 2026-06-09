from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DossierTypedClaim(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object_id: str | None = Field(default=None, min_length=1)
    value: str | None = Field(default=None, min_length=1)
    citation_artifact_ids: tuple[str, ...] = ()


class ProofFragment(BaseModel):
    model_config = ConfigDict(frozen=True)

    fragment_id: str = Field(min_length=1)
    content_summary: str = Field(min_length=1)
    source_chain: tuple[str, ...]
    provenance_flags: tuple[str, ...] = ()
    provenance_checked: bool = False

    def copy_for_transfer(
        self,
        *,
        new_fragment_id: str,
        sender_player_id: str,
        recipient_player_id: str,
    ) -> ProofFragment:
        return self.model_copy(
            update={
                "fragment_id": new_fragment_id,
                "source_chain": (
                    *self.source_chain,
                    f"transfer:{sender_player_id}->{recipient_player_id}",
                ),
                "provenance_checked": False,
            }
        )

    def surface_view(self) -> dict:
        return {
            "fragment_id": self.fragment_id,
            "content_summary": self.content_summary,
            "source_chain": list(self.source_chain),
            "provenance_checked": self.provenance_checked,
        }

    def checked_view(self) -> dict:
        return {
            **self.surface_view(),
            "provenance_checked": True,
            "provenance_flags": list(self.provenance_flags),
        }


class ProofDossier(BaseModel):
    model_config = ConfigDict(frozen=True)

    dossier_id: str = Field(min_length=1)
    crew_id: str = Field(min_length=1)
    packet_lead_player_id: str = Field(min_length=1)
    claim: str = ""
    evidence_ids: tuple[str, ...] = ()
    reasoning: str = ""
    weaknesses: str = ""
    provenance_concerns: str = ""
    member_contributions: tuple[dict, ...] = ()
    artifact_citations: tuple[dict, ...] = ()
    typed_claims: tuple[DossierTypedClaim, ...] = ()

    @classmethod
    def empty(
        cls,
        *,
        dossier_id: str,
        crew_id: str,
        packet_lead_player_id: str,
    ) -> ProofDossier:
        return cls(
            dossier_id=dossier_id,
            crew_id=crew_id,
            packet_lead_player_id=packet_lead_player_id,
        )

    def with_framing(
        self,
        *,
        claim: str | None = None,
        evidence_ids: list[str] | tuple[str, ...] | None = None,
        reasoning: str | None = None,
        weaknesses: str | None = None,
        provenance_concerns: str | None = None,
    ) -> ProofDossier:
        return self.model_copy(
            update={
                "claim": self.claim if claim is None else claim,
                "evidence_ids": self.evidence_ids if evidence_ids is None else tuple(evidence_ids),
                "reasoning": self.reasoning if reasoning is None else reasoning,
                "weaknesses": self.weaknesses if weaknesses is None else weaknesses,
                "provenance_concerns": (
                    self.provenance_concerns
                    if provenance_concerns is None
                    else provenance_concerns
                ),
            }
        )

    def with_contribution(
        self,
        *,
        player_id: str,
        note: str,
        evidence_ids: list[str] | tuple[str, ...],
    ) -> ProofDossier:
        return self.model_copy(
            update={
                "member_contributions": (
                    *self.member_contributions,
                    {
                        "player_id": player_id,
                        "note": note,
                        "evidence_ids": list(evidence_ids),
                    },
                )
            }
        )

    def with_artifact_citation(
        self,
        *,
        player_id: str,
        artifact_id: str,
        claim: str,
        quote: str,
    ) -> ProofDossier:
        return self.model_copy(
            update={
                "artifact_citations": (
                    *self.artifact_citations,
                    {
                        "player_id": player_id,
                        "artifact_id": artifact_id,
                        "claim": claim,
                        "quote": quote,
                    },
                )
            }
        )

    def with_typed_claim(
        self,
        *,
        claim_id: str,
        subject_id: str,
        predicate: str,
        object_id: str | None = None,
        value: str | None = None,
        citation_artifact_ids: list[str] | tuple[str, ...] = (),
    ) -> ProofDossier:
        claim = DossierTypedClaim(
            claim_id=claim_id,
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            value=value,
            citation_artifact_ids=tuple(citation_artifact_ids),
        )
        return self.model_copy(update={"typed_claims": (*self.typed_claims, claim)})

    def with_packet_lead(self, player_id: str) -> ProofDossier:
        return self.model_copy(update={"packet_lead_player_id": player_id})
