from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.auth import current_player


router = APIRouter(prefix="/events", tags=["events"])


class EventsResponse(BaseModel):
    events: list[dict[str, Any]]


@router.get("", response_model=EventsResponse)
def visible_events(
    request: Request,
    player: Player = Depends(current_player),
) -> EventsResponse:
    events = request.app.state.visibility_service.visible_events_for_player(player.player_id)
    return EventsResponse(events=[event.model_dump(mode="json") for event in events])

