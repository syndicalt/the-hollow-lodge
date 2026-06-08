from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.auth import current_player
from hollow_lodge.server.deal_service import DealService
from hollow_lodge.server.runtime_services import ensure_deal_service


router = APIRouter(prefix="/deals", tags=["deals"])


class ProposeDealRequest(BaseModel):
    contract_id: str = Field(min_length=1)
    proposer_crew_id: str = Field(min_length=1)
    recipient_crew_id: str = Field(min_length=1)
    offered_artifact_ids: list[str] = Field(min_length=1)
    requested_artifact_ids: list[str] = Field(min_length=1)
    soft_terms: list[str] = Field(default_factory=list)
    expires_phase: str | None = None


@router.get("")
def list_deals(
    request: Request,
    player: Player = Depends(current_player),
) -> dict[str, list[dict]]:
    return {"deals": _deal_service(request).list_for_player(player.player_id)}


@router.post("", status_code=status.HTTP_201_CREATED)
def propose_deal(
    payload: ProposeDealRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
) -> dict:
    try:
        return _deal_service(request).propose(
            contract_id=payload.contract_id,
            proposer_crew_id=payload.proposer_crew_id,
            recipient_crew_id=payload.recipient_crew_id,
            offered_artifact_ids=payload.offered_artifact_ids,
            requested_artifact_ids=payload.requested_artifact_ids,
            soft_terms=payload.soft_terms,
            expires_phase=payload.expires_phase,
            proposer_player_id=player.player_id,
            idempotency_key=idempotency_key,
        )
    except (PermissionError, KeyError, ValueError) as exc:
        raise _deal_http_exception(exc) from exc


@router.post("/{deal_id}/accept")
def accept_deal(
    deal_id: str,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
) -> dict:
    try:
        return _deal_service(request).accept(
            deal_id=deal_id,
            actor_player_id=player.player_id,
            idempotency_key=idempotency_key,
        )
    except (PermissionError, KeyError, ValueError) as exc:
        raise _deal_http_exception(exc, deal_id=deal_id) from exc


@router.post("/{deal_id}/decline")
def decline_deal(
    deal_id: str,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
) -> dict:
    try:
        return _deal_service(request).decline(
            deal_id=deal_id,
            actor_player_id=player.player_id,
            idempotency_key=idempotency_key,
        )
    except (PermissionError, KeyError, ValueError) as exc:
        raise _deal_http_exception(exc, deal_id=deal_id) from exc


@router.post("/{deal_id}/cancel")
def cancel_deal(
    deal_id: str,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
) -> dict:
    try:
        return _deal_service(request).cancel(
            deal_id=deal_id,
            actor_player_id=player.player_id,
            idempotency_key=idempotency_key,
        )
    except (PermissionError, KeyError, ValueError) as exc:
        raise _deal_http_exception(exc, deal_id=deal_id) from exc


def _deal_service(request: Request) -> DealService:
    return ensure_deal_service(request)


def _deal_http_exception(
    exc: PermissionError | KeyError | ValueError,
    *,
    deal_id: str | None = None,
) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, KeyError):
        if deal_id is not None and exc.args == (deal_id,):
            detail = "deal not found"
        else:
            detail = "crew not found" if exc.args == ("crew not found",) else "artifact not found"
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
