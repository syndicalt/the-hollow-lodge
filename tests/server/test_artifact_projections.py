from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def command_auth(token: str, key: str) -> dict[str, str]:
    return {**auth(token), "Idempotency-Key": key}


def register(client: TestClient, invite: str, name: str) -> dict:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def test_boards_include_visible_artifacts(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create"),
        json={"name": "Gilt"},
    ).json()

    contracts = client.get("/contracts", headers=auth(ada["token"]))
    inbox = client.get("/inbox", headers=auth(ada["token"]))
    board = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert "visible_artifacts" in contracts.json()
    assert "visible_artifacts" in inbox.json()
    assert "visible_artifacts" in board.json()
    assert any(
        artifact["artifact_id"] == "artifact_lot_card"
        for artifact in board.json()["visible_artifacts"]
    )
