from __future__ import annotations

from typing import Any

from fastapi import Request

from hollow_lodge.server.projection_readiness import projection_read_ready


def projected_pending_decisions(
    request: Request,
    player_id: str,
    *,
    crew_ids: list[str] | tuple[str, ...],
) -> list[dict[str, Any]] | None:
    if not projection_read_ready(
        request,
        "HOLLOW_LODGE_PENDING_DECISION_PROJECTION_READS",
    ):
        return None
    try:
        return request.app.state.projection_store.read_pending_decisions(
            player_id,
            crew_ids=crew_ids,
        )
    except Exception:
        return None
