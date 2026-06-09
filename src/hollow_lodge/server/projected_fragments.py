from __future__ import annotations

from typing import Any

from fastapi import Request

from hollow_lodge.server.projection_readiness import projection_read_ready


def projected_proof_fragment(
    request: Request,
    player_id: str,
    fragment_id: str,
) -> dict[str, Any] | None:
    if not projection_read_ready(
        request,
        "HOLLOW_LODGE_PROOF_FRAGMENT_PROJECTION_READS",
    ):
        return None
    try:
        return request.app.state.projection_store.read_proof_fragment(
            player_id,
            fragment_id,
        )
    except Exception:
        return None
