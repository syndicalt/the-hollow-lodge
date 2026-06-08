from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from hollow_lodge.eventlog.jsonl_store import JsonlEventStore
from hollow_lodge.server.routes_actions import router as actions_router
from hollow_lodge.server.routes_chat import router as chat_router
from hollow_lodge.server.routes_contracts import router as contracts_router
from hollow_lodge.server.routes_crews import router as crews_router
from hollow_lodge.server.routes_events import router as events_router
from hollow_lodge.server.routes_identity import router as identity_router
from hollow_lodge.server.routes_proofs import router as proofs_router
from hollow_lodge.server.services import (
    ActionService,
    ChatService,
    ContractService,
    CrewService,
    IdentityService,
    ProofService,
    VisibilityService,
)


def create_app(
    *,
    data_dir: str | Path | None = None,
    invite_codes: list[str] | None = None,
) -> FastAPI:
    app = FastAPI(
        title="The Hollow Lodge",
        version="0.1.0",
        summary="Authoritative server for The Hollow Lodge.",
    )
    root = Path(data_dir) if data_dir is not None else Path(os.environ.get("HOLLOW_LODGE_DATA_DIR", ".hollow-lodge"))
    event_store = JsonlEventStore(root / "server-events.jsonl")
    app.state.event_store = event_store
    identity_service = IdentityService(
        invite_codes=invite_codes or [],
        event_store=event_store,
    )
    crew_service = CrewService(event_store=event_store)
    app.state.identity_service = identity_service
    app.state.crew_service = crew_service
    app.state.chat_service = ChatService(
        event_store=event_store,
        identity_service=identity_service,
        crew_service=crew_service,
    )
    app.state.action_service = ActionService(
        event_store=event_store,
        crew_service=crew_service,
    )
    app.state.visibility_service = VisibilityService(
        event_store=event_store,
        crew_service=crew_service,
    )

    if data_dir is not None:
        app.state.contract_service = ContractService(event_store=event_store)
        app.state.proof_service = ProofService(
            event_store=event_store,
            identity_service=identity_service,
            crew_service=crew_service,
        )

    app.include_router(identity_router)
    app.include_router(crews_router)
    app.include_router(chat_router)
    app.include_router(actions_router)
    app.include_router(contracts_router)
    app.include_router(proofs_router)
    app.include_router(events_router)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
