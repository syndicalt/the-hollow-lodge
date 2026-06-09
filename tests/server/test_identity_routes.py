from fastapi.testclient import TestClient

from hollow_lodge.domain.events import EventVisibility
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


def test_register_replay_can_use_operational_sqlite_store(tmp_path, monkeypatch):
    operational_db = tmp_path / "operational.sqlite3"
    monkeypatch.setenv(
        "HOLLOW_LODGE_OPERATIONAL_DATABASE_URL",
        f"sqlite:///{operational_db}",
    )
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
    diagnostics = second_client.get("/diagnostics")

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()
    assert operational_db.exists()
    assert not (tmp_path / "server-events.registration-replays.json").exists()
    assert diagnostics.json()["data"]["identity_replay_store"] == {
        "backend": "sqlite",
        "path": str(operational_db),
        "database_url_env": "HOLLOW_LODGE_OPERATIONAL_DATABASE_URL",
    }


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


def test_admin_invite_creation_replay_can_use_operational_sqlite_store(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv(
        "HOLLOW_LODGE_OPERATIONAL_DATABASE_URL",
        f"sqlite:///{tmp_path / 'operational.sqlite3'}",
    )
    first_client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))

    first = first_client.post(
        "/identity/admin/invites",
        headers={
            "Idempotency-Key": "invite-create-1",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )
    second_client = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))
    replay = second_client.post(
        "/identity/admin/invites",
        headers={
            "Idempotency-Key": "invite-create-1",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()
    assert not (tmp_path / "server-events.invite-replays.json").exists()


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


def test_player_profile_returns_safe_crew_memberships_without_auth_material(tmp_path):
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

    response = client.get(
        "/identity/profile",
        headers={"Authorization": f"Bearer {registered['token']}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["player_id"] == registered["player_id"]
    assert body["display_name"] == "Ada"
    assert body["crew_count"] == 1
    assert body["crews"][0] == {
        "crew_id": crew["crew_id"],
        "name": "The Gilt Knives",
        "member_count": 1,
        "ready_for_full_contracts": False,
        "legacy": {
            "crew_id": crew["crew_id"],
            "reputation": 0,
            "heat": 0,
            "favors": 0,
            "debts": 0,
            "scars": [],
            "deal_conduct": {
                "score": 0,
                "reliability": "unproven",
                "fulfilled_count": 0,
                "canceled_count": 0,
                "declined_count": 0,
                "open_count": 0,
            },
            "counterintelligence": {
                "investigations_started": 0,
                "containments_started": 0,
                "heat_from_containment": 0,
            },
            "rumor_memory": {
                "verified_count": 0,
                "assessment_counts": {},
                "recent": [],
            },
            "rumor_escalation": {
                "contain_count": 0,
                "exploit_count": 0,
                "integrate_count": 0,
                "credible_count_total": 0,
            },
            "completed_contracts": [],
            "future_opportunities": [],
        },
    }
    assert registered["token"] not in response.text
    assert "token_hash" not in response.text
    assert "join_code" not in response.text
    assert "alpha-code" not in response.text


def test_player_profile_includes_safe_crew_legacy_without_hidden_sources(tmp_path):
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
    client.app.state.event_store.append(
        event_type="crew.legacy.delta.recorded",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload={
            "crew_id": crew["crew_id"],
            "contract_id": "contract_false_finger",
            "contract_title": "The Saint's False Finger",
            "phase": "Auction Preview",
            "standing": "Strong lead",
            "score": 82,
            "outcome": "lead",
            "deltas": {
                "reputation": 2,
                "heat": 1,
                "favors": 1,
                "debts": 0,
                "scars": [],
            },
            "summary": "Strong lead: reputation +2, heat +1, favors +1.",
            "hidden_source": "server-only oracle notes",
        },
    )

    response = client.get(
        "/identity/profile",
        headers={"Authorization": f"Bearer {registered['token']}"},
    )

    assert response.status_code == 200
    profile_crew = response.json()["crews"][0]
    assert profile_crew["legacy"]["reputation"] == 2
    assert profile_crew["legacy"]["heat"] == 1
    assert profile_crew["legacy"]["favors"] == 1
    assert profile_crew["legacy"]["completed_contracts"] == [
        {
            "contract_id": "contract_false_finger",
            "title": "The Saint's False Finger",
            "phase": "Auction Preview",
            "standing": "Strong lead",
            "score": 82,
            "outcome": "lead",
        }
    ]
    assert "server-only oracle notes" not in response.text
    assert "hidden_source" not in response.text
    assert registered["token"] not in response.text


def test_player_profile_reads_fresh_projected_crew_legacy_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_CREW_LEGACY_PROJECTION_READS", "1")
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
    client.app.state.event_store.append(
        event_type="crew.legacy.delta.recorded",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload={
            "crew_id": crew["crew_id"],
            "contract_id": "contract_false_finger",
            "contract_title": "The Saint's False Finger",
            "phase": "Auction Preview",
            "standing": "Strong lead",
            "score": 82,
            "outcome": "lead",
            "deltas": {
                "reputation": 2,
                "heat": 1,
                "favors": 1,
                "debts": 0,
                "scars": [],
            },
            "summary": "Strong lead: reputation +2, heat +1, favors +1.",
        },
    )
    events = client.app.state.event_store.read()
    client.app.state.projection_store.rebuild(events)
    last_sequence = events[-1].sequence
    monkeypatch.setattr(
        client.app.state.event_store,
        "diagnostics",
        lambda: {
            "backend": "jsonl",
            "path": str(tmp_path / "server-events.jsonl"),
            "exists": True,
            "status": "available",
            "event_count": last_sequence,
            "last_sequence": last_sequence,
            "last_event_hash": events[-1].event_hash,
            "event_hash_chain_sha256": "a" * 64,
        },
    )
    monkeypatch.setattr(
        client.app.state.event_store,
        "read",
        lambda **_: (_ for _ in ()).throw(
            AssertionError("profile should use fresh projected crew legacy")
        ),
    )

    response = client.get(
        "/identity/profile",
        headers={"Authorization": f"Bearer {registered['token']}"},
    )

    assert response.status_code == 200
    assert response.json()["crews"][0]["legacy"]["reputation"] == 2


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


def test_admin_identity_lists_read_fresh_projection_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("HOLLOW_LODGE_IDENTITY_ADMIN_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))
    key_request = client.post(
        "/identity/key-requests",
        json={"display_name": "Grace", "contact": "grace@example.com"},
        headers={"Idempotency-Key": "key-request-grace"},
    ).json()
    client.post(
        "/identity/admin/invites",
        headers={
            "Idempotency-Key": "admin-invite-extra",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )
    registered = client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    ).json()

    client.app.state.identity_service.list_players = (
        lambda: (_ for _ in ()).throw(
            AssertionError("fresh identity player projection should be used")
        )
    )
    client.app.state.identity_service.list_invites = (
        lambda: (_ for _ in ()).throw(
            AssertionError("fresh identity invite projection should be used")
        )
    )
    client.app.state.identity_service.list_access_key_requests = (
        lambda: (_ for _ in ()).throw(
            AssertionError("fresh identity key request projection should be used")
        )
    )

    players = client.get(
        "/identity/admin/players",
        headers={"X-Hollow-Lodge-Admin-Token": "admin-secret"},
    )
    invites = client.get(
        "/identity/admin/invites",
        headers={"X-Hollow-Lodge-Admin-Token": "admin-secret"},
    )
    key_requests = client.get(
        "/identity/admin/key-requests",
        headers={"X-Hollow-Lodge-Admin-Token": "admin-secret"},
    )

    assert players.status_code == 200
    assert players.json() == {
        "players": [
            {
                "player_id": registered["player_id"],
                "display_name": "Ada",
                "token_revoked": False,
            }
        ]
    }
    assert invites.status_code == 200
    assert [invite["invite_id"] for invite in invites.json()["invites"]] == [
        "invite_0001"
    ]
    assert key_requests.status_code == 200
    assert key_requests.json()["key_requests"] == [
        {
            "request_id": key_request["request_id"],
            "display_name": "Grace",
            "contact": "grace@example.com",
            "status": "pending",
        }
    ]
    assert registered["token"] not in players.text


def test_admin_identity_lists_fall_back_when_projection_is_stale(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("HOLLOW_LODGE_IDENTITY_ADMIN_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["alpha-code"]))
    registered = client.post(
        "/identity/register",
        json={"invite_code": "alpha-code", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-ada"},
    ).json()
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    client.app.state.event_store.append_command(
        event_type="contract.note.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload={"note": "identity projection stale marker"},
        idempotency_key="identity-projection-stale-marker",
    )

    def fail_if_projection_read():
        raise AssertionError("stale identity admin projection should not be used")

    client.app.state.projection_store.read_admin_players = fail_if_projection_read

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
