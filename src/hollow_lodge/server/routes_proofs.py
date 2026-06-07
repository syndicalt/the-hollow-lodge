from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.auth import current_player
from hollow_lodge.server.services import ProofService


router = APIRouter(prefix="/proofs", tags=["proofs"])


class TransferProofRequest(BaseModel):
    recipient_player_id: str = Field(min_length=1)


class DossierFramingRequest(BaseModel):
    claim: str | None = None
    evidence_ids: list[str] | None = None
    reasoning: str | None = None
    weaknesses: str | None = None
    provenance_concerns: str | None = None


class DossierContributionRequest(BaseModel):
    note: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class PacketLeadVoteRequest(BaseModel):
    candidate_player_id: str = Field(min_length=1)


@router.get("/fragments/{fragment_id}")
def get_fragment(
    fragment_id: str,
    request: Request,
    player: Player = Depends(current_player),
):
    try:
        return _proof_service(request).fragment_for_player(
            fragment_id=fragment_id,
            player_id=player.player_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="fragment not found") from exc


@router.post(
    "/fragments/{fragment_id}/transfer",
    status_code=status.HTTP_201_CREATED,
)
def transfer_fragment(
    fragment_id: str,
    payload: TransferProofRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    try:
        return _proof_service(request).transfer_fragment(
            fragment_id=fragment_id,
            sender_player_id=player.player_id,
            recipient_player_id=payload.recipient_player_id,
            idempotency_key=idempotency_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="fragment not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/fragments/{fragment_id}/check/provenance",
    status_code=status.HTTP_201_CREATED,
)
def check_fragment_provenance(
    fragment_id: str,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    try:
        return _proof_service(request).check_provenance(
            fragment_id=fragment_id,
            player_id=player.player_id,
            idempotency_key=idempotency_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="fragment not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/dossiers/{crew_id}")
def get_dossier(
    crew_id: str,
    request: Request,
    player: Player = Depends(current_player),
):
    try:
        return _proof_service(request).dossier_for_crew(
            crew_id=crew_id,
            player_id=player.player_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a crew member") from exc


@router.patch("/dossiers/{crew_id}/framing")
def update_dossier_framing(
    crew_id: str,
    payload: DossierFramingRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    try:
        return _proof_service(request).update_dossier_framing(
            crew_id=crew_id,
            player_id=player.player_id,
            updates=payload.model_dump(exclude_unset=True),
            idempotency_key=idempotency_key,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/dossiers/{crew_id}/contributions", status_code=status.HTTP_201_CREATED)
def add_dossier_contribution(
    crew_id: str,
    payload: DossierContributionRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    try:
        return _proof_service(request).add_dossier_contribution(
            crew_id=crew_id,
            player_id=player.player_id,
            note=payload.note,
            evidence_ids=payload.evidence_ids,
            idempotency_key=idempotency_key,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a crew member") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/dossiers/{crew_id}/packet-lead/votes")
def vote_packet_lead(
    crew_id: str,
    payload: PacketLeadVoteRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    try:
        return _proof_service(request).vote_packet_lead(
            crew_id=crew_id,
            voter_player_id=player.player_id,
            candidate_player_id=payload.candidate_player_id,
            idempotency_key=idempotency_key,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a crew member") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _proof_service(request: Request) -> ProofService:
    if not hasattr(request.app.state, "proof_service"):
        request.app.state.proof_service = ProofService(
            event_store=request.app.state.event_store,
            identity_service=request.app.state.identity_service,
            crew_service=request.app.state.crew_service,
        )
    return request.app.state.proof_service
