from __future__ import annotations

import re
from typing import Any

import httpx

from hollow_lodge.server.projection_store import (
    PROJECTION_SCHEMA_MIGRATIONS,
    SCHEMA_VERSION,
)


PASSWORD_IN_URL_PATTERN = re.compile(r"://[^/\s:]+:([^*@/\s]+)@")
CURRENT_PROJECTION_SCHEMA_VERSION = int(SCHEMA_VERSION)
CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT = len(PROJECTION_SCHEMA_MIGRATIONS)


def run_backend_smoke(
    *,
    server_url: str,
    expected_backend: str,
    expected_event_backend: str | None = None,
    require_projection_reads: bool = False,
    require_current_projection_schema: bool = False,
    require_sequence_alignment: bool = False,
) -> dict[str, Any]:
    base_url = server_url.rstrip("/")
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        health = client.get("/health")
        health.raise_for_status()
        if health.json() != {"status": "ok"}:
            raise RuntimeError(f"unexpected health response: {health.text}")

        diagnostics = client.get("/diagnostics")
        diagnostics.raise_for_status()
        return validate_backend_diagnostics(
            diagnostics.json(),
            expected_backend=expected_backend,
            expected_event_backend=expected_event_backend,
            require_projection_reads=require_projection_reads,
            require_current_projection_schema=require_current_projection_schema,
            require_sequence_alignment=require_sequence_alignment,
        )


def validate_backend_diagnostics(
    diagnostics: dict[str, Any],
    *,
    expected_backend: str,
    expected_event_backend: str | None = None,
    require_projection_reads: bool = False,
    require_current_projection_schema: bool = False,
    require_sequence_alignment: bool = False,
) -> dict[str, Any]:
    data = diagnostics.get("data", {})
    if not isinstance(data, dict):
        raise RuntimeError("diagnostics response did not include data")

    event_log = data.get("event_log")
    if not isinstance(event_log, dict):
        raise RuntimeError("diagnostics response did not include data.event_log")

    projection = data.get("projection_db")
    if not isinstance(projection, dict):
        raise RuntimeError("diagnostics response did not include data.projection_db")

    errors: list[str] = []
    event_backend = event_log.get("backend")
    if expected_event_backend is not None and event_backend != expected_event_backend:
        errors.append(
            f"expected event-log backend {expected_event_backend}, got {event_backend}"
        )
    event_status = event_log.get("status")
    if event_status not in {"available", "not_created"}:
        errors.append(f"event log status is {event_status}")
    event_count = _optional_int(event_log.get("event_count"))

    event_database_url = str(event_log.get("database_url", ""))
    if database_url_exposes_password(event_database_url):
        errors.append("event-log diagnostics expose an unredacted database URL password")

    backend = projection.get("backend")
    if backend != expected_backend:
        errors.append(f"expected projection backend {expected_backend}, got {backend}")

    status = projection.get("status")
    lag = _optional_int(projection.get("lag"))
    if status != "available":
        errors.append(f"projection status is {status}")
    if lag != 0:
        errors.append(f"projection lag is {lag}")

    database_url = str(projection.get("database_url", ""))
    if database_url_exposes_password(database_url):
        errors.append("projection diagnostics expose an unredacted database URL password")

    last_sequence = _optional_int(projection.get("last_sequence"))
    authoritative_last_sequence = _optional_int(
        projection.get("authoritative_last_sequence")
    )
    if require_sequence_alignment:
        if event_count is None:
            errors.append("event log event_count is missing or invalid")
        if last_sequence is None:
            errors.append("projection last_sequence is missing or invalid")
        if authoritative_last_sequence is None:
            errors.append(
                "projection authoritative_last_sequence is missing or invalid"
            )
        if lag is None:
            errors.append("projection lag is missing or invalid")
        if (
            event_count is not None
            and authoritative_last_sequence is not None
            and event_count != authoritative_last_sequence
        ):
            errors.append(
                "event log event_count "
                f"{event_count} does not match projection authoritative_last_sequence "
                f"{authoritative_last_sequence}"
            )
        if (
            last_sequence is not None
            and authoritative_last_sequence is not None
            and last_sequence != authoritative_last_sequence
        ):
            errors.append(
                "projection last_sequence "
                f"{last_sequence} does not match authoritative_last_sequence "
                f"{authoritative_last_sequence}"
            )
        if (
            lag is not None
            and last_sequence is not None
            and authoritative_last_sequence is not None
            and lag != max(0, authoritative_last_sequence - last_sequence)
        ):
            errors.append(
                "projection lag "
                f"{lag} does not match authoritative-last delta "
                f"{max(0, authoritative_last_sequence - last_sequence)}"
            )

    schema_version = _optional_int(projection.get("schema_version"))
    schema_migration_count = _optional_int(projection.get("schema_migration_count"))
    latest_schema_migration = _optional_int(projection.get("latest_schema_migration"))
    if require_current_projection_schema:
        if schema_version != CURRENT_PROJECTION_SCHEMA_VERSION:
            errors.append(
                "projection schema_version is "
                f"{schema_version}; expected {CURRENT_PROJECTION_SCHEMA_VERSION}"
            )
        if schema_migration_count != CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT:
            errors.append(
                "projection schema_migration_count is "
                f"{schema_migration_count}; expected "
                f"{CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT}"
            )
        if latest_schema_migration != CURRENT_PROJECTION_SCHEMA_VERSION:
            errors.append(
                "projection latest_schema_migration is "
                f"{latest_schema_migration}; expected {CURRENT_PROJECTION_SCHEMA_VERSION}"
            )

    projection_reads = data.get("projection_reads")
    if require_projection_reads:
        if not isinstance(projection_reads, dict):
            errors.append("diagnostics response did not include data.projection_reads")
        else:
            surfaces = projection_reads.get("surfaces")
            if not isinstance(surfaces, dict) or not surfaces:
                errors.append("projection read diagnostics did not include surfaces")
            else:
                disabled = sorted(
                    surface for surface, enabled in surfaces.items() if enabled is not True
                )
                if disabled:
                    errors.append(
                        "projection read surfaces disabled: " + ", ".join(disabled)
                    )

    if errors:
        raise RuntimeError("; ".join(errors))

    return {
        "event_log": {
            "backend": event_backend,
            "status": event_status,
            "event_count": event_count,
        },
        "projection": {
            "backend": backend,
            "status": status,
            "lag": lag,
            "last_sequence": last_sequence,
            "authoritative_last_sequence": authoritative_last_sequence,
            "schema_version": schema_version,
            "schema_migration_count": schema_migration_count,
            "latest_schema_migration": latest_schema_migration,
        },
        "projection_reads": projection_reads,
    }


def validate_projection_diagnostics(
    diagnostics: dict[str, Any],
    *,
    expected_backend: str,
    require_projection_reads: bool = False,
    require_current_projection_schema: bool = False,
    require_sequence_alignment: bool = False,
) -> dict[str, Any]:
    if not isinstance(diagnostics.get("data"), dict):
        diagnostics = {"data": {"event_log": {"backend": None, "status": "not_created"}}}
    elif not isinstance(diagnostics["data"].get("event_log"), dict):
        diagnostics = {
            **diagnostics,
            "data": {
                **diagnostics["data"],
                "event_log": {"backend": None, "status": "not_created"},
            },
        }
    result = validate_backend_diagnostics(
        diagnostics,
        expected_backend=expected_backend,
        require_projection_reads=require_projection_reads,
        require_current_projection_schema=require_current_projection_schema,
        require_sequence_alignment=require_sequence_alignment,
    )
    projection = result["projection"]
    return {
        "backend": projection["backend"],
        "status": projection["status"],
        "lag": projection["lag"],
        "last_sequence": projection["last_sequence"],
        "authoritative_last_sequence": projection["authoritative_last_sequence"],
        "schema_version": projection["schema_version"],
        "schema_migration_count": projection["schema_migration_count"],
        "latest_schema_migration": projection["latest_schema_migration"],
        "projection_reads": result["projection_reads"],
    }


def database_url_exposes_password(database_url: str) -> bool:
    if not database_url:
        return False
    match = PASSWORD_IN_URL_PATTERN.search(database_url)
    if match is None:
        return False
    return match.group(1) != "***"


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
