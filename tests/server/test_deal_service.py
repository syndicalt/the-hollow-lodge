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


def command_auth(token: str, key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


def create_crew(client: TestClient, token: str, name: str, key: str) -> dict:
    response = client.post("/crews", json={"name": name}, headers=command_auth(token, key))
    assert response.status_code == 201
    return response.json()


def test_accept_fulfills_artifact_swap_atomically(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "Gilt Knives", "crew-gilt")
    moth = create_crew(client, bela["token"], "Moth Lanterns", "crew-moth")
    app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="test setup",
        idempotency_key="grant-chapel",
    )

    deal = app.state.deal_service.propose(
        contract_id="contract_false_finger",
        proposer_crew_id=gilt["crew_id"],
        recipient_crew_id=moth["crew_id"],
        offered_artifact_ids=["artifact_ledger_rubric"],
        requested_artifact_ids=["artifact_chapel_debt_mark"],
        soft_terms=["Do not cite us."],
        expires_phase="Auction Preview",
        proposer_player_id=ada["player_id"],
        idempotency_key="deal-propose",
    )
    fulfilled = app.state.deal_service.accept(
        deal_id=deal["deal_id"],
        actor_player_id=bela["player_id"],
        idempotency_key="deal-accept",
    )

    assert fulfilled["status"] == "fulfilled"
    assert fulfilled["recipient_received_artifact_ids"][0].startswith(
        "artifact_ledger_rubric.dealcopy."
    )
    assert fulfilled["proposer_received_artifact_ids"][0].startswith(
        "artifact_chapel_debt_mark.dealcopy."
    )


def test_accept_rejects_when_requested_artifact_not_visible_to_recipient(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "Gilt Knives", "crew-gilt")
    moth = create_crew(client, bela["token"], "Moth Lanterns", "crew-moth")
    deal = app.state.deal_service.propose(
        contract_id="contract_false_finger",
        proposer_crew_id=gilt["crew_id"],
        recipient_crew_id=moth["crew_id"],
        offered_artifact_ids=["artifact_ledger_rubric"],
        requested_artifact_ids=["artifact_chapel_debt_mark"],
        soft_terms=[],
        expires_phase=None,
        proposer_player_id=ada["player_id"],
        idempotency_key="deal-propose",
    )

    try:
        app.state.deal_service.accept(
            deal_id=deal["deal_id"],
            actor_player_id=bela["player_id"],
            idempotency_key="deal-accept",
        )
    except KeyError as exc:
        assert str(exc).strip("'") == "artifact_chapel_debt_mark"
    else:
        raise AssertionError("accept should reject unavailable requested artifact")
