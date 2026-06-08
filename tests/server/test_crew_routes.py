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
