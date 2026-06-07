from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.auth import current_player
from hollow_lodge.server.services import ProofService


router = APIRouter(prefix="/proofs", tags=["proofs"])


class TransferProofRequest(BaseModel):
    recipient_player_id: str = Field(min_length=1)


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


def _proof_service(request: Request) -> ProofService:
    if not hasattr(request.app.state, "proof_service"):
        request.app.state.proof_service = ProofService(
            event_store=request.app.state.event_store,
            identity_service=request.app.state.identity_service,
        )
    return request.app.state.proof_service
