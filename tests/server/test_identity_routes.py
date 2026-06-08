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
    events = (tmp_path / "server-events.jsonl").read_text()
    assert body["token"] not in events
    assert "alpha-code" not in events


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


def test_access_key_request_is_recorded_without_registering_player(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["alpha-code"])
    client = TestClient(app)

    response = client.post(
        "/identity/key-requests",
        json={"display_name": "Ada", "contact": "ada@example.com"},
        headers={"Idempotency-Key": "key-request-ada"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body == {
        "request_id": "key_request_0001",
        "display_name": "Ada",
        "status": "pending",
    }
    assert app.state.identity_service.has_player("player_0001") is False
    events = (tmp_path / "server-events.jsonl").read_text(encoding="utf-8")
    assert "identity.key_request.created" in events
    assert "ada@example.com" in events


def test_access_key_request_replay_is_idempotent(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))

    first = client.post(
        "/identity/key-requests",
        json={"display_name": "Ada", "contact": "ada@example.com"},
        headers={"Idempotency-Key": "key-request-ada"},
    )
    replay = client.post(
        "/identity/key-requests",
        json={"display_name": "Ada", "contact": "ada@example.com"},
        headers={"Idempotency-Key": "key-request-ada"},
    )
    conflict = client.post(
        "/identity/key-requests",
        json={"display_name": "Grace", "contact": "grace@example.com"},
        headers={"Idempotency-Key": "key-request-ada"},
    )

    assert first.status_code == 202
    assert replay.status_code == 202
    assert replay.json() == first.json()
    assert conflict.status_code == 409


def test_access_key_request_survives_app_recreation_from_event_log(tmp_path):
    first_client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))
    first = first_client.post(
        "/identity/key-requests",
        json={"display_name": "Ada", "contact": "ada@example.com"},
        headers={"Idempotency-Key": "key-request-ada"},
    )

    second_client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))
    replay = second_client.post(
        "/identity/key-requests",
        json={"display_name": "Ada", "contact": "ada@example.com"},
        headers={"Idempotency-Key": "key-request-ada"},
    )

    assert first.status_code == 202
    assert replay.status_code == 202
    assert replay.json() == first.json()


def test_admin_invite_creation_requires_admin_token(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))

    missing = client.post(
        "/identity/admin/invites",
        headers={"Idempotency-Key": "invite-create-1"},
    )
    wrong = client.post(
        "/identity/admin/invites",
        headers={"Idempotency-Key": "invite-create-1", "X-Hollow-Lodge-Admin-Token": "bad"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_admin_invite_creation_issues_redeemable_invite(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))

    invite = client.post(
        "/identity/admin/invites",
        headers={"Idempotency-Key": "invite-create-1", "X-Hollow-Lodge-Admin-Token": "admin-secret"},
    )

    assert invite.status_code == 201
    invite_code = invite.json()["invite_code"]
    assert invite_code.startswith("lodge_")
    assert invite_code not in (tmp_path / "server-events.jsonl").read_text(encoding="utf-8")

    registered = client.post(
        "/identity/register",
        json={"invite_code": invite_code, "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    )

    assert registered.status_code == 201
    assert registered.json()["display_name"] == "Ada"
    assert invite_code not in (tmp_path / "server-events.jsonl").read_text(encoding="utf-8")


def test_admin_invite_creation_replays_by_idempotency_key(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))

    first = client.post(
        "/identity/admin/invites",
        headers={"Idempotency-Key": "invite-create-1", "X-Hollow-Lodge-Admin-Token": "admin-secret"},
    )
    replay = client.post(
        "/identity/admin/invites",
        headers={"Idempotency-Key": "invite-create-1", "X-Hollow-Lodge-Admin-Token": "admin-secret"},
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()


def test_admin_can_list_invite_inventory_without_raw_codes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))
    invite = client.post(
        "/identity/admin/invites",
        headers={"Idempotency-Key": "invite-create-1", "X-Hollow-Lodge-Admin-Token": "admin-secret"},
    ).json()

    response = client.get(
        "/identity/admin/invites",
        headers={"X-Hollow-Lodge-Admin-Token": "admin-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "invites": [
            {
                "invite_id": "invite_0001",
                "used": False,
            }
        ]
    }
    assert invite["invite_code"] not in response.text


def test_admin_player_lookup_returns_registered_players_without_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))
    registered = client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    ).json()

    response = client.get(
        "/identity/admin/players",
        headers={"X-Hollow-Lodge-Admin-Token": "admin-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "players": [
            {
                "player_id": registered["player_id"],
                "display_name": "Ada",
                "token_revoked": False,
            }
        ]
    }
    assert registered["token"] not in response.text
    assert "token_hash" not in response.text


def test_admin_player_detail_lookup_returns_crews_without_auth_material(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))
    registered = client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    ).json()
    crew = client.post(
        "/crews",
        json={"name": "The Gilt Knives"},
        headers={
            "Authorization": f"Bearer {registered['token']}",
            "Idempotency-Key": "crew-create-gilt",
        },
    ).json()

    missing_admin = client.get(
        f"/identity/admin/players/{registered['player_id']}",
        headers={"Authorization": f"Bearer {registered['token']}"},
    )
    response = client.get(
        f"/identity/admin/players/{registered['player_id']}",
        headers={"X-Hollow-Lodge-Admin-Token": "admin-secret"},
    )
    missing = client.get(
        "/identity/admin/players/player_missing",
        headers={"X-Hollow-Lodge-Admin-Token": "admin-secret"},
    )

    assert missing_admin.status_code == 401
    assert response.status_code == 200
    assert response.json() == {
        "player_id": registered["player_id"],
        "display_name": "Ada",
        "token_revoked": False,
        "crew_ids": [crew["crew_id"]],
        "crew_count": 1,
    }
    assert missing.status_code == 404
    assert registered["token"] not in response.text
    assert "token_hash" not in response.text
    assert "join_code" not in response.text
    assert "alpha-code" not in response.text


def test_admin_can_verify_and_export_event_log(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))
    client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    )

    verify = client.get(
        "/identity/admin/event-log/verify",
        headers={"X-Hollow-Lodge-Admin-Token": "admin-secret"},
    )
    exported = client.get(
        "/identity/admin/event-log/export",
        headers={"X-Hollow-Lodge-Admin-Token": "admin-secret"},
    )

    assert verify.status_code == 200
    assert verify.json()["ok"] is True
    assert verify.json()["event_count"] >= 1
    assert verify.json()["repaired_trailing_row"] is False
    assert exported.status_code == 200
    assert any(event["type"] == "identity.player.registered" for event in exported.json()["events"])
    assert "alpha-code" not in exported.text


def test_admin_can_list_access_key_requests(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))
    client.post(
        "/identity/key-requests",
        json={"display_name": "Ada", "contact": "ada@example.com"},
        headers={"Idempotency-Key": "key-request-ada"},
    )

    missing = client.get("/identity/admin/key-requests")
    listed = client.get(
        "/identity/admin/key-requests",
        headers={"X-Hollow-Lodge-Admin-Token": "admin-secret"},
    )

    assert missing.status_code == 401
    assert listed.status_code == 200
    assert listed.json() == {
        "key_requests": [
            {
                "request_id": "key_request_0001",
                "display_name": "Ada",
                "contact": "ada@example.com",
                "status": "pending",
            }
        ]
    }


def test_admin_approves_access_key_request_into_redeemable_invite(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))
    requested = client.post(
        "/identity/key-requests",
        json={"display_name": "Ada", "contact": "ada@example.com"},
        headers={"Idempotency-Key": "key-request-ada"},
    ).json()

    approved = client.post(
        f"/identity/admin/key-requests/{requested['request_id']}/approve",
        headers={
            "Idempotency-Key": "approve-request-ada",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )

    assert approved.status_code == 201
    body = approved.json()
    assert body["request_id"] == requested["request_id"]
    assert body["status"] == "approved"
    invite_code = body["invite_code"]
    assert invite_code.startswith("lodge_")
    assert invite_code not in (tmp_path / "server-events.jsonl").read_text(encoding="utf-8")

    registered = client.post(
        "/identity/register",
        json={"invite_code": invite_code, "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    )
    listed = client.get(
        "/identity/admin/key-requests",
        headers={"X-Hollow-Lodge-Admin-Token": "admin-secret"},
    ).json()

    assert registered.status_code == 201
    assert listed["key_requests"][0]["status"] == "approved"
    assert invite_code not in (tmp_path / "server-events.jsonl").read_text(encoding="utf-8")


def test_admin_approval_replays_by_idempotency_key(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))
    requested = client.post(
        "/identity/key-requests",
        json={"display_name": "Ada", "contact": "ada@example.com"},
        headers={"Idempotency-Key": "key-request-ada"},
    ).json()

    first = client.post(
        f"/identity/admin/key-requests/{requested['request_id']}/approve",
        headers={
            "Idempotency-Key": "approve-request-ada",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )
    replay = client.post(
        f"/identity/admin/key-requests/{requested['request_id']}/approve",
        headers={
            "Idempotency-Key": "approve-request-ada",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()


def test_admin_approval_replay_survives_app_recreation(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    first_client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))
    requested = first_client.post(
        "/identity/key-requests",
        json={"display_name": "Ada", "contact": "ada@example.com"},
        headers={"Idempotency-Key": "key-request-ada"},
    ).json()
    approved = first_client.post(
        f"/identity/admin/key-requests/{requested['request_id']}/approve",
        headers={
            "Idempotency-Key": "approve-request-ada",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )

    second_client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))
    replay = second_client.post(
        f"/identity/admin/key-requests/{requested['request_id']}/approve",
        headers={
            "Idempotency-Key": "approve-request-ada",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )

    assert approved.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == approved.json()


def test_admin_approval_rejects_missing_or_already_approved_request(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))
    requested = client.post(
        "/identity/key-requests",
        json={"display_name": "Ada", "contact": "ada@example.com"},
        headers={"Idempotency-Key": "key-request-ada"},
    ).json()

    missing = client.post(
        "/identity/admin/key-requests/key_request_missing/approve",
        headers={
            "Idempotency-Key": "approve-missing",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )
    first = client.post(
        f"/identity/admin/key-requests/{requested['request_id']}/approve",
        headers={
            "Idempotency-Key": "approve-request-ada",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )
    second = client.post(
        f"/identity/admin/key-requests/{requested['request_id']}/approve",
        headers={
            "Idempotency-Key": "approve-request-ada-second",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )

    assert missing.status_code == 404
    assert first.status_code == 201
    assert second.status_code == 409
