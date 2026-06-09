from __future__ import annotations

from typing import Any

from fastapi import Request

from hollow_lodge.server.projection_readiness import projection_read_ready


IDENTITY_ADMIN_PROJECTION_READS_ENV = "HOLLOW_LODGE_IDENTITY_ADMIN_PROJECTION_READS"


def projected_admin_players(request: Request) -> list[dict[str, Any]] | None:
    if not projection_read_ready(request, IDENTITY_ADMIN_PROJECTION_READS_ENV):
        return None
    try:
        return request.app.state.projection_store.read_admin_players()
    except Exception:
        return None


def projected_admin_invites(request: Request) -> list[dict[str, Any]] | None:
    if not projection_read_ready(request, IDENTITY_ADMIN_PROJECTION_READS_ENV):
        return None
    try:
        return request.app.state.projection_store.read_admin_invites()
    except Exception:
        return None


def projected_admin_key_requests(request: Request) -> list[dict[str, Any]] | None:
    if not projection_read_ready(request, IDENTITY_ADMIN_PROJECTION_READS_ENV):
        return None
    try:
        return request.app.state.projection_store.read_admin_key_requests()
    except Exception:
        return None
