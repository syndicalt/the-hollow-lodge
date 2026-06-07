from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def test_invite_registration_succeeds_once_and_stores_hashed_token(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))

    response = client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["player_id"].startswith("player_")
    assert len(body["token"]) >= 43
    assert body["display_name"] == "Ada"

    replay = client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Grace"},
        headers={"Idempotency-Key": "register-grace"},
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
        headers={"Idempotency-Key": "register-ada"},
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
        headers={"Idempotency-Key": "register-ada"},
    )

    assert response.status_code == 401
    assert "wrong-secret-code" not in response.text
    assert "alpha-code" not in response.text


def test_registered_player_auth_survives_app_recreation_from_event_log(tmp_path):
    first_app = create_app(data_dir=tmp_path, invite_codes=["alpha-code"])
    first_client = TestClient(first_app)
    registered = first_client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    ).json()

    second_client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))

    response = second_client.get(
        "/identity/me",
        headers={"Authorization": f"Bearer {registered['token']}"},
    )
    assert response.status_code == 200
    assert response.json()["player_id"] == registered["player_id"]

    reused = second_client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Grace"},
        headers={"Idempotency-Key": "register-grace"},
    )
    assert reused.status_code == 409


def test_register_replay_uses_request_idempotency_key(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))

    first = client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    )
    replay = client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()


def test_register_replay_survives_app_recreation_from_event_log(tmp_path):
    first_client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))
    first = first_client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    )

    second_client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))
    replay = second_client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()


def test_expired_registration_replay_cache_does_not_return_token(tmp_path):
    first_client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))
    first = first_client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    )
    (tmp_path / "server-events.registration-replays.json").write_text(
        '{"register-ada":{"created_at":"1970-01-01T00:00:00Z","token":"expired"}}\n',
        encoding="utf-8",
    )

    second_client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))
    replay = second_client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    )

    assert first.status_code == 201
    assert replay.status_code == 409


def test_register_replay_rejects_same_key_with_different_payload(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))

    first = client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    )
    conflict = client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Grace"},
        headers={"Idempotency-Key": "register-ada"},
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
