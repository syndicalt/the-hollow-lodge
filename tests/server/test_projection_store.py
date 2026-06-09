import json
import sqlite3

from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


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
