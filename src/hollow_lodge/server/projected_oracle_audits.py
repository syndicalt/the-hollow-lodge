from __future__ import annotations

from typing import Any

from fastapi import Request

from hollow_lodge.server.projection_readiness import projection_read_ready


def projected_oracle_audits(request: Request) -> list[dict[str, Any]] | None:
    if not projection_read_ready(
        request,
        "HOLLOW_LODGE_ORACLE_AUDIT_PROJECTION_READS",
    ):
        return None
    try:
        return request.app.state.projection_store.read_oracle_audits()
    except Exception:
        return None
