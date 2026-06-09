from __future__ import annotations

from typing import Any

from fastapi import Request

from hollow_lodge.server.projection_readiness import projection_read_ready


def projected_contract_unlock_statuses(
    request: Request,
    *,
    crew_ids: list[str] | tuple[str, ...],
) -> dict[str, dict[str, Any]] | None:
    if not crew_ids:
        return None
    if not projection_read_ready(
        request,
        "HOLLOW_LODGE_CONTRACT_UNLOCK_PROJECTION_READS",
    ):
        return None
    try:
        return request.app.state.projection_store.read_contract_unlock_statuses(
            crew_ids=crew_ids,
        )
    except Exception:
        return None


def apply_projected_contract_unlock_statuses(
    *,
    contracts: list[dict[str, Any]],
    unlock_statuses: dict[str, dict[str, Any]],
) -> None:
    for contract in contracts:
        status = unlock_statuses.get(contract["contract_id"])
        if status is not None:
            contract["unlock_status"] = status
