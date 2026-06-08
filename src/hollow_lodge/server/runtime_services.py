from __future__ import annotations

from fastapi import Request

from hollow_lodge.server.artifact_service import ArtifactService
from hollow_lodge.server.deal_service import DealService


def ensure_artifact_service(request: Request) -> ArtifactService:
    if not hasattr(request.app.state, "artifact_service"):
        request.app.state.artifact_service = ArtifactService(
            event_store=request.app.state.event_store,
        )
    artifact_service = request.app.state.artifact_service
    request.app.state.chat_service.set_artifact_service(artifact_service)
    request.app.state.action_service.set_artifact_service(artifact_service)
    return artifact_service


def ensure_deal_service(request: Request) -> DealService:
    artifact_service = ensure_artifact_service(request)
    if not hasattr(request.app.state, "deal_service"):
        request.app.state.deal_service = DealService(
            event_store=request.app.state.event_store,
            crew_service=request.app.state.crew_service,
            artifact_service=artifact_service,
        )
    return request.app.state.deal_service
