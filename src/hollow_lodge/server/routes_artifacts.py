from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.artifact_service import ArtifactService
from hollow_lodge.server.auth import current_player


router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("")
def artifacts(
    request: Request,
    player: Player = Depends(current_player),
):
    return _artifact_service(request).visible_artifacts_for_player(player.player_id)


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
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="artifact not found",
        ) from exc


def _artifact_service(request: Request) -> ArtifactService:
    if not hasattr(request.app.state, "artifact_service"):
        request.app.state.artifact_service = ArtifactService(
            event_store=request.app.state.event_store,
        )
    return request.app.state.artifact_service
