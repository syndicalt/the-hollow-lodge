from __future__ import annotations

from typing import Any

from fastapi import Request

from hollow_lodge.server.projection_readiness import projection_read_ready


def projected_visible_events(
    request: Request,
    player_id: str,
    *,
    since_sequence: int = 0,
) -> list[dict[str, Any]] | None:
    if not projection_read_ready(request, "HOLLOW_LODGE_VISIBLE_EVENT_PROJECTION_READS"):
        return None
    try:
        return request.app.state.projection_store.read_visible_events(
            player_id,
            crew_ids=request.app.state.crew_service.crew_ids_for_player(player_id),
            since_sequence=since_sequence,
        )
    except Exception:
        return None
