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


def test_starter_contract_seed_is_visible_without_hidden_truth(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    response = client.get("/contracts", headers=auth(ada["token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["campaign"]["title"] == "Saints & Ledgers"
    contract = body["contracts"][0]
    assert contract["title"] == "The Saint's False Finger"
    assert contract["phase"]["name"] == "Auction Preview"
    assert contract["crew_heat"] == 0
    assert "hidden_truth" not in response.text
    assert "finger is a saint-bone forgery" not in response.text


def test_hidden_truth_is_committed_server_only_and_not_in_visible_events(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    event_log = (tmp_path / "server-events.jsonl").read_text()
    assert "contract.hidden_truth.seeded" in event_log
    assert "finger is a saint-bone forgery" in event_log

    visible = client.get("/events", headers=auth(ada["token"]))
    assert visible.status_code == 200
    visible_text = visible.text
    assert "contract.board.published" in visible_text
    assert "contract.hidden_truth.seeded" not in visible_text
    assert "finger is a saint-bone forgery" not in visible_text


def test_inbox_renders_contract_state_and_empty_notices(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    response = client.get("/inbox", headers=auth(ada["token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["player_id"] == ada["player_id"]
    assert body["display_name"] == "Ada"
    assert body["active_contracts"][0]["title"] == "The Saint's False Finger"
    assert body["active_contracts"][0]["proof_dossier_needs"] == [
        "provenance chain",
        "material authenticity",
        "auction leverage",
    ]
    assert body["incoming_proof_fragments"] == []


def test_admin_can_activate_second_contract_seed_and_render_it(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    seed = "tests/fixtures/ash_window_contract.json"

    activated = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": seed},
    )
    contracts = client.get("/contracts", headers=auth(ada["token"]))
    inbox = client.get("/inbox", headers=auth(ada["token"]))
    events = client.get("/events", headers=auth(ada["token"]))

    assert activated.status_code == 201
    assert activated.json() == {
        "contract_id": "contract_ash_window",
        "lifecycle_status": "active",
    }
    rendered = {
        contract["contract_id"]: contract
        for contract in contracts.json()["contracts"]
    }
    assert rendered["contract_ash_window"]["title"] == "The Ash Window"
    assert rendered["contract_ash_window"]["phase"]["name"] == "Cinder Preview"
    assert rendered["contract_ash_window"]["lifecycle_status"] == "active"
    assert any(
        contract["contract_id"] == "contract_ash_window"
        for contract in inbox.json()["active_contracts"]
    )
    assert "cinder oracle" not in contracts.text
    assert "contract.hidden_truth.seeded" not in events.text
    assert "cinder oracle" not in events.text


def test_admin_contract_activation_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))

    first = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )
    replay = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()


def test_admin_contract_activation_rejects_invalid_seed(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    bad_seed = tmp_path / "bad.json"
    bad_seed.write_text("{}", encoding="utf-8")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))

    response = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-bad",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": str(bad_seed)},
    )

    assert response.status_code == 422
