import sqlite3

from fastapi.testclient import TestClient

from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.server.app import create_app
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


def test_visible_events_since_sequence_excludes_prior_and_server_only_events(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    first = client.get("/events", headers=auth(ada["token"])).json()["events"]
    checkpoint = max(event["sequence"] for event in first)

    message = client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-1"),
        json={"recipient_player_id": grace["player_id"], "body": "Trade the ledger?"},
    )
    assert message.status_code == 201

    delta = client.get(
        f"/events?since_sequence={checkpoint}",
        headers=auth(ada["token"]),
    )

    assert delta.status_code == 200
    events = delta.json()["events"]
    assert [event["type"] for event in events] == ["chat.message.created"]
    assert all(event["sequence"] > checkpoint for event in events)
    assert "contract.hidden_truth.seeded" not in str(events)
    assert "truth_false_finger_forgery" not in str(events)


def test_full_visible_event_sync_recovers_events_that_become_visible_after_join(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create"),
        json={"name": "The Gilt Knives"},
    ).json()
    crew_message = client.post(
        "/chat/crew",
        headers=command_auth(ada["token"], "crew-chat-1"),
        json={"crew_id": crew["crew_id"], "body": "Ledger stayed in the chapel."},
    )
    later_direct = client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "direct-chat-1"),
        json={"recipient_player_id": grace["player_id"], "body": "Join us."},
    )
    join = client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(grace["token"], "crew-join-grace"),
        json={"join_code": crew["join_code"]},
    )

    assert crew_message.status_code == 201
    assert later_direct.status_code == 201
    assert join.status_code == 200
    grace_events = client.get("/events", headers=auth(grace["token"])).json()["events"]
    direct_sequence = next(
        event["sequence"]
        for event in grace_events
        if event["type"] == "chat.message.created" and event["payload"]["body"] == "Join us."
    )
    stale_delta = client.get(
        f"/events?since_sequence={direct_sequence}",
        headers=auth(grace["token"]),
    ).json()["events"]
    full_sync = client.get("/events", headers=auth(grace["token"])).json()["events"]

    assert "Ledger stayed in the chapel." not in str(stale_delta)
    assert "Ledger stayed in the chapel." in str(full_sync)


def test_visible_events_route_reads_fresh_projection_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_VISIBLE_EVENT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    linus = register(client, "c", "Linus")
    sent = client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-1"),
        json={"recipient_player_id": grace["player_id"], "body": "Trade the ledger?"},
    )
    original_read = client.app.state.projection_store.read_visible_events
    calls = {"count": 0}

    def tracked_read_visible_events(player_id: str, crew_ids=(), since_sequence: int = 0):
        calls["count"] += 1
        return original_read(
            player_id,
            crew_ids=crew_ids,
            since_sequence=since_sequence,
        )

    client.app.state.projection_store.read_visible_events = tracked_read_visible_events
    client.app.state.visibility_service.visible_events_for_player = (
        lambda player_id: (_ for _ in ()).throw(
            AssertionError("fresh visible event projection should be used")
        )
    )

    ada_events = client.get("/events", headers=auth(ada["token"]))
    grace_events = client.get("/events", headers=auth(grace["token"]))
    linus_events = client.get("/events", headers=auth(linus["token"]))
    diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]

    assert sent.status_code == 201
    assert ada_events.status_code == 200
    assert grace_events.status_code == 200
    assert linus_events.status_code == 200
    assert diagnostics["lag"] == 0
    assert diagnostics["visible_event_count"] > 0
    assert calls["count"] == 3
    assert [event["type"] for event in ada_events.json()["events"] if event["type"].startswith("chat.")] == [
        "chat.message.created"
    ]
    assert [event["type"] for event in grace_events.json()["events"] if event["type"].startswith("chat.")] == [
        "chat.message.created"
    ]
    assert [event["type"] for event in linus_events.json()["events"] if event["type"].startswith("chat.")] == []
    assert "Trade the ledger?" not in str(linus_events.json())
    assert "contract.hidden_truth.seeded" not in str(ada_events.json())
    assert "truth_false_finger_forgery" not in str(ada_events.json())
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        stored_activity = "\n".join(
            row[0]
            for row in connection.execute(
                "select payload_json from visible_event_surface order by sequence"
            ).fetchall()
        )
    assert "contract.hidden_truth.seeded" not in stored_activity
    assert "truth_false_finger_forgery" not in stored_activity


def test_visible_events_projection_honors_since_sequence(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_VISIBLE_EVENT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    checkpoint = max(
        event["sequence"]
        for event in client.get("/events", headers=auth(ada["token"])).json()["events"]
    )
    sent = client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-1"),
        json={"recipient_player_id": grace["player_id"], "body": "Trade the ledger?"},
    )
    client.app.state.visibility_service.visible_events_for_player = (
        lambda player_id: (_ for _ in ()).throw(
            AssertionError("fresh visible event projection should be used")
        )
    )

    response = client.get(
        f"/events?since_sequence={checkpoint}",
        headers=auth(ada["token"]),
    )

    assert sent.status_code == 201
    assert response.status_code == 200
    events = response.json()["events"]
    assert [event["type"] for event in events] == ["chat.message.created"]
    assert all(event["sequence"] > checkpoint for event in events)


def test_visible_events_projection_full_sync_recovers_crew_events_after_join(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_VISIBLE_EVENT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create"),
        json={"name": "The Gilt Knives"},
    ).json()
    crew_message = client.post(
        "/chat/crew",
        headers=command_auth(ada["token"], "crew-chat-1"),
        json={"crew_id": crew["crew_id"], "body": "Ledger stayed in the chapel."},
    )
    later_direct = client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "direct-chat-1"),
        json={"recipient_player_id": grace["player_id"], "body": "Join us."},
    )
    join = client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(grace["token"], "crew-join-grace"),
        json={"join_code": crew["join_code"]},
    )
    client.app.state.visibility_service.visible_events_for_player = (
        lambda player_id: (_ for _ in ()).throw(
            AssertionError("fresh visible event projection should be used")
        )
    )

    grace_events = client.get("/events", headers=auth(grace["token"])).json()["events"]
    direct_sequence = next(
        event["sequence"]
        for event in grace_events
        if event["type"] == "chat.message.created" and event["payload"]["body"] == "Join us."
    )
    stale_delta = client.get(
        f"/events?since_sequence={direct_sequence}",
        headers=auth(grace["token"]),
    ).json()["events"]

    assert crew_message.status_code == 201
    assert later_direct.status_code == 201
    assert join.status_code == 200
    assert "Ledger stayed in the chapel." in str(grace_events)
    assert "Ledger stayed in the chapel." not in str(stale_delta)


def test_visible_events_route_falls_back_when_projection_is_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_VISIBLE_EVENT_PROJECTION_READS", "1")
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

    def fail_if_projection_read(player_id: str, crew_ids=(), since_sequence: int = 0):
        raise AssertionError("stale visible event projection should not be used")

    client.app.state.projection_store.read_visible_events = fail_if_projection_read

    response = client.get("/events", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert "contract_out_of_band" in str(response.json()["events"])
