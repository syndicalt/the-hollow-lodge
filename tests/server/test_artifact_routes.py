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


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_player_sees_public_starter_artifacts(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    response = client.get("/artifacts", headers=auth(ada["token"]))

    assert response.status_code == 200
    artifact_ids = {
        artifact["artifact_id"]
        for artifact in response.json()["artifacts"]
    }
    assert "artifact_lot_card" in artifact_ids
    assert "artifact_ledger_rubric" in artifact_ids
    assert "artifact_chapel_debt_mark" not in artifact_ids


def test_player_can_inspect_visible_artifact_without_hidden_flags(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    response = client.get(
        "/artifacts/artifact_ledger_rubric",
        headers=auth(ada["token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["artifact_id"] == "artifact_ledger_rubric"
    assert "full_text" in body
    assert "ink-after-binding" not in response.text


def test_hidden_artifact_is_not_visible_until_unlocked(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    response = client.get(
        "/artifacts/artifact_chapel_debt_mark",
        headers=auth(ada["token"]),
    )

    assert response.status_code == 404


def test_inspection_idempotency_conflict_returns_409(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    first_response = client.post(
        "/artifacts/artifact_lot_card/inspect",
        headers={
            **auth(ada["token"]),
            "Idempotency-Key": "inspect-conflict",
        },
    )
    second_response = client.post(
        "/artifacts/artifact_ledger_rubric/inspect",
        headers={
            **auth(ada["token"]),
            "Idempotency-Key": "inspect-conflict",
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "idempotency key conflict"


def test_crew_scoped_artifact_access_is_visible_through_routes(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew_response = client.post(
        "/crews",
        json={"name": "Ledger Cell"},
        headers={
            **auth(ada["token"]),
            "Idempotency-Key": "crew-ledger-cell",
        },
    )
    assert crew_response.status_code == 201
    crew = crew_response.json()

    client.app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[crew["crew_id"]],
        reason="review guard",
        idempotency_key="grant-chapel-to-crew",
    )

    route_response = client.get("/artifacts", headers=auth(ada["token"]))
    route_artifact_ids = {
        artifact["artifact_id"]
        for artifact in route_response.json()["artifacts"]
    }
    inspect_response = client.get(
        "/artifacts/artifact_chapel_debt_mark",
        headers=auth(ada["token"]),
    )

    assert route_response.status_code == 200
    assert "artifact_chapel_debt_mark" in route_artifact_ids
    assert inspect_response.status_code == 200
    assert inspect_response.json()["artifact_id"] == "artifact_chapel_debt_mark"


def test_graph_seed_event_is_server_only_and_appended_once(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    first_response = client.get("/artifacts", headers=auth(ada["token"]))
    second_response = client.get("/artifacts", headers=auth(ada["token"]))

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    events = client.app.state.event_store.read()
    seed_events = [
        event for event in events if event.type == "artifact.graph.seeded"
    ]
    assert len(seed_events) == 1
    assert seed_events[0].visibility.model_dump(mode="json") == {
        "entries": [{"kind": "server", "id": None}]
    }

    visible = client.get("/events", headers=auth(ada["token"]))
    assert visible.status_code == 200
    assert "artifact.graph.seeded" not in visible.text


def test_public_artifact_list_never_includes_full_text_or_hidden_flags(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    response = client.get("/artifacts", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert "full_text" not in response.text
    assert "hidden_flags" not in response.text
    assert "ink-after-binding" not in response.text


def test_activated_contract_public_artifacts_are_visible_without_hidden_nodes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )

    response = client.get("/artifacts", headers=auth(ada["token"]))

    assert response.status_code == 200
    artifact_ids = {
        artifact["artifact_id"]
        for artifact in response.json()["artifacts"]
    }
    assert "artifact_ash_notice" in artifact_ids
    assert "artifact_soot_sample" not in artifact_ids
    assert "future-burn" not in response.text
