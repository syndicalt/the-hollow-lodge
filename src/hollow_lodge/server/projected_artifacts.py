from __future__ import annotations

import os
from typing import Any

from fastapi import Request


def projected_visible_artifacts(
    request: Request,
    player_id: str,
    *,
    crew_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
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
            crew_ids=(
                request.app.state.crew_service.crew_ids_for_player(player_id)
                if crew_ids is None
                else crew_ids
            ),
        )
    except Exception:
        return None
