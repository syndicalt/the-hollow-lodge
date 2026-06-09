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


def activate_ash_window(client: TestClient) -> None:
    response = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )
    assert response.status_code == 201


def test_crew_creation_and_join_are_authoritative_events(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")

    created = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    )
    assert created.status_code == 201
    crew_id = created.json()["crew_id"]
    join_code = created.json()["join_code"]

    joined = client.post(
        f"/crews/{crew_id}/join",
        headers=command_auth(grace["token"], "crew-join-grace"),
        json={"join_code": join_code},
    )

    assert joined.status_code == 200
    assert joined.json()["member_count"] == 2
    events = (tmp_path / "server-events.jsonl").read_text()
    assert "crew.created" in events
    assert "crew.member.joined" in events


def test_wrong_crew_and_missing_actor_operations_are_denied(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    assert client.post("/crews", json={"name": "No Auth"}).status_code == 401
    assert client.post(
        "/crews/crew_missing/join",
        headers=command_auth(ada["token"], "crew-join-missing"),
        json={"join_code": "wrong"},
    ).status_code == 404


def test_crew_readiness_warns_below_three_but_allows_two_player_slice(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()

    joined = client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(grace["token"], "crew-join-grace"),
        json={"join_code": crew["join_code"]},
    )

    assert joined.status_code == 200
    assert joined.json()["ready_for_full_contracts"] is False
    assert "3-5" in joined.json()["readiness_warning"]


def test_crew_board_shows_member_roster_contracts_and_dossier(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()
    client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(grace["token"], "crew-join-grace"),
        json={"join_code": crew["join_code"]},
    )

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["crew"]["crew_id"] == crew["crew_id"]
    assert body["crew"]["name"] == "The Gilt Knives"
    assert body["crew"]["member_ids"] == ["player_0001", "player_0002"]
    assert body["dossier"]["packet_lead_player_id"] == "player_0001"
    assert body["active_contracts"][0]["title"] == "The Saint's False Finger"
    assert "join_code" not in body["crew"]


def test_crew_board_legacy_changes_future_contract_risk_and_opportunity(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    activate_ash_window(client)
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()
    action = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-ledger"),
        json={
            "crew_id": crew["crew_id"],
            "intent": "Inspect the red ledger timestamp for forged provenance.",
            "confirmed": True,
        },
    )
    claim = client.patch(
        f"/proofs/dossiers/{crew['crew_id']}/framing",
        headers=command_auth(ada["token"], "claim-ledger"),
        json={"claim": "The finger is a false relic with forged provenance."},
    )
    resolved = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock"),
        json={"hours_elapsed": 6},
    )

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert action.status_code == 201
    assert claim.status_code == 200
    assert resolved.status_code == 200
    assert response.status_code == 200
    legacy = response.json()["legacy"]
    assert legacy["reputation"] == 2
    assert legacy["heat"] == 1
    assert legacy["favors"] == 1
    assert legacy["debts"] == 0
    assert legacy["completed_contracts"] == [
        {
            "contract_id": "contract_false_finger",
            "title": "The Saint's False Finger",
            "phase": "Auction Preview",
            "standing": "Strong lead",
            "score": 70,
            "outcome": "strong_lead",
        }
    ]
    future = {
        opportunity["contract_id"]: opportunity
        for opportunity in legacy["future_opportunities"]
    }
    assert future["contract_ash_window"]["modifiers"] == [
        {
            "kind": "reputation_leverage",
            "label": "Reputation leverage",
            "description": "Prior strong work gives this crew an opening on The Ash Window.",
            "value": 2,
        },
        {
            "kind": "heat_attention",
            "label": "Heat attention",
            "description": "Prior heat makes The Ash Window riskier for this crew.",
            "value": 1,
        },
    ]
    ash = {
        contract["contract_id"]: contract
        for contract in response.json()["active_contracts"]
    }["contract_ash_window"]
    assert ash["crew_modifiers"] == future["contract_ash_window"]["modifiers"]


def test_crew_board_legacy_remembers_verified_rumors_without_private_sources(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    linus = register(client, "c", "Linus")
    gilt = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()
    moth = client.post(
        "/crews",
        headers=command_auth(grace["token"], "crew-create-moth"),
        json={"name": "The Moth Choir"},
    ).json()
    ash = client.post(
        "/crews",
        headers=command_auth(linus["token"], "crew-create-ash"),
        json={"name": "The Ash Keys"},
    ).json()
    leaked = client.post(
        "/chat/crew-to-crew",
        headers=command_auth(ada["token"], "chat-gilt-moth-ledger"),
        json={
            "sender_crew_id": gilt["crew_id"],
            "recipient_crew_id": moth["crew_id"],
            "body": "The ledger proves our leverage. Keep quiet.",
            "artifact_ids": ["artifact_ledger_rubric"],
        },
    )
    submitted = client.post(
        "/actions",
        headers=command_auth(linus["token"], "action-investigate-rumor"),
        json={
            "crew_id": ash["crew_id"],
            "intent": "Quietly verify the artifact rumor through the auction clerk.",
            "confirmed": True,
            "rumor_id": "rumor_msg_000001",
        },
    )

    response = client.get(f"/crews/{ash['crew_id']}/board", headers=auth(linus["token"]))

    assert leaked.status_code == 201
    assert submitted.status_code == 201
    assert response.status_code == 200
    memory = response.json()["legacy"]["rumor_memory"]
    assert memory == {
        "verified_count": 1,
        "assessment_counts": {"credible_artifact_signal": 1},
        "recent": [
            {
                "rumor_id": "rumor_msg_000001",
                "pressure": "artifact_reference_detected",
                "assessment": "credible_artifact_signal",
                "confidence": "medium",
                "summary": (
                    "The investigation found a credible artifact signal, but "
                    "not enough to expose the private source."
                ),
            }
        ],
    }
    memory_text = str(memory)
    assert "source_id" not in memory_text
    assert "chat.message.created" not in memory_text
    assert "The ledger proves our leverage" not in memory_text
    assert "artifact_ledger_rubric" not in memory_text
    assert gilt["crew_id"] not in memory_text
    assert moth["crew_id"] not in memory_text


def test_repeated_credible_rumors_create_escalation_decision_on_boards(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    linus = register(client, "c", "Linus")
    gilt = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()
    moth = client.post(
        "/crews",
        headers=command_auth(grace["token"], "crew-create-moth"),
        json={"name": "The Moth Choir"},
    ).json()
    ash = client.post(
        "/crews",
        headers=command_auth(linus["token"], "crew-create-ash"),
        json={"name": "The Ash Keys"},
    ).json()
    for index in range(2):
        leaked = client.post(
            "/chat/crew-to-crew",
            headers=command_auth(ada["token"], f"chat-gilt-moth-ledger-{index}"),
            json={
                "sender_crew_id": gilt["crew_id"],
                "recipient_crew_id": moth["crew_id"],
                "body": f"The ledger proves our leverage. Keep quiet. {index}",
                "artifact_ids": ["artifact_ledger_rubric"],
            },
        )
        submitted = client.post(
            "/actions",
            headers=command_auth(linus["token"], f"action-investigate-rumor-{index}"),
            json={
                "crew_id": ash["crew_id"],
                "intent": "Quietly verify the artifact rumor through the auction clerk.",
                "confirmed": True,
                "rumor_id": f"rumor_msg_00000{index + 1}",
            },
        )
        assert leaked.status_code == 201
        assert submitted.status_code == 201

    crew_board = client.get(f"/crews/{ash['crew_id']}/board", headers=auth(linus["token"]))
    inbox = client.get("/inbox", headers=auth(linus["token"]))

    assert crew_board.status_code == 200
    assert inbox.status_code == 200
    expected = {
        "kind": "rumor_escalation",
        "label": "Repeated credible rumor signals",
        "description": (
            f"Crew {ash['crew_id']} has 2 credible rumor verifications. Decide "
            "whether to contain, exploit, or fold them into contract strategy."
        ),
        "crew_id": ash["crew_id"],
        "action": "review_rumor_escalation",
        "credible_count": 2,
        "assessment_counts": {"credible_artifact_signal": 2},
    }
    assert expected in crew_board.json()["pending_decisions"]
    assert expected in inbox.json()["pending_decisions"]
    assert not any(
        decision["kind"] == "rumor_response"
        for decision in crew_board.json()["pending_decisions"]
    )
    assert "msg_000001" not in str(crew_board.json()["pending_decisions"])
    assert "chat.message.created" not in str(crew_board.json()["pending_decisions"])
    assert "The ledger proves our leverage" not in str(crew_board.json()["pending_decisions"])
    assert "artifact_ledger_rubric" not in str(crew_board.json()["pending_decisions"])


def test_crew_board_projects_rumor_escalation_legacy_and_future_modifier(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    linus = register(client, "c", "Linus")
    gilt = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()
    moth = client.post(
        "/crews",
        headers=command_auth(grace["token"], "crew-create-moth"),
        json={"name": "The Moth Choir"},
    ).json()
    ash = client.post(
        "/crews",
        headers=command_auth(linus["token"], "crew-create-ash"),
        json={"name": "The Ash Keys"},
    ).json()
    for index in range(2):
        leaked = client.post(
            "/chat/crew-to-crew",
            headers=command_auth(ada["token"], f"chat-escalation-source-{index}"),
            json={
                "sender_crew_id": gilt["crew_id"],
                "recipient_crew_id": moth["crew_id"],
                "body": f"The ledger proves our leverage. Keep quiet. {index}",
                "artifact_ids": ["artifact_ledger_rubric"],
            },
        )
        verified = client.post(
            "/actions",
            headers=command_auth(linus["token"], f"action-verify-escalation-{index}"),
            json={
                "crew_id": ash["crew_id"],
                "intent": "Quietly verify the artifact rumor through the auction clerk.",
                "confirmed": True,
                "rumor_id": f"rumor_msg_00000{index + 1}",
            },
        )
        assert leaked.status_code == 201
        assert verified.status_code == 201
    escalated = client.post(
        "/actions",
        headers=command_auth(linus["token"], "action-exploit-escalation"),
        json={
            "crew_id": ash["crew_id"],
            "intent": "Exploit the repeated rumor pattern as auction leverage.",
            "confirmed": True,
            "responds_to_rumor_escalation": True,
            "rumor_escalation_mode": "exploit",
        },
    )

    response = client.get(f"/crews/{ash['crew_id']}/board", headers=auth(linus["token"]))

    assert escalated.status_code == 201
    assert response.status_code == 200
    body = response.json()
    assert body["legacy"]["rumor_escalation"] == {
        "contain_count": 0,
        "exploit_count": 1,
        "integrate_count": 0,
        "credible_count_total": 2,
    }
    assert any(
        modifier == {
            "kind": "rumor_exploitation",
            "label": "Rumor exploitation",
            "description": (
                "Recent rumor exploitation gives this crew leverage on "
                f"{contract['title']}."
            ),
            "value": 1,
        }
        for contract in body["active_contracts"]
        for modifier in contract.get("crew_modifiers", [])
    )
    legacy_text = str(body["legacy"])
    assert "source_id" not in legacy_text
    assert "chat.message.created" not in legacy_text
    assert "The ledger proves our leverage" not in legacy_text
    assert "artifact_ledger_rubric" not in legacy_text
    assert gilt["crew_id"] not in legacy_text
    assert moth["crew_id"] not in legacy_text


def test_crew_board_pending_decisions_include_dossier_needs_and_action(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert response.status_code == 200
    pending = response.json()["pending_decisions"]
    assert {
        "kind": "dossier_need",
        "label": "Dossier needs provenance chain",
        "description": "The Saint's False Finger still needs dossier coverage for provenance chain.",
        "crew_id": crew["crew_id"],
        "contract_id": "contract_false_finger",
        "missing_need": "provenance chain",
    } in pending
    assert {
        "kind": "contract_action",
        "label": "Contract action opportunity",
        "description": "The Saint's False Finger is active and unresolved.",
        "crew_id": crew["crew_id"],
        "contract_id": "contract_false_finger",
        "action": "submit_action",
    } in pending


def test_crew_board_pending_action_decision_tracks_submitted_actions(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()
    submitted = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-1"),
        json={
            "crew_id": crew["crew_id"],
            "intent": "I inspect the red ledger rubric quietly.",
            "confirmed": True,
        },
    ).json()

    board = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"])).json()
    pending = board["pending_decisions"]

    assert {
        "kind": "contract_action",
        "label": "Submitted action open for edits",
        "description": (
            "The Saint's False Finger has submitted action(s) that can still be "
            "reviewed, edited, or canceled before lock."
        ),
        "crew_id": crew["crew_id"],
        "contract_id": "contract_false_finger",
        "action": "review_submitted_action",
        "action_ids": [submitted["action_id"]],
    } in pending
    assert not any(
        decision.get("kind") == "contract_action"
        and decision.get("action") == "submit_action"
        for decision in pending
    )


def test_crew_board_pending_action_decision_returns_to_submit_after_cancel(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()
    submitted = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-1"),
        json={
            "crew_id": crew["crew_id"],
            "intent": "I inspect the red ledger rubric quietly.",
            "confirmed": True,
        },
    ).json()
    client.delete(
        f"/actions/{submitted['action_id']}",
        headers=command_auth(ada["token"], "action-cancel-1"),
    )

    pending = client.get(
        f"/crews/{crew['crew_id']}/board",
        headers=auth(ada["token"]),
    ).json()["pending_decisions"]

    assert {
        "kind": "contract_action",
        "label": "Contract action opportunity",
        "description": "The Saint's False Finger is active and unresolved.",
        "crew_id": crew["crew_id"],
        "contract_id": "contract_false_finger",
        "action": "submit_action",
    } in pending
    assert not any("action_ids" in decision for decision in pending)


def test_crew_board_lazy_contract_service_preserves_injected_oracle(tmp_path):
    class InjectedOracle:
        def resolve_auction_preview(self, packet):
            raise AssertionError("crew board should not resolve phases")

    oracle = InjectedOracle()
    client = TestClient(
        create_app(data_dir=tmp_path, invite_codes=["a"], resolution_oracle=oracle)
    )
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()
    del client.app.state.contract_service

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert client.app.state.contract_service._resolution_oracle is oracle


def test_crew_board_shapes_contracts_and_dossier_at_server_boundary(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()

    class ContractServiceStub:
        def board_for_player(self, player_id: str):
            assert player_id == "player_0001"
            return {
                "contracts": [
                    {
                        "contract_id": "contract_false_finger",
                        "title": "The Saint's False Finger",
                        "phase": {
                            "name": "Auction Preview",
                            "remaining_hours": 6,
                            "status": "active",
                            "server_timer_seed": "hidden",
                        },
                        "crew_heat": 0,
                        "proof_dossier_needs": ["provenance chain"],
                        "arc": {
                            "arc_id": "arc_saints_ledgers",
                            "title": "Saints & Ledgers",
                            "chapter": 1,
                            "sequence": 10,
                            "public_summary": "The Lodge starts with a false finger.",
                            "next_contract_hint": "Ash follows the ledger.",
                            "hidden_truth": "server-only",
                        },
                        "phase_result": {
                            "standings": [
                                {
                                    "crew_id": crew["crew_id"],
                                    "standing": "Strong lead",
                                    "score": 82,
                                    "server_tiebreaker": 17,
                                }
                            ],
                            "hidden_truth": "forged reliquary",
                        },
                        "server_only_truth": "forged reliquary",
                    }
                ]
            }

    class ProofServiceStub:
        def dossier_for_crew(self, *, crew_id: str, player_id: str):
            assert crew_id == crew["crew_id"]
            assert player_id == "player_0001"
            return {
                "dossier_id": "dossier_crew_0001",
                "crew_id": crew_id,
                "packet_lead_player_id": player_id,
                "claim": "The relic is false.",
                "evidence_ids": ["fragment_0001"],
                "reasoning": "Ledger mismatch.",
                "weaknesses": "Missing witness.",
                "provenance_concerns": "Ink after binding.",
                "member_contributions": [
                    {
                        "player_id": player_id,
                        "note": "Checked the lot card.",
                        "evidence_ids": ["fragment_0001"],
                        "server_notes": "hidden",
                    }
                ],
                "server_notes": "hidden",
            }

    client.app.state.contract_service = ContractServiceStub()
    client.app.state.proof_service = ProofServiceStub()

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert response.status_code == 200
    body = response.json()
    contract = body["active_contracts"][0]
    assert contract == {
        "contract_id": "contract_false_finger",
        "title": "The Saint's False Finger",
        "phase": {
            "name": "Auction Preview",
            "remaining_hours": 6,
            "status": "active",
        },
        "crew_heat": 0,
        "proof_dossier_needs": ["provenance chain"],
        "arc": {
            "arc_id": "arc_saints_ledgers",
            "title": "Saints & Ledgers",
            "chapter": 1,
            "sequence": 10,
            "public_summary": "The Lodge starts with a false finger.",
            "next_contract_hint": "Ash follows the ledger.",
        },
        "phase_result": {
            "standings": [
                {
                    "crew_id": crew["crew_id"],
                    "standing": "Strong lead",
                    "score": 82,
                }
            ]
        },
    }
    assert body["dossier"] == {
        "dossier_id": "dossier_crew_0001",
        "crew_id": crew["crew_id"],
        "packet_lead_player_id": "player_0001",
        "claim": "The relic is false.",
        "evidence_ids": ["fragment_0001"],
        "reasoning": "Ledger mismatch.",
        "weaknesses": "Missing witness.",
        "provenance_concerns": "Ink after binding.",
        "member_contributions": [
            {
                "player_id": "player_0001",
                "note": "Checked the lot card.",
                "evidence_ids": ["fragment_0001"],
            }
        ],
    }


def test_crew_board_is_crew_scoped(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()

    denied = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(grace["token"]))

    assert denied.status_code == 403


def test_crew_board_deals_are_scoped_to_requested_crew(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    crew_a = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-a"),
        json={"name": "Crew A"},
    ).json()
    crew_b = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-b"),
        json={"name": "Crew B"},
    ).json()
    crew_c = client.post(
        "/crews",
        headers=command_auth(bela["token"], "crew-create-c"),
        json={"name": "Crew C"},
    ).json()
    crew_a_deal = app.state.deal_service.propose(
        contract_id="contract_false_finger",
        proposer_crew_id=crew_a["crew_id"],
        recipient_crew_id=crew_c["crew_id"],
        offered_artifact_ids=["artifact_ledger_rubric"],
        requested_artifact_ids=[],
        soft_terms=["Crew A terms."],
        expires_phase=None,
        proposer_player_id=ada["player_id"],
        idempotency_key="deal-a-c",
    )
    crew_b_deal = app.state.deal_service.propose(
        contract_id="contract_false_finger",
        proposer_crew_id=crew_b["crew_id"],
        recipient_crew_id=crew_c["crew_id"],
        offered_artifact_ids=["artifact_ledger_rubric"],
        requested_artifact_ids=[],
        soft_terms=["Crew B terms."],
        expires_phase=None,
        proposer_player_id=ada["player_id"],
        idempotency_key="deal-b-c",
    )

    response = client.get(f"/crews/{crew_a['crew_id']}/board", headers=auth(ada["token"]))

    assert response.status_code == 200
    deal_ids = {deal["deal_id"] for deal in response.json()["deals"]}
    assert crew_a_deal["deal_id"] in deal_ids
    assert crew_b_deal["deal_id"] not in deal_ids


def test_fulfilled_deal_adds_reliable_broker_legacy_to_crew_board(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b"])
    client = TestClient(app)
    activate_ash_window(client)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()
    moth = client.post(
        "/crews",
        headers=command_auth(bela["token"], "crew-create-moth"),
        json={"name": "The Moth Choir"},
    ).json()
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
        expires_phase=None,
        proposer_player_id=ada["player_id"],
        idempotency_key="deal-propose",
    )
    fulfilled = app.state.deal_service.accept(
        deal_id=deal["deal_id"],
        actor_player_id=bela["player_id"],
        idempotency_key="deal-accept",
    )

    response = client.get(f"/crews/{gilt['crew_id']}/board", headers=auth(ada["token"]))

    assert fulfilled["status"] == "fulfilled"
    assert response.status_code == 200
    body = response.json()
    assert body["legacy"]["deal_conduct"] == {
        "score": 2,
        "fulfilled_count": 1,
        "canceled_count": 0,
        "declined_count": 0,
        "open_count": 0,
        "reliability": "reliable_escrow_partner",
    }
    ash_window = next(
        contract
        for contract in body["active_contracts"]
        if contract["contract_id"] == "contract_ash_window"
    )
    assert ash_window["crew_modifiers"] == [
        {
            "kind": "deal_reliability",
            "label": "Deal reliability",
            "description": (
                "Recent escrowed trades make this crew easier to trust on side "
                "arrangements for The Ash Window."
            ),
            "value": 2,
        }
    ]
    assert "artifact_chapel_debt_mark" not in str(body["legacy"])
    assert "Do not cite us." not in str(body["legacy"])


def test_join_requires_crew_join_code(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()

    denied = client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(grace["token"], "crew-join-wrong"),
        json={"join_code": "wrong-code"},
    )

    assert denied.status_code == 403


def test_crew_commands_require_idempotency_key(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")

    missing_create_key = client.post(
        "/crews",
        headers=auth(ada["token"]),
        json={"name": "The Gilt Knives"},
    )
    assert missing_create_key.status_code == 422

    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()
    missing_join_key = client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=auth(grace["token"]),
        json={"join_code": crew["join_code"]},
    )
    assert missing_join_key.status_code == 422


def test_replayed_crew_create_key_returns_original_crew(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    first = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    )
    replay = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["crew_id"] == first.json()["crew_id"]
    assert replay.json()["name"] == "The Gilt Knives"
    events = [
        line
        for line in (tmp_path / "server-events.jsonl").read_text().splitlines()
        if "crew.created" in line
    ]
    assert len(events) == 1


def test_crew_create_replay_key_cannot_be_used_by_another_player(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")

    created = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    )
    leaked = client.post(
        "/crews",
        headers=command_auth(grace["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    )

    assert created.status_code == 201
    assert leaked.status_code == 409
    assert created.json()["join_code"] not in leaked.text


def test_crew_create_replay_rejects_same_key_with_different_payload(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    first = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    )
    conflict = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Moth Choir"},
    )

    assert first.status_code == 201
    assert conflict.status_code == 409


def test_crew_authority_survives_app_recreation_from_event_log(tmp_path):
    first_client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(first_client, "a", "Ada")
    grace = register(first_client, "b", "Grace")
    crew = first_client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()

    second_client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    joined = second_client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(grace["token"], "crew-join-grace"),
        json={"join_code": crew["join_code"]},
    )

    assert joined.status_code == 200
    assert joined.json()["member_count"] == 2
