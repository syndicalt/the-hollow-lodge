from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.auth import current_player
from hollow_lodge.server.services import ContractService


router = APIRouter(tags=["contracts"])


class LockAuctionPreviewRequest(BaseModel):
    hours_elapsed: int = Field(ge=0)


@router.get("/contracts")
def contracts(
    request: Request,
    player: Player = Depends(current_player),
):
    return _contract_service(request).board_for_player(player.player_id)


@router.get("/inbox")
def inbox(
    request: Request,
    player: Player = Depends(current_player),
):
    payload = _contract_service(request).inbox_for_player(player.player_id)
    payload["display_name"] = player.display_name
    return payload


@router.post("/contracts/{contract_id}/phases/auction-preview/lock")
def lock_auction_preview(
    contract_id: str,
    payload: LockAuctionPreviewRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    try:
        return _contract_service(request).lock_auction_preview(
            contract_id=contract_id,
            actor_id=player.player_id,
            hours_elapsed=payload.hours_elapsed,
            idempotency_key=idempotency_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contract not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _contract_service(request: Request) -> ContractService:
    if not hasattr(request.app.state, "contract_service"):
        request.app.state.contract_service = ContractService(
            event_store=request.app.state.event_store,
        )
    return request.app.state.contract_service
