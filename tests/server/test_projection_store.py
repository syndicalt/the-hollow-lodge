import json
import sqlite3

from fastapi.testclient import TestClient

from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.server.app import create_app
from hollow_lodge.server.projections import contract_board_from_events
from hollow_lodge.server.seed_data import STARTER_CONTRACT


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


def command_auth(token: str, key: str) -> dict[str, str]:
    return {**auth(token), "Idempotency-Key": key}


def create_crew(client: TestClient, token: str, key: str, name: str) -> dict:
    response = client.post(
        "/crews",
        headers=command_auth(token, key),
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()


def submit_action(client: TestClient, player: dict, crew: dict, key: str, intent: str) -> dict:
    response = client.post(
        "/actions",
        headers=command_auth(player["token"], key),
        json={"crew_id": crew["crew_id"], "intent": intent, "confirmed": True},
    )
    assert response.status_code == 201
    return response.json()


def set_claim(client: TestClient, player: dict, crew: dict, key: str, claim: str) -> dict:
    response = client.patch(
        f"/proofs/dossiers/{crew['crew_id']}/framing",
        headers=command_auth(player["token"], key),
        json={"claim": claim},
    )
    assert response.status_code == 200
    return response.json()


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
    monkeypatch.setenv("HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    out_of_band_contract = STARTER_CONTRACT.model_copy(
        update={"contract_id": "contract_out_of_band", "title": "Out Of Band"}
    )
    client.app.state.event_store.append_command(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload=out_of_band_contract.model_dump(mode="json"),
        idempotency_key="out-of-band-contract",
    )

    def fail_if_projection_read():
        raise AssertionError("stale projection should not be used")

    client.app.state.projection_store.read_contract_board = fail_if_projection_read

    response = client.get("/contracts", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert {
        contract["contract_id"]
        for contract in response.json()["contracts"]
    } == {"contract_false_finger", "contract_out_of_band"}


def test_contract_activation_refreshes_projection_for_flagged_reads(tmp_path, monkeypatch):
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
    original_read = client.app.state.projection_store.read_contract_board
    calls = {"count": 0}

    def tracked_read_contract_board():
        calls["count"] += 1
        return original_read()

    client.app.state.projection_store.read_contract_board = tracked_read_contract_board

    response = client.get("/contracts", headers=auth(ada["token"]))
    diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]

    assert activated.status_code == 201
    assert diagnostics["lag"] == 0
    assert diagnostics["contract_count"] == 2
    assert calls["count"] == 1
    assert {
        contract["contract_id"]
        for contract in response.json()["contracts"]
    } == {"contract_false_finger", "contract_ash_window"}


def test_contract_archive_refreshes_projection_for_flagged_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS", "1")
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
    archived = client.post(
        "/contracts/admin/contract_ash_window/archive",
        headers={
            "Idempotency-Key": "archive-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )
    original_read = client.app.state.projection_store.read_contract_board
    calls = {"count": 0}

    def tracked_read_contract_board():
        calls["count"] += 1
        return original_read()

    client.app.state.projection_store.read_contract_board = tracked_read_contract_board

    response = client.get("/contracts", headers=auth(ada["token"]))
    rendered = {
        contract["contract_id"]: contract
        for contract in response.json()["contracts"]
    }

    assert archived.status_code == 200
    assert calls["count"] == 1
    assert rendered["contract_ash_window"]["lifecycle_status"] == "archived"


def test_phase_resolution_refreshes_projection_for_flagged_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    linus = register(client, "b", "Linus")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, linus["token"], "crew-create-moth", "The Moth Choir")
    set_claim(client, ada, gilt, "claim-gilt", "The finger is likely a false relic.")
    submit_action(
        client,
        ada,
        gilt,
        "action-gilt",
        "Compare the red ledger date to the chapel timestamp for forged provenance.",
    )
    set_claim(client, linus, moth, "claim-moth", "The reliquary has occult resonance.")
    submit_action(
        client,
        linus,
        moth,
        "action-moth",
        "Watch the moth jar door omen near the auction room for occult resonance.",
    )
    locked = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock"),
        json={"hours_elapsed": 6},
    )
    original_read = client.app.state.projection_store.read_contract_board
    calls = {"count": 0}

    def tracked_read_contract_board():
        calls["count"] += 1
        return original_read()

    client.app.state.projection_store.read_contract_board = tracked_read_contract_board

    response = client.get("/contracts", headers=auth(ada["token"]))
    diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]
    rendered = {
        contract["contract_id"]: contract
        for contract in response.json()["contracts"]
    }

    assert locked.status_code == 200
    assert diagnostics["lag"] == 0
    assert calls["count"] == 1
    assert rendered["contract_false_finger"]["phase"]["status"] == "resolved"


def test_contract_mutation_still_succeeds_when_projection_refresh_fails(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))

    def fail_refresh(events):
        raise sqlite3.OperationalError("projection store unavailable")

    client.app.state.projection_store.rebuild = fail_refresh

    response = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )

    assert response.status_code == 201
    assert response.json()["contract_id"] == "contract_ash_window"


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
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    out_of_band_contract = STARTER_CONTRACT.model_copy(
        update={"contract_id": "contract_out_of_band", "title": "Out Of Band"}
    )
    client.app.state.event_store.append_command(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload=out_of_band_contract.model_dump(mode="json"),
        idempotency_key="out-of-band-contract",
    )

    stale_response = client.get("/diagnostics")
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    response = client.get("/diagnostics")

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

    assert contract_ids == ["contract_false_finger", "contract_out_of_band"]
    assert int(meta_rows["last_sequence"]) == projection["last_sequence"]
    assert client.app.state.projection_store.read_contract_board() == (
        contract_board_from_events(client.app.state.event_store.read())
    )


def test_projection_diagnostics_does_not_mutate_stale_projection(tmp_path, monkeypatch):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    initial = client.get("/diagnostics").json()["data"]["projection_db"]
    out_of_band_contract = STARTER_CONTRACT.model_copy(
        update={"contract_id": "contract_out_of_band", "title": "Out Of Band"}
    )
    client.app.state.event_store.append_command(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload=out_of_band_contract.model_dump(mode="json"),
        idempotency_key="out-of-band-contract",
    )
    first_diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]
    second_diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        contract_count = connection.execute(
            "select count(*) from contract_board"
        ).fetchone()[0]

    assert initial["lag"] == 0
    assert first_diagnostics["status"] == "stale"
    assert first_diagnostics["contract_count"] == 1
    assert first_diagnostics == second_diagnostics
    assert contract_count == 1
