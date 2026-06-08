from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def command_auth(token: str, key: str) -> dict[str, str]:
    return {**auth(token), "Idempotency-Key": key}


def register(client: TestClient, invite: str, name: str) -> dict:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def test_phase_resolution_awards_leader_followup_artifact(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-a"),
        json={"name": "Gilt"},
    ).json()
    moth = client.post(
        "/crews",
        headers=command_auth(bela["token"], "crew-b"),
        json={"name": "Moth"},
    ).json()
    client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-a"),
        json={
            "crew_id": gilt["crew_id"],
            "intent": "Inspect the ledger for forged provenance.",
            "confirmed": True,
        },
    )
    client.post(
        "/actions",
        headers=command_auth(bela["token"], "action-b"),
        json={
            "crew_id": moth["crew_id"],
            "intent": "Read the chapel omen.",
            "confirmed": True,
        },
    )

    resolved = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock"),
        json={"hours_elapsed": 6},
    )
    artifacts = client.get("/artifacts", headers=auth(ada["token"]))
    events = client.get("/events", headers=auth(ada["token"])).json()["events"]

    assert resolved.status_code == 200
    assert any(
        artifact["artifact_id"] == "artifact_clerk_pencil_note"
        for artifact in artifacts.json()["artifacts"]
    )
    assert any(event["type"] == "artifact.phase_reward.awarded" for event in events)
