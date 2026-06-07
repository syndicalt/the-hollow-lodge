from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, status

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.auth import current_player


router = APIRouter(prefix="/crews", tags=["crews"])


class CreateCrewRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class CrewResponse(BaseModel):
    crew_id: str
    name: str
    member_count: int
    ready_for_full_contracts: bool
    readiness_warning: str | None


@router.post("", response_model=CrewResponse, status_code=status.HTTP_201_CREATED)
def create_crew(
    payload: CreateCrewRequest,
    request: Request,
    player: Player = Depends(current_player),
) -> CrewResponse:
    crew = request.app.state.crew_service.create_crew(name=payload.name, owner_id=player.player_id)
    return _crew_response(crew)


@router.post("/{crew_id}/join", response_model=CrewResponse)
def join_crew(
    crew_id: str,
    request: Request,
    player: Player = Depends(current_player),
) -> CrewResponse:
    try:
        crew = request.app.state.crew_service.join_crew(crew_id=crew_id, player_id=player.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="crew not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _crew_response(crew)


def _crew_response(crew) -> CrewResponse:
    return CrewResponse(
        crew_id=crew.crew_id,
        name=crew.name,
        member_count=len(crew.member_ids),
        ready_for_full_contracts=crew.ready_for_full_contracts,
        readiness_warning=crew.readiness_warning,
    )

