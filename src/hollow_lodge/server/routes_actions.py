from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.auth import current_player
from hollow_lodge.server.services import ActionService


router = APIRouter(prefix="/actions", tags=["actions"])


class SubmitActionRequest(BaseModel):
    crew_id: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    confirmed: bool


class EditActionRequest(BaseModel):
    intent: str = Field(min_length=1)


@router.post("", status_code=status.HTTP_201_CREATED)
def submit_action(
    payload: SubmitActionRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    try:
        return _action_service(request).submit_action(
            player_id=player.player_id,
            crew_id=payload.crew_id,
            intent=payload.intent,
            confirmed=payload.confirmed,
            idempotency_key=idempotency_key,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a crew member") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/{action_id}")
def edit_action(
    action_id: str,
    payload: EditActionRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    try:
        return _action_service(request).edit_action(
            action_id=action_id,
            player_id=player.player_id,
            intent=payload.intent,
            idempotency_key=idempotency_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="action not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/{action_id}")
def cancel_action(
    action_id: str,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    try:
        return _action_service(request).cancel_action(
            action_id=action_id,
            player_id=player.player_id,
            idempotency_key=idempotency_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="action not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _action_service(request: Request) -> ActionService:
    if not hasattr(request.app.state, "action_service"):
        request.app.state.action_service = ActionService(
            event_store=request.app.state.event_store,
            crew_service=request.app.state.crew_service,
        )
    return request.app.state.action_service
