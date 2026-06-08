from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.auth import current_player
from hollow_lodge.server.services import ContractService, ProofService


router = APIRouter(prefix="/crews", tags=["crews"])


class CreateCrewRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class JoinCrewRequest(BaseModel):
    join_code: str = Field(min_length=1)


class CrewResponse(BaseModel):
    crew_id: str
    name: str
    member_count: int
    ready_for_full_contracts: bool
    readiness_warning: str | None
    join_code: str | None = None


@router.post("", response_model=CrewResponse, status_code=status.HTTP_201_CREATED)
def create_crew(
    payload: CreateCrewRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
) -> CrewResponse:
    try:
        crew = request.app.state.crew_service.create_crew(
            name=payload.name,
            owner_id=player.player_id,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _crew_response(crew)


@router.post("/{crew_id}/join", response_model=CrewResponse)
def join_crew(
    crew_id: str,
    payload: JoinCrewRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
) -> CrewResponse:
    try:
        crew = request.app.state.crew_service.join_crew(
            crew_id=crew_id,
            player_id=player.player_id,
            join_code=payload.join_code,
            idempotency_key=idempotency_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="crew not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid join code") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _crew_response(crew, include_join_code=False)


@router.get("/{crew_id}/board")
def crew_board(
    crew_id: str,
    request: Request,
    player: Player = Depends(current_player),
):
    crew_service = request.app.state.crew_service
    if not crew_service.has_crew(crew_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="crew not found")
    if not crew_service.is_member(crew_id=crew_id, player_id=player.player_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a crew member")
    return {
        "player_id": player.player_id,
        "crew": crew_service.summary(crew_id),
        "active_contracts": _contract_service(request).board_for_player(player.player_id)[
            "contracts"
        ],
        "dossier": _proof_service(request).dossier_for_crew(
            crew_id=crew_id,
            player_id=player.player_id,
        ),
    }


def _crew_response(crew, *, include_join_code: bool = True) -> CrewResponse:
    return CrewResponse(
        crew_id=crew.crew_id,
        name=crew.name,
        member_count=len(crew.member_ids),
        ready_for_full_contracts=crew.ready_for_full_contracts,
        readiness_warning=crew.readiness_warning,
        join_code=crew.join_code if include_join_code else None,
    )


def _contract_service(request: Request) -> ContractService:
    if not hasattr(request.app.state, "contract_service"):
        request.app.state.contract_service = ContractService(
            event_store=request.app.state.event_store,
        )
    return request.app.state.contract_service


def _proof_service(request: Request) -> ProofService:
    if not hasattr(request.app.state, "proof_service"):
        request.app.state.proof_service = ProofService(
            event_store=request.app.state.event_store,
            identity_service=request.app.state.identity_service,
            crew_service=request.app.state.crew_service,
        )
    return request.app.state.proof_service
