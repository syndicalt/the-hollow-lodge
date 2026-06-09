from __future__ import annotations

import argparse
from typing import Any

from hollow_lodge.client.backend_smoke import (
    database_url_exposes_password,
    run_backend_smoke,
    validate_backend_diagnostics,
    validate_projection_diagnostics,
)


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
        required=True,
        help="Projection backend expected in /diagnostics.",
    )
    parser.add_argument(
        "--expected-event-backend",
        choices=["jsonl", "postgres"],
        help="Authoritative event-log backend expected in /diagnostics.",
    )
    parser.add_argument(
        "--require-projection-reads",
        action="store_true",
        help="Require all implemented projection read surfaces to be enabled.",
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
    args = parser.parse_args()

    result = run_smoke(
        server_url=args.server_url,
        expected_backend=args.expected_backend,
        expected_event_backend=args.expected_event_backend,
        require_projection_reads=args.require_projection_reads,
        require_current_projection_schema=args.require_current_projection_schema,
        require_sequence_alignment=args.require_sequence_alignment,
    )
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
    )


def run_smoke(
    *,
    server_url: str,
    expected_backend: str,
    expected_event_backend: str | None = None,
    require_projection_reads: bool = False,
    require_current_projection_schema: bool = False,
    require_sequence_alignment: bool = False,
) -> dict[str, Any]:
    return run_backend_smoke(
        server_url=server_url,
        expected_backend=expected_backend,
        expected_event_backend=expected_event_backend,
        require_projection_reads=require_projection_reads,
        require_current_projection_schema=require_current_projection_schema,
        require_sequence_alignment=require_sequence_alignment,
    )


def _database_url_exposes_password(database_url: str) -> bool:
    return database_url_exposes_password(database_url)


if __name__ == "__main__":
    main()
