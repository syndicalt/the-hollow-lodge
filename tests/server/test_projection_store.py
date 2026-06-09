import json
import sqlite3

from fastapi.testclient import TestClient

from hollow_lodge.domain.deals import deal_rows_from_events
from hollow_lodge.domain.events import EventVisibility
import hollow_lodge.server.routes_contracts as routes_contracts
import hollow_lodge.server.routes_crews as routes_crews
from hollow_lodge.server.app import create_app
from hollow_lodge.server.projections import (
    contract_board_from_events,
    crew_summaries_from_events,
)
from hollow_lodge.server.projection_store import (
    PROJECTION_SCHEMA_MIGRATIONS,
    SCHEMA_VERSION,
)
from hollow_lodge.server.seed_data import STARTER_CONTRACT


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


def create_crew(client: TestClient, token: str, key: str, name: str) -> dict:
    response = client.post(
        "/crews",
        headers=command_auth(token, key),
        json={"name": name},
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


def submit_action(client: TestClient, player: dict, crew: dict, key: str, intent: str) -> dict:
    response = client.post(
        "/actions",
        headers=command_auth(player["token"], key),
        json={"crew_id": crew["crew_id"], "intent": intent, "confirmed": True},
    )
    assert response.status_code == 201
    return response.json()


def set_claim(client: TestClient, player: dict, crew: dict, key: str, claim: str) -> dict:
    response = client.patch(
        f"/proofs/dossiers/{crew['crew_id']}/framing",
        headers=command_auth(player["token"], key),
        json={"claim": claim},
    )
    assert response.status_code == 200
    return response.json()


def test_projection_store_materializes_current_proof_dossiers_without_command_metadata(
    tmp_path,
):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    join_crew(client, grace["token"], crew, "crew-join-grace")
    set_claim(
        client,
        ada,
        crew,
        "dossier-frame-1",
        "The finger is an engineered fraud.",
    )
    contribution = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/contributions",
        headers=command_auth(grace["token"], "dossier-note-grace"),
        json={
            "note": "The provenance chain names the wrong chapel clerk.",
            "evidence_ids": ["fragment_starter_ledger"],
        },
    )
    vote = client.post(
        f"/proofs/dossiers/{crew['crew_id']}/packet-lead/votes",
        headers=command_auth(grace["token"], "packet-vote-grace"),
        json={"candidate_player_id": grace["player_id"]},
    )

    assert contribution.status_code == 201
    assert vote.status_code == 200

    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    dossier = client.app.state.projection_store.read_proof_dossier(crew["crew_id"])

    assert dossier["claim"] == "The finger is an engineered fraud."
    assert dossier["packet_lead_player_id"] == ada["player_id"]
    assert dossier["member_contributions"] == [
        {
            "player_id": grace["player_id"],
            "note": "The provenance chain names the wrong chapel clerk.",
            "evidence_ids": ["fragment_starter_ledger"],
        }
    ]
    assert len(dossier["packet_lead_votes"]) == 1
    assert dossier["packet_lead_votes"][0]["sequence"] > 0
    assert dossier["packet_lead_votes"][0]["voter_player_id"] == grace["player_id"]
    assert dossier["packet_lead_votes"][0]["candidate_player_id"] == grace["player_id"]
    assert "dossier-note-grace" not in str(dossier)
    assert "packet-vote-grace" not in str(dossier)


def test_dossier_route_reads_fresh_projection_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_PROOF_DOSSIER_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    set_claim(
        client,
        ada,
        crew,
        "dossier-frame-1",
        "The finger is an engineered fraud.",
    )
    original_read = client.app.state.projection_store.read_proof_dossier
    calls = {"count": 0}

    def tracked_read_proof_dossier(crew_id: str):
        calls["count"] += 1
        return original_read(crew_id)

    client.app.state.projection_store.read_proof_dossier = tracked_read_proof_dossier

    response = client.get(
        f"/proofs/dossiers/{crew['crew_id']}",
        headers=auth(ada["token"]),
    )

    assert response.status_code == 200
    assert calls["count"] == 1
    assert response.json()["claim"] == "The finger is an engineered fraud."


def test_embedded_dossier_surfaces_read_fresh_projection_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_PROOF_DOSSIER_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    set_claim(
        client,
        ada,
        crew,
        "dossier-frame-1",
        "The finger is an engineered fraud.",
    )
    original_read = client.app.state.projection_store.read_proof_dossier
    calls = {"count": 0}

    def tracked_read_proof_dossier(crew_id: str):
        calls["count"] += 1
        return original_read(crew_id)

    client.app.state.projection_store.read_proof_dossier = tracked_read_proof_dossier

    crew_board = client.get(
        f"/crews/{crew['crew_id']}/board",
        headers=auth(ada["token"]),
    )
    inbox = client.get("/inbox", headers=auth(ada["token"]))

    assert crew_board.status_code == 200
    assert inbox.status_code == 200
    assert calls["count"] >= 2
    assert crew_board.json()["dossier"]["claim"] == "The finger is an engineered fraud."
    assert any(
        decision["kind"] == "dossier_need"
        for decision in inbox.json()["pending_decisions"]
    )


def test_dossier_route_falls_back_when_projected_dossier_is_stale(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_PROOF_DOSSIER_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    client.app.state.event_store.append_command(
        event_type="contract.note.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload={"note": "projection stale marker"},
        idempotency_key="projection-stale-marker",
    )

    def fail_if_projection_read(crew_id: str):
        raise AssertionError("stale proof dossier projection should not be used")

    client.app.state.projection_store.read_proof_dossier = fail_if_projection_read

    response = client.get(
        f"/proofs/dossiers/{crew['crew_id']}",
        headers=auth(ada["token"]),
    )

    assert response.status_code == 200
    assert response.json()["dossier_id"] == f"dossier_{crew['crew_id']}"


def test_projection_store_records_schema_migration_ledger(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    projection = client.get("/diagnostics").json()["data"]["projection_db"]

    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        migrations = connection.execute(
            """
            select applied_version, description
            from projection_schema_migrations
            order by cast(applied_version as integer)
            """
        ).fetchall()
        meta_rows = dict(
            connection.execute("select key, value from projection_meta").fetchall()
        )

    assert migrations == list(PROJECTION_SCHEMA_MIGRATIONS)
    assert meta_rows["schema_version"] == SCHEMA_VERSION
    assert projection["schema_version"] == int(SCHEMA_VERSION)
    assert projection["schema_migration_count"] == len(PROJECTION_SCHEMA_MIGRATIONS)
    assert projection["latest_schema_migration"] == SCHEMA_VERSION


def test_projection_store_materializes_visible_chat_messages_without_bystander_access(
    tmp_path,
):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    cora = register(client, "c", "Cora")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    create_crew(client, cora["token"], "crew-create-cora", "The Glass Index")
    sent = client.post(
        "/chat/crew-to-crew",
        headers=command_auth(ada["token"], "chat-gilt-moth"),
        json={
            "sender_crew_id": gilt["crew_id"],
            "recipient_crew_id": moth["crew_id"],
            "body": "The ledger is useful, but keep this private.",
        },
    )

    assert sent.status_code == 201

    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    ada_visible = client.app.state.projection_store.read_visible_chat_events(
        ada["player_id"],
        crew_ids=[gilt["crew_id"]],
    )
    bela_thread = client.app.state.projection_store.read_visible_chat_events(
        bela["player_id"],
        crew_ids=[moth["crew_id"]],
        conversation_id=f"{moth['crew_id']}:{gilt['crew_id']}",
    )
    cora_visible = client.app.state.projection_store.read_visible_chat_events(
        cora["player_id"],
        crew_ids=[],
    )
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        rows = connection.execute(
            """
            select message_id, conversation_id, payload_json
            from chat_message_surface
            """
        ).fetchall()

    assert len(rows) == 1
    assert rows[0][0] == sent.json()["message_id"]
    assert rows[0][1] == f"{gilt['crew_id']}:{moth['crew_id']}"
    assert "chat-gilt-moth" not in rows[0][2]
    assert len(ada_visible) == 1
    assert len(bela_thread) == 1
    assert cora_visible == []
    assert ada_visible[0]["payload"]["body"] == "The ledger is useful, but keep this private."


def test_chat_messages_route_reads_fresh_projection_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_CHAT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    sent = client.post(
        "/chat/crew-to-crew",
        headers=command_auth(ada["token"], "chat-gilt-moth"),
        json={
            "sender_crew_id": gilt["crew_id"],
            "recipient_crew_id": moth["crew_id"],
            "body": "Meet after the preview.",
        },
    )
    original_read = client.app.state.projection_store.read_visible_chat_events
    calls = {"count": 0}

    def tracked_read_visible_chat_events(player_id: str, *, crew_ids=(), conversation_id=None):
        calls["count"] += 1
        return original_read(
            player_id,
            crew_ids=crew_ids,
            conversation_id=conversation_id,
        )

    client.app.state.projection_store.read_visible_chat_events = (
        tracked_read_visible_chat_events
    )

    response = client.get(
        "/chat/messages",
        headers=auth(ada["token"]),
        params={"conversation_id": f"{moth['crew_id']}:{gilt['crew_id']}"},
    )

    assert sent.status_code == 201
    assert response.status_code == 200
    assert calls["count"] == 1
    assert [event["payload"]["body"] for event in response.json()["events"]] == [
        "Meet after the preview."
    ]


def test_chat_messages_route_falls_back_when_projection_is_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_CHAT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    sent = client.post(
        "/chat/crew-to-crew",
        headers=command_auth(ada["token"], "chat-gilt-moth"),
        json={
            "sender_crew_id": gilt["crew_id"],
            "recipient_crew_id": moth["crew_id"],
            "body": "This arrives after the projection checkpoint.",
        },
    )

    def fail_if_projection_read(player_id: str, *, crew_ids=(), conversation_id=None):
        raise AssertionError("stale chat projection should not be used")

    client.app.state.projection_store.read_visible_chat_events = fail_if_projection_read

    response = client.get("/chat/messages", headers=auth(ada["token"]))

    assert sent.status_code == 201
    assert response.status_code == 200
    assert [event["payload"]["body"] for event in response.json()["events"]] == [
        "This arrives after the projection checkpoint."
    ]


def test_projection_store_materializes_pending_decisions_without_private_deal_terms(
    tmp_path,
):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    ash = create_crew(client, caro["token"], "crew-create-ash", "The Ash Keys")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )

    assert proposed.status_code == 201

    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    bela_decisions = client.app.state.projection_store.read_pending_decisions(
        bela["player_id"],
        crew_ids=[moth["crew_id"]],
    )
    caro_decisions = client.app.state.projection_store.read_pending_decisions(
        caro["player_id"],
        crew_ids=[ash["crew_id"]],
    )
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        rows = connection.execute(
            """
            select player_id, crew_id, kind, payload_json
            from pending_decision_surface
            order by player_id, crew_id, decision_index
            """
        ).fetchall()

    assert any(
        decision["kind"] == "incoming_deal"
        and decision["deal_id"] == proposed.json()["deal_id"]
        for decision in bela_decisions
    )
    assert not any(
        decision.get("deal_id") == proposed.json()["deal_id"]
        for decision in caro_decisions
    )
    serialized_rows = str(rows)
    assert "Do not cite us." not in serialized_rows
    assert "artifact_ledger_rubric" not in serialized_rows
    assert "artifact_chapel_debt_mark" not in serialized_rows
    assert "deal-propose" not in serialized_rows


def test_projection_store_materializes_visible_rumors_without_private_sources(
    tmp_path,
):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    ash = create_crew(client, caro["token"], "crew-create-ash", "The Ash Keys")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )

    assert proposed.status_code == 201

    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    rumors = client.app.state.projection_store.read_visible_rumors_for_crew(
        ash["crew_id"]
    )
    diagnostics = client.app.state.projection_store.diagnostics()
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        rows = connection.execute(
            """
            select crew_id, rumor_id, payload_json
            from visible_rumor_surface
            order by crew_id, rumor_id
            """
        ).fetchall()

    assert rumors == [
        {
            "rumor_id": "rumor_deal_000001",
            "source_type": "deal.proposed",
            "source_id": proposed.json()["deal_id"],
            "contract_id": "contract_false_finger",
            "suspected_crew_ids": [gilt["crew_id"], moth["crew_id"]],
            "summary": "A side arrangement is circulating around contract_false_finger.",
            "pressure": "escrow_terms_detected",
            "leak_vector": "soft_term_reference",
        }
    ]
    assert rows == [
        (
            ash["crew_id"],
            "rumor_deal_000001",
            json.dumps(rumors[0], sort_keys=True, separators=(",", ":")),
        )
    ]
    assert diagnostics["visible_rumor_count"] == 1
    serialized_rows = str(rows)
    assert "Do not cite us." not in serialized_rows
    assert "artifact_ledger_rubric" not in serialized_rows
    assert "artifact_chapel_debt_mark" not in serialized_rows
    assert "deal-propose" not in serialized_rows
    assert client.app.state.projection_store.read_visible_rumors_for_crew(
        gilt["crew_id"]
    ) == []


def test_crew_board_embeds_projected_visible_rumors_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_RUMOR_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    ash = create_crew(client, caro["token"], "crew-create-ash", "The Ash Keys")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    original_read = client.app.state.projection_store.read_visible_rumors_for_crew
    calls = {"count": 0}

    def tracked_read_visible_rumors_for_crew(crew_id: str):
        calls["count"] += 1
        return original_read(crew_id)

    client.app.state.projection_store.read_visible_rumors_for_crew = (
        tracked_read_visible_rumors_for_crew
    )
    monkeypatch.setattr(
        routes_crews,
        "visible_rumors_for_crew",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("crew board should use fresh rumor projection")
        ),
    )

    response = client.get(
        f"/crews/{ash['crew_id']}/board",
        headers=auth(caro["token"]),
    )

    assert proposed.status_code == 201
    assert response.status_code == 200
    assert calls["count"] == 1
    assert response.json()["rumors"] == [
        {
            "rumor_id": "rumor_deal_000001",
            "source_type": "deal.proposed",
            "source_id": proposed.json()["deal_id"],
            "contract_id": "contract_false_finger",
            "suspected_crew_ids": [gilt["crew_id"], moth["crew_id"]],
            "summary": "A side arrangement is circulating around contract_false_finger.",
            "pressure": "escrow_terms_detected",
            "leak_vector": "soft_term_reference",
        }
    ]
    assert "Do not cite us." not in str(response.json()["rumors"])
    assert "artifact_ledger_rubric" not in str(response.json()["rumors"])
    assert "artifact_chapel_debt_mark" not in str(response.json()["rumors"])


def test_crew_board_visible_rumors_fall_back_when_projection_is_stale(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_RUMOR_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    rumor = {
        "rumor_id": "rumor_out_of_band",
        "source_type": "manual.test",
        "source_id": "source_out_of_band",
        "contract_id": "contract_false_finger",
        "suspected_crew_ids": ["crew_shadow"],
        "summary": "A late rumor reached the crew after projection refresh.",
        "pressure": "late_signal",
        "leak_vector": "manual",
        "private_note": "must not appear",
    }
    client.app.state.event_store.append_command(
        event_type="contract.rumor.leaked",
        actor_id="server",
        visibility=EventVisibility.crews([crew["crew_id"]]),
        payload=rumor,
        idempotency_key="out-of-band-rumor",
    )

    def fail_if_projection_read(crew_id: str):
        raise AssertionError("stale rumor projection should not be used")

    client.app.state.projection_store.read_visible_rumors_for_crew = (
        fail_if_projection_read
    )

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert response.json()["rumors"] == [
        {
            "rumor_id": "rumor_out_of_band",
            "source_type": "manual.test",
            "source_id": "source_out_of_band",
            "contract_id": "contract_false_finger",
            "suspected_crew_ids": ["crew_shadow"],
            "summary": "A late rumor reached the crew after projection refresh.",
            "pressure": "late_signal",
            "leak_vector": "manual",
        }
    ]
    assert "private_note" not in str(response.json()["rumors"])


def test_inbox_pending_decisions_use_projected_visible_rumors_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_RUMOR_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    ash = create_crew(client, caro["token"], "crew-create-ash", "The Ash Keys")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    original_read = client.app.state.projection_store.read_visible_rumors_for_crew
    calls = {"count": 0}

    def tracked_read_visible_rumors_for_crew(crew_id: str):
        calls["count"] += 1
        return original_read(crew_id)

    client.app.state.projection_store.read_visible_rumors_for_crew = (
        tracked_read_visible_rumors_for_crew
    )
    monkeypatch.setattr(
        routes_contracts,
        "visible_rumors_for_crew",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("inbox should use fresh rumor projection")
        ),
    )

    response = client.get("/inbox", headers=auth(caro["token"]))

    assert proposed.status_code == 201
    assert response.status_code == 200
    assert calls["count"] == 1
    assert {
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
    } in response.json()["pending_decisions"]
    assert "Do not cite us." not in str(response.json()["pending_decisions"])
    assert "artifact_ledger_rubric" not in str(response.json()["pending_decisions"])
    assert "artifact_chapel_debt_mark" not in str(response.json()["pending_decisions"])


def test_inbox_visible_rumors_fall_back_when_projection_is_stale(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_RUMOR_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    rumor = {
        "rumor_id": "rumor_out_of_band",
        "source_type": "manual.test",
        "source_id": "source_out_of_band",
        "contract_id": "contract_false_finger",
        "suspected_crew_ids": ["crew_shadow"],
        "summary": "A late rumor reached the crew after projection refresh.",
        "pressure": "late_signal",
        "leak_vector": "manual",
        "private_note": "must not appear",
    }
    client.app.state.event_store.append_command(
        event_type="contract.rumor.leaked",
        actor_id="server",
        visibility=EventVisibility.crews([crew["crew_id"]]),
        payload=rumor,
        idempotency_key="out-of-band-rumor",
    )

    def fail_if_projection_read(crew_id: str):
        raise AssertionError("stale inbox rumor projection should not be used")

    client.app.state.projection_store.read_visible_rumors_for_crew = (
        fail_if_projection_read
    )

    response = client.get("/inbox", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert {
        "kind": "rumor_response",
        "label": "Rumor needs response",
        "description": (
            "Rumor rumor_out_of_band suggests late_signal. "
            "Decide whether to verify, ignore, or answer with a crew action."
        ),
        "crew_id": crew["crew_id"],
        "rumor_id": "rumor_out_of_band",
        "source_type": "manual.test",
        "source_id": "source_out_of_band",
        "pressure": "late_signal",
        "leak_vector": "manual",
        "action": "review_rumor",
    } in response.json()["pending_decisions"]
    assert "private_note" not in str(response.json()["pending_decisions"])


def test_inbox_and_crew_board_read_fresh_pending_decision_projection_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_PENDING_DECISION_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    original_read = client.app.state.projection_store.read_pending_decisions
    calls = {"count": 0}

    def tracked_read_pending_decisions(player_id: str, *, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_pending_decisions = (
        tracked_read_pending_decisions
    )

    inbox = client.get("/inbox", headers=auth(bela["token"]))
    crew_board = client.get(
        f"/crews/{moth['crew_id']}/board",
        headers=auth(bela["token"]),
    )

    assert proposed.status_code == 201
    assert inbox.status_code == 200
    assert crew_board.status_code == 200
    assert calls["count"] == 2
    assert any(
        decision["kind"] == "incoming_deal"
        and decision["deal_id"] == proposed.json()["deal_id"]
        for decision in inbox.json()["pending_decisions"]
    )
    assert crew_board.json()["pending_decisions"] == inbox.json()["pending_decisions"]


def test_inbox_projection_reads_share_request_freshness_check(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    monkeypatch.setenv("HOLLOW_LODGE_DEAL_PROJECTION_READS", "1")
    monkeypatch.setenv("HOLLOW_LODGE_PENDING_DECISION_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    original_diagnostics = client.app.state.projection_store.diagnostics
    diagnostics_calls = {"count": 0}

    def tracked_diagnostics(*, authoritative_last_sequence=None):
        diagnostics_calls["count"] += 1
        return original_diagnostics(
            authoritative_last_sequence=authoritative_last_sequence,
        )

    client.app.state.projection_store.diagnostics = tracked_diagnostics

    response = client.get("/inbox", headers=auth(bela["token"]))

    assert proposed.status_code == 201
    assert response.status_code == 200
    assert diagnostics_calls["count"] == 1
    assert response.json()["deals"] == [proposed.json()]
    assert any(
        decision["kind"] == "incoming_deal"
        and decision["deal_id"] == proposed.json()["deal_id"]
        for decision in response.json()["pending_decisions"]
    )
    assert {
        artifact["artifact_id"]
        for artifact in response.json()["visible_artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}


def test_pending_decision_projection_reads_fall_back_when_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_PENDING_DECISION_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    out_of_band_contract = STARTER_CONTRACT.model_copy(
        update={"contract_id": "contract_out_of_band", "title": "Out Of Band"}
    )
    client.app.state.event_store.append_command(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload=out_of_band_contract.model_dump(mode="json"),
        idempotency_key="out-of-band-contract",
    )

    def fail_if_projection_read(player_id: str, *, crew_ids=()):
        raise AssertionError("stale pending-decision projection should not be used")

    client.app.state.projection_store.read_pending_decisions = fail_if_projection_read

    inbox = client.get("/inbox", headers=auth(ada["token"]))
    crew_board = client.get(
        f"/crews/{crew['crew_id']}/board",
        headers=auth(ada["token"]),
    )

    assert inbox.status_code == 200
    assert crew_board.status_code == 200
    assert any(
        decision["kind"] == "contract_action"
        and decision["contract_id"] == "contract_out_of_band"
        for decision in inbox.json()["pending_decisions"]
    )
    assert any(
        decision["kind"] == "contract_action"
        and decision["contract_id"] == "contract_out_of_band"
        for decision in crew_board.json()["pending_decisions"]
    )


def test_projection_store_materializes_current_actions_without_command_metadata(
    tmp_path,
):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    submitted = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-ledger"),
        json={
            "crew_id": crew["crew_id"],
            "intent": "Inspect the ledger quietly.",
            "confirmed": True,
        },
    )
    edited = client.patch(
        f"/actions/{submitted.json()['action_id']}",
        headers=command_auth(ada["token"], "action-edit-ledger"),
        json={"intent": "Inspect the ledger and auction margin quietly."},
    )
    canceled = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-cancel"),
        json={
            "crew_id": crew["crew_id"],
            "intent": "Ask the auction clerk directly.",
            "confirmed": True,
        },
    )
    canceled_response = client.delete(
        f"/actions/{canceled.json()['action_id']}",
        headers=command_auth(ada["token"], "action-cancel"),
    )

    assert submitted.status_code == 201
    assert edited.status_code == 200
    assert canceled.status_code == 201
    assert canceled_response.status_code == 200

    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    actions = client.app.state.projection_store.read_current_actions_for_crew(
        crew["crew_id"]
    )
    diagnostics = client.app.state.projection_store.diagnostics()
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        rows = connection.execute(
            "select action_id, crew_id, status, payload_json from action_surface"
        ).fetchall()

    assert actions == [edited.json()]
    assert diagnostics["action_count"] == 1
    assert rows == [
        (
            edited.json()["action_id"],
            crew["crew_id"],
            "submitted",
            json.dumps(edited.json(), sort_keys=True, separators=(",", ":")),
        )
    ]
    serialized_rows = str(rows)
    assert "action-submit-ledger" not in serialized_rows
    assert "action-edit-ledger" not in serialized_rows
    assert canceled.json()["action_id"] not in serialized_rows


def test_inbox_and_crew_board_read_fresh_action_projection_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ACTION_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    submitted = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-submit-ledger"),
        json={
            "crew_id": crew["crew_id"],
            "intent": "Inspect the ledger quietly.",
            "confirmed": True,
        },
    )
    original_read = client.app.state.projection_store.read_current_actions_for_crew
    calls = {"count": 0}

    def tracked_read_current_actions_for_crew(crew_id: str):
        calls["count"] += 1
        return original_read(crew_id)

    client.app.state.projection_store.read_current_actions_for_crew = (
        tracked_read_current_actions_for_crew
    )
    client.app.state.action_service.current_actions_for_crew = (
        lambda crew_id: (_ for _ in ()).throw(
            AssertionError("fresh action projection should be used")
        )
    )

    inbox = client.get("/inbox", headers=auth(ada["token"]))
    crew_board = client.get(
        f"/crews/{crew['crew_id']}/board",
        headers=auth(ada["token"]),
    )

    assert submitted.status_code == 201
    assert inbox.status_code == 200
    assert crew_board.status_code == 200
    assert calls["count"] == 2
    assert any(
        decision["kind"] == "contract_action"
        and decision["action"] == "review_submitted_action"
        and decision["action_ids"] == [submitted.json()["action_id"]]
        for decision in inbox.json()["pending_decisions"]
    )
    assert any(
        decision["kind"] == "contract_action"
        and decision["action"] == "review_submitted_action"
        and decision["action_ids"] == [submitted.json()["action_id"]]
        for decision in crew_board.json()["pending_decisions"]
    )


def test_action_projection_reads_fall_back_when_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ACTION_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    action = {
        "action_id": "action_out_of_band",
        "status": "submitted",
        "actor_player_id": ada["player_id"],
        "crew_id": crew["crew_id"],
        "intent": "Inspect the ledger after the projection checkpoint.",
        "approach": "quiet",
        "risk_posture": "careful",
        "target": "ledger",
        "crew_noise_impact": 0,
    }
    client.app.state.event_store.append_command(
        event_type="action.submitted",
        actor_id=ada["player_id"],
        visibility=EventVisibility.crews([crew["crew_id"]]),
        payload={"confirmed": True, "action": action},
        idempotency_key="out-of-band-action",
    )

    def fail_if_projection_read(crew_id: str):
        raise AssertionError("stale action projection should not be used")

    client.app.state.projection_store.read_current_actions_for_crew = (
        fail_if_projection_read
    )

    inbox = client.get("/inbox", headers=auth(ada["token"]))
    crew_board = client.get(
        f"/crews/{crew['crew_id']}/board",
        headers=auth(ada["token"]),
    )

    assert inbox.status_code == 200
    assert crew_board.status_code == 200
    assert any(
        decision["kind"] == "contract_action"
        and decision["action"] == "review_submitted_action"
        and decision["action_ids"] == ["action_out_of_band"]
        for decision in inbox.json()["pending_decisions"]
    )
    assert any(
        decision["kind"] == "contract_action"
        and decision["action"] == "review_submitted_action"
        and decision["action_ids"] == ["action_out_of_band"]
        for decision in crew_board.json()["pending_decisions"]
    )


def test_contract_board_route_reads_fresh_projection_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    original_read = client.app.state.projection_store.read_contract_board
    calls = {"count": 0}

    def tracked_read_contract_board():
        calls["count"] += 1
        return original_read()

    client.app.state.projection_store.read_contract_board = tracked_read_contract_board

    response = client.get("/contracts", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert calls["count"] == 1
    assert response.json()["contracts"][0]["contract_id"] == "contract_false_finger"


def test_contract_board_route_reads_projection_when_global_flag_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_PROJECTION_READS", "1")
    monkeypatch.delenv("HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS", raising=False)
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    original_read = client.app.state.projection_store.read_contract_board
    calls = {"count": 0}

    def tracked_read_contract_board():
        calls["count"] += 1
        return original_read()

    client.app.state.projection_store.read_contract_board = tracked_read_contract_board

    response = client.get("/contracts", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert calls["count"] == 1
    assert response.json()["contracts"][0]["contract_id"] == "contract_false_finger"


def test_contract_board_route_falls_back_to_event_log_when_projection_is_stale(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    out_of_band_contract = STARTER_CONTRACT.model_copy(
        update={"contract_id": "contract_out_of_band", "title": "Out Of Band"}
    )
    client.app.state.event_store.append_command(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload=out_of_band_contract.model_dump(mode="json"),
        idempotency_key="out-of-band-contract",
    )

    def fail_if_projection_read():
        raise AssertionError("stale projection should not be used")

    client.app.state.projection_store.read_contract_board = fail_if_projection_read

    response = client.get("/contracts", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert {
        contract["contract_id"]
        for contract in response.json()["contracts"]
    } == {"contract_false_finger", "contract_out_of_band"}


def test_contract_activation_refreshes_projection_for_flagged_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    activated = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )
    original_read = client.app.state.projection_store.read_contract_board
    calls = {"count": 0}

    def tracked_read_contract_board():
        calls["count"] += 1
        return original_read()

    client.app.state.projection_store.read_contract_board = tracked_read_contract_board

    response = client.get("/contracts", headers=auth(ada["token"]))
    diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]

    assert activated.status_code == 201
    assert diagnostics["lag"] == 0
    assert diagnostics["contract_count"] == 2
    assert calls["count"] == 1
    assert {
        contract["contract_id"]
        for contract in response.json()["contracts"]
    } == {"contract_false_finger", "contract_ash_window"}


def test_contract_archive_refreshes_projection_for_flagged_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )
    archived = client.post(
        "/contracts/admin/contract_ash_window/archive",
        headers={
            "Idempotency-Key": "archive-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )
    original_read = client.app.state.projection_store.read_contract_board
    calls = {"count": 0}

    def tracked_read_contract_board():
        calls["count"] += 1
        return original_read()

    client.app.state.projection_store.read_contract_board = tracked_read_contract_board

    response = client.get("/contracts", headers=auth(ada["token"]))
    rendered = {
        contract["contract_id"]: contract
        for contract in response.json()["contracts"]
    }

    assert archived.status_code == 200
    assert calls["count"] == 1
    assert rendered["contract_ash_window"]["lifecycle_status"] == "archived"


def test_phase_resolution_refreshes_projection_for_flagged_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    linus = register(client, "b", "Linus")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, linus["token"], "crew-create-moth", "The Moth Choir")
    set_claim(client, ada, gilt, "claim-gilt", "The finger is likely a false relic.")
    submit_action(
        client,
        ada,
        gilt,
        "action-gilt",
        "Compare the red ledger date to the chapel timestamp for forged provenance.",
    )
    set_claim(client, linus, moth, "claim-moth", "The reliquary has occult resonance.")
    submit_action(
        client,
        linus,
        moth,
        "action-moth",
        "Watch the moth jar door omen near the auction room for occult resonance.",
    )
    locked = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock"),
        json={"hours_elapsed": 6},
    )
    original_read = client.app.state.projection_store.read_contract_board
    calls = {"count": 0}

    def tracked_read_contract_board():
        calls["count"] += 1
        return original_read()

    client.app.state.projection_store.read_contract_board = tracked_read_contract_board

    response = client.get("/contracts", headers=auth(ada["token"]))
    diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]
    rendered = {
        contract["contract_id"]: contract
        for contract in response.json()["contracts"]
    }

    assert locked.status_code == 200
    assert diagnostics["lag"] == 0
    assert calls["count"] == 1
    assert rendered["contract_false_finger"]["phase"]["status"] == "resolved"


def test_contract_mutation_still_succeeds_when_projection_refresh_fails(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))

    def fail_refresh(events):
        raise sqlite3.OperationalError("projection secret postgresql://user:secret@db")

    client.app.state.projection_store.rebuild = fail_refresh

    response = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )

    assert response.status_code == 201
    assert response.json()["contract_id"] == "contract_ash_window"
    diagnostics_response = client.get("/diagnostics")
    refresh = diagnostics_response.json()["data"]["projection_refresh"]
    assert refresh["status"] == "failed"
    assert refresh["last_context"] == "contracts"
    assert refresh["last_success_sequence"] == 5
    assert refresh["failure_count"] == 1
    assert refresh["last_failure"] == {
        "context": "contracts",
        "error_type": "OperationalError",
    }
    assert "secret" not in diagnostics_response.text


def test_crew_board_reads_fresh_projected_crew_summary_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_CREW_SUMMARY_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    joined = client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(grace["token"], "crew-join-grace"),
        json={"join_code": crew["join_code"]},
    )
    original_read = client.app.state.projection_store.read_crew_summary
    calls = {"count": 0}

    def tracked_read_crew_summary(crew_id: str):
        calls["count"] += 1
        return original_read(crew_id)

    client.app.state.projection_store.read_crew_summary = tracked_read_crew_summary
    client.app.state.crew_service.summary = (
        lambda crew_id: (_ for _ in ()).throw(
            AssertionError("fresh crew summary projection should be used")
        )
    )

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))
    diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]

    assert joined.status_code == 200
    assert response.status_code == 200
    assert diagnostics["lag"] == 0
    assert diagnostics["crew_count"] == 1
    assert calls["count"] == 1
    assert response.json()["crew"] == {
        "crew_id": crew["crew_id"],
        "name": "The Gilt Knives",
        "member_ids": ["player_0001", "player_0002"],
        "member_count": 2,
        "ready_for_full_contracts": False,
        "readiness_warning": (
            "Crews should have 3-5 players for full contracts; "
            "2-player starter slices are allowed."
        ),
    }
    assert "join_code" not in str(response.json()["crew"])


def test_crew_board_falls_back_when_projected_crew_summary_is_stale(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_CREW_SUMMARY_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    out_of_band_contract = STARTER_CONTRACT.model_copy(
        update={"contract_id": "contract_out_of_band", "title": "Out Of Band"}
    )
    client.app.state.event_store.append_command(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload=out_of_band_contract.model_dump(mode="json"),
        idempotency_key="out-of-band-contract",
    )

    def fail_if_projection_read(crew_id: str):
        raise AssertionError("stale crew summary projection should not be used")

    client.app.state.projection_store.read_crew_summary = fail_if_projection_read

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert response.json()["crew"]["crew_id"] == crew["crew_id"]
    assert response.json()["crew"]["member_ids"] == ["player_0001"]


def test_crew_creation_still_succeeds_when_projection_refresh_fails(
    tmp_path,
    monkeypatch,
):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    def fail_refresh(events):
        raise sqlite3.OperationalError("projection store unavailable")

    client.app.state.projection_store.rebuild = fail_refresh

    response = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "The Gilt Knives"


def test_projection_store_rebuilds_for_environment_configured_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("HOLLOW_LODGE_DATA_DIR", str(data_dir))

    client = TestClient(create_app())

    response = client.get("/diagnostics")

    projection = response.json()["data"]["projection_db"]
    assert projection["path"] == str(data_dir / "server-projections.sqlite3")
    assert projection["exists"] is True
    assert projection["status"] == "available"


def test_projection_store_materializes_public_contract_board_without_hidden_truth(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/diagnostics")

    assert response.status_code == 200
    projection = response.json()["data"]["projection_db"]
    assert projection["path"] == str(tmp_path / "server-projections.sqlite3")
    assert projection["exists"] is True
    assert projection["status"] == "available"
    assert projection["contract_count"] == 1
    assert projection["last_sequence"] > 0

    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        rows = connection.execute(
            "select contract_id, payload_json from contract_board order by contract_id"
        ).fetchall()

    assert len(rows) == 1
    assert rows[0][0] == "contract_false_finger"
    payload = json.loads(rows[0][1])
    assert payload["title"] == "The Saint's False Finger"
    assert "saint-bone forgery" not in rows[0][1]
    assert "hidden_truth" not in rows[0][1]


def test_projection_store_materializes_crew_summaries_without_join_codes(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    joined = client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(grace["token"], "crew-join-grace"),
        json={"join_code": crew["join_code"]},
    )

    assert joined.status_code == 200
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        rows = connection.execute(
            "select crew_id, member_count, payload_json from crew_summary"
        ).fetchall()

    assert rows == [
        (
            crew["crew_id"],
            2,
            (
                '{"crew_id":"crew_0001","member_count":2,'
                '"member_ids":["player_0001","player_0002"],'
                '"name":"The Gilt Knives",'
                '"readiness_warning":"Crews should have 3-5 players for full contracts; '
                '2-player starter slices are allowed.",'
                '"ready_for_full_contracts":false}'
            ),
        )
    ]
    assert "join_code" not in rows[0][2]
    assert crew["join_code"] not in rows[0][2]
    assert client.app.state.projection_store.read_crew_summary(crew["crew_id"]) == (
        crew_summaries_from_events(client.app.state.event_store.read())[crew["crew_id"]]
    )


def test_artifact_route_reads_fresh_projected_visible_artifacts_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    original_read = client.app.state.projection_store.read_visible_artifacts
    calls = {"count": 0}

    def tracked_read_visible_artifacts(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_artifacts = tracked_read_visible_artifacts
    client.app.state.artifact_service.visible_artifacts_for_player = (
        lambda player_id, crew_ids=(): (_ for _ in ()).throw(
            AssertionError("fresh artifact projection should be used")
        )
    )

    response = client.get("/artifacts", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert calls["count"] == 1
    assert {
        artifact["artifact_id"]
        for artifact in response.json()["artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}
    assert response.json()["edges"] == [
        {
            "source_id": "artifact_lot_card",
            "target_id": "artifact_ledger_rubric",
            "relation": "contradicts",
            "public_summary": "The public lot card and copied ledger disagree on custody.",
        }
    ]
    assert "full_text" not in response.text
    assert "hidden_flags" not in response.text
    assert "ink-after-binding" not in response.text


def test_artifact_route_falls_back_when_projection_is_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    out_of_band_contract = STARTER_CONTRACT.model_copy(
        update={"contract_id": "contract_out_of_band", "title": "Out Of Band"}
    )
    client.app.state.event_store.append_command(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload=out_of_band_contract.model_dump(mode="json"),
        idempotency_key="out-of-band-contract",
    )

    def fail_if_projection_read(player_id: str, crew_ids=()):
        raise AssertionError("stale artifact projection should not be used")

    client.app.state.projection_store.read_visible_artifacts = fail_if_projection_read

    response = client.get("/artifacts", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert {
        artifact["artifact_id"]
        for artifact in response.json()["artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}


def test_artifact_projection_reads_player_and_crew_scoped_surfaces(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(grace["token"], "crew-join-grace"),
        json={"join_code": crew["join_code"]},
    )
    client.app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[crew["crew_id"]],
        reason="projection test",
        idempotency_key="grant-chapel-to-crew",
    )
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    client.app.state.artifact_service.visible_artifacts_for_player = (
        lambda player_id, crew_ids=(): (_ for _ in ()).throw(
            AssertionError("fresh scoped artifact projection should be used")
        )
    )

    ada_response = client.get("/artifacts", headers=auth(ada["token"]))
    grace_response = client.get("/artifacts", headers=auth(grace["token"]))

    assert ada_response.status_code == 200
    assert grace_response.status_code == 200
    assert "artifact_chapel_debt_mark" in {
        artifact["artifact_id"]
        for artifact in ada_response.json()["artifacts"]
    }
    assert "artifact_chapel_debt_mark" in {
        artifact["artifact_id"]
        for artifact in grace_response.json()["artifacts"]
    }
    assert "full_text" not in ada_response.text
    assert "hidden_flags" not in ada_response.text


def test_artifact_transfer_refreshes_projection_for_flagged_reads(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")

    transferred = client.post(
        "/artifacts/artifact_lot_card/transfer",
        headers=command_auth(ada["token"], "transfer-lot-card"),
        json={"recipient_player_id": grace["player_id"]},
    )
    original_read = client.app.state.projection_store.read_visible_artifacts
    calls = {"count": 0}

    def tracked_read_visible_artifacts(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_artifacts = tracked_read_visible_artifacts
    client.app.state.artifact_service.visible_artifacts_for_player = (
        lambda player_id, crew_ids=(): (_ for _ in ()).throw(
            AssertionError("fresh artifact projection should be used after transfer")
        )
    )

    response = client.get("/artifacts", headers=auth(grace["token"]))
    copy_ids = [
        artifact["artifact_id"]
        for artifact in response.json()["artifacts"]
        if artifact.get("is_copy")
    ]

    assert transferred.status_code == 201
    assert response.status_code == 200
    assert calls["count"] == 1
    assert copy_ids == ["artifact_lot_card.copy.player_0002.1"]


def test_contract_board_embeds_projected_visible_artifacts_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    original_read = client.app.state.projection_store.read_visible_artifacts
    calls = {"count": 0}

    def tracked_read_visible_artifacts(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_artifacts = tracked_read_visible_artifacts
    client.app.state.artifact_service.visible_artifacts_for_player = (
        lambda player_id, crew_ids=(): (_ for _ in ()).throw(
            AssertionError("contract board should use fresh artifact projection")
        )
    )

    response = client.get("/contracts", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert calls["count"] == 1
    assert {
        artifact["artifact_id"]
        for artifact in response.json()["visible_artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}


def test_inbox_embeds_projected_visible_artifacts_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    original_read = client.app.state.projection_store.read_visible_artifacts
    calls = {"count": 0}

    def tracked_read_visible_artifacts(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_artifacts = tracked_read_visible_artifacts
    client.app.state.artifact_service.visible_artifacts_for_player = (
        lambda player_id, crew_ids=(): (_ for _ in ()).throw(
            AssertionError("inbox should use fresh artifact projection")
        )
    )

    response = client.get("/inbox", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert calls["count"] == 1
    assert {
        artifact["artifact_id"]
        for artifact in response.json()["visible_artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}


def test_crew_board_embeds_projected_visible_artifacts_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    original_read = client.app.state.projection_store.read_visible_artifacts
    calls = {"count": 0}

    def tracked_read_visible_artifacts(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_artifacts = tracked_read_visible_artifacts
    client.app.state.artifact_service.visible_artifacts_for_player = (
        lambda player_id, crew_ids=(): (_ for _ in ()).throw(
            AssertionError("crew board should use fresh artifact projection")
        )
    )

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert calls["count"] == 1
    assert {
        artifact["artifact_id"]
        for artifact in response.json()["visible_artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}


def test_embedded_visible_artifacts_fall_back_when_projection_is_stale(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ARTIFACT_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    out_of_band_contract = STARTER_CONTRACT.model_copy(
        update={"contract_id": "contract_out_of_band", "title": "Out Of Band"}
    )
    client.app.state.event_store.append_command(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload=out_of_band_contract.model_dump(mode="json"),
        idempotency_key="out-of-band-contract",
    )

    def fail_if_projection_read(player_id: str, crew_ids=()):
        raise AssertionError("stale embedded artifact projection should not be used")

    client.app.state.projection_store.read_visible_artifacts = fail_if_projection_read

    response = client.get("/contracts", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert {
        artifact["artifact_id"]
        for artifact in response.json()["visible_artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}


def test_deal_route_reads_fresh_projected_visible_deals_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_DEAL_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    ash = create_crew(client, caro["token"], "crew-create-ash", "The Ash Keys")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    original_read = client.app.state.projection_store.read_visible_deals
    calls = {"count": 0}

    def tracked_read_visible_deals(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_deals = tracked_read_visible_deals
    client.app.state.deal_service.list_for_player = (
        lambda player_id: (_ for _ in ()).throw(
            AssertionError("fresh deal projection should be used")
        )
    )

    participant = client.get("/deals", headers=auth(bela["token"]))
    bystander = client.get("/deals", headers=auth(caro["token"]))
    diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]

    assert proposed.status_code == 201
    assert participant.status_code == 200
    assert bystander.status_code == 200
    assert diagnostics["lag"] == 0
    assert diagnostics["deal_count"] == 1
    assert calls["count"] == 2
    assert participant.json()["deals"] == [proposed.json()]
    assert bystander.json()["deals"] == []
    assert "Do not cite us." not in str(bystander.json())
    assert ash["crew_id"] not in {
        deal["proposer_crew_id"] for deal in participant.json()["deals"]
    }


def test_deal_route_falls_back_when_projection_is_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_DEAL_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    out_of_band_contract = STARTER_CONTRACT.model_copy(
        update={"contract_id": "contract_out_of_band", "title": "Out Of Band"}
    )
    client.app.state.event_store.append_command(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload=out_of_band_contract.model_dump(mode="json"),
        idempotency_key="out-of-band-contract",
    )

    def fail_if_projection_read(player_id: str, crew_ids=()):
        raise AssertionError("stale deal projection should not be used")

    client.app.state.projection_store.read_visible_deals = fail_if_projection_read

    response = client.get("/deals", headers=auth(bela["token"]))

    assert proposed.status_code == 201
    assert response.status_code == 200
    assert response.json()["deals"] == [proposed.json()]


def test_deal_accept_refreshes_projection_for_flagged_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_DEAL_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    client.app.state.artifact_service.grant_artifact_access(
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
    accepted = client.post(
        f"/deals/{proposed['deal_id']}/accept",
        headers=command_auth(bela["token"], "deal-accept"),
    )
    original_read = client.app.state.projection_store.read_visible_deals
    calls = {"count": 0}

    def tracked_read_visible_deals(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_deals = tracked_read_visible_deals
    client.app.state.deal_service.list_for_player = (
        lambda player_id: (_ for _ in ()).throw(
            AssertionError("fresh deal projection should be used after accept")
        )
    )

    response = client.get("/deals", headers=auth(ada["token"]))
    diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]

    assert accepted.status_code == 200
    assert accepted.json()["status"] == "fulfilled"
    assert response.status_code == 200
    assert diagnostics["lag"] == 0
    assert diagnostics["deal_count"] == 1
    assert calls["count"] == 1
    assert response.json()["deals"][0]["status"] == "fulfilled"
    assert response.json()["deals"][0]["proposer_received_artifact_ids"] == (
        accepted.json()["proposer_received_artifact_ids"]
    )
    assert response.json()["deals"][0]["recipient_received_artifact_ids"] == (
        accepted.json()["recipient_received_artifact_ids"]
    )


def test_inbox_embeds_projected_visible_deals_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_DEAL_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    ash = create_crew(client, caro["token"], "crew-create-ash", "The Ash Keys")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    original_read = client.app.state.projection_store.read_visible_deals
    calls = {"count": 0}

    def tracked_read_visible_deals(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_deals = tracked_read_visible_deals
    client.app.state.deal_service.list_for_player = (
        lambda player_id: (_ for _ in ()).throw(
            AssertionError("inbox should use fresh deal projection")
        )
    )

    participant = client.get("/inbox", headers=auth(bela["token"]))
    bystander = client.get("/inbox", headers=auth(caro["token"]))

    assert proposed.status_code == 201
    assert participant.status_code == 200
    assert bystander.status_code == 200
    assert calls["count"] >= 2
    assert participant.json()["deals"] == [proposed.json()]
    assert bystander.json()["deals"] == []
    assert "Do not cite us." not in str(bystander.json())
    assert ash["crew_id"] not in {
        deal["proposer_crew_id"] for deal in participant.json()["deals"]
    }


def test_crew_board_embeds_projected_visible_deals_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_DEAL_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    ash = create_crew(client, caro["token"], "crew-create-ash", "The Ash Keys")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    original_read = client.app.state.projection_store.read_visible_deals
    calls = {"count": 0}

    def tracked_read_visible_deals(player_id: str, crew_ids=()):
        calls["count"] += 1
        return original_read(player_id, crew_ids=crew_ids)

    client.app.state.projection_store.read_visible_deals = tracked_read_visible_deals
    client.app.state.deal_service.list_for_player = (
        lambda player_id: (_ for _ in ()).throw(
            AssertionError("crew board should use fresh deal projection")
        )
    )

    participant = client.get(f"/crews/{moth['crew_id']}/board", headers=auth(bela["token"]))
    bystander = client.get(f"/crews/{ash['crew_id']}/board", headers=auth(caro["token"]))

    assert proposed.status_code == 201
    assert participant.status_code == 200
    assert bystander.status_code == 200
    assert calls["count"] >= 2
    assert participant.json()["deals"] == [proposed.json()]
    assert bystander.json()["deals"] == []
    assert "Do not cite us." not in str(bystander.json())


def test_embedded_visible_deals_fall_back_when_projection_is_stale(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_DEAL_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    out_of_band_contract = STARTER_CONTRACT.model_copy(
        update={"contract_id": "contract_out_of_band", "title": "Out Of Band"}
    )
    client.app.state.event_store.append_command(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload=out_of_band_contract.model_dump(mode="json"),
        idempotency_key="out-of-band-contract",
    )

    def fail_if_projection_read(player_id: str, crew_ids=()):
        raise AssertionError("stale embedded deal projection should not be used")

    client.app.state.projection_store.read_visible_deals = fail_if_projection_read

    inbox = client.get("/inbox", headers=auth(bela["token"]))
    crew_board = client.get(f"/crews/{moth['crew_id']}/board", headers=auth(bela["token"]))

    assert proposed.status_code == 201
    assert inbox.status_code == 200
    assert crew_board.status_code == 200
    assert inbox.json()["deals"] == [proposed.json()]
    assert crew_board.json()["deals"] == [proposed.json()]


def test_projection_store_materializes_visible_deals_without_bystander_terms(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    ash = create_crew(client, caro["token"], "crew-create-ash", "The Ash Keys")
    proposed = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )

    participant = client.app.state.projection_store.read_visible_deals(
        bela["player_id"],
        crew_ids=[moth["crew_id"]],
    )
    bystander = client.app.state.projection_store.read_visible_deals(
        caro["player_id"],
        crew_ids=[ash["crew_id"]],
    )
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        rows = connection.execute(
            "select deal_id, proposer_crew_id, recipient_crew_id, payload_json "
            "from deal_surface order by deal_id"
        ).fetchall()

    assert proposed.status_code == 201
    assert participant == [proposed.json()]
    assert bystander == []
    assert rows == [
        (
            proposed.json()["deal_id"],
            gilt["crew_id"],
            moth["crew_id"],
            json.dumps(proposed.json(), sort_keys=True, separators=(",", ":")),
        )
    ]
    assert "Do not cite us." not in str(bystander)
    assert client.app.state.projection_store.read_visible_deals(
        ada["player_id"],
        crew_ids=[gilt["crew_id"]],
    ) == deal_rows_from_events(client.app.state.event_store.read())


def test_crew_board_reads_fresh_projected_crew_legacy_when_enabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("HOLLOW_LODGE_CREW_LEGACY_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    activated = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    action = submit_action(
        client,
        ada,
        crew,
        "action-ledger",
        "Inspect the red ledger timestamp for forged provenance.",
    )
    claim = set_claim(
        client,
        ada,
        crew,
        "claim-ledger",
        "The finger is a false relic with forged provenance.",
    )
    resolved = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock"),
        json={"hours_elapsed": 6},
    )
    original_read = client.app.state.projection_store.read_crew_legacy
    calls = {"count": 0}

    def tracked_read_crew_legacy(crew_id: str):
        calls["count"] += 1
        return original_read(crew_id)

    client.app.state.projection_store.read_crew_legacy = tracked_read_crew_legacy
    monkeypatch.setattr(
        routes_crews,
        "crew_legacy_from_contracts",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("fresh crew legacy projection should be used")
        ),
    )

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))
    diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]
    body = response.json()
    future = {
        opportunity["contract_id"]: opportunity
        for opportunity in body["legacy"]["future_opportunities"]
    }
    ash = {
        contract["contract_id"]: contract
        for contract in body["active_contracts"]
    }["contract_ash_window"]

    assert activated.status_code == 201
    assert action["status"] == "submitted"
    assert claim["claim"] == "The finger is a false relic with forged provenance."
    assert resolved.status_code == 200
    assert response.status_code == 200
    assert diagnostics["lag"] == 0
    assert diagnostics["crew_legacy_count"] == 1
    assert calls["count"] == 1
    assert body["legacy"]["reputation"] == 2
    assert body["legacy"]["heat"] == 1
    assert body["legacy"]["completed_contracts"] == [
        {
            "contract_id": "contract_false_finger",
            "title": "The Saint's False Finger",
            "phase": "Auction Preview",
            "standing": "Strong lead",
            "score": 70,
            "outcome": "strong_lead",
        }
    ]
    assert ash["crew_modifiers"] == future["contract_ash_window"]["modifiers"]


def test_crew_board_falls_back_when_projected_crew_legacy_is_stale(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_CREW_LEGACY_PROJECTION_READS", "1")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    out_of_band_contract = STARTER_CONTRACT.model_copy(
        update={"contract_id": "contract_out_of_band", "title": "Out Of Band"}
    )
    client.app.state.event_store.append_command(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload=out_of_band_contract.model_dump(mode="json"),
        idempotency_key="out-of-band-contract",
    )

    def fail_if_projection_read(crew_id: str):
        raise AssertionError("stale crew legacy projection should not be used")

    client.app.state.projection_store.read_crew_legacy = fail_if_projection_read

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert response.status_code == 200
    assert response.json()["legacy"]["crew_id"] == crew["crew_id"]
    assert response.json()["legacy"]["reputation"] == 0


def test_projection_store_materializes_crew_legacy_without_private_deal_terms(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    client.app.state.artifact_service.grant_artifact_access(
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
    accepted = client.post(
        f"/deals/{proposed.json()['deal_id']}/accept",
        headers=command_auth(bela["token"], "deal-accept"),
    )

    legacy = client.app.state.projection_store.read_crew_legacy(gilt["crew_id"])
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        rows = connection.execute(
            "select crew_id, payload_json from crew_legacy order by crew_id"
        ).fetchall()

    assert proposed.status_code == 201
    assert accepted.status_code == 200
    assert legacy["deal_conduct"] == {
        "score": 2,
        "fulfilled_count": 1,
        "canceled_count": 0,
        "declined_count": 0,
        "open_count": 0,
        "reliability": "reliable_escrow_partner",
    }
    assert any(row[0] == gilt["crew_id"] for row in rows)
    stored_text = "\n".join(row[1] for row in rows)
    assert "artifact_chapel_debt_mark" not in stored_text
    assert "artifact_ledger_rubric" not in stored_text
    assert "Do not cite us." not in stored_text


def test_projection_store_materializes_visible_artifacts_without_hidden_fields(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    projected = client.app.state.projection_store.read_visible_artifacts(
        ada["player_id"],
        crew_ids=(),
    )
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        public_rows = connection.execute(
            "select artifact_id, payload_json from artifact_surface order by artifact_id"
        ).fetchall()

    assert {
        artifact["artifact_id"]
        for artifact in projected["artifacts"]
    } == {"artifact_lot_card", "artifact_ledger_rubric"}
    assert [row[0] for row in public_rows] == [
        "artifact_ledger_rubric",
        "artifact_lot_card",
    ]
    stored_text = "\n".join(row[1] for row in public_rows)
    assert "full_text" not in stored_text
    assert "hidden_flags" not in stored_text
    assert "ink-after-binding" not in stored_text
    assert "saint-bone forgery" not in stored_text


def test_projection_store_allows_same_scoped_artifact_for_multiple_crews(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, bela["token"], "crew-create-moth", "The Moth Choir")
    for crew, key in ((gilt, "grant-gilt"), (moth, "grant-moth")):
        client.app.state.artifact_service.grant_artifact_access(
            artifact_id="artifact_chapel_debt_mark",
            actor_id="server",
            player_ids=[],
            crew_ids=[crew["crew_id"]],
            reason="projection duplicate scope test",
            idempotency_key=key,
        )

    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    gilt_projected = client.app.state.projection_store.read_visible_artifacts(
        ada["player_id"],
        crew_ids=[gilt["crew_id"]],
    )
    moth_projected = client.app.state.projection_store.read_visible_artifacts(
        bela["player_id"],
        crew_ids=[moth["crew_id"]],
    )
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        scoped_rows = connection.execute(
            """
            select artifact_id, visibility_json
            from artifact_scoped_surface
            order by artifact_id, scope_key
            """
        ).fetchall()

    assert [row[0] for row in scoped_rows] == [
        "artifact_chapel_debt_mark",
        "artifact_chapel_debt_mark",
    ]
    assert "artifact_chapel_debt_mark" in {
        artifact["artifact_id"] for artifact in gilt_projected["artifacts"]
    }
    assert "artifact_chapel_debt_mark" in {
        artifact["artifact_id"] for artifact in moth_projected["artifacts"]
    }


def test_projection_store_rebuilds_after_new_public_contract_event(tmp_path, monkeypatch):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    out_of_band_contract = STARTER_CONTRACT.model_copy(
        update={"contract_id": "contract_out_of_band", "title": "Out Of Band"}
    )
    client.app.state.event_store.append_command(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload=out_of_band_contract.model_dump(mode="json"),
        idempotency_key="out-of-band-contract",
    )

    stale_response = client.get("/diagnostics")
    client.app.state.projection_store.rebuild(client.app.state.event_store.read())
    response = client.get("/diagnostics")

    stale_projection = stale_response.json()["data"]["projection_db"]
    assert stale_projection["status"] == "stale"
    assert stale_projection["contract_count"] == 1
    assert stale_projection["lag"] > 0
    projection = response.json()["data"]["projection_db"]
    assert projection["status"] == "available"
    assert projection["contract_count"] == 2
    assert projection["lag"] == 0
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        contract_ids = [
            row[0]
            for row in connection.execute(
                "select contract_id from contract_board order by contract_id"
            ).fetchall()
        ]
        meta_rows = dict(
            connection.execute("select key, value from projection_meta").fetchall()
        )

    assert contract_ids == ["contract_false_finger", "contract_out_of_band"]
    assert int(meta_rows["last_sequence"]) == projection["last_sequence"]
    assert client.app.state.projection_store.read_contract_board() == (
        contract_board_from_events(client.app.state.event_store.read())
    )


def test_projection_diagnostics_does_not_mutate_stale_projection(tmp_path, monkeypatch):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    initial = client.get("/diagnostics").json()["data"]["projection_db"]
    out_of_band_contract = STARTER_CONTRACT.model_copy(
        update={"contract_id": "contract_out_of_band", "title": "Out Of Band"}
    )
    client.app.state.event_store.append_command(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload=out_of_band_contract.model_dump(mode="json"),
        idempotency_key="out-of-band-contract",
    )
    first_diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]
    second_diagnostics = client.get("/diagnostics").json()["data"]["projection_db"]
    with sqlite3.connect(tmp_path / "server-projections.sqlite3") as connection:
        contract_count = connection.execute(
            "select count(*) from contract_board"
        ).fetchone()[0]

    assert initial["lag"] == 0
    assert first_diagnostics["status"] == "stale"
    assert first_diagnostics["contract_count"] == 1
    assert first_diagnostics == second_diagnostics
    assert contract_count == 1
