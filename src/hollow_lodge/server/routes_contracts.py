from __future__ import annotations

import logging
import os
import secrets
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.artifact_service import ArtifactService
from hollow_lodge.server.auth import current_player
from hollow_lodge.server.contract_seed import ContractSeed, load_contract_seed_file
from hollow_lodge.server.pending_decisions import pending_decisions_for_player
from hollow_lodge.server.projected_actions import projected_current_actions_for_crew
from hollow_lodge.server.projected_artifacts import projected_visible_artifacts
from hollow_lodge.server.projected_deals import projected_visible_deals
from hollow_lodge.server.projected_dossiers import projected_proof_dossier
from hollow_lodge.server.projected_fragments import projected_incoming_proof_fragments
from hollow_lodge.server.projected_pending_decisions import projected_pending_decisions
from hollow_lodge.server.projected_rumors import projected_visible_rumors_for_crew
from hollow_lodge.server.projected_unlocks import (
    apply_projected_contract_unlock_statuses,
    projected_contract_unlock_statuses,
)
from hollow_lodge.server.projection_readiness import projection_read_ready
from hollow_lodge.server.projections import (
    apply_contract_unlock_status,
    crew_legacy_from_contracts,
    inbox_from_board,
    unlocked_actionable_contracts,
)
from hollow_lodge.server.runtime_services import (
    ensure_deal_service,
    read_authoritative_events,
    refresh_projection_store,
)
from hollow_lodge.server.rumors import visible_rumors_for_crew
from hollow_lodge.server.services import ActionService, ContractService, ProofService


router = APIRouter(tags=["contracts"])
logger = logging.getLogger(__name__)


class LockAuctionPreviewRequest(BaseModel):
    # Deprecated: the server derives elapsed phase time from the contract's
    # publish timestamp; a client-supplied value is accepted but ignored.
    hours_elapsed: int | None = Field(default=None, ge=0)


class ActivateContractSeedRequest(BaseModel):
    seed: Any


class ActivateContractSeedResponse(BaseModel):
    contract_id: str
    lifecycle_status: str


@router.get("/contracts")
def contracts(
    request: Request,
    player: Player = Depends(current_player),
):
    payload = _board_for_player_with_unlocks(request, player.player_id)
    payload["visible_artifacts"] = _visible_artifacts_for_player(request, player.player_id)
    return payload


@router.post(
    "/contracts/admin/activate",
    response_model=ActivateContractSeedResponse,
    status_code=status.HTTP_201_CREATED,
)
def activate_contract_seed(
    payload: ActivateContractSeedRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    admin_token: str | None = Header(None, alias="X-Hollow-Lodge-Admin-Token"),
) -> ActivateContractSeedResponse:
    _require_admin_token(admin_token)
    try:
        seed = _parse_contract_seed(payload.seed)
        result = _contract_service(request).activate_contract_seed(
            seed=seed,
            actor_id="admin",
            idempotency_key=idempotency_key,
        )
        _refresh_projection_store(request)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        message = str(exc)
        if message == "idempotency key conflict":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=message) from exc
    return ActivateContractSeedResponse(**result)


@router.post(
    "/contracts/admin/{contract_id}/archive",
    response_model=ActivateContractSeedResponse,
)
def archive_contract(
    contract_id: str,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    admin_token: str | None = Header(None, alias="X-Hollow-Lodge-Admin-Token"),
) -> ActivateContractSeedResponse:
    _require_admin_token(admin_token)
    try:
        result = _contract_service(request).archive_contract(
            contract_id=contract_id,
            actor_id="admin",
            idempotency_key=idempotency_key,
        )
        _refresh_projection_store(request)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contract not found") from exc
    except ValueError as exc:
        message = str(exc)
        if message == "idempotency key conflict":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=message) from exc
    return ActivateContractSeedResponse(**result)


@router.get("/inbox")
def inbox(
    request: Request,
    player: Player = Depends(current_player),
):
    board = _board_for_player_with_unlocks(request, player.player_id)
    events = None
    projected_fragments = projected_incoming_proof_fragments(
        request,
        player.player_id,
    )
    if projected_fragments is None:
        events = read_authoritative_events(request)
    payload = inbox_from_board(
        player_id=player.player_id,
        board=board,
        events=events,
        incoming_proof_fragments=projected_fragments,
    )
    payload["active_contracts"] = unlocked_actionable_contracts(
        payload["active_contracts"]
    )
    payload["display_name"] = player.display_name
    payload["visible_artifacts"] = _visible_artifacts_for_player(request, player.player_id)
    payload["deals"] = _deals_for_player(request, player.player_id)
    crew_ids = request.app.state.crew_service.crew_ids_for_player(player.player_id)
    projected_decisions = projected_pending_decisions(
        request,
        player.player_id,
        crew_ids=crew_ids,
    )
    if projected_decisions is not None:
        payload["pending_decisions"] = projected_decisions
    else:
        if events is None:
            events = read_authoritative_events(request)
        deals_by_crew = {
            crew_id: _deals_for_crew(request, player.player_id, crew_id)
            for crew_id in crew_ids
        }
        payload["pending_decisions"] = pending_decisions_for_player(
            player_id=player.player_id,
            crew_ids=crew_ids,
            active_contracts=payload["active_contracts"],
            deals=payload["deals"],
            crew_summaries={
                crew_id: request.app.state.crew_service.summary(crew_id)
                for crew_id in crew_ids
            },
            dossiers={
                crew_id: _dossier_for_crew(
                    request,
                    player_id=player.player_id,
                    crew_id=crew_id,
                )
                for crew_id in crew_ids
            },
            actions_by_crew={
                crew_id: _current_actions_for_crew(request, crew_id)
                for crew_id in crew_ids
            },
            rumors_by_crew={
                crew_id: _visible_rumors_for_crew(request, crew_id)
                for crew_id in crew_ids
            },
            crew_legacies={
                crew_id: crew_legacy_from_contracts(
                    crew_id=crew_id,
                    contracts=payload["active_contracts"],
                    deals=deals_by_crew.get(crew_id, []),
                    events=events,
                )
                for crew_id in crew_ids
            },
        )
    return payload


def _board_for_player_with_unlocks(request: Request, player_id: str) -> dict:
    payload = _projection_contract_board(request) or _contract_service(
        request
    ).board_for_player(player_id)
    crew_ids = request.app.state.crew_service.crew_ids_for_player(player_id)
    unlock_statuses = projected_contract_unlock_statuses(request, crew_ids=crew_ids)
    if unlock_statuses is None:
        apply_contract_unlock_status(
            contracts=payload["contracts"],
            crew_ids=crew_ids,
            events=read_authoritative_events(request),
            deals_by_crew={
                crew_id: _deals_for_crew(request, player_id, crew_id)
                for crew_id in crew_ids
            },
        )
    else:
        apply_projected_contract_unlock_statuses(
            contracts=payload["contracts"],
            unlock_statuses=unlock_statuses,
        )
    return payload


def _projection_contract_board(request: Request) -> dict | None:
    if not projection_read_ready(
        request,
        "HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS",
    ):
        return None
    try:
        return request.app.state.projection_store.read_contract_board()
    except Exception:
        return None


def _refresh_projection_store(request: Request) -> None:
    refresh_projection_store(request, context="contracts", logger=logger)


@router.post("/contracts/{contract_id}/phases/auction-preview/lock")
def lock_auction_preview(
    contract_id: str,
    payload: LockAuctionPreviewRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    if not request.app.state.crew_service.member_of_any(player.player_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not a crew member",
        )
    try:
        result = _contract_service(request).lock_auction_preview(
            contract_id=contract_id,
            actor_id=player.player_id,
            idempotency_key=idempotency_key,
            client_hours_elapsed=payload.hours_elapsed,
        )
        _refresh_projection_store(request)
        return result
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contract not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _contract_service(request: Request) -> ContractService:
    if not hasattr(request.app.state, "artifact_service"):
        request.app.state.artifact_service = ArtifactService(
            event_store=request.app.state.event_store,
        )
    if not hasattr(request.app.state, "contract_service"):
        request.app.state.contract_service = ContractService(
            event_store=request.app.state.event_store,
            resolution_oracle=getattr(request.app.state, "resolution_oracle", None),
            artifact_service=request.app.state.artifact_service,
        )
    if hasattr(request.app.state.contract_service, "set_artifact_service"):
        request.app.state.contract_service.set_artifact_service(
            request.app.state.artifact_service,
        )
    return request.app.state.contract_service


def _visible_artifacts_for_player(request: Request, player_id: str) -> list[dict]:
    projected = projected_visible_artifacts(request, player_id)
    if projected is not None:
        return projected["artifacts"]
    return request.app.state.artifact_service.visible_artifacts_for_player(
        player_id,
        crew_ids=request.app.state.crew_service.crew_ids_for_player(player_id),
    )["artifacts"]


def _deals_for_player(request: Request, player_id: str) -> list[dict]:
    projected = projected_visible_deals(request, player_id)
    if projected is not None:
        return projected
    return ensure_deal_service(request).list_for_player(player_id)


def _deals_for_crew(request: Request, player_id: str, crew_id: str) -> list[dict]:
    return [
        deal
        for deal in _deals_for_player(request, player_id)
        if crew_id in {deal.get("proposer_crew_id"), deal.get("recipient_crew_id")}
    ]


def _dossier_for_crew(request: Request, *, player_id: str, crew_id: str) -> dict:
    projected = projected_proof_dossier(request, crew_id)
    if projected is not None:
        return projected
    return _proof_service(request).dossier_for_crew(
        crew_id=crew_id,
        player_id=player_id,
    )


def _current_actions_for_crew(request: Request, crew_id: str) -> list[dict]:
    projected = projected_current_actions_for_crew(request, crew_id)
    if projected is not None:
        return projected
    return _action_service(request).current_actions_for_crew(crew_id)


def _visible_rumors_for_crew(request: Request, crew_id: str) -> list[dict]:
    projected = projected_visible_rumors_for_crew(request, crew_id)
    if projected is not None:
        return projected
    return visible_rumors_for_crew(request.app.state.event_store, crew_id)


def _parse_contract_seed(seed: Any) -> ContractSeed:
    if isinstance(seed, str):
        return load_contract_seed_file(seed)
    return ContractSeed.model_validate(seed)


def _require_admin_token(admin_token: str | None) -> None:
    expected = os.environ.get("HOLLOW_LODGE_ADMIN_TOKEN")
    if not expected or not admin_token or not secrets.compare_digest(expected, admin_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin token required")


def _proof_service(request: Request) -> ProofService:
    if not hasattr(request.app.state, "proof_service"):
        request.app.state.proof_service = ProofService(
            event_store=request.app.state.event_store,
            identity_service=request.app.state.identity_service,
            crew_service=request.app.state.crew_service,
        )
    return request.app.state.proof_service


def _action_service(request: Request) -> ActionService:
    if not hasattr(request.app.state, "action_service"):
        request.app.state.action_service = ActionService(
            event_store=request.app.state.event_store,
            crew_service=request.app.state.crew_service,
            artifact_service=getattr(request.app.state, "artifact_service", None),
        )
    return request.app.state.action_service
