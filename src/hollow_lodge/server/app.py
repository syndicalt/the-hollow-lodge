from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from hollow_lodge.eventlog.jsonl_store import JsonlEventStore
from hollow_lodge.server.routes_crews import router as crews_router
from hollow_lodge.server.routes_identity import router as identity_router
from hollow_lodge.server.services import CrewService, IdentityService


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
    root = Path(data_dir) if data_dir is not None else Path(".hollow-lodge")
    event_store = JsonlEventStore(root / "server-events.jsonl")
    app.state.event_store = event_store
    app.state.identity_service = IdentityService(
        invite_codes=invite_codes or [],
        event_store=event_store,
    )
    app.state.crew_service = CrewService(event_store=event_store)
    app.include_router(identity_router)
    app.include_router(crews_router)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
