from __future__ import annotations

from typing import Any

from fastapi import Request

from hollow_lodge.server.projection_config import projection_read_enabled


_DIAGNOSTICS_CACHE_ATTR = "_hollow_lodge_projection_diagnostics"


def projection_read_ready(request: Request, surface_env: str) -> bool:
    if not projection_read_enabled(surface_env):
        return False
    diagnostics = _projection_diagnostics(request)
    return diagnostics.get("status") == "available" and diagnostics.get("lag") == 0


def _projection_diagnostics(request: Request) -> dict[str, Any]:
    cached = getattr(request.state, _DIAGNOSTICS_CACHE_ATTR, None)
    if cached is not None:
        return cached
    events = request.app.state.event_store.read()
    authoritative_last_sequence = events[-1].sequence if events else 0
    diagnostics = request.app.state.projection_store.diagnostics(
        authoritative_last_sequence=authoritative_last_sequence,
    )
    setattr(request.state, _DIAGNOSTICS_CACHE_ATTR, diagnostics)
    return diagnostics
