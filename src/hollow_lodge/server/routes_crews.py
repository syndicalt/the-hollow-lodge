from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.artifact_service import ArtifactService
from hollow_lodge.server.auth import current_player
from hollow_lodge.eventlog.visibility import Principal
from hollow_lodge.server.pending_decisions import pending_decisions_for_player
from hollow_lodge.server.runtime_services import ensure_deal_service
from hollow_lodge.server.projections import (
    apply_crew_modifiers_to_contracts,
    crew_legacy_from_contracts,
)
from hollow_lodge.server.services import ActionService, ContractService, ProofService


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
    active_contracts = _contract_service(request).board_for_player(player.player_id)[
        "contracts"
    ]
    dossier = _proof_service(request).dossier_for_crew(
        crew_id=crew_id,
        player_id=player.player_id,
    )
    shaped_contracts = [
        _crew_board_contract(contract)
        for contract in active_contracts
    ]
    legacy = crew_legacy_from_contracts(
        crew_id=crew_id,
        contracts=active_contracts,
    )
    apply_crew_modifiers_to_contracts(
        contracts=shaped_contracts,
        opportunities=legacy["future_opportunities"],
    )
    deals = _deals_for_crew(request, player.player_id, crew_id)
    crew = crew_service.summary(crew_id)
    return {
        "player_id": player.player_id,
        "crew": crew,
        "active_contracts": shaped_contracts,
        "legacy": legacy,
        "dossier": _crew_board_dossier(dossier),
        "visible_artifacts": _visible_artifacts_for_player(request, player.player_id),
        "deals": deals,
        "rumors": _rumors_for_crew(request, crew_id),
        "pending_decisions": pending_decisions_for_player(
            player_id=player.player_id,
            crew_ids=[crew_id],
            active_contracts=shaped_contracts,
            deals=deals,
            crew_summaries={crew_id: crew},
            dossiers={crew_id: _crew_board_dossier(dossier)},
            actions_by_crew={
                crew_id: _action_service(request).current_actions_for_crew(crew_id),
            },
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


def _crew_board_contract(contract: dict) -> dict:
    shaped = {
        key: contract[key]
        for key in ("contract_id", "title", "crew_heat", "proof_dossier_needs")
        if key in contract
    }
    if "phase" in contract:
        shaped["phase"] = {
            key: contract["phase"][key]
            for key in ("name", "remaining_hours", "status")
            if key in contract["phase"]
        }
    if "phase_result" in contract:
        shaped["phase_result"] = {
            "standings": [
                {
                    key: standing[key]
                    for key in ("crew_id", "standing", "score")
                    if key in standing
                }
                for standing in contract["phase_result"].get("standings", [])
            ]
        }
    return shaped


def _crew_board_dossier(dossier: dict) -> dict:
    shaped = {
        key: dossier[key]
        for key in (
            "dossier_id",
            "crew_id",
            "packet_lead_player_id",
            "claim",
            "evidence_ids",
            "artifact_citations",
            "reasoning",
            "weaknesses",
            "provenance_concerns",
        )
        if key in dossier
    }
    shaped["member_contributions"] = [
        {
            key: contribution[key]
            for key in ("player_id", "note", "evidence_ids")
            if key in contribution
        }
        for contribution in dossier.get("member_contributions", [])
    ]
    return shaped


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


def _deals_for_crew(request: Request, player_id: str, crew_id: str) -> list[dict]:
    return [
        deal
        for deal in _deals_for_player(request, player_id)
        if deal["proposer_crew_id"] == crew_id or deal["recipient_crew_id"] == crew_id
    ]


def _rumors_for_crew(request: Request, crew_id: str) -> list[dict]:
    rumors: list[dict] = []
    for event in request.app.state.event_store.read_for_principal(Principal.crew(crew_id)):
        if event.type != "contract.rumor.leaked":
            continue
        payload = event.payload
        rumors.append(
            {
                key: payload[key]
                for key in (
                    "rumor_id",
                    "source_type",
                    "source_id",
                    "contract_id",
                    "suspected_crew_ids",
                    "summary",
                    "pressure",
                )
                if key in payload
            }
        )
    return rumors


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
