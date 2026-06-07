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


def setup_three_player_crew(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    linus = register(client, "c", "Linus")
    crew = create_crew(client, ada["token"])
    join_crew(client, grace["token"], crew, "crew-join-grace")
    join_crew(client, linus["token"], crew, "crew-join-linus")
    return client, crew, ada, grace, linus


def test_packet_lead_can_edit_claim_and_reasoning(tmp_path):
    client, crew, ada, _, _ = setup_three_player_crew(tmp_path)

    response = client.patch(
        f"/proofs/dossiers/{crew['crew_id']}/framing",
        headers=command_auth(ada["token"], "dossier-frame-1"),
        json={
            "claim": "The finger is a false relic.",
            "evidence_ids": ["fragment_starter_ledger"],
            "reasoning": "The ledger contradicts the lot card.",
            "weaknesses": "Need material proof.",
            "provenance_concerns": "Rubric copied by unknown hand.",
        },
    )

    assert response.status_code == 200
    assert response.json()["packet_lead_player_id"] == ada["player_id"]
    assert response.json()["claim"] == "The finger is a false relic."


def test_non_lead_cannot_overwrite_framing_but_can_contribute_note(tmp_path):
    client, crew, _, grace, _ = setup_three_player_crew(tmp_path)

    denied = client.patch(
        f"/proofs/dossiers/{crew['crew_id']}/framing",
        headers=command_auth(grace["token"], "dossier-frame-denied"),
        json={"claim": "Grace overwrites it."},
    )
    contribution = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/contributions",
        headers=command_auth(grace["token"], "dossier-note-grace"),
        json={"note": "I can vouch for the transfer chain.", "evidence_ids": ["fragment_a"]},
    )

    assert denied.status_code == 403
    assert contribution.status_code == 201
    assert contribution.json()["member_contributions"][0]["player_id"] == grace["player_id"]


def test_simple_majority_vote_replaces_packet_lead(tmp_path):
    client, crew, _, grace, linus = setup_three_player_crew(tmp_path)

    first = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(grace["token"], "vote-grace-linus"),
        json={"candidate_player_id": linus["player_id"]},
    )
    second = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(linus["token"], "vote-linus-linus"),
        json={"candidate_player_id": linus["player_id"]},
    )

    assert first.json()["packet_lead_player_id"] != linus["player_id"]
    assert second.json()["packet_lead_player_id"] == linus["player_id"]


def test_tie_duplicate_vote_and_vote_change_do_not_replace_until_majority(tmp_path):
    client, crew, ada, grace, linus = setup_three_player_crew(tmp_path)

    tied = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(grace["token"], "vote-grace-grace"),
        json={"candidate_player_id": grace["player_id"]},
    )
    duplicate = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(grace["token"], "vote-grace-grace-duplicate"),
        json={"candidate_player_id": grace["player_id"]},
    )
    changed = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(grace["token"], "vote-grace-linus"),
        json={"candidate_player_id": linus["player_id"]},
    )

    assert tied.json()["packet_lead_player_id"] == ada["player_id"]
    assert duplicate.json()["packet_lead_player_id"] == ada["player_id"]
    assert changed.json()["packet_lead_player_id"] == ada["player_id"]


def test_two_player_test_crew_requires_two_votes_for_replacement(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = create_crew(client, ada["token"])
    join_crew(client, grace["token"], crew, "crew-join-grace")

    one_vote = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(grace["token"], "vote-grace-grace"),
        json={"candidate_player_id": grace["player_id"]},
    )
    two_votes = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(ada["token"], "vote-ada-grace"),
        json={"candidate_player_id": grace["player_id"]},
    )

    assert one_vote.json()["packet_lead_player_id"] == ada["player_id"]
    assert two_votes.json()["packet_lead_player_id"] == grace["player_id"]


def test_packet_lead_can_be_replaced_back_to_prior_lead_and_persist(tmp_path):
    client, crew, ada, grace, linus = setup_three_player_crew(tmp_path)
    client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(grace["token"], "vote-grace-linus"),
        json={"candidate_player_id": linus["player_id"]},
    )
    client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(linus["token"], "vote-linus-linus"),
        json={"candidate_player_id": linus["player_id"]},
    )
    client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(ada["token"], "vote-ada-ada"),
        json={"candidate_player_id": ada["player_id"]},
    )
    client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(grace["token"], "vote-grace-ada"),
        json={"candidate_player_id": ada["player_id"]},
    )
    back_to_linus = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(ada["token"], "vote-ada-linus"),
        json={"candidate_player_id": linus["player_id"]},
    )

    assert back_to_linus.json()["packet_lead_player_id"] == linus["player_id"]
    current = client.get(f"/proofs/dossiers/{crew['crew_id']}", headers=auth(ada["token"]))
    assert current.json()["packet_lead_player_id"] == linus["player_id"]


def test_dossier_idempotency_key_rejects_different_payload_or_crew(tmp_path):
    client, crew, ada, _, _ = setup_three_player_crew(tmp_path)
    second = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-second"),
        json={"name": "Second Crew"},
    ).json()

    first = client.patch(
        f"/proofs/dossiers/{crew['crew_id']}/framing",
        headers=command_auth(ada["token"], "dossier-frame-1"),
        json={"claim": "First claim."},
    )
    changed_payload = client.patch(
        f"/proofs/dossiers/{crew['crew_id']}/framing",
        headers=command_auth(ada["token"], "dossier-frame-1"),
        json={"claim": "Changed claim."},
    )
    changed_crew = client.patch(
        f"/proofs/dossiers/{second['crew_id']}/framing",
        headers=command_auth(ada["token"], "dossier-frame-1"),
        json={"claim": "First claim."},
    )

    assert first.status_code == 200
    assert changed_payload.status_code == 409
    assert changed_crew.status_code == 409


def test_framing_replay_survives_packet_lead_replacement(tmp_path):
    client, crew, ada, grace, linus = setup_three_player_crew(tmp_path)
    first = client.patch(
        f"/proofs/dossiers/{crew['crew_id']}/framing",
        headers=command_auth(ada["token"], "dossier-frame-1"),
        json={"claim": "First claim."},
    )
    client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(grace["token"], "vote-grace-linus"),
        json={"candidate_player_id": linus["player_id"]},
    )
    client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(linus["token"], "vote-linus-linus"),
        json={"candidate_player_id": linus["player_id"]},
    )
    replay = client.patch(
        f"/proofs/dossiers/{crew['crew_id']}/framing",
        headers=command_auth(ada["token"], "dossier-frame-1"),
        json={"claim": "First claim."},
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == first.json()


def test_dossier_unknown_crew_returns_not_found_or_forbidden(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    response = client.get("/proofs/dossiers/no_such_crew", headers=auth(ada["token"]))
    framing = client.patch(
        "/proofs/dossiers/no_such_crew/framing",
        headers=command_auth(ada["token"], "dossier-frame-missing"),
        json={"claim": "Missing crew."},
    )

    assert response.status_code in {403, 404}
    assert framing.status_code in {403, 404}
