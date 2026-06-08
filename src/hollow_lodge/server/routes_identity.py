from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.auth import current_player


router = APIRouter(prefix="/identity", tags=["identity"])


class RegisterRequest(BaseModel):
    invite_code: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=80)


class AccessKeyRequestCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    contact: str | None = Field(default=None, max_length=200)


class AccessKeyRequestResponse(BaseModel):
    request_id: str
    display_name: str
    status: str


class RegisterResponse(BaseModel):
    player_id: str
    display_name: str
    token: str


class MeResponse(BaseModel):
    player_id: str
    display_name: str


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(
    request: Request,
    payload: RegisterRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> RegisterResponse:
    try:
        player, token = request.app.state.identity_service.register(
            invite_code=payload.invite_code,
            display_name=payload.display_name,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        message = str(exc)
        if message in {
            "invite already used",
            "idempotency key conflict",
            "registration replay token unavailable",
        }:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid invite") from exc
    return RegisterResponse(
        player_id=player.player_id,
        display_name=player.display_name,
        token=token,
    )


@router.post(
    "/key-requests",
    response_model=AccessKeyRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_access_key(
    request: Request,
    payload: AccessKeyRequestCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> AccessKeyRequestResponse:
    try:
        key_request = request.app.state.identity_service.request_access_key(
            display_name=payload.display_name,
            contact=payload.contact,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        if str(exc) == "idempotency key conflict":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        raise
    return AccessKeyRequestResponse(
        request_id=key_request.request_id,
        display_name=key_request.display_name,
        status=key_request.status,
    )


@router.get("/me", response_model=MeResponse)
def me(player: Player = Depends(current_player)) -> MeResponse:
    return MeResponse(player_id=player.player_id, display_name=player.display_name)
