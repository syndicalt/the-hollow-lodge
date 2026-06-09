from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from hollow_lodge.domain.identity import Player
from hollow_lodge.eventlog.jsonl_store import IdempotencyConflictError
from hollow_lodge.server.artifact_service import ArtifactService
from hollow_lodge.server.auth import current_player


router = APIRouter(prefix="/artifacts", tags=["artifacts"])
logger = logging.getLogger(__name__)


class TransferArtifactRequest(BaseModel):
    recipient_player_id: str = Field(min_length=1)


@router.get("")
def artifacts(
    request: Request,
    player: Player = Depends(current_player),
):
    projected = _projected_visible_artifacts(request, player.player_id)
    if projected is not None:
        return projected
    return _artifact_service(request).visible_artifacts_for_player(
        player.player_id,
        crew_ids=_crew_ids_for_player(request, player.player_id),
    )


@router.get("/{artifact_id}")
def inspect_artifact(
    artifact_id: str,
    request: Request,
    player: Player = Depends(current_player),
):
    try:
        return _artifact_service(request).inspect_artifact(
            artifact_id=artifact_id,
            player_id=player.player_id,
            crew_ids=_crew_ids_for_player(request, player.player_id),
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="artifact not found",
        ) from exc


@router.post("/{artifact_id}/inspect")
def record_artifact_inspection(
    artifact_id: str,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    try:
        return _artifact_service(request).inspect_artifact(
            artifact_id=artifact_id,
            player_id=player.player_id,
            idempotency_key=idempotency_key,
            crew_ids=_crew_ids_for_player(request, player.player_id),
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="artifact not found",
        ) from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="idempotency key conflict",
        ) from exc


@router.post("/{artifact_id}/transfer", status_code=status.HTTP_201_CREATED)
def transfer_artifact(
    artifact_id: str,
    payload: TransferArtifactRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    if not request.app.state.identity_service.has_player(payload.recipient_player_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="recipient not found",
        )
    try:
        result = _artifact_service(request).transfer_artifact(
            artifact_id=artifact_id,
            sender_player_id=player.player_id,
            recipient_player_id=payload.recipient_player_id,
            idempotency_key=idempotency_key,
            sender_crew_ids=_crew_ids_for_player(request, player.player_id),
        )
        _refresh_projection_store(request)
        return result
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="artifact not found",
        ) from exc
    except (IdempotencyConflictError, ValueError) as exc:
        detail = "idempotency key conflict" if "idempotency key conflict" in str(exc) else str(exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from exc


def _artifact_service(request: Request) -> ArtifactService:
    if not hasattr(request.app.state, "artifact_service"):
        request.app.state.artifact_service = ArtifactService(
            event_store=request.app.state.event_store,
        )
    return request.app.state.artifact_service


def _projected_visible_artifacts(request: Request, player_id: str) -> dict | None:
    if os.environ.get("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS") != "1":
        return None
    events = request.app.state.event_store.read()
    authoritative_last_sequence = events[-1].sequence if events else 0
    diagnostics = request.app.state.projection_store.diagnostics(
        authoritative_last_sequence=authoritative_last_sequence,
    )
    if diagnostics.get("status") != "available" or diagnostics.get("lag") != 0:
        return None
    try:
        return request.app.state.projection_store.read_visible_artifacts(
            player_id,
            crew_ids=_crew_ids_for_player(request, player_id),
        )
    except Exception:
        return None


def _refresh_projection_store(request: Request) -> None:
    if hasattr(request.app.state, "projection_store"):
        try:
            request.app.state.projection_store.rebuild(
                request.app.state.event_store.read()
            )
        except Exception:
            logger.exception("failed to refresh artifact projection")


def _crew_ids_for_player(request: Request, player_id: str) -> list[str]:
    return request.app.state.crew_service.crew_ids_for_player(player_id)
