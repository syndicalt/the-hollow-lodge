from __future__ import annotations

import logging
import os
import secrets

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from hollow_lodge.domain.deals import deal_rows_from_events
from hollow_lodge.domain.identity import Player
from hollow_lodge.eventlog.jsonl_store import EventLogIntegrityError
from hollow_lodge.server.auth import current_player
from hollow_lodge.server.projections import (
    contract_board_from_events,
    crew_legacy_from_contracts,
)
from hollow_lodge.server.projected_legacy import projected_crew_legacy
from hollow_lodge.server.runtime_services import (
    read_authoritative_events,
    refresh_projection_store,
)


router = APIRouter(prefix="/identity", tags=["identity"])
logger = logging.getLogger(__name__)


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


class AdminAccessKeyRequestResponse(AccessKeyRequestResponse):
    contact: str | None


class AdminAccessKeyRequestListResponse(BaseModel):
    key_requests: list[AdminAccessKeyRequestResponse]


class AdminInviteResponse(BaseModel):
    invite_id: str
    used: bool


class AdminInviteListResponse(BaseModel):
    invites: list[AdminInviteResponse]


class AdminPlayerResponse(BaseModel):
    player_id: str
    display_name: str
    token_revoked: bool


class AdminPlayerListResponse(BaseModel):
    players: list[AdminPlayerResponse]


class AdminPlayerDetailResponse(AdminPlayerResponse):
    crew_ids: list[str]
    crew_count: int


class EventLogVerifyResponse(BaseModel):
    ok: bool
    event_count: int
    repaired_trailing_row: bool


class EventLogExportResponse(BaseModel):
    events: list[dict]


class AccessKeyApprovalResponse(BaseModel):
    request_id: str
    status: str
    invite_code: str


class InviteResponse(BaseModel):
    invite_code: str


class RegisterResponse(BaseModel):
    player_id: str
    display_name: str
    token: str


class MeResponse(BaseModel):
    player_id: str
    display_name: str


class PlayerProfileCrewResponse(BaseModel):
    crew_id: str
    name: str
    member_count: int
    ready_for_full_contracts: bool
    legacy: dict


class PlayerProfileResponse(BaseModel):
    player_id: str
    display_name: str
    crew_count: int
    crews: list[PlayerProfileCrewResponse]


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
        _refresh_projection_store(request)
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


def _refresh_projection_store(request: Request) -> None:
    refresh_projection_store(request, context="identity", logger=logger)


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


@router.post(
    "/admin/invites",
    response_model=InviteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_invite(
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    admin_token: str | None = Header(None, alias="X-Hollow-Lodge-Admin-Token"),
) -> InviteResponse:
    _require_admin_token(admin_token)
    try:
        invite_code = request.app.state.identity_service.create_invite(
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        message = str(exc)
        if message in {"idempotency key conflict", "invite replay code unavailable"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message) from exc
        raise
    return InviteResponse(invite_code=invite_code)


@router.get(
    "/admin/invites",
    response_model=AdminInviteListResponse,
)
def list_invites(
    request: Request,
    admin_token: str | None = Header(None, alias="X-Hollow-Lodge-Admin-Token"),
) -> AdminInviteListResponse:
    _require_admin_token(admin_token)
    return AdminInviteListResponse(
        invites=[
            AdminInviteResponse(invite_id=invite.invite_id, used=invite.used)
            for invite in request.app.state.identity_service.list_invites()
        ]
    )


@router.get(
    "/admin/players",
    response_model=AdminPlayerListResponse,
)
def list_players(
    request: Request,
    admin_token: str | None = Header(None, alias="X-Hollow-Lodge-Admin-Token"),
) -> AdminPlayerListResponse:
    _require_admin_token(admin_token)
    return AdminPlayerListResponse(
        players=[
            AdminPlayerResponse(
                player_id=player.player_id,
                display_name=player.display_name,
                token_revoked=player.token_revoked,
            )
            for player in request.app.state.identity_service.list_players()
        ]
    )


@router.get(
    "/admin/players/{player_id}",
    response_model=AdminPlayerDetailResponse,
)
def get_player_detail(
    player_id: str,
    request: Request,
    admin_token: str | None = Header(None, alias="X-Hollow-Lodge-Admin-Token"),
) -> AdminPlayerDetailResponse:
    _require_admin_token(admin_token)
    try:
        player = request.app.state.identity_service.player_by_id(player_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player not found") from exc
    crew_ids = request.app.state.crew_service.crew_ids_for_player(player.player_id)
    return AdminPlayerDetailResponse(
        player_id=player.player_id,
        display_name=player.display_name,
        token_revoked=player.token_revoked,
        crew_ids=crew_ids,
        crew_count=len(crew_ids),
    )


@router.get(
    "/admin/key-requests",
    response_model=AdminAccessKeyRequestListResponse,
)
def list_key_requests(
    request: Request,
    admin_token: str | None = Header(None, alias="X-Hollow-Lodge-Admin-Token"),
) -> AdminAccessKeyRequestListResponse:
    _require_admin_token(admin_token)
    return AdminAccessKeyRequestListResponse(
        key_requests=[
            AdminAccessKeyRequestResponse(
                request_id=key_request.request_id,
                display_name=key_request.display_name,
                contact=key_request.contact,
                status=key_request.status,
            )
            for key_request in request.app.state.identity_service.list_access_key_requests()
        ]
    )


@router.get(
    "/admin/event-log/verify",
    response_model=EventLogVerifyResponse,
)
def verify_event_log(
    request: Request,
    admin_token: str | None = Header(None, alias="X-Hollow-Lodge-Admin-Token"),
) -> EventLogVerifyResponse:
    _require_admin_token(admin_token)
    try:
        report = request.app.state.event_store.verify_integrity()
    except EventLogIntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return EventLogVerifyResponse(
        ok=report.ok,
        event_count=report.event_count,
        repaired_trailing_row=report.repaired_trailing_row,
    )


@router.get(
    "/admin/event-log/export",
    response_model=EventLogExportResponse,
)
def export_event_log(
    request: Request,
    admin_token: str | None = Header(None, alias="X-Hollow-Lodge-Admin-Token"),
) -> EventLogExportResponse:
    _require_admin_token(admin_token)
    try:
        events = request.app.state.event_store.read()
    except EventLogIntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return EventLogExportResponse(
        events=[event.model_dump(mode="json") for event in events]
    )


@router.post(
    "/admin/key-requests/{request_id}/approve",
    response_model=AccessKeyApprovalResponse,
    status_code=status.HTTP_201_CREATED,
)
def approve_key_request(
    request_id: str,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    admin_token: str | None = Header(None, alias="X-Hollow-Lodge-Admin-Token"),
) -> AccessKeyApprovalResponse:
    _require_admin_token(admin_token)
    try:
        key_request, invite_code = request.app.state.identity_service.approve_access_key_request(
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="key request not found") from exc
    except ValueError as exc:
        message = str(exc)
        if message in {
            "idempotency key conflict",
            "invite replay code unavailable",
            "key request already approved",
        }:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message) from exc
        raise
    return AccessKeyApprovalResponse(
        request_id=key_request.request_id,
        status=key_request.status,
        invite_code=invite_code,
    )


@router.get("/me", response_model=MeResponse)
def me(player: Player = Depends(current_player)) -> MeResponse:
    return MeResponse(player_id=player.player_id, display_name=player.display_name)


@router.get("/profile", response_model=PlayerProfileResponse)
def profile(
    request: Request,
    player: Player = Depends(current_player),
) -> PlayerProfileResponse:
    crews = []
    fallback_events = None
    fallback_board = None
    fallback_deals = None
    for crew_id in request.app.state.crew_service.crew_ids_for_player(player.player_id):
        crew = request.app.state.crew_service.summary(crew_id)
        legacy = projected_crew_legacy(request, crew_id)
        if legacy is None:
            if fallback_events is None:
                fallback_events = read_authoritative_events(request)
                fallback_board = contract_board_from_events(fallback_events)
                fallback_deals = deal_rows_from_events(fallback_events)
            assert fallback_board is not None
            assert fallback_deals is not None
            legacy = crew_legacy_from_contracts(
                crew_id=crew_id,
                contracts=fallback_board["contracts"],
                deals=fallback_deals,
                events=fallback_events,
            )
        crews.append(
            PlayerProfileCrewResponse(
                crew_id=crew["crew_id"],
                name=crew["name"],
                member_count=crew["member_count"],
                ready_for_full_contracts=crew["ready_for_full_contracts"],
                legacy=legacy,
            )
        )
    return PlayerProfileResponse(
        player_id=player.player_id,
        display_name=player.display_name,
        crew_count=len(crews),
        crews=crews,
    )


def _require_admin_token(admin_token: str | None) -> None:
    expected = os.environ.get("HOLLOW_LODGE_ADMIN_TOKEN")
    if not expected or not admin_token or not secrets.compare_digest(expected, admin_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin token required")
