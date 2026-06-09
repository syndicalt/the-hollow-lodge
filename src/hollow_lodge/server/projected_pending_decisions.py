from __future__ import annotations

from typing import Any

from fastapi import Request

from hollow_lodge.server.projection_config import projection_read_enabled


def projected_pending_decisions(
    request: Request,
    player_id: str,
    *,
    crew_ids: list[str] | tuple[str, ...],
) -> list[dict[str, Any]] | None:
    if not projection_read_enabled("HOLLOW_LODGE_PENDING_DECISION_PROJECTION_READS"):
        return None
    events = request.app.state.event_store.read()
    authoritative_last_sequence = events[-1].sequence if events else 0
    diagnostics = request.app.state.projection_store.diagnostics(
        authoritative_last_sequence=authoritative_last_sequence,
    )
    if diagnostics.get("status") != "available" or diagnostics.get("lag") != 0:
        return None
    try:
        return request.app.state.projection_store.read_pending_decisions(
            player_id,
            crew_ids=crew_ids,
        )
    except Exception:
        return None
