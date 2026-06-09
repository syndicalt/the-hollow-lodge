from __future__ import annotations

from typing import Any

from fastapi import Request

from hollow_lodge.server.projection_config import projection_read_enabled


def projected_visible_artifacts(
    request: Request,
    player_id: str,
    *,
    crew_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    if not projection_read_enabled("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS"):
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
