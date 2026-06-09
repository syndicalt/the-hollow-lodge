from __future__ import annotations

from typing import Any

from fastapi import Request

from hollow_lodge.server.projection_config import projection_read_enabled


_DIAGNOSTICS_CACHE_ATTR = "_hollow_lodge_projection_diagnostics"
_EVENT_LOG_DIAGNOSTICS_CACHE_ATTR = "_hollow_lodge_event_log_diagnostics"


def projection_read_ready(request: Request, surface_env: str) -> bool:
    if not projection_read_enabled(surface_env):
        return False
    diagnostics = _projection_diagnostics(request)
    return diagnostics.get("status") == "available" and diagnostics.get("lag") == 0


def _projection_diagnostics(request: Request) -> dict[str, Any]:
    cached = getattr(request.state, _DIAGNOSTICS_CACHE_ATTR, None)
    if cached is not None:
        return cached
    authoritative_last_sequence = _authoritative_last_sequence(request)
    if authoritative_last_sequence < 0:
        diagnostics = {"status": "unavailable", "lag": None}
        setattr(request.state, _DIAGNOSTICS_CACHE_ATTR, diagnostics)
        return diagnostics
    diagnostics = request.app.state.projection_store.diagnostics(
        authoritative_last_sequence=authoritative_last_sequence,
    )
    setattr(request.state, _DIAGNOSTICS_CACHE_ATTR, diagnostics)
    return diagnostics


def _authoritative_last_sequence(request: Request) -> int:
    cached = getattr(request.state, _EVENT_LOG_DIAGNOSTICS_CACHE_ATTR, None)
    if cached is None:
        cached = request.app.state.event_store.diagnostics()
        setattr(request.state, _EVENT_LOG_DIAGNOSTICS_CACHE_ATTR, cached)
    if cached.get("status") == "unavailable":
        return -1
    sequence = cached.get("last_sequence")
    if sequence is None:
        return 0
    try:
        return int(sequence)
    except (TypeError, ValueError):
        return -1
