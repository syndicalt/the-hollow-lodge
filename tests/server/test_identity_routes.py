from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def test_invite_registration_succeeds_once_and_stores_hashed_token(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))

    response = client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["player_id"].startswith("player_")
    assert len(body["token"]) >= 43
    assert body["display_name"] == "Ada"

    replay = client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Grace"},
    )

    assert replay.status_code == 409
    assert "alpha-code" not in replay.text
    assert body["token"] not in (tmp_path / "server-events.jsonl").read_text()


def test_token_auth_rejects_missing_invalid_and_revoked_tokens(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["alpha-code"])
    client = TestClient(app)
    token = client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
    ).json()["token"]

    assert client.get("/identity/me").status_code == 401
    assert client.get("/identity/me", headers={"Authorization": "Bearer bad-token"}).status_code == 401
    assert client.get("/identity/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    player_id = client.get(
        "/identity/me",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["player_id"]
    app.state.identity_service.revoke_player_token(player_id)

    assert client.get("/identity/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_invalid_invite_error_does_not_leak_secret_values(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))

    response = client.post(
        "/identity/register",
        json={"invite_code": "wrong-secret-code", "display_name": "Ada"},
    )

    assert response.status_code == 401
    assert "wrong-secret-code" not in response.text
    assert "alpha-code" not in response.text
