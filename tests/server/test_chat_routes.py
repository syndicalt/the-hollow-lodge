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


def make_crew(client: TestClient, token: str, name: str) -> dict:
    response = client.post(
        "/crews",
        headers=command_auth(token, f"crew-{name}"),
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()


def test_direct_messages_sync_only_to_sender_and_recipient(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    linus = register(client, "c", "Linus")

    sent = client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-direct-ada-grace"),
        json={"recipient_player_id": grace["player_id"], "body": "Trade the ledger?"},
    )

    assert sent.status_code == 201
    message_id = sent.json()["message_id"]
    assert message_id.startswith("msg_")
    assert _visible_types(client, ada["token"]) == ["chat.message.created"]
    assert _visible_types(client, grace["token"]) == ["chat.message.created"]
    assert _visible_types(client, linus["token"]) == []


def test_crew_messages_sync_only_to_crew_members(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    linus = register(client, "c", "Linus")
    crew = make_crew(client, ada["token"], "The Gilt Knives")
    assert client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(grace["token"], "crew-join-grace"),
        json={"join_code": crew["join_code"]},
    ).status_code == 200

    sent = client.post(
        "/chat/crew",
        headers=command_auth(ada["token"], "chat-crew-gilt"),
        json={"crew_id": crew["crew_id"], "body": "Packet Lead needs provenance."},
    )

    assert sent.status_code == 201
    assert _visible_types(client, ada["token"]) == ["crew.created", "crew.member.joined", "chat.message.created"]
    assert _visible_types(client, grace["token"]) == ["crew.created", "crew.member.joined", "chat.message.created"]
    assert _visible_types(client, linus["token"]) == []


def test_crew_to_crew_messages_sync_only_to_both_crews(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    linus = register(client, "c", "Linus")
    gilt = make_crew(client, ada["token"], "The Gilt Knives")["crew_id"]
    moth = make_crew(client, grace["token"], "The Moth Choir")["crew_id"]

    sent = client.post(
        "/chat/crew-to-crew",
        headers=command_auth(ada["token"], "chat-gilt-moth"),
        json={"sender_crew_id": gilt, "recipient_crew_id": moth, "body": "No public claims until lock."},
    )

    assert sent.status_code == 201
    assert "chat.message.created" in _visible_types(client, ada["token"])
    assert "chat.message.created" in _visible_types(client, grace["token"])
    assert "chat.message.created" not in _visible_types(client, linus["token"])


def test_chat_does_not_create_binding_deal_state(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")

    client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-direct-ada-grace"),
        json={"recipient_player_id": grace["player_id"], "body": "I promise you the bell cipher."},
    )

    visible = client.get("/events", headers=auth(ada["token"])).json()["events"]
    assert [event["type"] for event in visible] == ["chat.message.created"]
    assert all(not event["type"].startswith("deal.") for event in visible)


def test_chat_commands_require_idempotency_key(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")

    missing_key = client.post(
        "/chat/direct",
        headers=auth(ada["token"]),
        json={"recipient_player_id": grace["player_id"], "body": "Trade the ledger?"},
    )

    assert missing_key.status_code == 422


def test_replayed_chat_key_returns_original_message_without_duplicate_event(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    payload = {"recipient_player_id": grace["player_id"], "body": "Trade the ledger?"}

    first = client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-direct-ada-grace"),
        json=payload,
    )
    replay = client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-direct-ada-grace"),
        json=payload,
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["message_id"] == first.json()["message_id"]
    events = [
        line
        for line in (tmp_path / "server-events.jsonl").read_text().splitlines()
        if "chat.message.created" in line
    ]
    assert len(events) == 1


def test_chat_message_ids_advance_after_app_recreation(tmp_path):
    first_client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(first_client, "a", "Ada")
    grace = register(first_client, "b", "Grace")
    first = first_client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-direct-one"),
        json={"recipient_player_id": grace["player_id"], "body": "First."},
    )

    second_client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    second = second_client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-direct-two"),
        json={"recipient_player_id": grace["player_id"], "body": "Second."},
    )

    assert first.json()["message_id"] == "msg_000001"
    assert second.json()["message_id"] == "msg_000002"


def _visible_types(client: TestClient, token: str) -> list[str]:
    response = client.get("/events", headers=auth(token))
    assert response.status_code == 200
    return [event["type"] for event in response.json()["events"]]
