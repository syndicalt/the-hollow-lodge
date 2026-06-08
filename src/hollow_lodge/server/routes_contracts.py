from __future__ import annotations

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
from hollow_lodge.server.runtime_services import ensure_deal_service
from hollow_lodge.server.services import ActionService, ContractService, ProofService


router = APIRouter(tags=["contracts"])


class LockAuctionPreviewRequest(BaseModel):
    hours_elapsed: int = Field(ge=0)


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
    payload = _contract_service(request).board_for_player(player.player_id)
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
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
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
    payload = _contract_service(request).inbox_for_player(player.player_id)
    payload["display_name"] = player.display_name
    payload["visible_artifacts"] = _visible_artifacts_for_player(request, player.player_id)
    payload["deals"] = _deals_for_player(request, player.player_id)
    crew_ids = request.app.state.crew_service.crew_ids_for_player(player.player_id)
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
            crew_id: _proof_service(request).dossier_for_crew(
                crew_id=crew_id,
                player_id=player.player_id,
            )
            for crew_id in crew_ids
        },
        actions_by_crew={
            crew_id: _action_service(request).current_actions_for_crew(crew_id)
            for crew_id in crew_ids
        },
    )
    return payload


@router.post("/contracts/{contract_id}/phases/auction-preview/lock")
def lock_auction_preview(
    contract_id: str,
    payload: LockAuctionPreviewRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    try:
        return _contract_service(request).lock_auction_preview(
            contract_id=contract_id,
            actor_id=player.player_id,
            hours_elapsed=payload.hours_elapsed,
            idempotency_key=idempotency_key,
        )
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
    return request.app.state.artifact_service.visible_artifacts_for_player(
        player_id,
        crew_ids=request.app.state.crew_service.crew_ids_for_player(player_id),
    )["artifacts"]


def _deals_for_player(request: Request, player_id: str) -> list[dict]:
    return ensure_deal_service(request).list_for_player(player_id)


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
