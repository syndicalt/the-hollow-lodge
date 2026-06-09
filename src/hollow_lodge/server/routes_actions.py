from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.auth import current_player
from hollow_lodge.server.artifact_service import ArtifactService
from hollow_lodge.server.runtime_services import refresh_projection_store
from hollow_lodge.server.services import ActionService


router = APIRouter(prefix="/actions", tags=["actions"])
logger = logging.getLogger(__name__)


class SubmitActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crew_id: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    confirmed: bool
    rumor_id: str | None = Field(default=None, min_length=1)
    rumor_response_mode: Literal["investigate", "contain"] = "investigate"
    responds_to_rumor_escalation: bool = False
    rumor_escalation_mode: Literal["contain", "exploit", "integrate"] | None = None


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
        result = _action_service(request).submit_action(
            player_id=player.player_id,
            crew_id=payload.crew_id,
            intent=payload.intent,
            confirmed=payload.confirmed,
            rumor_id=payload.rumor_id,
            rumor_response_mode=payload.rumor_response_mode,
            responds_to_rumor_escalation=payload.responds_to_rumor_escalation,
            rumor_escalation_mode=payload.rumor_escalation_mode,
            idempotency_key=idempotency_key,
        )
        _refresh_projection_store(request)
        return result
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rumor not found") from exc
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
        result = _action_service(request).edit_action(
            action_id=action_id,
            player_id=player.player_id,
            intent=payload.intent,
            idempotency_key=idempotency_key,
        )
        _refresh_projection_store(request)
        return result
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
        result = _action_service(request).cancel_action(
            action_id=action_id,
            player_id=player.player_id,
            idempotency_key=idempotency_key,
        )
        _refresh_projection_store(request)
        return result
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="action not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _action_service(request: Request) -> ActionService:
    if not hasattr(request.app.state, "artifact_service"):
        request.app.state.artifact_service = ArtifactService(
            event_store=request.app.state.event_store,
        )
    if not hasattr(request.app.state, "action_service"):
        request.app.state.action_service = ActionService(
            event_store=request.app.state.event_store,
            crew_service=request.app.state.crew_service,
            artifact_service=request.app.state.artifact_service,
        )
    else:
        request.app.state.action_service.set_artifact_service(
            request.app.state.artifact_service,
        )
    return request.app.state.action_service


def _refresh_projection_store(request: Request) -> None:
    refresh_projection_store(request, context="actions", logger=logger)
