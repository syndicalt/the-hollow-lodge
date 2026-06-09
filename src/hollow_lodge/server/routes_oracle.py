from __future__ import annotations

import os
import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel


router = APIRouter(prefix="/admin/oracle", tags=["admin"])


class OracleAuditRecord(BaseModel):
    sequence: int
    event_id: str
    event_type: str
    audit_schema_version: int | None = None
    contract_id: str
    phase: str
    provider: str | None = None
    provider_attempted: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    validation_status: str | None = None
    failure_stage: str | None = None
    failure_type: str | None = None
    fallback: bool | None = None
    fallback_provider: str | None = None
    fallback_reason: str | None = None
    crew_count: int | None = None
    standing_count: int | None = None
    warning_count: int | None = None
    input_packet_hash: str | None = None
    accepted_output_hash: str | None = None


class OracleAuditListResponse(BaseModel):
    audits: list[OracleAuditRecord]


@router.get(
    "/audits",
    response_model=OracleAuditListResponse,
    response_model_exclude_none=True,
)
def list_oracle_audits(
    request: Request,
    admin_token: str | None = Header(None, alias="X-Hollow-Lodge-Admin-Token"),
) -> OracleAuditListResponse:
    _require_admin_token(admin_token)
    return OracleAuditListResponse(
        audits=[
            _shape_oracle_audit_event(event)
            for event in request.app.state.event_store.read()
            if event.type.startswith("oracle.resolution.")
        ]
    )


def _shape_oracle_audit_event(event: Any) -> OracleAuditRecord:
    payload = event.payload
    return OracleAuditRecord(
        sequence=event.sequence,
        event_id=event.event_id,
        event_type=event.type,
        audit_schema_version=payload.get("audit_schema_version"),
        contract_id=str(payload.get("contract_id", "")),
        phase=str(payload.get("phase", "")),
        provider=payload.get("provider"),
        provider_attempted=payload.get("provider_attempted"),
        model=payload.get("model"),
        prompt_version=payload.get("prompt_version"),
        validation_status=payload.get("validation_status"),
        failure_stage=payload.get("failure_stage"),
        failure_type=payload.get("failure_type"),
        fallback=payload.get("fallback"),
        fallback_provider=payload.get("fallback_provider"),
        fallback_reason=payload.get("fallback_reason"),
        crew_count=payload.get("crew_count"),
        standing_count=payload.get("standing_count"),
        warning_count=payload.get("warning_count"),
        input_packet_hash=payload.get("input_packet_hash"),
        accepted_output_hash=payload.get("accepted_output_hash"),
    )


def _require_admin_token(admin_token: str | None) -> None:
    expected = os.environ.get("HOLLOW_LODGE_ADMIN_TOKEN")
    if not expected or not admin_token or not secrets.compare_digest(expected, admin_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="admin token required",
        )
