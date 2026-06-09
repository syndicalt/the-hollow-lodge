from fastapi.testclient import TestClient

from hollow_lodge.client.local_log import LocalEventLog
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


def create_crew(client: TestClient, token: str, key: str, name: str) -> dict:
    response = client.post(
        "/crews",
        headers=command_auth(token, key),
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()


def test_saints_and_ledgers_auction_preview_vertical_slice(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["moth", "gilt"]))
    moth_player = register(client, "moth", "Mira")
    gilt_player = register(client, "gilt", "Ada")
    moth = create_crew(client, moth_player["token"], "crew-create-moth", "The Moth Choir")
    gilt = create_crew(client, gilt_player["token"], "crew-create-gilt", "The Gilt Knives")

    board = client.get("/contracts", headers=auth(gilt_player["token"])).json()
    assert board["campaign"]["title"] == "Saints & Ledgers"
    assert board["contracts"][0]["title"] == "The Saint's False Finger"
    assert board["contracts"][0]["phase"]["name"] == "Auction Preview"
    assert "truth_false_finger_forgery" not in str(board)

    transfer = client.post(
        "/proofs/fragments/fragment_starter_ledger/transfer",
        headers=command_auth(moth_player["token"], "transfer-ledger-to-gilt"),
        json={"recipient_player_id": gilt_player["player_id"]},
    )
    assert transfer.status_code == 201
    copied_fragment_id = transfer.json()["fragment_id"]

    provenance = client.post(
        f"/proofs/fragments/{copied_fragment_id}/check/provenance",
        headers=command_auth(gilt_player["token"], "gilt-check-ledger"),
    )
    assert provenance.status_code == 201
    assert provenance.json()["provenance_flags"] == ["copied-hand", "ink-after-binding"]

    offer = client.post(
        "/chat/crew-to-crew",
        headers=command_auth(moth_player["token"], "moth-offer"),
        json={
            "sender_crew_id": moth["crew_id"],
            "recipient_crew_id": gilt["crew_id"],
            "body": "Trade quiet access for no public claims until the auction locks.",
        },
    )
    assert offer.status_code == 201

    gilt_log = LocalEventLog(tmp_path / "gilt-local.jsonl")
    deal_draft = gilt_log.append_local_note(
        note_type="handler.deal_draft",
        payload={
            "source_message_id": offer.json()["message_id"],
            "terms": "Moth offers quiet access for silence until lock.",
            "binding": False,
        },
    )
    assert deal_draft["origin"] == "local"
    assert "handler.deal_draft" not in client.get("/events", headers=auth(gilt_player["token"])).text

    gilt_action = client.post(
        "/actions",
        headers=command_auth(gilt_player["token"], "gilt-action"),
        json={
            "crew_id": gilt["crew_id"],
            "intent": "Quietly compare the red ledger date to the chapel timestamp for forged provenance.",
            "confirmed": True,
        },
    )
    moth_action = client.post(
        "/actions",
        headers=command_auth(moth_player["token"], "moth-action"),
        json={
            "crew_id": moth["crew_id"],
            "intent": "Observe the moth jar door omen near the auction room for occult resonance.",
            "confirmed": True,
        },
    )
    assert gilt_action.status_code == 201
    assert moth_action.status_code == 201

    gilt_claim = client.patch(
        f"/proofs/dossiers/{gilt['crew_id']}/framing",
        headers=command_auth(gilt_player["token"], "gilt-claim"),
        json={
            "claim": "The finger is likely a false relic.",
            "evidence_ids": [copied_fragment_id],
            "reasoning": "The copied ledger hand and ink timing undercut the chapel provenance.",
            "weaknesses": "No material confirmation yet.",
            "provenance_concerns": "Copied hand; ink after binding.",
        },
    )
    moth_claim = client.patch(
        f"/proofs/dossiers/{moth['crew_id']}/framing",
        headers=command_auth(moth_player["token"], "moth-claim"),
        json={
            "claim": "The reliquary has occult resonance.",
            "reasoning": "The moth jar door omen repeats near the auction room.",
            "weaknesses": "The omen is not corroborated.",
            "provenance_concerns": "Ledger chain is contaminated.",
        },
    )
    assert gilt_claim.status_code == 200
    assert moth_claim.status_code == 200

    reveal = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(gilt_player["token"], "phase-lock"),
        json={"hours_elapsed": 6},
    )
    assert reveal.status_code == 200
    standings = reveal.json()["standings"]
    assert standings[0]["crew_id"] == gilt["crew_id"]
    assert standings[0]["standing"] == "Strong lead"
    assert "clean provenance contradiction" in standings[0]["strengths"]
    assert standings[1]["crew_id"] == moth["crew_id"]
    assert standings[1]["standing"] == "Weak"
    assert standings[1]["strengths"] == []
    assert "truth_false_finger_forgery" not in str(reveal.json())

    moth_log = LocalEventLog(tmp_path / "moth-local.jsonl")
    gilt_visible_events = client.get("/events", headers=auth(gilt_player["token"])).json()["events"]
    moth_visible_events = client.get("/events", headers=auth(moth_player["token"])).json()["events"]
    gilt_synced = gilt_log.sync_visible_server_events(gilt_visible_events)
    moth_synced = moth_log.sync_visible_server_events(moth_visible_events)
    assert gilt_synced > 0
    assert moth_synced > 0
    assert _server_event_ids(gilt_log) == {event["event_id"] for event in gilt_visible_events}
    assert _server_event_ids(moth_log) == {event["event_id"] for event in moth_visible_events}
    assert offer.json()["message_id"] in str(gilt_log.read())
    assert offer.json()["message_id"] in str(moth_log.read())
    assert "truth_false_finger_forgery" not in str(gilt_log.read())
    assert "truth_false_finger_forgery" not in str(moth_log.read())

    gilt_replay = "\n".join(gilt_log.render_replay(since_sequence=0))
    moth_replay = "\n".join(moth_log.render_replay(since_sequence=0))
    assert "proof fragment" in gilt_replay
    assert "provenance" in gilt_replay
    assert "phase result" in gilt_replay
    assert "Trade quiet access" in moth_replay


def _server_event_ids(log: LocalEventLog) -> set[str]:
    return {
        event["event_id"]
        for event in log.read()
        if event.get("origin") == "server"
    }
