from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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
from hollow_lodge.server.production_postgres import (
    PRODUCTION_POSTGRES_ENV,
    production_postgres_enabled,
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
from hollow_lodge.server.identity_replay_store import (
    identity_replay_store_from_env,
    identity_replay_store_guard_diagnostics,
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


MAINTENANCE_READ_ONLY_ENV = "HOLLOW_LODGE_MAINTENANCE_READ_ONLY"
READ_ONLY_ALLOWED_METHODS = {"GET", "HEAD", "OPTIONS"}


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
    app.state.maintenance_read_only = _env_flag(MAINTENANCE_READ_ONLY_ENV)
    configured_data_dir = os.environ.get("HOLLOW_LODGE_DATA_DIR")
    storage_configured = data_dir is not None or configured_data_dir is not None
    root = Path(data_dir) if data_dir is not None else Path(configured_data_dir or ".hollow-lodge")
    event_store = event_store_from_env(root)
    projection_store = projection_store_from_env(root)
    identity_replay_store = identity_replay_store_from_env(root)
    resolved_oracle = resolution_oracle if resolution_oracle is not None else resolution_oracle_from_env()
    app.state.event_store = event_store
    app.state.projection_store = projection_store
    app.state.resolution_oracle = resolved_oracle
    try:
        identity_service = IdentityService(
            invite_codes=invite_codes or [],
            event_store=event_store,
            replay_dir=root,
            replay_store=identity_replay_store,
        )
    except Exception as exc:
        raise _startup_bootstrap_error(
            "replaying authoritative events",
            exc,
        ) from None
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

    @app.middleware("http")
    async def maintenance_read_only_guard(request: Request, call_next):
        if not app.state.maintenance_read_only:
            return await call_next(request)
        if request.method.upper() in READ_ONLY_ALLOWED_METHODS:
            return await call_next(request)
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "60"},
            content={
                "detail": (
                    "server is in read-only maintenance mode; mutating "
                    "commands are temporarily disabled"
                )
            },
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
        startup_events = _read_startup_events(event_store)
        _rebuild_startup_projection(projection_store, startup_events)
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
        event_log_diagnostics = _event_log_diagnostics(app.state.event_store)
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
                    "production_postgres": production_postgres_enabled(),
                    "production_postgres_env": PRODUCTION_POSTGRES_ENV,
                    **event_store_guard_diagnostics(),
                    **projection_guard_diagnostics(),
                    **identity_replay_store_guard_diagnostics(),
                },
                "maintenance": _maintenance_diagnostics(app),
                "identity_replay_store": app.state.identity_service.replay_store.diagnostics(),
            },
        }

    return app


def _maintenance_diagnostics(app: FastAPI) -> dict[str, Any]:
    return {
        "read_only": bool(getattr(app.state, "maintenance_read_only", False)),
        "env": MAINTENANCE_READ_ONLY_ENV,
    }


def _env_flag(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if value in {"", "0", "false", "no", "off"}:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    raise RuntimeError(
        f"{name} must be one of 1, true, yes, on, 0, false, no, or off; "
        f"got {value!r}"
    )


def _oracle_provider_name(oracle: ResolutionOracle) -> str:
    if isinstance(oracle, OpenAIResolutionOracle):
        return "openai"
    if isinstance(oracle, DeterministicResolutionOracle):
        return "deterministic"
    return oracle.__class__.__name__


def _last_event_sequence(events: list[Any]) -> int:
    return events[-1].sequence if events else 0


def _read_startup_events(event_store: Any) -> list[Any]:
    try:
        return event_store.read()
    except Exception as exc:
        raise _startup_bootstrap_error(
            "replaying authoritative events",
            exc,
        ) from None


def _rebuild_startup_projection(projection_store: Any, events: list[Any]) -> None:
    try:
        projection_store.rebuild(events)
    except Exception as exc:
        raise _startup_bootstrap_error(
            "rebuilding projection store",
            exc,
        ) from None


def _startup_bootstrap_error(context: str, exc: Exception) -> RuntimeError:
    return RuntimeError(
        "startup bootstrap failed while "
        f"{context}; error_type={exc.__class__.__name__}"
    )


def _event_log_diagnostics(event_store: Any) -> dict[str, Any]:
    try:
        return event_store.diagnostics()
    except Exception as exc:
        diagnostics: dict[str, Any] = {
            "backend": _store_backend(event_store),
            "exists": False,
            "status": "unavailable",
            "event_count": 0,
            "last_sequence": None,
            "last_event_hash": None,
            "event_hash_chain_sha256": None,
            "error_type": exc.__class__.__name__,
        }
        path = getattr(event_store, "path", None)
        if path is not None:
            diagnostics["path"] = str(path)
        safe_database_url = getattr(event_store, "safe_database_url", None)
        if safe_database_url is not None:
            diagnostics["database_url"] = str(safe_database_url)
        database_url_env = getattr(event_store, "database_url_env", None)
        if database_url_env is not None:
            diagnostics["database_url_env"] = str(database_url_env)
        return diagnostics


def _projection_unavailable_diagnostics(
    projection_store: Any,
    *,
    authoritative_last_sequence: int | None,
    error_type: str,
) -> dict[str, Any]:
    authoritative = authoritative_last_sequence or 0
    diagnostics: dict[str, Any] = {
        "backend": _store_backend(projection_store),
        "exists": False,
        "status": "unavailable",
        "schema_version": None,
        "last_sequence": 0,
        "authoritative_last_sequence": authoritative_last_sequence,
        "lag": None if authoritative_last_sequence is None else authoritative,
        "contract_count": 0,
        "crew_count": 0,
        "deal_count": 0,
        "crew_legacy_count": 0,
        "proof_dossier_count": 0,
        "proof_fragment_count": 0,
        "chat_message_count": 0,
        "action_count": 0,
        "pending_decision_count": 0,
        "visible_rumor_count": 0,
        "contract_unlock_count": 0,
        "oracle_audit_count": 0,
        "artifact_inspection_count": 0,
        "schema_migration_count": 0,
        "latest_schema_migration": None,
        "visible_event_count": 0,
        "public_artifact_count": 0,
        "scoped_artifact_count": 0,
        "error_type": error_type,
    }
    path = getattr(projection_store, "path", None)
    if path is not None:
        diagnostics["path"] = str(path)
    safe_database_url = getattr(projection_store, "safe_database_url", None)
    if safe_database_url is not None:
        diagnostics["database_url"] = str(safe_database_url)
    database_url_env = getattr(projection_store, "database_url_env", None)
    if database_url_env is not None:
        diagnostics["database_url_env"] = str(database_url_env)
    return diagnostics


def _store_backend(store: Any) -> str:
    backend = getattr(store, "backend", None)
    if backend is not None:
        return str(backend)
    if getattr(store, "path", None) is not None:
        return "jsonl"
    return "unknown"


def _projection_diagnostics_from_event_log(
    state: Any,
    event_log_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    authoritative_last_sequence = _authoritative_last_sequence_from_diagnostics(
        event_log_diagnostics
    )
    if authoritative_last_sequence is None:
        try:
            projection_diagnostics = state.projection_store.diagnostics(
                authoritative_last_sequence=0
            )
        except Exception as exc:
            return _projection_unavailable_diagnostics(
                state.projection_store,
                authoritative_last_sequence=None,
                error_type=exc.__class__.__name__,
            )
        return {
            **projection_diagnostics,
            "status": "unavailable",
            "authoritative_last_sequence": None,
            "lag": None,
        }
    try:
        return state.projection_store.diagnostics(
            authoritative_last_sequence=authoritative_last_sequence
        )
    except Exception as exc:
        return _projection_unavailable_diagnostics(
            state.projection_store,
            authoritative_last_sequence=authoritative_last_sequence,
            error_type=exc.__class__.__name__,
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
