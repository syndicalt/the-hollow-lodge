from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def test_two_crews_complete_escrowed_artifact_swap(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = client.post(
        "/identity/register",
        json={"invite_code": "a", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-a"},
    ).json()
    bela = client.post(
        "/identity/register",
        json={"invite_code": "b", "display_name": "Bela"},
        headers={"Idempotency-Key": "register-b"},
    ).json()
    ada_headers = {"Authorization": f"Bearer {ada['token']}"}
    bela_headers = {"Authorization": f"Bearer {bela['token']}"}
    gilt = client.post(
        "/crews",
        json={"name": "Gilt Knives"},
        headers={**ada_headers, "Idempotency-Key": "crew-gilt"},
    ).json()
    moth = client.post(
        "/crews",
        json={"name": "Moth Lanterns"},
        headers={**bela_headers, "Idempotency-Key": "crew-moth"},
    ).json()
    client.app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="e2e setup",
        idempotency_key="grant-chapel",
    )

    proposed = client.post(
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
    ).json()
    fulfilled = client.post(
        f"/deals/{proposed['deal_id']}/accept",
        json={},
        headers={**bela_headers, "Idempotency-Key": "deal-accept"},
    ).json()
    gilt_board = client.get(f"/crews/{gilt['crew_id']}/board", headers=ada_headers).json()
    moth_board = client.get(f"/crews/{moth['crew_id']}/board", headers=bela_headers).json()

    assert fulfilled["status"] == "fulfilled"
    assert any(item["status"] == "fulfilled" for item in gilt_board["deals"])
    assert any(item["status"] == "fulfilled" for item in moth_board["deals"])
