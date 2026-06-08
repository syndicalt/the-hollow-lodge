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
    assert _visible_types(client, ada["token"], prefix="chat.") == ["chat.message.created"]
    assert _visible_types(client, grace["token"], prefix="chat.") == ["chat.message.created"]
    assert _visible_types(client, linus["token"], prefix="chat.") == []


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
    assert _visible_types(client, ada["token"], prefix=("crew.", "chat.")) == [
        "crew.created",
        "crew.member.joined",
        "chat.message.created",
    ]
    assert _visible_types(client, grace["token"], prefix=("crew.", "chat.")) == [
        "crew.created",
        "crew.member.joined",
        "chat.message.created",
    ]
    assert _visible_types(client, linus["token"], prefix=("crew.", "chat.")) == []


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


def test_crew_to_crew_artifact_chat_leaks_redacted_rumor_to_bystander_crew(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    linus = register(client, "c", "Linus")
    gilt = make_crew(client, ada["token"], "The Gilt Knives")["crew_id"]
    moth = make_crew(client, grace["token"], "The Moth Choir")["crew_id"]
    ash = make_crew(client, linus["token"], "The Ash Keys")["crew_id"]

    sent = client.post(
        "/chat/crew-to-crew",
        headers=command_auth(ada["token"], "chat-gilt-moth-ledger"),
        json={
            "sender_crew_id": gilt,
            "recipient_crew_id": moth,
            "body": "The ledger proves our leverage. Keep quiet.",
            "artifact_ids": ["artifact_ledger_rubric"],
        },
    )
    bystander_events = client.get("/events", headers=auth(linus["token"])).json()["events"]
    participant_events = client.get("/events", headers=auth(ada["token"])).json()["events"]
    bystander_board = client.get(f"/crews/{ash}/board", headers=auth(linus["token"]))

    assert sent.status_code == 201
    assert not any(event["type"] == "chat.message.created" for event in bystander_events)
    rumor_events = [
        event for event in bystander_events
        if event["type"] == "contract.rumor.leaked"
    ]
    assert len(rumor_events) == 1
    rumor = rumor_events[0]["payload"]
    assert rumor == {
        "rumor_id": "rumor_msg_000001",
        "source_type": "chat.message.created",
        "source_id": "msg_000001",
        "conversation_scope": "crew_to_crew",
        "suspected_crew_ids": [gilt, moth],
        "summary": "A private artifact discussion is echoing between crews.",
        "pressure": "artifact_reference_detected",
    }
    assert "artifact_ledger_rubric" not in str(rumor_events)
    assert "The ledger proves our leverage" not in str(rumor_events)
    assert not any(
        event["type"] == "contract.rumor.leaked"
        for event in participant_events
    )
    assert bystander_board.status_code == 200
    assert bystander_board.json()["rumors"] == [rumor]


def test_crew_to_crew_body_artifact_reference_leaks_redacted_rumor(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    linus = register(client, "c", "Linus")
    gilt = make_crew(client, ada["token"], "The Gilt Knives")["crew_id"]
    moth = make_crew(client, grace["token"], "The Moth Choir")["crew_id"]
    ash = make_crew(client, linus["token"], "The Ash Keys")["crew_id"]

    sent = client.post(
        "/chat/crew-to-crew",
        headers=command_auth(ada["token"], "chat-gilt-moth-body-ledger"),
        json={
            "sender_crew_id": gilt,
            "recipient_crew_id": moth,
            "body": "The Red Ledger Rubric is enough leverage. Do not attach it.",
        },
    )
    bystander_events = client.get("/events", headers=auth(linus["token"])).json()["events"]
    bystander_board = client.get(f"/crews/{ash}/board", headers=auth(linus["token"]))

    assert sent.status_code == 201
    assert not any(event["type"] == "chat.message.created" for event in bystander_events)
    rumor_events = [
        event for event in bystander_events
        if event["type"] == "contract.rumor.leaked"
    ]
    assert len(rumor_events) == 1
    rumor = rumor_events[0]["payload"]
    assert rumor == {
        "rumor_id": "rumor_msg_000001",
        "source_type": "chat.message.created",
        "source_id": "msg_000001",
        "conversation_scope": "crew_to_crew",
        "suspected_crew_ids": [gilt, moth],
        "summary": "A private artifact discussion is echoing between crews.",
        "pressure": "artifact_reference_detected",
    }
    assert "Red Ledger Rubric" not in str(rumor_events)
    assert "enough leverage" not in str(rumor_events)
    assert "artifact_ledger_rubric" not in str(rumor_events)
    assert bystander_board.status_code == 200
    assert bystander_board.json()["rumors"] == [rumor]
    assert bystander_board.json()["pending_decisions"][0]["kind"] == "rumor_response"


def test_visible_chat_rumor_becomes_pending_decision_for_bystander_crew(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    linus = register(client, "c", "Linus")
    gilt = make_crew(client, ada["token"], "The Gilt Knives")["crew_id"]
    moth = make_crew(client, grace["token"], "The Moth Choir")["crew_id"]
    ash = make_crew(client, linus["token"], "The Ash Keys")["crew_id"]

    sent = client.post(
        "/chat/crew-to-crew",
        headers=command_auth(ada["token"], "chat-gilt-moth-ledger"),
        json={
            "sender_crew_id": gilt,
            "recipient_crew_id": moth,
            "body": "The ledger proves our leverage. Keep quiet.",
            "artifact_ids": ["artifact_ledger_rubric"],
        },
    )
    board = client.get(f"/crews/{ash}/board", headers=auth(linus["token"]))
    inbox = client.get("/inbox", headers=auth(linus["token"]))

    expected = {
        "kind": "rumor_response",
        "label": "Rumor needs response",
        "description": (
            "Rumor rumor_msg_000001 suggests artifact_reference_detected. "
            "Decide whether to verify, ignore, or answer with a crew action."
        ),
        "crew_id": ash,
        "rumor_id": "rumor_msg_000001",
        "source_type": "chat.message.created",
        "source_id": sent.json()["message_id"],
        "pressure": "artifact_reference_detected",
        "action": "review_rumor",
    }
    assert sent.status_code == 201
    assert board.status_code == 200
    assert inbox.status_code == 200
    assert expected in board.json()["pending_decisions"]
    assert expected in inbox.json()["pending_decisions"]
    assert "artifact_ledger_rubric" not in str(board.json()["pending_decisions"])
    assert "The ledger proves our leverage" not in str(board.json()["pending_decisions"])


def test_crew_to_crew_chat_without_artifacts_does_not_leak_rumor(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    linus = register(client, "c", "Linus")
    gilt = make_crew(client, ada["token"], "The Gilt Knives")["crew_id"]
    moth = make_crew(client, grace["token"], "The Moth Choir")["crew_id"]
    make_crew(client, linus["token"], "The Ash Keys")

    sent = client.post(
        "/chat/crew-to-crew",
        headers=command_auth(ada["token"], "chat-gilt-moth-plain"),
        json={
            "sender_crew_id": gilt,
            "recipient_crew_id": moth,
            "body": "No public claims until lock.",
        },
    )
    bystander_events = client.get("/events", headers=auth(linus["token"])).json()["events"]

    assert sent.status_code == 201
    assert not any(
        event["type"] == "contract.rumor.leaked"
        for event in bystander_events
    )


def test_crew_to_crew_body_scanner_ignores_partial_artifact_terms(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    linus = register(client, "c", "Linus")
    gilt = make_crew(client, ada["token"], "The Gilt Knives")["crew_id"]
    moth = make_crew(client, grace["token"], "The Moth Choir")["crew_id"]
    make_crew(client, linus["token"], "The Ash Keys")

    sent = client.post(
        "/chat/crew-to-crew",
        headers=command_auth(ada["token"], "chat-gilt-moth-partial-ledger"),
        json={
            "sender_crew_id": gilt,
            "recipient_crew_id": moth,
            "body": "The ledger helps, but do not name the source.",
        },
    )
    bystander_events = client.get("/events", headers=auth(linus["token"])).json()["events"]

    assert sent.status_code == 201
    assert not any(
        event["type"] == "contract.rumor.leaked"
        for event in bystander_events
    )


def test_replayed_crew_to_crew_artifact_chat_does_not_duplicate_rumor(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    linus = register(client, "c", "Linus")
    gilt = make_crew(client, ada["token"], "The Gilt Knives")["crew_id"]
    moth = make_crew(client, grace["token"], "The Moth Choir")["crew_id"]
    make_crew(client, linus["token"], "The Ash Keys")
    payload = {
        "sender_crew_id": gilt,
        "recipient_crew_id": moth,
        "body": "The ledger proves our leverage. Keep quiet.",
        "artifact_ids": ["artifact_ledger_rubric"],
    }

    first = client.post(
        "/chat/crew-to-crew",
        headers=command_auth(ada["token"], "chat-gilt-moth-ledger"),
        json=payload,
    )
    replay = client.post(
        "/chat/crew-to-crew",
        headers=command_auth(ada["token"], "chat-gilt-moth-ledger"),
        json=payload,
    )
    bystander_events = client.get("/events", headers=auth(linus["token"])).json()["events"]

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["message_id"] == first.json()["message_id"]
    assert [
        event["payload"]["rumor_id"]
        for event in bystander_events
        if event["type"] == "contract.rumor.leaked"
    ] == ["rumor_msg_000001"]


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
    assert [event["type"] for event in visible if event["type"].startswith("chat.")] == [
        "chat.message.created"
    ]
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


def test_direct_message_with_artifact_ids_records_references(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")

    sent = client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-direct-artifact"),
        json={
            "recipient_player_id": grace["player_id"],
            "body": "See the ledger.",
            "artifact_ids": ["artifact_ledger_rubric"],
        },
    )

    assert sent.status_code == 201
    visible = client.get("/events", headers=auth(grace["token"])).json()["events"]
    chat_event = [event for event in visible if event["type"] == "chat.message.created"][0]
    assert chat_event["payload"]["artifact_ids"] == ["artifact_ledger_rubric"]


def test_direct_message_with_hidden_artifact_id_returns_404(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")

    sent = client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-direct-hidden-artifact"),
        json={
            "recipient_player_id": grace["player_id"],
            "body": "See this.",
            "artifact_ids": ["artifact_chapel_debt_mark"],
        },
    )

    assert sent.status_code == 404
    assert sent.json()["detail"] == "artifact not found"


def test_replayed_chat_key_includes_artifact_ids_in_conflict_check(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    payload = {
        "recipient_player_id": grace["player_id"],
        "body": "See the ledger.",
        "artifact_ids": ["artifact_ledger_rubric"],
    }

    first = client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-direct-artifact-replay"),
        json=payload,
    )
    replay = client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-direct-artifact-replay"),
        json=payload,
    )
    conflict = client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-direct-artifact-replay"),
        json={**payload, "artifact_ids": []},
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["message_id"] == first.json()["message_id"]
    assert conflict.status_code == 409


def test_recipient_cannot_inspect_attached_artifact_unless_transferred_separately(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    transfer = client.post(
        "/artifacts/artifact_ledger_rubric/transfer",
        headers=command_auth(ada["token"], "transfer-ledger-to-self"),
        json={"recipient_player_id": ada["player_id"]},
    )
    copied_id = transfer.json()["artifact_id"]

    sent = client.post(
        "/chat/direct",
        headers=command_auth(ada["token"], "chat-direct-self-copy"),
        json={
            "recipient_player_id": grace["player_id"],
            "body": "Reference only.",
            "artifact_ids": [copied_id],
        },
    )
    recipient_view = client.get(f"/artifacts/{copied_id}", headers=auth(grace["token"]))

    assert sent.status_code == 201
    assert recipient_view.status_code == 404


def _visible_types(
    client: TestClient,
    token: str,
    *,
    prefix: str | tuple[str, ...] | None = None,
) -> list[str]:
    response = client.get("/events", headers=auth(token))
    assert response.status_code == 200
    types = [event["type"] for event in response.json()["events"]]
    if prefix is None:
        return types
    return [event_type for event_type in types if event_type.startswith(prefix)]
