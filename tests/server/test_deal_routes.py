from fastapi.testclient import TestClient
import pytest

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


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_crew(client: TestClient, token: str, name: str, key: str) -> dict:
    response = client.post("/crews", json={"name": name}, headers=command_auth(token, key))
    assert response.status_code == 201
    return response.json()


def proposed_deal_payload(gilt: dict, moth: dict) -> dict:
    return {
        "contract_id": "contract_false_finger",
        "proposer_crew_id": gilt["crew_id"],
        "recipient_crew_id": moth["crew_id"],
        "offered_artifact_ids": ["artifact_ledger_rubric"],
        "requested_artifact_ids": ["artifact_chapel_debt_mark"],
        "soft_terms": ["Do not cite us."],
        "expires_phase": "Auction Preview",
    }


def test_deal_routes_propose_list_accept(tmp_path):
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

    propose = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    visible = client.get("/deals", headers=auth(bela["token"]))
    accept = client.post(
        f"/deals/{propose.json()['deal_id']}/accept",
        headers=command_auth(bela["token"], "deal-accept"),
        json={},
    )

    assert propose.status_code == 201
    assert propose.json()["status"] == "proposed"
    assert visible.status_code == 200
    assert visible.json()["deals"][0]["soft_terms"] == ["Do not cite us."]
    assert accept.status_code == 200
    assert accept.json()["status"] == "fulfilled"


def test_deal_proposal_leaks_partial_rumor_to_bystander_crew_without_deal_terms(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "Gilt Knives", "crew-gilt")
    moth = create_crew(client, bela["token"], "Moth Lanterns", "crew-moth")
    ash = create_crew(client, caro["token"], "Ash Keys", "crew-ash")
    app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="test setup",
        idempotency_key="grant-chapel",
    )

    propose = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    bystander_deals = client.get("/deals", headers=auth(caro["token"]))
    bystander_events = client.get("/events", headers=auth(caro["token"])).json()["events"]
    bystander_board = client.get(f"/crews/{ash['crew_id']}/board", headers=auth(caro["token"]))
    participant_events = client.get("/events", headers=auth(ada["token"])).json()["events"]
    accepted = client.post(
        f"/deals/{propose.json()['deal_id']}/accept",
        headers=command_auth(bela["token"], "deal-accept"),
        json={},
    )

    assert propose.status_code == 201
    assert bystander_deals.status_code == 200
    assert bystander_deals.json()["deals"] == []
    rumor_events = [
        event for event in bystander_events
        if event["type"] == "contract.rumor.leaked"
    ]
    assert len(rumor_events) == 1
    rumor = rumor_events[0]["payload"]
    assert rumor == {
        "rumor_id": "rumor_deal_000001",
        "source_type": "deal.proposed",
        "source_id": "deal_000001",
        "contract_id": "contract_false_finger",
        "suspected_crew_ids": [gilt["crew_id"], moth["crew_id"]],
        "summary": "A side arrangement is circulating around contract_false_finger.",
        "pressure": "escrow_terms_detected",
        "leak_vector": "soft_term_reference",
    }
    assert "artifact_ledger_rubric" not in str(rumor_events)
    assert "artifact_chapel_debt_mark" not in str(rumor_events)
    assert "Do not cite us." not in str(rumor_events)
    assert bystander_board.status_code == 200
    assert bystander_board.json()["deals"] == []
    assert bystander_board.json()["rumors"] == [rumor]
    assert "artifact_ledger_rubric" not in str(bystander_board.json()["rumors"])
    assert "artifact_chapel_debt_mark" not in str(bystander_board.json()["rumors"])
    assert "Do not cite us." not in str(bystander_board.json()["rumors"])
    assert not any(
        event["type"] == "contract.rumor.leaked"
        for event in participant_events
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "fulfilled"
    assert ash["crew_id"] not in {
        event["payload"].get("recipient_crew_id")
        for event in participant_events
        if event["type"] == "deal.proposed"
    }


def test_deal_rumor_becomes_pending_decision_for_bystander_crew(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "Gilt Knives", "crew-gilt")
    moth = create_crew(client, bela["token"], "Moth Lanterns", "crew-moth")
    ash = create_crew(client, caro["token"], "Ash Keys", "crew-ash")
    app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="test setup",
        idempotency_key="grant-chapel",
    )

    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    board = client.get(f"/crews/{ash['crew_id']}/board", headers=auth(caro["token"]))
    inbox = client.get("/inbox", headers=auth(caro["token"]))

    expected = {
        "kind": "rumor_response",
        "label": "Rumor needs response",
        "description": (
            "Rumor rumor_deal_000001 suggests escrow_terms_detected. "
            "Decide whether to verify, ignore, or answer with a crew action."
        ),
        "crew_id": ash["crew_id"],
        "rumor_id": "rumor_deal_000001",
        "source_type": "deal.proposed",
        "source_id": proposed.json()["deal_id"],
        "pressure": "escrow_terms_detected",
        "leak_vector": "soft_term_reference",
        "action": "review_rumor",
    }
    assert proposed.status_code == 201
    assert board.status_code == 200
    assert inbox.status_code == 200
    assert expected in board.json()["pending_decisions"]
    assert expected in inbox.json()["pending_decisions"]
    assert "artifact_ledger_rubric" not in str(board.json()["pending_decisions"])
    assert "artifact_chapel_debt_mark" not in str(board.json()["pending_decisions"])
    assert "Do not cite us." not in str(board.json()["pending_decisions"])


def test_deal_rumor_without_soft_terms_uses_artifact_swap_leak_vector(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "Gilt Knives", "crew-gilt")
    moth = create_crew(client, bela["token"], "Moth Lanterns", "crew-moth")
    ash = create_crew(client, caro["token"], "Ash Keys", "crew-ash")
    app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="test setup",
        idempotency_key="grant-chapel",
    )

    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose-no-soft-terms"),
        json={
            **proposed_deal_payload(gilt, moth),
            "soft_terms": [],
        },
    )
    board = client.get(f"/crews/{ash['crew_id']}/board", headers=auth(caro["token"]))

    assert proposed.status_code == 201
    rumors = board.json()["rumors"]
    assert rumors == [
        {
            "rumor_id": "rumor_deal_000001",
            "source_type": "deal.proposed",
            "source_id": proposed.json()["deal_id"],
            "contract_id": "contract_false_finger",
            "suspected_crew_ids": [gilt["crew_id"], moth["crew_id"]],
            "summary": "A side arrangement is circulating around contract_false_finger.",
            "pressure": "escrow_terms_detected",
            "leak_vector": "escrow_artifact_swap",
        }
    ]
    assert "artifact_ledger_rubric" not in str(rumors)
    assert "artifact_chapel_debt_mark" not in str(rumors)


def test_persisted_deals_render_after_restart_before_deals_route(tmp_path):
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
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    ).json()

    restarted = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))
    inbox = restarted.get("/inbox", headers=auth(bela["token"]))
    crew_board = restarted.get(f"/crews/{moth['crew_id']}/board", headers=auth(bela["token"]))

    assert inbox.status_code == 200
    assert [deal["deal_id"] for deal in inbox.json()["deals"]] == [proposed["deal_id"]]
    assert crew_board.status_code == 200
    assert [deal["deal_id"] for deal in crew_board.json()["deals"]] == [proposed["deal_id"]]


def test_pending_decisions_include_incoming_and_outgoing_deals(tmp_path):
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
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    ).json()

    proposer_inbox = client.get("/inbox", headers=auth(ada["token"])).json()
    recipient_board = client.get(
        f"/crews/{moth['crew_id']}/board",
        headers=auth(bela["token"]),
    ).json()

    assert {
        "kind": "outgoing_deal",
        "label": "Outgoing deal awaiting response",
        "description": "Deal deal_000001 is proposed to crew_0002.",
        "crew_id": gilt["crew_id"],
        "contract_id": "contract_false_finger",
        "deal_id": proposed["deal_id"],
    } in proposer_inbox["pending_decisions"]
    assert {
        "kind": "incoming_deal",
        "label": "Incoming deal needs response",
        "description": "Deal deal_000001 from crew_0001 needs a response.",
        "crew_id": moth["crew_id"],
        "contract_id": "contract_false_finger",
        "deal_id": proposed["deal_id"],
    } in recipient_board["pending_decisions"]


def test_non_member_cannot_accept_deal(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
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
    propose = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )

    accept = client.post(
        f"/deals/{propose.json()['deal_id']}/accept",
        headers=command_auth(caro["token"], "deal-accept"),
        json={},
    )

    assert accept.status_code == 403
    assert accept.json()["detail"] == "not a crew member"


@pytest.mark.parametrize("action", ["accept", "decline", "cancel"])
def test_missing_deal_returns_deal_not_found(tmp_path, action):
    app = create_app(data_dir=tmp_path, invite_codes=["a"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")

    response = client.post(
        f"/deals/deal_missing/{action}",
        headers=command_auth(ada["token"], f"deal-missing-{action}"),
        json={},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "deal not found"
