from __future__ import annotations

from typing import Any

from fastapi import Request

from hollow_lodge.server.projection_readiness import projection_read_ready


def projected_current_actions_for_crew(
    request: Request,
    crew_id: str,
) -> list[dict[str, Any]] | None:
    if not projection_read_ready(request, "HOLLOW_LODGE_ACTION_PROJECTION_READS"):
        return None
    try:
        return request.app.state.projection_store.read_current_actions_for_crew(crew_id)
    except Exception:
        return None
