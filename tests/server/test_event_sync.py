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
