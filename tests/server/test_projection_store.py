import json
import sqlite3

from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app
from hollow_lodge.server.projections import contract_board_from_events


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


def test_contract_board_route_reads_fresh_projection_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    original_read = client.app.state.projection_store.read_contract_board
    calls = {"count": 0}

    def tracked_read_contract_board():
        calls["count"] += 1
        return original_read()

    client.app.state.projection_store.read_contract_board = tracked_read_contract_board

    response = client.get("/contracts", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert calls["count"] == 1
    assert response.json()["contracts"][0]["contract_id"] == "contract_false_finger"


def test_contract_board_route_falls_back_to_event_log_when_projection_is_stale(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    activated = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )

    def fail_if_projection_read():
        raise AssertionError("stale projection should not be used")

    client.app.state.projection_store.read_contract_board = fail_if_projection_read

    response = client.get("/contracts", headers=auth(ada["token"]))

    assert activated.status_code == 201
    assert response.status_code == 200
    assert {
        contract["contract_id"]
        for contract in response.json()["contracts"]
    } == {"contract_false_finger", "contract_ash_window"}


def test_projection_store_rebuilds_for_environment_configured_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("HOLLOW_LODGE_DATA_DIR", str(data_dir))

    client = TestClient(create_app())

    response = client.get("/diagnostics")

    projection = response.json()["data"]["projection_db"]
    assert projection["path"] == str(data_dir / "server-projections.sqlite3")
    assert projection["exists"] is True
    assert projection["status"] == "available"


def test_projection_store_materializes_public_contract_board_without_hidden_truth(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/diagnostics")

    assert response.status_code == 200
    projection = response.json()["data"]["projection_db"]
    assert projection["path"] == str(tmp_path / "server-projections.sqlite3")
    assert projection["exists"] is True
    assert projection["status"] == "available"
    assert projection["contract_count"] == 1
    assert projection["last_sequence"] > 0

    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        rows = connection.execute(
            "select contract_id, payload_json from contract_board order by contract_id"
        ).fetchall()

    assert len(rows) == 1
    assert rows[0][0] == "contract_false_finger"
    payload = json.loads(rows[0][1])
    assert payload["title"] == "The Saint's False Finger"
    assert "saint-bone forgery" not in rows[0][1]
    assert "hidden_truth" not in rows[0][1]


def test_projection_store_rebuilds_after_new_public_contract_event(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    activated = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )

    stale_response = client.get("/diagnostics")
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    response = client.get("/diagnostics")

    assert activated.status_code == 201
    stale_projection = stale_response.json()["data"]["projection_db"]
    assert stale_projection["status"] == "stale"
    assert stale_projection["contract_count"] == 1
    assert stale_projection["lag"] > 0
    projection = response.json()["data"]["projection_db"]
    assert projection["status"] == "available"
    assert projection["contract_count"] == 2
    assert projection["lag"] == 0
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        contract_ids = [
            row[0]
            for row in connection.execute(
                "select contract_id from contract_board order by contract_id"
            ).fetchall()
        ]
        meta_rows = dict(
            connection.execute("select key, value from projection_meta").fetchall()
        )

    assert contract_ids == ["contract_ash_window", "contract_false_finger"]
    assert int(meta_rows["last_sequence"]) == projection["last_sequence"]
    assert client.app.state.projection_store.read_contract_board() == (
        contract_board_from_events(client.app.state.event_store.read())
    )


def test_projection_diagnostics_does_not_mutate_stale_projection(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    initial = client.get("/diagnostics").json()["data"]["projection_db"]

    activated = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )
    first_diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]
    second_diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        contract_count = connection.execute(
            "select count(*) from contract_board"
        ).fetchone()[0]

    assert activated.status_code == 201
    assert initial["lag"] == 0
    assert first_diagnostics["status"] == "stale"
    assert first_diagnostics["contract_count"] == 1
    assert first_diagnostics == second_diagnostics
    assert contract_count == 1
