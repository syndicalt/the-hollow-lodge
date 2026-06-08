import json
from pathlib import Path

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


def activate_contract(client: TestClient, seed_path: str) -> None:
    response = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-contract",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": seed_path},
    )
    assert response.status_code == 201


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


def test_seeded_phase_reward_awards_configured_artifact_to_phase_leader(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    seed = json.loads(
        Path("tests/fixtures/ash_window_contract.json").read_text(encoding="utf-8")
    )
    seed["artifact_graph"]["artifacts"].append(
        {
            "artifact_id": "artifact_burned_ledger",
            "contract_id": "contract_ash_window",
            "kind": "ledger",
            "title": "Burned Ledger Folio",
            "public_summary": "A scorched folio names the first buyer of the window.",
            "full_text": "Folio: the first buyer paid before Bellweather House burned.",
            "tags": ["ledger", "buyer", "fire"],
            "proof_lanes": ["provenance", "leverage"],
            "phase_relevance": ["Cinder Preview"],
            "hidden_flags": ["future-burn"],
        }
    )
    seed["phase_rewards"] = [
        {
            "phase": "Cinder Preview",
            "trigger": "phase_resolved",
            "award_to": "standing_leader",
            "artifact_id": "artifact_burned_ledger",
            "reason": "Leader follow-up from cinder preview resolution.",
        }
    ]
    seed_path = tmp_path / "ash-window-reward.json"
    seed_path.write_text(json.dumps(seed), encoding="utf-8")
    client = TestClient(create_app(data_dir=tmp_path / "server", invite_codes=["a", "b"]))
    activate_contract(client, str(seed_path))
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
            "intent": "Compare the ash notice timestamp with the soot cooling pattern.",
            "confirmed": True,
        },
    )
    client.post(
        "/actions",
        headers=command_auth(bela["token"], "action-b"),
        json={
            "crew_id": moth["crew_id"],
            "intent": "Interview the witness about the recovered window frame.",
            "confirmed": True,
        },
    )

    resolved = client.post(
        "/contracts/contract_ash_window/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock-ash"),
        json={"hours_elapsed": 4},
    )
    replayed = client.post(
        "/contracts/contract_ash_window/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock-ash-replay"),
        json={"hours_elapsed": 4},
    )
    leader_artifacts = client.get("/artifacts", headers=auth(ada["token"]))
    bystander_artifacts = client.get("/artifacts", headers=auth(bela["token"]))
    events = client.get("/events", headers=auth(ada["token"])).json()["events"]
    bystander_events = client.get("/events", headers=auth(bela["token"])).json()["events"]

    assert resolved.status_code == 200
    assert replayed.status_code == 200
    assert any(
        artifact["artifact_id"] == "artifact_burned_ledger"
        for artifact in leader_artifacts.json()["artifacts"]
    )
    assert "artifact_burned_ledger" not in {
        artifact["artifact_id"] for artifact in bystander_artifacts.json()["artifacts"]
    }
    assert any(
        event["type"] == "artifact.phase_reward.awarded"
        and event["payload"]["artifact_id"] == "artifact_burned_ledger"
        and event["payload"]["crew_id"] == gilt["crew_id"]
        for event in events
    )
    reward_events = [
        event
        for event in events
        if event["type"] == "artifact.phase_reward.awarded"
        and event["payload"]["artifact_id"] == "artifact_burned_ledger"
    ]
    assert len(reward_events) == 1
    assert "artifact_burned_ledger" not in str(bystander_events)
