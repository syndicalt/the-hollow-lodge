from __future__ import annotations

import tempfile
from typing import Any

from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


TIMELINE_EVENT_TYPES = {
    "deal.proposed",
    "deal.accepted",
    "artifact.deal_copied",
    "artifact.deal_copied.internal",
    "deal.fulfilled",
}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="hollow-lodge-deal-smoke-") as data_dir:
        client = TestClient(create_app(data_dir=data_dir, invite_codes=["a", "b"]))
        ada = _post(
            client,
            "/identity/register",
            json={"invite_code": "a", "display_name": "Ada"},
            headers={"Idempotency-Key": "register-a"},
            expected_status=201,
        )
        bela = _post(
            client,
            "/identity/register",
            json={"invite_code": "b", "display_name": "Bela"},
            headers={"Idempotency-Key": "register-b"},
            expected_status=201,
        )
        ada_headers = {"Authorization": f"Bearer {ada['token']}"}
        bela_headers = {"Authorization": f"Bearer {bela['token']}"}
        gilt = _post(
            client,
            "/crews",
            json={"name": "Gilt Knives"},
            headers={**ada_headers, "Idempotency-Key": "crew-gilt"},
            expected_status=201,
        )
        moth = _post(
            client,
            "/crews",
            json={"name": "Moth Lanterns"},
            headers={**bela_headers, "Idempotency-Key": "crew-moth"},
            expected_status=201,
        )
        client.app.state.artifact_service.grant_artifact_access(
            artifact_id="artifact_chapel_debt_mark",
            actor_id="server",
            player_ids=[],
            crew_ids=[moth["crew_id"]],
            reason="deal smoke setup",
            idempotency_key="grant-chapel",
        )

        proposed = _post(
            client,
            "/deals",
            json={
                "contract_id": "contract_false_finger",
                "proposer_crew_id": gilt["crew_id"],
                "recipient_crew_id": moth["crew_id"],
                "offered_artifact_ids": ["artifact_ledger_rubric"],
                "requested_artifact_ids": ["artifact_chapel_debt_mark"],
                "soft_terms": ["Do not cite us."],
                "expires_phase": "Auction Preview",
            },
            headers={**ada_headers, "Idempotency-Key": "deal-propose"},
            expected_status=201,
        )
        fulfilled = _post(
            client,
            f"/deals/{proposed['deal_id']}/accept",
            json={},
            headers={**bela_headers, "Idempotency-Key": "deal-accept"},
            expected_status=200,
        )
        if fulfilled["status"] != "fulfilled":
            raise RuntimeError(f"expected fulfilled deal, got {fulfilled['status']}")

        for event in client.app.state.event_store.read():
            if event.type in TIMELINE_EVENT_TYPES:
                print(event.type)


def _post(
    client: TestClient,
    path: str,
    *,
    json: dict[str, Any],
    headers: dict[str, str],
    expected_status: int,
) -> dict[str, Any]:
    response = client.post(path, json=json, headers=headers)
    if response.status_code != expected_status:
        raise RuntimeError(
            f"POST {path} returned {response.status_code}: {response.text}"
        )
    return response.json()


if __name__ == "__main__":
    main()
