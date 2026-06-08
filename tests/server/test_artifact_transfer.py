import json

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


def test_transfer_creates_copy_visible_to_recipient(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    sender = register(client, "a", "Ada")
    recipient = register(client, "b", "Bela")

    transfer = client.post(
        "/artifacts/artifact_ledger_rubric/transfer",
        headers=command_auth(sender["token"], "transfer-ledger"),
        json={"recipient_player_id": recipient["player_id"]},
    )
    copied_id = transfer.json()["artifact_id"]
    recipient_view = client.get(f"/artifacts/{copied_id}", headers=auth(recipient["token"]))

    assert transfer.status_code == 201
    assert copied_id.startswith("artifact_ledger_rubric.copy.")
    assert recipient_view.status_code == 200
    assert "transfer:" in str(recipient_view.json()["source_chain"])


def test_sender_can_inspect_copied_artifact_after_transfer(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    sender = register(client, "a", "Ada")
    recipient = register(client, "b", "Bela")

    transfer = client.post(
        "/artifacts/artifact_ledger_rubric/transfer",
        headers=command_auth(sender["token"], "transfer-ledger"),
        json={"recipient_player_id": recipient["player_id"]},
    )
    copied_id = transfer.json()["artifact_id"]
    sender_view = client.get(f"/artifacts/{copied_id}", headers=auth(sender["token"]))

    assert sender_view.status_code == 200
    assert sender_view.json()["artifact_id"] == copied_id


def test_third_player_cannot_inspect_copied_artifact(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    sender = register(client, "a", "Ada")
    recipient = register(client, "b", "Bela")
    outsider = register(client, "c", "Caro")

    transfer = client.post(
        "/artifacts/artifact_ledger_rubric/transfer",
        headers=command_auth(sender["token"], "transfer-ledger"),
        json={"recipient_player_id": recipient["player_id"]},
    )
    copied_id = transfer.json()["artifact_id"]
    outsider_view = client.get(f"/artifacts/{copied_id}", headers=auth(outsider["token"]))

    assert outsider_view.status_code == 404


def test_transfer_of_hidden_unseen_artifact_returns_404(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    sender = register(client, "a", "Ada")
    recipient = register(client, "b", "Bela")

    transfer = client.post(
        "/artifacts/artifact_chapel_debt_mark/transfer",
        headers=command_auth(sender["token"], "transfer-hidden"),
        json={"recipient_player_id": recipient["player_id"]},
    )

    assert transfer.status_code == 404
    assert transfer.json()["detail"] == "artifact not found"


def test_replayed_transfer_key_returns_same_copy_without_duplicate_events(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    sender = register(client, "a", "Ada")
    recipient = register(client, "b", "Bela")
    payload = {"recipient_player_id": recipient["player_id"]}

    first = client.post(
        "/artifacts/artifact_ledger_rubric/transfer",
        headers=command_auth(sender["token"], "transfer-ledger"),
        json=payload,
    )
    replay = client.post(
        "/artifacts/artifact_ledger_rubric/transfer",
        headers=command_auth(sender["token"], "transfer-ledger"),
        json=payload,
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["artifact_id"] == first.json()["artifact_id"]
    rows = [
        json.loads(line)
        for line in (tmp_path / "server-events.jsonl").read_text().splitlines()
    ]
    transfer_events = [
        event for event in rows if event["type"].startswith("artifact.transferred")
    ]
    assert [event["type"] for event in transfer_events] == [
        "artifact.transferred",
        "artifact.transferred.internal",
    ]


def test_transfer_idempotency_conflict_same_key_different_recipient_returns_409(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    sender = register(client, "a", "Ada")
    first_recipient = register(client, "b", "Bela")
    second_recipient = register(client, "c", "Caro")

    first = client.post(
        "/artifacts/artifact_ledger_rubric/transfer",
        headers=command_auth(sender["token"], "transfer-ledger"),
        json={"recipient_player_id": first_recipient["player_id"]},
    )
    conflict = client.post(
        "/artifacts/artifact_ledger_rubric/transfer",
        headers=command_auth(sender["token"], "transfer-ledger"),
        json={"recipient_player_id": second_recipient["player_id"]},
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "idempotency key conflict"
