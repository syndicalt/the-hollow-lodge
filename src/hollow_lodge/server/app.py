from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from hollow_lodge import __version__
from hollow_lodge.eventlog.config import (
    event_store_from_env,
    event_store_guard_diagnostics,
)
from hollow_lodge.server.artifact_service import ArtifactService
from hollow_lodge.server.deal_service import DealService
from hollow_lodge.server.projection_config import (
    projection_guard_diagnostics,
    projection_read_diagnostics,
    projection_store_from_env,
)
from hollow_lodge.server.routes_actions import router as actions_router
from hollow_lodge.server.routes_artifacts import router as artifacts_router
from hollow_lodge.server.routes_chat import router as chat_router
from hollow_lodge.server.routes_contracts import router as contracts_router
from hollow_lodge.server.routes_crews import router as crews_router
from hollow_lodge.server.routes_deals import router as deals_router
from hollow_lodge.server.routes_events import router as events_router
from hollow_lodge.server.routes_identity import router as identity_router
from hollow_lodge.server.routes_oracle import router as oracle_router
from hollow_lodge.server.routes_proofs import router as proofs_router
from hollow_lodge.server.runtime_services import (
    projection_refresh_diagnostics,
    record_projection_refresh_success,
)
from hollow_lodge.server.services import (
    ActionService,
    ChatService,
    ContractService,
    CrewService,
    IdentityService,
    ProofService,
    VisibilityService,
)
from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_boundary import ResolutionOracle
from hollow_lodge.workflows.openai_oracle import OpenAIResolutionOracle
from hollow_lodge.workflows.oracle_factory import oracle_diagnostics_from_env, resolution_oracle_from_env


def create_app(
    *,
    data_dir: str | Path | None = None,
    invite_codes: list[str] | None = None,
    resolution_oracle: ResolutionOracle | None = None,
) -> FastAPI:
    app = FastAPI(
        title="The Hollow Lodge",
        version="0.1.0",
        summary="Authoritative server for The Hollow Lodge.",
    )
    configured_data_dir = os.environ.get("HOLLOW_LODGE_DATA_DIR")
    storage_configured = data_dir is not None or configured_data_dir is not None
    root = Path(data_dir) if data_dir is not None else Path(configured_data_dir or ".hollow-lodge")
    event_store = event_store_from_env(root)
    projection_store = projection_store_from_env(root)
    resolved_oracle = resolution_oracle if resolution_oracle is not None else resolution_oracle_from_env()
    app.state.event_store = event_store
    app.state.projection_store = projection_store
    app.state.resolution_oracle = resolved_oracle
    identity_service = IdentityService(
        invite_codes=invite_codes or [],
        event_store=event_store,
        replay_dir=root,
    )
    crew_service = CrewService(event_store=event_store)
    artifact_service = ArtifactService(event_store=event_store) if data_dir is not None else None
    app.state.identity_service = identity_service
    app.state.crew_service = crew_service
    if artifact_service is not None:
        app.state.artifact_service = artifact_service
        app.state.deal_service = DealService(
            event_store=event_store,
            crew_service=crew_service,
            artifact_service=artifact_service,
        )
    app.state.chat_service = ChatService(
        event_store=event_store,
        identity_service=identity_service,
        crew_service=crew_service,
        artifact_service=artifact_service,
    )
    app.state.action_service = ActionService(
        event_store=event_store,
        crew_service=crew_service,
        artifact_service=artifact_service,
    )
    app.state.visibility_service = VisibilityService(
        event_store=event_store,
        crew_service=crew_service,
    )

    if data_dir is not None:
        app.state.contract_service = ContractService(
            event_store=event_store,
            resolution_oracle=resolved_oracle,
            artifact_service=artifact_service,
        )
        app.state.proof_service = ProofService(
            event_store=event_store,
            identity_service=identity_service,
            crew_service=crew_service,
            artifact_service=artifact_service,
        )
    if storage_configured:
        startup_events = event_store.read()
        projection_store.rebuild(startup_events)
        record_projection_refresh_success(
            app.state,
            context="startup",
            last_sequence=_last_event_sequence(startup_events),
        )

    app.include_router(identity_router)
    app.include_router(crews_router)
    app.include_router(chat_router)
    app.include_router(actions_router)
    app.include_router(artifacts_router)
    app.include_router(deals_router)
    app.include_router(contracts_router)
    app.include_router(proofs_router)
    app.include_router(events_router)
    app.include_router(oracle_router)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/diagnostics", tags=["system"])
    def diagnostics() -> dict[str, Any]:
        event_log_diagnostics = app.state.event_store.diagnostics()
        return {
            "server": {"version": __version__},
            "oracle": oracle_diagnostics_from_env(
                active_provider=_oracle_provider_name(app.state.resolution_oracle)
            ),
            "data": {
                "directory": str(root),
                "event_log": event_log_diagnostics,
                "projection_db": _projection_diagnostics_from_event_log(
                    app.state,
                    event_log_diagnostics,
                ),
                "projection_reads": projection_read_diagnostics(),
                "projection_refresh": projection_refresh_diagnostics(app.state),
                "storage_guards": {
                    **event_store_guard_diagnostics(),
                    **projection_guard_diagnostics(),
                },
            },
        }

    return app


def _oracle_provider_name(oracle: ResolutionOracle) -> str:
    if isinstance(oracle, OpenAIResolutionOracle):
        return "openai"
    if isinstance(oracle, DeterministicResolutionOracle):
        return "deterministic"
    return oracle.__class__.__name__


def _last_event_sequence(events: list[Any]) -> int:
    return events[-1].sequence if events else 0


def _projection_diagnostics_from_event_log(
    state: Any,
    event_log_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    authoritative_last_sequence = _authoritative_last_sequence_from_diagnostics(
        event_log_diagnostics
    )
    if authoritative_last_sequence is None:
        projection_diagnostics = state.projection_store.diagnostics(
            authoritative_last_sequence=0
        )
        return {
            **projection_diagnostics,
            "status": "unavailable",
            "authoritative_last_sequence": None,
            "lag": None,
        }
    return state.projection_store.diagnostics(
        authoritative_last_sequence=authoritative_last_sequence
    )


def _authoritative_last_sequence_from_diagnostics(
    event_log_diagnostics: dict[str, Any],
) -> int | None:
    if event_log_diagnostics.get("status") == "unavailable":
        return None
    sequence = event_log_diagnostics.get("last_sequence")
    if sequence is None:
        return 0
    try:
        return int(sequence)
    except (TypeError, ValueError):
        return None


app = create_app()
