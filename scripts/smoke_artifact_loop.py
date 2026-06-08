from __future__ import annotations

import argparse
import json
import os
import uuid
from typing import Any

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="https://server.thehollowlodge.com")
    parser.add_argument("--admin-token", default=os.environ.get("HOLLOW_LODGE_ADMIN_TOKEN"))
    args = parser.parse_args()
    if not args.admin_token:
        raise SystemExit("HOLLOW_LODGE_ADMIN_TOKEN is required")

    run = uuid.uuid4().hex[:8]
    server = args.server.rstrip("/")

    def post(
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float = 30,
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{server}{path}",
            headers=headers or {},
            json=json_body or {},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def get(path: str, *, token: str) -> dict[str, Any]:
        response = httpx.get(
            f"{server}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def invite(label: str) -> str:
        return post(
            "/identity/admin/invites",
            headers={
                "X-Hollow-Lodge-Admin-Token": args.admin_token,
                "Idempotency-Key": f"artifact-smoke-{run}-invite-{label}",
            },
        )["invite_code"]

    def register(label: str) -> dict[str, Any]:
        return post(
            "/identity/register",
            headers={"Idempotency-Key": f"artifact-smoke-{run}-register-{label}"},
            json_body={
                "invite_code": invite(label),
                "display_name": f"Artifact Smoke {label} {run}",
            },
        )

    first = register("one")
    second = register("two")
    first_headers = {
        "Authorization": f"Bearer {first['token']}",
        "Idempotency-Key": f"artifact-smoke-{run}-crew-one",
    }
    second_headers = {
        "Authorization": f"Bearer {second['token']}",
        "Idempotency-Key": f"artifact-smoke-{run}-crew-two",
    }
    crew_one = post(
        "/crews",
        headers=first_headers,
        json_body={"name": f"Smoke Gilt {run}"},
    )
    crew_two = post(
        "/crews",
        headers=second_headers,
        json_body={"name": f"Smoke Moth {run}"},
    )

    artifacts = get("/artifacts", token=first["token"])
    post(
        "/artifacts/artifact_ledger_rubric/inspect",
        headers={
            "Authorization": f"Bearer {first['token']}",
            "Idempotency-Key": f"artifact-smoke-{run}-inspect",
        },
    )
    transfer = post(
        "/artifacts/artifact_ledger_rubric/transfer",
        headers={
            "Authorization": f"Bearer {first['token']}",
            "Idempotency-Key": f"artifact-smoke-{run}-transfer",
        },
        json_body={"recipient_player_id": second["player_id"]},
    )

    print(
        json.dumps(
            {
                "run": run,
                "players": [first["player_id"], second["player_id"]],
                "crews": [crew_one["crew_id"], crew_two["crew_id"]],
                "visible_artifact_count": len(artifacts["artifacts"]),
                "transferred_artifact_id": transfer["artifact_id"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
