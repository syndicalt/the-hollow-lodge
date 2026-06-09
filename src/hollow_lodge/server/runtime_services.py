from __future__ import annotations

import logging
from typing import Any

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


def refresh_projection_store(
    request: Request,
    *,
    context: str,
    logger: logging.Logger,
) -> None:
    if not hasattr(request.app.state, "projection_store"):
        return
    events = request.app.state.event_store.read()
    last_sequence = events[-1].sequence if events else 0
    try:
        request.app.state.projection_store.rebuild(events)
    except Exception as exc:
        _record_projection_refresh_failure(
            request.app.state,
            context=context,
            error_type=exc.__class__.__name__,
        )
        logger.exception("failed to refresh projection store for %s", context)
        return
    record_projection_refresh_success(
        request.app.state,
        context=context,
        last_sequence=last_sequence,
    )


def record_projection_refresh_success(
    state: Any,
    *,
    context: str,
    last_sequence: int,
) -> None:
    previous = getattr(state, "projection_refresh", {})
    state.projection_refresh = {
        "status": "ok",
        "last_context": context,
        "last_success_sequence": last_sequence,
        "failure_count": int(previous.get("failure_count", 0)),
        "last_failure": None,
    }


def projection_refresh_diagnostics(state: Any) -> dict[str, Any]:
    return dict(
        getattr(
            state,
            "projection_refresh",
            {
                "status": "not_refreshed",
                "last_context": None,
                "last_success_sequence": None,
                "failure_count": 0,
                "last_failure": None,
            },
        )
    )


def _record_projection_refresh_failure(
    state: Any,
    *,
    context: str,
    error_type: str,
) -> None:
    previous = projection_refresh_diagnostics(state)
    state.projection_refresh = {
        "status": "failed",
        "last_context": context,
        "last_success_sequence": previous.get("last_success_sequence"),
        "failure_count": int(previous.get("failure_count", 0)) + 1,
        "last_failure": {
            "context": context,
            "error_type": error_type,
        },
    }
