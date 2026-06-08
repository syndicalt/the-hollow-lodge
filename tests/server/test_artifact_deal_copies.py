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


def command_auth(token: str, key: str) -> dict[str, str]:
    return {**auth(token), "Idempotency-Key": key}


def test_deal_copy_is_visible_to_recipient_crew_members(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    crew = client.post(
        "/crews",
        json={"name": "Moth"},
        headers=command_auth(bela["token"], "crew-moth"),
    ).json()
    client.post(
        f"/crews/{crew['crew_id']}/join",
        json={"join_code": crew["join_code"]},
        headers=command_auth(caro["token"], "join-caro"),
    )

    copied = app.state.artifact_service.copy_artifact_for_deal(
        source_artifact_id="artifact_ledger_rubric",
        source_crew_id="crew_source",
        recipient_crew_id=crew["crew_id"],
        actor_id=ada["player_id"],
        deal_id="deal_000001",
        idempotency_key="deal-copy-ledger",
    )

    bela_view = client.get(f"/artifacts/{copied['artifact_id']}", headers=auth(bela["token"]))
    caro_view = client.get(f"/artifacts/{copied['artifact_id']}", headers=auth(caro["token"]))
    assert bela_view.status_code == 200
    assert caro_view.status_code == 200
    assert "deal:deal_000001" in bela_view.json()["source_chain"]


def test_deal_copy_replay_returns_same_copy(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    first = app.state.artifact_service.copy_artifact_for_deal(
        source_artifact_id="artifact_ledger_rubric",
        source_crew_id="crew_0001",
        recipient_crew_id="crew_0002",
        actor_id=ada["player_id"],
        deal_id="deal_000001",
        idempotency_key="deal-copy-ledger",
    )
    replay = app.state.artifact_service.copy_artifact_for_deal(
        source_artifact_id="artifact_ledger_rubric",
        source_crew_id="crew_0001",
        recipient_crew_id="crew_0002",
        actor_id=ada["player_id"],
        deal_id="deal_000001",
        idempotency_key="deal-copy-ledger",
    )

    assert replay["artifact_id"] == first["artifact_id"]


def test_repeated_deal_copies_with_different_keys_get_unique_ids(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    crew = client.post(
        "/crews",
        json={"name": "Moth"},
        headers=command_auth(bela["token"], "crew-moth"),
    ).json()

    first = app.state.artifact_service.copy_artifact_for_deal(
        source_artifact_id="artifact_ledger_rubric",
        source_crew_id="crew_source",
        recipient_crew_id=crew["crew_id"],
        actor_id=ada["player_id"],
        deal_id="deal_000001",
        idempotency_key="deal-copy-ledger-1",
    )
    second = app.state.artifact_service.copy_artifact_for_deal(
        source_artifact_id="artifact_ledger_rubric",
        source_crew_id="crew_source",
        recipient_crew_id=crew["crew_id"],
        actor_id=ada["player_id"],
        deal_id="deal_000001",
        idempotency_key="deal-copy-ledger-2",
    )

    first_view = client.get(f"/artifacts/{first['artifact_id']}", headers=auth(bela["token"]))
    second_view = client.get(f"/artifacts/{second['artifact_id']}", headers=auth(bela["token"]))
    assert first["artifact_id"] != second["artifact_id"]
    assert first_view.status_code == 200
    assert second_view.status_code == 200
