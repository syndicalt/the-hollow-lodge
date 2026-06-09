from __future__ import annotations

import os
from typing import Any

from fastapi import Request


def projected_proof_dossier(
    request: Request,
    crew_id: str,
) -> dict[str, Any] | None:
    if os.environ.get("HOLLOW_LODGE_PROOF_DOSSIER_PROJECTION_READS") != "1":
        return None
    events = request.app.state.event_store.read()
    authoritative_last_sequence = events[-1].sequence if events else 0
    diagnostics = request.app.state.projection_store.diagnostics(
        authoritative_last_sequence=authoritative_last_sequence,
    )
    if diagnostics.get("status") != "available" or diagnostics.get("lag") != 0:
        return None
    try:
        return request.app.state.projection_store.read_proof_dossier(crew_id)
    except Exception:
        return None
