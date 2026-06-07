from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.auth import current_player


router = APIRouter(prefix="/chat", tags=["chat"])


class DirectMessageRequest(BaseModel):
    recipient_player_id: str = Field(min_length=1)
    body: str = Field(min_length=1, max_length=4000)


class CrewMessageRequest(BaseModel):
    crew_id: str = Field(min_length=1)
    body: str = Field(min_length=1, max_length=4000)


class CrewToCrewMessageRequest(BaseModel):
    sender_crew_id: str = Field(min_length=1)
    recipient_crew_id: str = Field(min_length=1)
    body: str = Field(min_length=1, max_length=4000)


class ChatMessageResponse(BaseModel):
    message_id: str
    conversation_id: str


@router.post("/direct", response_model=ChatMessageResponse, status_code=status.HTTP_201_CREATED)
def direct_message(
    payload: DirectMessageRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
) -> ChatMessageResponse:
    try:
        message = request.app.state.chat_service.send_direct(
            sender_player_id=player.player_id,
            recipient_player_id=payload.recipient_player_id,
            body=payload.body,
            idempotency_key=idempotency_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="recipient not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ChatMessageResponse(message_id=message.message_id, conversation_id=message.message_id)


@router.post("/crew", response_model=ChatMessageResponse, status_code=status.HTTP_201_CREATED)
def crew_message(
    payload: CrewMessageRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
) -> ChatMessageResponse:
    try:
        message = request.app.state.chat_service.send_crew(
            sender_player_id=player.player_id,
            crew_id=payload.crew_id,
            body=payload.body,
            idempotency_key=idempotency_key,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a crew member") from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="crew not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ChatMessageResponse(message_id=message.message_id, conversation_id=payload.crew_id)


@router.post(
    "/crew-to-crew",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def crew_to_crew_message(
    payload: CrewToCrewMessageRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
) -> ChatMessageResponse:
    try:
        message = request.app.state.chat_service.send_crew_to_crew(
            sender_player_id=player.player_id,
            sender_crew_id=payload.sender_crew_id,
            recipient_crew_id=payload.recipient_crew_id,
            body=payload.body,
            idempotency_key=idempotency_key,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a crew member") from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="crew not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ChatMessageResponse(
        message_id=message.message_id,
        conversation_id=f"{payload.sender_crew_id}:{payload.recipient_crew_id}",
    )
