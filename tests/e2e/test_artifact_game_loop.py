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


def test_player_gets_artifacts_inspects_transfers_cites_and_resolves(tmp_path):
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

    inbox = client.get("/inbox", headers=auth(ada["token"]))
    starter_artifacts = client.get("/artifacts", headers=auth(ada["token"])).json()
    assert inbox.status_code == 200
    assert "artifact_ledger_rubric" in {
        artifact["artifact_id"] for artifact in starter_artifacts["artifacts"]
    }

    inspected = client.post(
        "/artifacts/artifact_ledger_rubric/inspect",
        headers=command_auth(ada["token"], "inspect-ledger"),
    )
    assert inspected.status_code == 200
    assert "The last hand is redder" in inspected.json()["full_text"]

    transferred = client.post(
        "/artifacts/artifact_ledger_rubric/transfer",
        headers=command_auth(ada["token"], "transfer-ledger"),
        json={"recipient_player_id": bela["player_id"]},
    )
    assert transferred.status_code == 201
    assert transferred.json()["artifact_id"].startswith("artifact_ledger_rubric.copy.")

    citation = client.post(
        f"/proofs/dossiers/{gilt['crew_id']}/artifact-citations",
        headers=command_auth(ada["token"], "cite-ledger"),
        json={
            "artifact_id": "artifact_ledger_rubric",
            "claim": "The ledger contradicts the public lot card.",
            "quote": "The last hand is redder and later than the binding.",
        },
    )
    assert citation.status_code == 201

    gilt_action = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-clerk"),
        json={
            "crew_id": gilt["crew_id"],
            "intent": "Question the clerk about the catalogue correction.",
            "confirmed": True,
        },
    )
    moth_action = client.post(
        "/actions",
        headers=command_auth(bela["token"], "action-chapel"),
        json={
            "crew_id": moth["crew_id"],
            "intent": "Follow the chapel omen and debt mark.",
            "confirmed": True,
        },
    )
    assert gilt_action.status_code == 201
    assert moth_action.status_code == 201

    resolved = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock"),
        json={"hours_elapsed": 6},
    )

    assert resolved.status_code == 200
    assert resolved.json()["standings"]
    assert "truth_false_finger_forgery" not in str(resolved.json())
