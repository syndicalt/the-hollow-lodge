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


def create_crew(client: TestClient, token: str) -> dict:
    response = client.post(
        "/crews",
        headers=command_auth(token, "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    )
    assert response.status_code == 201
    return response.json()


def join_crew(client: TestClient, token: str, crew: dict, key: str) -> None:
    response = client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(token, key),
        json={"join_code": crew["join_code"]},
    )
    assert response.status_code == 200


def test_confirmed_action_is_private_until_result(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = create_crew(client, ada["token"])

    submitted = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-1"),
        json={
            "crew_id": crew["crew_id"],
            "intent": "I inspect the red ledger rubric quietly for provenance gaps.",
            "confirmed": True,
        },
    )

    assert submitted.status_code == 201
    action = submitted.json()
    assert action["status"] == "submitted"
    assert action["crew_noise_impact"] == 0
    ada_events = client.get("/events", headers=auth(ada["token"])).text
    grace_events = client.get("/events", headers=auth(grace["token"])).text
    assert "action.submitted" in ada_events
    assert "action.submitted" not in grace_events


def test_action_submit_replay_rejects_same_key_with_different_payload(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"])

    first = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-1"),
        json={"crew_id": crew["crew_id"], "intent": "I inspect the ledger.", "confirmed": True},
    )
    conflict = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-1"),
        json={"crew_id": crew["crew_id"], "intent": "I pressure the clerk.", "confirmed": True},
    )

    assert first.status_code == 201
    assert conflict.status_code == 409


def test_unconfirmed_action_does_not_reach_server(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"])

    response = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-1"),
        json={
            "crew_id": crew["crew_id"],
            "intent": "I inspect the red ledger rubric quietly.",
            "confirmed": False,
        },
    )

    assert response.status_code == 409
    assert "action.submitted" not in client.get("/events", headers=auth(ada["token"])).text


def test_action_can_be_edited_and_canceled_before_phase_lock(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"])
    submitted = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-1"),
        json={"crew_id": crew["crew_id"], "intent": "I inspect the ledger.", "confirmed": True},
    ).json()

    edited = client.patch(
        f"/actions/{submitted['action_id']}",
        headers=command_auth(ada["token"], "action-edit-1"),
        json={"intent": "I inspect the ledger under candlelight."},
    )
    canceled = client.delete(
        f"/actions/{submitted['action_id']}",
        headers=command_auth(ada["token"], "action-cancel-1"),
    )

    assert edited.status_code == 200
    assert edited.json()["intent"] == "I inspect the ledger under candlelight."
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"


def test_crew_member_can_see_edit_and_cancel_pre_result_action(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = create_crew(client, ada["token"])
    join_crew(client, grace["token"], crew, "crew-join-grace")
    submitted = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-1"),
        json={"crew_id": crew["crew_id"], "intent": "I inspect the ledger.", "confirmed": True},
    ).json()

    grace_events = client.get("/events", headers=auth(grace["token"])).text
    edited = client.patch(
        f"/actions/{submitted['action_id']}",
        headers=command_auth(grace["token"], "action-edit-grace"),
        json={"intent": "We inspect the ledger together."},
    )
    canceled = client.delete(
        f"/actions/{submitted['action_id']}",
        headers=command_auth(grace["token"], "action-cancel-grace"),
    )

    assert "action.submitted" in grace_events
    assert edited.status_code == 200
    assert edited.json()["intent"] == "We inspect the ledger together."
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"


def test_edit_replay_returns_original_edit_after_cancel(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"])
    submitted = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-1"),
        json={"crew_id": crew["crew_id"], "intent": "I inspect the ledger.", "confirmed": True},
    ).json()
    first_edit = client.patch(
        f"/actions/{submitted['action_id']}",
        headers=command_auth(ada["token"], "action-edit-1"),
        json={"intent": "I inspect the ledger under candlelight."},
    )
    client.delete(
        f"/actions/{submitted['action_id']}",
        headers=command_auth(ada["token"], "action-cancel-1"),
    )
    replay_edit = client.patch(
        f"/actions/{submitted['action_id']}",
        headers=command_auth(ada["token"], "action-edit-1"),
        json={"intent": "I inspect the ledger under candlelight."},
    )

    assert first_edit.status_code == 200
    assert replay_edit.status_code == 200
    assert replay_edit.json() == first_edit.json()


def test_second_full_action_in_phase_increases_crew_noise_risk(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"])

    first = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-1"),
        json={"crew_id": crew["crew_id"], "intent": "I inspect the ledger.", "confirmed": True},
    )
    second = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-2"),
        json={"crew_id": crew["crew_id"], "intent": "I pressure the clerk.", "confirmed": True},
    )

    assert first.json()["crew_noise_impact"] == 0
    assert second.json()["crew_noise_impact"] == 1


def test_second_full_action_by_different_crew_member_increases_crew_noise(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = create_crew(client, ada["token"])
    join_crew(client, grace["token"], crew, "crew-join-grace")

    first = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-1"),
        json={"crew_id": crew["crew_id"], "intent": "I inspect the ledger.", "confirmed": True},
    )
    second = client.post(
        "/actions",
        headers=command_auth(grace["token"], "action-submit-2"),
        json={"crew_id": crew["crew_id"], "intent": "I pressure the clerk.", "confirmed": True},
    )

    assert first.json()["crew_noise_impact"] == 0
    assert second.json()["crew_noise_impact"] == 1


def test_action_ids_do_not_collide_across_crews_for_multi_crew_member(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    gilt = create_crew(client, ada["token"])
    moth = client.post(
        "/crews",
        headers=command_auth(grace["token"], "crew-create-moth"),
        json={"name": "The Moth Choir"},
    ).json()
    join_crew(client, ada["token"], moth, "crew-join-ada-moth")

    first = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-gilt-1"),
        json={"crew_id": gilt["crew_id"], "intent": "I inspect the ledger.", "confirmed": True},
    ).json()
    second = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-moth-1"),
        json={"crew_id": moth["crew_id"], "intent": "I inspect the bell.", "confirmed": True},
    ).json()

    assert first["action_id"] != second["action_id"]
    edited = client.patch(
        f"/actions/{first['action_id']}",
        headers=command_auth(ada["token"], "action-edit-gilt"),
        json={"intent": "I inspect only the gilt ledger."},
    )
    assert edited.status_code == 200
    assert edited.json()["crew_id"] == gilt["crew_id"]
