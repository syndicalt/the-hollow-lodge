import json
import sqlite3

from fastapi.testclient import TestClient

from hollow_lodge.domain.deals import deal_rows_from_events
from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.server.app import create_app
from hollow_lodge.server.projections import (
    contract_board_from_events,
    crew_summaries_from_events,
)
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


def proposed_deal_payload(gilt: dict, moth: dict) -> dict:
    return {
        "contract_id": "contract_false_finger",
        "proposer_crew_id": gilt["crew_id"],
        "recipient_crew_id": moth["crew_id"],
        "offered_artifact_ids": ["artifact_ledger_rubric"],
        "requested_artifact_ids": ["artifact_chapel_debt_mark"],
        "soft_terms": ["Do not cite us."],
        "expires_phase": "Auction Preview",
    }


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


def test_crew_board_reads_fresh_projected_crew_summary_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_CREW_SUMMARY_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    joined = client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(grace["token"], "crew-join-grace"),
        json={"join_code": crew["join_code"]},
    )
    original_read = client.app.state.projection_store.read_crew_summary
    calls = {"count": 0}

    def tracked_read_crew_summary(crew_id: str):
        calls["count"] += 1
        return original_read(crew_id)

    client.app.state.projection_store.read_crew_summary = tracked_read_crew_summary
    client.app.state.crew_service.summary = (
        lambda crew_id: (_ for _ in ()).throw(
            AssertionError("fresh crew summary projection should be used")
        )
    )

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))
    diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]

    assert joined.status_code == 200
    assert response.status_code == 200
    assert diagnostics["lag"] == 0
    assert diagnostics["crew_count"] == 1
    assert calls["count"] == 1
    assert response.json()["crew"] == {
        "crew_id": crew["crew_id"],
        "name": "The Gilt Knives",
        "member_ids": ["player_0001", "player_0002"],
        "member_count": 2,
        "ready_for_full_contracts": False,
        "readiness_warning": (
            "Crews should have 3-5 players for full contracts; "
            "2-player starter slices are allowed."
        ),
    }
    assert "join_code" not in str(response.json()["crew"])


def test_crew_board_falls_back_when_projected_crew_summary_is_stale(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_CREW_SUMMARY_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
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

    def fail_if_projection_read(crew_id: str):
        raise AssertionError("stale crew summary projection should not be used")

    client.app.state.projection_store.read_crew_summary = fail_if_projection_read

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert response.json()["crew"]["crew_id"] == crew["crew_id"]
    assert response.json()["crew"]["member_ids"] == ["player_0001"]


def test_crew_creation_still_succeeds_when_projection_refresh_fails(
    tmp_path,
    monkeypatch,
):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    def fail_refresh(events):
        raise sqlite3.OperationalError("projection store unavailable")

    client.app.state.projection_store.rebuild = fail_refresh

    response = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "The Gilt Knives"


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


def test_projection_store_materializes_crew_summaries_without_join_codes(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    joined = client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(grace["token"], "crew-join-grace"),
        json={"join_code": crew["join_code"]},
    )

    assert joined.status_code == 200
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        rows = connection.execute(
            "select crew_id, member_count, payload_json from crew_summary"
        ).fetchall()

    assert rows == [
        (
            crew["crew_id"],
            2,
            (
                '{"crew_id":"crew_0001","member_count":2,'
                '"member_ids":["player_0001","player_0002"],'
                '"name":"The Gilt Knives",'
                '"readiness_warning":"Crews should have 3-5 players for full contracts; '
                '2-player starter slices are allowed.",'
                '"ready_for_full_contracts":false}'
            ),
        )
    ]
    assert "join_code" not in rows[0][2]
    assert crew["join_code"] not in rows[0][2]
    assert client.app.state.projection_store.read_crew_summary(crew["crew_id"]) == (
        crew_summaries_from_events(client.app.state.event_store.read())[crew["crew_id"]]
    )


def test_artifact_route_reads_fresh_projected_visible_artifacts_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    original_read = client.app.state.projection_store.read_visible_artifacts
    calls = {"count": 0}

    def tracked_read_visible_artifacts(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_artifacts = tracked_read_visible_artifacts
    client.app.state.artifact_service.visible_artifacts_for_player = (
        lambda player_id, crew_ids=(): (_ for _ in ()).throw(
            AssertionError("fresh artifact projection should be used")
        )
    )

    response = client.get("/artifacts", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert calls["count"] == 1
    assert {
        artifact["artifact_id"]
        for artifact in response.json()["artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}
    assert response.json()["edges"] == [
        {
            "source_id": "artifact_lot_card",
            "target_id": "artifact_ledger_rubric",
            "relation": "contradicts",
            "public_summary": "The public lot card and copied ledger disagree on custody.",
        }
    ]
    assert "full_text" not in response.text
    assert "hidden_flags" not in response.text
    assert "ink-after-binding" not in response.text


def test_artifact_route_falls_back_when_projection_is_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
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

    def fail_if_projection_read(player_id: str, crew_ids=()):
        raise AssertionError("stale artifact projection should not be used")

    client.app.state.projection_store.read_visible_artifacts = fail_if_projection_read

    response = client.get("/artifacts", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert {
        artifact["artifact_id"]
        for artifact in response.json()["artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}


def test_artifact_projection_reads_player_and_crew_scoped_surfaces(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(grace["token"], "crew-join-grace"),
        json={"join_code": crew["join_code"]},
    )
    client.app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[crew["crew_id"]],
        reason="projection test",
        idempotency_key="grant-chapel-to-crew",
    )
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    client.app.state.artifact_service.visible_artifacts_for_player = (
        lambda player_id, crew_ids=(): (_ for _ in ()).throw(
            AssertionError("fresh scoped artifact projection should be used")
        )
    )

    ada_response = client.get("/artifacts", headers=auth(ada["token"]))
    grace_response = client.get("/artifacts", headers=auth(grace["token"]))

    assert ada_response.status_code == 200
    assert grace_response.status_code == 200
    assert "artifact_chapel_debt_mark" in {
        artifact["artifact_id"]
        for artifact in ada_response.json()["artifacts"]
    }
    assert "artifact_chapel_debt_mark" in {
        artifact["artifact_id"]
        for artifact in grace_response.json()["artifacts"]
    }
    assert "full_text" not in ada_response.text
    assert "hidden_flags" not in ada_response.text


def test_artifact_transfer_refreshes_projection_for_flagged_reads(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")

    transferred = client.post(
        "/artifacts/artifact_lot_card/transfer",
        headers=command_auth(ada["token"], "transfer-lot-card"),
        json={"recipient_player_id": grace["player_id"]},
    )
    original_read = client.app.state.projection_store.read_visible_artifacts
    calls = {"count": 0}

    def tracked_read_visible_artifacts(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_artifacts = tracked_read_visible_artifacts
    client.app.state.artifact_service.visible_artifacts_for_player = (
        lambda player_id, crew_ids=(): (_ for _ in ()).throw(
            AssertionError("fresh artifact projection should be used after transfer")
        )
    )

    response = client.get("/artifacts", headers=auth(grace["token"]))
    copy_ids = [
        artifact["artifact_id"]
        for artifact in response.json()["artifacts"]
        if artifact.get("is_copy")
    ]

    assert transferred.status_code == 201
    assert response.status_code == 200
    assert calls["count"] == 1
    assert copy_ids == ["artifact_lot_card.copy.player_0002.1"]


def test_contract_board_embeds_projected_visible_artifacts_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    original_read = client.app.state.projection_store.read_visible_artifacts
    calls = {"count": 0}

    def tracked_read_visible_artifacts(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_artifacts = tracked_read_visible_artifacts
    client.app.state.artifact_service.visible_artifacts_for_player = (
        lambda player_id, crew_ids=(): (_ for _ in ()).throw(
            AssertionError("contract board should use fresh artifact projection")
        )
    )

    response = client.get("/contracts", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert calls["count"] == 1
    assert {
        artifact["artifact_id"]
        for artifact in response.json()["visible_artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}


def test_inbox_embeds_projected_visible_artifacts_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    original_read = client.app.state.projection_store.read_visible_artifacts
    calls = {"count": 0}

    def tracked_read_visible_artifacts(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_artifacts = tracked_read_visible_artifacts
    client.app.state.artifact_service.visible_artifacts_for_player = (
        lambda player_id, crew_ids=(): (_ for _ in ()).throw(
            AssertionError("inbox should use fresh artifact projection")
        )
    )

    response = client.get("/inbox", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert calls["count"] == 1
    assert {
        artifact["artifact_id"]
        for artifact in response.json()["visible_artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}


def test_crew_board_embeds_projected_visible_artifacts_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    original_read = client.app.state.projection_store.read_visible_artifacts
    calls = {"count": 0}

    def tracked_read_visible_artifacts(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_artifacts = tracked_read_visible_artifacts
    client.app.state.artifact_service.visible_artifacts_for_player = (
        lambda player_id, crew_ids=(): (_ for _ in ()).throw(
            AssertionError("crew board should use fresh artifact projection")
        )
    )

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert calls["count"] == 1
    assert {
        artifact["artifact_id"]
        for artifact in response.json()["visible_artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}


def test_embedded_visible_artifacts_fall_back_when_projection_is_stale(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
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

    def fail_if_projection_read(player_id: str, crew_ids=()):
        raise AssertionError("stale embedded artifact projection should not be used")

    client.app.state.projection_store.read_visible_artifacts = fail_if_projection_read

    response = client.get("/contracts", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert {
        artifact["artifact_id"]
        for artifact in response.json()["visible_artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}


def test_deal_route_reads_fresh_projected_visible_deals_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_DEAL_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    ash = create_crew(client, caro["token"], "crew-create-ash", "The Ash Keys")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    original_read = client.app.state.projection_store.read_visible_deals
    calls = {"count": 0}

    def tracked_read_visible_deals(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_deals = tracked_read_visible_deals
    client.app.state.deal_service.list_for_player = (
        lambda player_id: (_ for _ in ()).throw(
            AssertionError("fresh deal projection should be used")
        )
    )

    participant = client.get("/deals", headers=auth(bela["token"]))
    bystander = client.get("/deals", headers=auth(caro["token"]))
    diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]

    assert proposed.status_code == 201
    assert participant.status_code == 200
    assert bystander.status_code == 200
    assert diagnostics["lag"] == 0
    assert diagnostics["deal_count"] == 1
    assert calls["count"] == 2
    assert participant.json()["deals"] == [proposed.json()]
    assert bystander.json()["deals"] == []
    assert "Do not cite us." not in str(bystander.json())
    assert ash["crew_id"] not in {
        deal["proposer_crew_id"] for deal in participant.json()["deals"]
    }


def test_deal_route_falls_back_when_projection_is_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_DEAL_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
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

    def fail_if_projection_read(player_id: str, crew_ids=()):
        raise AssertionError("stale deal projection should not be used")

    client.app.state.projection_store.read_visible_deals = fail_if_projection_read

    response = client.get("/deals", headers=auth(bela["token"]))

    assert proposed.status_code == 201
    assert response.status_code == 200
    assert response.json()["deals"] == [proposed.json()]


def test_deal_accept_refreshes_projection_for_flagged_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_DEAL_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    client.app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="test setup",
        idempotency_key="grant-chapel",
    )
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    ).json()
    accepted = client.post(
        f"/deals/{proposed['deal_id']}/accept",
        headers=command_auth(bela["token"], "deal-accept"),
    )
    original_read = client.app.state.projection_store.read_visible_deals
    calls = {"count": 0}

    def tracked_read_visible_deals(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_deals = tracked_read_visible_deals
    client.app.state.deal_service.list_for_player = (
        lambda player_id: (_ for _ in ()).throw(
            AssertionError("fresh deal projection should be used after accept")
        )
    )

    response = client.get("/deals", headers=auth(ada["token"]))
    diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]

    assert accepted.status_code == 200
    assert accepted.json()["status"] == "fulfilled"
    assert response.status_code == 200
    assert diagnostics["lag"] == 0
    assert diagnostics["deal_count"] == 1
    assert calls["count"] == 1
    assert response.json()["deals"][0]["status"] == "fulfilled"
    assert response.json()["deals"][0]["proposer_received_artifact_ids"] == (
        accepted.json()["proposer_received_artifact_ids"]
    )
    assert response.json()["deals"][0]["recipient_received_artifact_ids"] == (
        accepted.json()["recipient_received_artifact_ids"]
    )


def test_inbox_embeds_projected_visible_deals_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_DEAL_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    ash = create_crew(client, caro["token"], "crew-create-ash", "The Ash Keys")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    original_read = client.app.state.projection_store.read_visible_deals
    calls = {"count": 0}

    def tracked_read_visible_deals(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_deals = tracked_read_visible_deals
    client.app.state.deal_service.list_for_player = (
        lambda player_id: (_ for _ in ()).throw(
            AssertionError("inbox should use fresh deal projection")
        )
    )

    participant = client.get("/inbox", headers=auth(bela["token"]))
    bystander = client.get("/inbox", headers=auth(caro["token"]))

    assert proposed.status_code == 201
    assert participant.status_code == 200
    assert bystander.status_code == 200
    assert calls["count"] >= 2
    assert participant.json()["deals"] == [proposed.json()]
    assert bystander.json()["deals"] == []
    assert "Do not cite us." not in str(bystander.json())
    assert ash["crew_id"] not in {
        deal["proposer_crew_id"] for deal in participant.json()["deals"]
    }


def test_crew_board_embeds_projected_visible_deals_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_DEAL_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    ash = create_crew(client, caro["token"], "crew-create-ash", "The Ash Keys")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    original_read = client.app.state.projection_store.read_visible_deals
    calls = {"count": 0}

    def tracked_read_visible_deals(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_deals = tracked_read_visible_deals
    client.app.state.deal_service.list_for_player = (
        lambda player_id: (_ for _ in ()).throw(
            AssertionError("crew board should use fresh deal projection")
        )
    )

    participant = client.get(f"/crews/{moth['crew_id']}/board", headers=auth(bela["token"]))
    bystander = client.get(f"/crews/{ash['crew_id']}/board", headers=auth(caro["token"]))

    assert proposed.status_code == 201
    assert participant.status_code == 200
    assert bystander.status_code == 200
    assert calls["count"] >= 2
    assert participant.json()["deals"] == [proposed.json()]
    assert bystander.json()["deals"] == []
    assert "Do not cite us." not in str(bystander.json())


def test_embedded_visible_deals_fall_back_when_projection_is_stale(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_DEAL_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
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

    def fail_if_projection_read(player_id: str, crew_ids=()):
        raise AssertionError("stale embedded deal projection should not be used")

    client.app.state.projection_store.read_visible_deals = fail_if_projection_read

    inbox = client.get("/inbox", headers=auth(bela["token"]))
    crew_board = client.get(f"/crews/{moth['crew_id']}/board", headers=auth(bela["token"]))

    assert proposed.status_code == 201
    assert inbox.status_code == 200
    assert crew_board.status_code == 200
    assert inbox.json()["deals"] == [proposed.json()]
    assert crew_board.json()["deals"] == [proposed.json()]


def test_projection_store_materializes_visible_deals_without_bystander_terms(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    ash = create_crew(client, caro["token"], "crew-create-ash", "The Ash Keys")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )

    participant = client.app.state.projection_store.read_visible_deals(
        bela["player_id"],
        crew_ids=[moth["crew_id"]],
    )
    bystander = client.app.state.projection_store.read_visible_deals(
        caro["player_id"],
        crew_ids=[ash["crew_id"]],
    )
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        rows = connection.execute(
            "select deal_id, proposer_crew_id, recipient_crew_id, payload_json "
            "from deal_surface order by deal_id"
        ).fetchall()

    assert proposed.status_code == 201
    assert participant == [proposed.json()]
    assert bystander == []
    assert rows == [
        (
            proposed.json()["deal_id"],
            gilt["crew_id"],
            moth["crew_id"],
            json.dumps(proposed.json(), sort_keys=True, separators=(",", ":")),
        )
    ]
    assert "Do not cite us." not in str(bystander)
    assert client.app.state.projection_store.read_visible_deals(
        ada["player_id"],
        crew_ids=[gilt["crew_id"]],
    ) == deal_rows_from_events(client.app.state.event_store.read())


def test_projection_store_materializes_visible_artifacts_without_hidden_fields(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    projected = client.app.state.projection_store.read_visible_artifacts(
        ada["player_id"],
        crew_ids=(),
    )
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        public_rows = connection.execute(
            "select artifact_id, payload_json from artifact_surface order by artifact_id"
        ).fetchall()

    assert {
        artifact["artifact_id"]
        for artifact in projected["artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}
    assert [row[0] for row in public_rows] == [
        "artifact_ledger_rubric",
        "artifact_lot_card",
    ]
    stored_text = "\n".join(row[1] for row in public_rows)
    assert "full_text" not in stored_text
    assert "hidden_flags" not in stored_text
    assert "ink-after-binding" not in stored_text
    assert "saint-bone forgery" not in stored_text


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
