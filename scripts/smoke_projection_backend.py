from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hollow_lodge.client.backend_smoke import (
    database_url_exposes_password,
    resolve_backend_smoke_options,
    run_backend_smoke,
    validate_backend_diagnostics,
    validate_projection_diagnostics,
)


__all__ = [
    "database_url_exposes_password",
    "resolve_backend_smoke_options",
    "run_backend_smoke",
    "validate_backend_diagnostics",
    "validate_projection_diagnostics",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the deployed Hollow Lodge projection backend."
    )
    parser.add_argument(
        "--server-url",
        default="https://server.thehollowlodge.com",
        help="Base URL for the Hollow Lodge server.",
    )
    parser.add_argument(
        "--expected-backend",
        choices=["sqlite", "postgres"],
        help="Projection backend expected in /diagnostics.",
    )
    parser.add_argument(
        "--expected-event-backend",
        choices=["jsonl", "postgres"],
        help="Authoritative event-log backend expected in /diagnostics.",
    )
    parser.add_argument(
        "--expected-operational-backend",
        choices=["jsonl-sidecar", "sqlite", "postgres"],
        help="Operational replay backend expected in /diagnostics.",
    )
    parser.add_argument(
        "--require-projection-reads",
        action="store_true",
        help="Require all implemented projection read surfaces to be enabled.",
    )
    parser.add_argument(
        "--require-current-projection-read-surfaces",
        action="store_true",
        help="Require projection read diagnostics to include this package's surfaces.",
    )
    parser.add_argument(
        "--require-current-projection-schema",
        action="store_true",
        help="Require projection diagnostics to match this package's schema version.",
    )
    parser.add_argument(
        "--require-sequence-alignment",
        action="store_true",
        help="Require event count and projection sequence diagnostics to agree.",
    )
    parser.add_argument(
        "--event-log-manifest",
        type=Path,
        help="Event-log backup manifest file to compare with hosted diagnostics.",
    )
    parser.add_argument(
        "--require-postgres-event-log-guard",
        action="store_true",
        help="Require the deployed server to enforce Postgres event-log startup.",
    )
    parser.add_argument(
        "--require-postgres-projection-guard",
        action="store_true",
        help="Require the deployed server to enforce Postgres projection startup.",
    )
    parser.add_argument(
        "--require-postgres-operational-guard",
        action="store_true",
        help="Require the deployed server to enforce Postgres operational startup.",
    )
    parser.add_argument(
        "--require-production-postgres-preset",
        action="store_true",
        help="Require the deployed server to enable HOLLOW_LODGE_PRODUCTION_POSTGRES.",
    )
    parser.add_argument(
        "--require-projection-refresh-ok",
        action="store_true",
        help="Require the latest projection refresh diagnostic status to be ok.",
    )
    parser.add_argument(
        "--require-maintenance-read-only",
        action="store_true",
        help="Require deployed diagnostics to prove read-only maintenance mode is active.",
    )
    parser.add_argument(
        "--require-maintenance-read-write",
        action="store_true",
        help="Require deployed diagnostics to prove maintenance read-only mode is inactive.",
    )
    parser.add_argument(
        "--production-postgres",
        action="store_true",
        help=(
            "Require production Postgres readiness: Postgres event log, Postgres "
            "projections, Postgres operational store, storage guards, current "
            "schema, projection reads, sequence alignment, and successful "
            "projection refresh."
        ),
    )
    args = parser.parse_args()

    try:
        result = run_smoke(
            server_url=args.server_url,
            expected_backend=args.expected_backend,
            expected_event_backend=args.expected_event_backend,
            expected_operational_backend=args.expected_operational_backend,
            require_projection_reads=args.require_projection_reads,
            require_current_projection_read_surfaces=(
                args.require_current_projection_read_surfaces
            ),
            require_current_projection_schema=args.require_current_projection_schema,
            require_sequence_alignment=args.require_sequence_alignment,
            event_log_manifest=args.event_log_manifest,
            require_postgres_event_log_guard=args.require_postgres_event_log_guard,
            require_postgres_projection_guard=args.require_postgres_projection_guard,
            require_postgres_operational_guard=args.require_postgres_operational_guard,
            require_production_postgres_preset=(
                args.require_production_postgres_preset
            ),
            require_projection_refresh_ok=args.require_projection_refresh_ok,
            require_maintenance_read_only=args.require_maintenance_read_only,
            require_maintenance_read_write=args.require_maintenance_read_write,
            production_postgres=args.production_postgres,
        )
    except RuntimeError as exc:
        parser.error(str(exc))
    print(
        "backend readiness ok: "
        f"event={result['event_log']['backend']} "
        f"event_status={result['event_log']['status']} "
        f"events={result['event_log']['event_count']} "
        f"projection={result['projection']['backend']} "
        f"projection_status={result['projection']['status']} "
        f"projection_lag={result['projection']['lag']} "
        f"sequence={result['projection']['last_sequence']} "
        f"schema={result['projection']['schema_version']} "
        f"migrations={result['projection']['schema_migration_count']}"
        f"{_operational_backend_suffix(result)}"
    )


def run_smoke(
    *,
    server_url: str,
    expected_backend: str | None = None,
    expected_event_backend: str | None = None,
    expected_operational_backend: str | None = None,
    require_projection_reads: bool = False,
    require_current_projection_read_surfaces: bool = False,
    require_current_projection_schema: bool = False,
    require_sequence_alignment: bool = False,
    event_log_manifest: Path | None = None,
    require_postgres_event_log_guard: bool = False,
    require_postgres_projection_guard: bool = False,
    require_postgres_operational_guard: bool = False,
    require_production_postgres_preset: bool = False,
    require_projection_refresh_ok: bool = False,
    require_maintenance_read_only: bool = False,
    require_maintenance_read_write: bool = False,
    production_postgres: bool = False,
) -> dict[str, Any]:
    smoke_options = resolve_backend_smoke_options(
        production_postgres=production_postgres,
        expected_backend=expected_backend,
        expected_event_backend=expected_event_backend,
        expected_operational_backend=expected_operational_backend,
        require_projection_reads=require_projection_reads,
        require_current_projection_read_surfaces=require_current_projection_read_surfaces,
        require_current_projection_schema=require_current_projection_schema,
        require_sequence_alignment=require_sequence_alignment,
        require_postgres_event_log_guard=require_postgres_event_log_guard,
        require_postgres_projection_guard=require_postgres_projection_guard,
        require_postgres_operational_guard=require_postgres_operational_guard,
        require_production_postgres_preset=require_production_postgres_preset,
        require_projection_refresh_ok=require_projection_refresh_ok,
        require_maintenance_read_only=require_maintenance_read_only,
        require_maintenance_read_write=require_maintenance_read_write,
    )
    return run_backend_smoke(
        server_url=server_url,
        event_log_manifest=event_log_manifest,
        **smoke_options,
    )


def _database_url_exposes_password(database_url: str) -> bool:
    return database_url_exposes_password(database_url)


def _operational_backend_suffix(result: dict[str, Any]) -> str:
    identity_replay_store = result.get("identity_replay_store")
    if not isinstance(identity_replay_store, dict):
        return ""
    backend = identity_replay_store.get("backend")
    if backend is None:
        return ""
    return f" operational={backend}"


if __name__ == "__main__":
    main()
