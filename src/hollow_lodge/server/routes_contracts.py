from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.auth import current_player
from hollow_lodge.server.services import ContractService


router = APIRouter(tags=["contracts"])


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
    return _contract_service(request).inbox_for_player(player.player_id)


def _contract_service(request: Request) -> ContractService:
    if not hasattr(request.app.state, "contract_service"):
        request.app.state.contract_service = ContractService(
            event_store=request.app.state.event_store,
        )
    return request.app.state.contract_service
