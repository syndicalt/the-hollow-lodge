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


def test_recipient_sees_only_surface_provenance_until_check_is_spent(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")

    transfer = client.post(
        "/proofs/fragments/fragment_starter_ledger/transfer",
        headers=command_auth(ada["token"], "proof-transfer-1"),
        json={"recipient_player_id": grace["player_id"]},
    )
    copy_id = transfer.json()["fragment_id"]
    surface = client.get(
        f"/proofs/fragments/{copy_id}",
        headers=auth(grace["token"]),
    )

    assert transfer.status_code == 201
    assert copy_id != "fragment_starter_ledger"
    assert surface.status_code == 200
    assert surface.json()["provenance_checked"] is False
    assert "copied-hand" not in surface.text
    assert "ink-after-binding" not in surface.text
    visible_events = client.get("/events", headers=auth(grace["token"])).text
    assert "proof.fragment.transferred.internal" not in visible_events
    assert "copied-hand" not in visible_events
    assert "ink-after-binding" not in visible_events

    checked = client.post(
        f"/proofs/fragments/{copy_id}/check/provenance",
        headers=command_auth(grace["token"], "proof-check-1"),
    )

    assert checked.status_code == 201
    assert checked.json()["provenance_checked"] is True
    assert checked.json()["provenance_flags"] == ["copied-hand", "ink-after-binding"]


def test_untargeted_player_cannot_fetch_or_check_starter_fragment(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")

    assert client.get(
        "/proofs/fragments/fragment_starter_ledger",
        headers=auth(grace["token"]),
    ).status_code == 404
    denied = client.post(
        "/proofs/fragments/fragment_starter_ledger/check/provenance",
        headers=command_auth(grace["token"], "proof-check-denied"),
    )

    assert denied.status_code == 404
    assert client.post(
        "/proofs/fragments/fragment_starter_ledger/check/provenance",
        headers=command_auth(ada["token"], "proof-check-allowed"),
    ).status_code == 201


def test_transferred_copy_preserves_internal_provenance_for_recipient_check(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    transfer = client.post(
        "/proofs/fragments/fragment_starter_ledger/transfer",
        headers=command_auth(ada["token"], "proof-transfer-1"),
        json={"recipient_player_id": grace["player_id"]},
    )
    copy_id = transfer.json()["fragment_id"]

    checked = client.post(
        f"/proofs/fragments/{copy_id}/check/provenance",
        headers=command_auth(grace["token"], "proof-check-copy"),
    )

    assert checked.status_code == 201
    assert checked.json()["provenance_flags"] == ["copied-hand", "ink-after-binding"]


def test_provenance_check_replay_rejects_same_key_for_different_fragment(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    first = client.post(
        "/proofs/fragments/fragment_starter_ledger/check/provenance",
        headers=command_auth(ada["token"], "proof-check-1"),
    )
    conflict = client.post(
        "/proofs/fragments/fragment_missing/check/provenance",
        headers=command_auth(ada["token"], "proof-check-1"),
    )

    assert first.status_code == 201
    assert conflict.status_code == 409


def test_side_action_limit_rejects_extra_provenance_checks(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    first = client.post(
        "/proofs/fragments/fragment_starter_ledger/check/provenance",
        headers=command_auth(ada["token"], "proof-check-1"),
    )
    second = client.post(
        "/proofs/fragments/fragment_starter_ledger/check/provenance",
        headers=command_auth(ada["token"], "proof-check-2"),
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert "side action" in second.text


def test_handler_summary_cannot_create_official_provenance_result_events(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    visible_before = client.get("/events", headers=auth(ada["token"])).text
    assert "proof.provenance.checked" not in visible_before

    summary_like_payload = {
        "fragment_id": "fragment_starter_ledger",
        "summary": "Handler thinks this looks copied.",
    }
    denied = client.post(
        "/events",
        headers=command_auth(ada["token"], "fake-provenance"),
        json=summary_like_payload,
    )

    assert denied.status_code == 405
    visible_after = client.get("/events", headers=auth(ada["token"])).text
    assert "proof.provenance.checked" not in visible_after


def test_crew_member_can_cite_visible_artifact_in_dossier(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create"),
        json={"name": "The Gilt Knives"},
    ).json()

    cited = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/artifact-citations",
        headers=command_auth(ada["token"], "cite-ledger"),
        json={
            "artifact_id": "artifact_ledger_rubric",
            "claim": "The ledger contradicts the public lot card.",
            "quote": "The last hand is redder and later than the binding.",
        },
    )

    assert cited.status_code == 201
    assert cited.json()["artifact_citations"] == [
        {
            "player_id": ada["player_id"],
            "artifact_id": "artifact_ledger_rubric",
            "claim": "The ledger contradicts the public lot card.",
            "quote": "The last hand is redder and later than the binding.",
        }
    ]
    visible = client.get("/events", headers=auth(ada["token"])).json()["events"]
    citation_event = [
        event for event in visible if event["type"] == "artifact.dossier.cited"
    ][0]
    assert citation_event["payload"]["crew_id"] == crew["crew_id"]
    assert citation_event["payload"]["artifact_id"] == "artifact_ledger_rubric"


def test_citing_hidden_artifact_returns_404(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create"),
        json={"name": "The Gilt Knives"},
    ).json()

    cited = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/artifact-citations",
        headers=command_auth(ada["token"], "cite-hidden"),
        json={
            "artifact_id": "artifact_chapel_debt_mark",
            "claim": "The chapel mark proves a concealed debt.",
            "quote": "Marked under chapel seal.",
        },
    )

    assert cited.status_code == 404
    assert cited.json()["detail"] == "artifact not found"


def test_artifact_citation_idempotency_conflict_rejects_changed_payload(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create"),
        json={"name": "The Gilt Knives"},
    ).json()
    payload = {
        "artifact_id": "artifact_ledger_rubric",
        "claim": "The ledger contradicts the public lot card.",
        "quote": "The last hand is redder and later than the binding.",
    }

    first = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/artifact-citations",
        headers=command_auth(ada["token"], "cite-ledger"),
        json=payload,
    )
    replay = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/artifact-citations",
        headers=command_auth(ada["token"], "cite-ledger"),
        json=payload,
    )
    conflict = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/artifact-citations",
        headers=command_auth(ada["token"], "cite-ledger"),
        json={**payload, "claim": "A different claim."},
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["artifact_citations"] == first.json()["artifact_citations"]
    assert conflict.status_code == 409
