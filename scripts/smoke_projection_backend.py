from __future__ import annotations

import argparse
import re
from typing import Any

import httpx


PASSWORD_IN_URL_PATTERN = re.compile(r"://[^/\s:]+:([^*@/\s]+)@")


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
    args = parser.parse_args()

    result = run_smoke(
        server_url=args.server_url,
        expected_backend=args.expected_backend,
        expected_event_backend=args.expected_event_backend,
        require_projection_reads=args.require_projection_reads,
    )
    print(
        "backend readiness ok: "
        f"event={result['event_log']['backend']} "
        f"event_status={result['event_log']['status']} "
        f"projection={result['projection']['backend']} "
        f"projection_status={result['projection']['status']} "
        f"projection_lag={result['projection']['lag']} "
        f"sequence={result['projection']['last_sequence']}"
    )


def run_smoke(
    *,
    server_url: str,
    expected_backend: str,
    expected_event_backend: str | None = None,
    require_projection_reads: bool = False,
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
        )


def validate_backend_diagnostics(
    diagnostics: dict[str, Any],
    *,
    expected_backend: str,
    expected_event_backend: str | None = None,
    require_projection_reads: bool = False,
) -> dict[str, Any]:
    data = diagnostics.get("data", {})
    if not isinstance(data, dict):
        raise RuntimeError("diagnostics response did not include data")

    event_log = data.get("event_log")
    if not isinstance(event_log, dict):
        raise RuntimeError("diagnostics response did not include data.event_log")

    projection = diagnostics.get("data", {}).get("projection_db")
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

    event_database_url = str(event_log.get("database_url", ""))
    if _database_url_exposes_password(event_database_url):
        errors.append("event-log diagnostics expose an unredacted database URL password")

    backend = projection.get("backend")
    if backend != expected_backend:
        raise RuntimeError(
            f"expected projection backend {expected_backend}, got {backend}"
        )

    status = projection.get("status")
    lag = int(projection.get("lag", 0))
    if status != "available":
        errors.append(f"projection status is {status}")
    if lag != 0:
        errors.append(f"projection lag is {lag}")

    database_url = str(projection.get("database_url", ""))
    if _database_url_exposes_password(database_url):
        errors.append("projection diagnostics expose an unredacted database URL password")

    projection_reads = diagnostics.get("data", {}).get("projection_reads")
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
        },
        "projection": {
            "backend": backend,
            "status": status,
            "lag": lag,
            "last_sequence": int(projection.get("last_sequence", 0)),
            "authoritative_last_sequence": int(
                projection.get("authoritative_last_sequence", 0)
            ),
        },
        "projection_reads": projection_reads,
    }


def validate_projection_diagnostics(
    diagnostics: dict[str, Any],
    *,
    expected_backend: str,
    require_projection_reads: bool = False,
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
    )
    projection = result["projection"]
    return {
        "backend": projection["backend"],
        "status": projection["status"],
        "lag": projection["lag"],
        "last_sequence": projection["last_sequence"],
        "authoritative_last_sequence": projection["authoritative_last_sequence"],
        "projection_reads": result["projection_reads"],
    }


def _database_url_exposes_password(database_url: str) -> bool:
    if not database_url:
        return False
    match = PASSWORD_IN_URL_PATTERN.search(database_url)
    if match is None:
        return False
    return match.group(1) != "***"


if __name__ == "__main__":
    main()
