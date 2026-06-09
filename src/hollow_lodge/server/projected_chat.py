from __future__ import annotations

import os
from typing import Any

from fastapi import Request


def projected_visible_chat_events(
    request: Request,
    player_id: str,
    *,
    conversation_id: str | None = None,
) -> list[dict[str, Any]] | None:
    if os.environ.get("HOLLOW_LODGE_CHAT_PROJECTION_READS") != "1":
        return None
    events = request.app.state.event_store.read()
    authoritative_last_sequence = events[-1].sequence if events else 0
    diagnostics = request.app.state.projection_store.diagnostics(
        authoritative_last_sequence=authoritative_last_sequence,
    )
    if diagnostics.get("status") != "available" or diagnostics.get("lag") != 0:
        return None
    try:
        return request.app.state.projection_store.read_visible_chat_events(
            player_id,
            crew_ids=request.app.state.crew_service.crew_ids_for_player(player_id),
            conversation_id=conversation_id,
        )
    except Exception:
        return None
