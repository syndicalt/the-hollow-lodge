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
    args = parser.parse_args()

    result = run_smoke(
        server_url=args.server_url,
        expected_backend=args.expected_backend,
    )
    print(
        "projection backend ok: "
        f"{result['backend']} status={result['status']} "
        f"lag={result['lag']} sequence={result['last_sequence']}"
    )


def run_smoke(*, server_url: str, expected_backend: str) -> dict[str, Any]:
    base_url = server_url.rstrip("/")
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        health = client.get("/health")
        health.raise_for_status()
        if health.json() != {"status": "ok"}:
            raise RuntimeError(f"unexpected health response: {health.text}")

        diagnostics = client.get("/diagnostics")
        diagnostics.raise_for_status()
        return validate_projection_diagnostics(
            diagnostics.json(),
            expected_backend=expected_backend,
        )


def validate_projection_diagnostics(
    diagnostics: dict[str, Any],
    *,
    expected_backend: str,
) -> dict[str, Any]:
    projection = diagnostics.get("data", {}).get("projection_db")
    if not isinstance(projection, dict):
        raise RuntimeError("diagnostics response did not include data.projection_db")

    backend = projection.get("backend")
    if backend != expected_backend:
        raise RuntimeError(
            f"expected projection backend {expected_backend}, got {backend}"
        )

    errors: list[str] = []
    status = projection.get("status")
    lag = int(projection.get("lag", 0))
    if status != "available":
        errors.append(f"projection status is {status}")
    if lag != 0:
        errors.append(f"projection lag is {lag}")

    database_url = str(projection.get("database_url", ""))
    if _database_url_exposes_password(database_url):
        errors.append("projection diagnostics expose an unredacted database URL password")

    if errors:
        raise RuntimeError("; ".join(errors))

    return {
        "backend": backend,
        "status": status,
        "lag": lag,
        "last_sequence": int(projection.get("last_sequence", 0)),
        "authoritative_last_sequence": int(
            projection.get("authoritative_last_sequence", 0)
        ),
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
