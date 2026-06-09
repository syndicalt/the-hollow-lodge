from __future__ import annotations

from typing import Any

from fastapi import Request

from hollow_lodge.server.projection_readiness import projection_read_ready


def projected_visible_chat_events(
    request: Request,
    player_id: str,
    *,
    conversation_id: str | None = None,
) -> list[dict[str, Any]] | None:
    if not projection_read_ready(request, "HOLLOW_LODGE_CHAT_PROJECTION_READS"):
        return None
    try:
        return request.app.state.projection_store.read_visible_chat_events(
            player_id,
            crew_ids=request.app.state.crew_service.crew_ids_for_player(player_id),
            conversation_id=conversation_id,
        )
    except Exception:
        return None
