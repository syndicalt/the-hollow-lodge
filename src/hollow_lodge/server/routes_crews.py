from __future__ import annotations

import logging
import os

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.artifact_service import ArtifactService
from hollow_lodge.server.auth import current_player
from hollow_lodge.server.pending_decisions import pending_decisions_for_player
from hollow_lodge.server.projected_artifacts import projected_visible_artifacts
from hollow_lodge.server.projected_deals import projected_visible_deals
from hollow_lodge.server.projected_legacy import projected_crew_legacy
from hollow_lodge.server.runtime_services import ensure_deal_service
from hollow_lodge.server.rumors import visible_rumors_for_crew
from hollow_lodge.server.projections import (
    apply_crew_modifiers_to_contracts,
    apply_contract_unlock_status,
    crew_legacy_from_contracts,
    unlocked_actionable_contracts,
)
from hollow_lodge.server.services import ActionService, ContractService, ProofService


router = APIRouter(prefix="/crews", tags=["crews"])
logger = logging.getLogger(__name__)


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
        _refresh_projection_store(request)
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
        _refresh_projection_store(request)
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
    contracts = [
        contract
        for contract in _contract_service(request).board_for_player(player.player_id)[
            "contracts"
        ]
        if contract.get("lifecycle_status", "active") != "archived"
    ]
    deals = _deals_for_crew(request, player.player_id, crew_id)
    apply_contract_unlock_status(
        contracts=contracts,
        crew_ids=[crew_id],
        events=request.app.state.event_store.read(),
        deals_by_crew={crew_id: deals},
    )
    active_contracts = unlocked_actionable_contracts(contracts)
    dossier = _proof_service(request).dossier_for_crew(
        crew_id=crew_id,
        player_id=player.player_id,
    )
    shaped_contracts = [
        _crew_board_contract(contract)
        for contract in active_contracts
    ]
    legacy = _crew_legacy_for_board(
        request,
        crew_id=crew_id,
        contracts=active_contracts,
        deals=deals,
    )
    apply_crew_modifiers_to_contracts(
        contracts=shaped_contracts,
        opportunities=legacy["future_opportunities"],
    )
    rumors = visible_rumors_for_crew(request.app.state.event_store, crew_id)
    crew = _crew_summary(request, crew_id)
    return {
        "player_id": player.player_id,
        "crew": crew,
        "active_contracts": shaped_contracts,
        "legacy": legacy,
        "dossier": _crew_board_dossier(dossier),
        "visible_artifacts": _visible_artifacts_for_player(request, player.player_id),
        "deals": deals,
        "rumors": rumors,
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
            rumors_by_crew={crew_id: rumors},
            crew_legacies={crew_id: legacy},
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


def _crew_summary(request: Request, crew_id: str) -> dict:
    projected = _projected_crew_summary(request, crew_id)
    if projected is not None:
        return projected
    return request.app.state.crew_service.summary(crew_id)


def _projected_crew_summary(request: Request, crew_id: str) -> dict | None:
    if os.environ.get("HOLLOW_LODGE_CREW_SUMMARY_PROJECTION_READS") != "1":
        return None
    events = request.app.state.event_store.read()
    authoritative_last_sequence = events[-1].sequence if events else 0
    diagnostics = request.app.state.projection_store.diagnostics(
        authoritative_last_sequence=authoritative_last_sequence,
    )
    if diagnostics.get("status") != "available" or diagnostics.get("lag") != 0:
        return None
    try:
        return request.app.state.projection_store.read_crew_summary(crew_id)
    except Exception:
        return None


def _refresh_projection_store(request: Request) -> None:
    if hasattr(request.app.state, "projection_store"):
        try:
            request.app.state.projection_store.rebuild(
                request.app.state.event_store.read()
            )
        except Exception:
            logger.exception("failed to refresh crew summary projection")


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
    if contract.get("arc"):
        shaped["arc"] = {
            key: contract["arc"][key]
            for key in (
                "arc_id",
                "title",
                "chapter",
                "sequence",
                "public_summary",
                "previous_contract_id",
                "next_contract_hint",
            )
            if key in contract["arc"]
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
            "packet_lead_votes",
            "packet_lead_replacements",
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
    packet_lead_votes = [
        {
            key: vote[key]
            for key in ("sequence", "voter_player_id", "candidate_player_id")
            if key in vote
        }
        for vote in dossier.get("packet_lead_votes", [])
    ]
    if packet_lead_votes:
        shaped["packet_lead_votes"] = packet_lead_votes
    packet_lead_replacements = [
        {
            key: replacement[key]
            for key in (
                "sequence",
                "previous_packet_lead_player_id",
                "packet_lead_player_id",
            )
            if key in replacement
        }
        for replacement in dossier.get("packet_lead_replacements", [])
    ]
    if packet_lead_replacements:
        shaped["packet_lead_replacements"] = packet_lead_replacements
    return shaped


def _crew_legacy_for_board(
    request: Request,
    *,
    crew_id: str,
    contracts: list[dict],
    deals: list[dict],
) -> dict:
    projected = projected_crew_legacy(request, crew_id)
    if projected is not None:
        return projected
    return crew_legacy_from_contracts(
        crew_id=crew_id,
        contracts=contracts,
        deals=deals,
        events=request.app.state.event_store.read(),
    )


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
        if deal["proposer_crew_id"] == crew_id or deal["recipient_crew_id"] == crew_id
    ]


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
