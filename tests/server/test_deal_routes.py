from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def register(client: TestClient, invite: str, name: str) -> dict[str, str]:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def command_auth(token: str, key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_crew(client: TestClient, token: str, name: str, key: str) -> dict:
    response = client.post("/crews", json={"name": name}, headers=command_auth(token, key))
    assert response.status_code == 201
    return response.json()


def proposed_deal_payload(gilt: dict, moth: dict) -> dict:
    return {
        "contract_id": "contract_false_finger",
        "proposer_crew_id": gilt["crew_id"],
        "recipient_crew_id": moth["crew_id"],
        "offered_artifact_ids": ["artifact_ledger_rubric"],
        "requested_artifact_ids": ["artifact_chapel_debt_mark"],
        "soft_terms": ["Do not cite us."],
        "expires_phase": "Auction Preview",
    }


def test_deal_routes_propose_list_accept(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "Gilt Knives", "crew-gilt")
    moth = create_crew(client, bela["token"], "Moth Lanterns", "crew-moth")
    app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="test setup",
        idempotency_key="grant-chapel",
    )

    propose = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    visible = client.get("/deals", headers=auth(bela["token"]))
    accept = client.post(
        f"/deals/{propose.json()['deal_id']}/accept",
        headers=command_auth(bela["token"], "deal-accept"),
        json={},
    )

    assert propose.status_code == 201
    assert propose.json()["status"] == "proposed"
    assert visible.status_code == 200
    assert visible.json()["deals"][0]["soft_terms"] == ["Do not cite us."]
    assert accept.status_code == 200
    assert accept.json()["status"] == "fulfilled"


def test_non_member_cannot_accept_deal(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "Gilt Knives", "crew-gilt")
    moth = create_crew(client, bela["token"], "Moth Lanterns", "crew-moth")
    app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="test setup",
        idempotency_key="grant-chapel",
    )
    propose = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )

    accept = client.post(
        f"/deals/{propose.json()['deal_id']}/accept",
        headers=command_auth(caro["token"], "deal-accept"),
        json={},
    )

    assert accept.status_code == 403
    assert accept.json()["detail"] == "not a crew member"
