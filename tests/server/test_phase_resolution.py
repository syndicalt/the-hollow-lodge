from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app
from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.server.services import ContractService
from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle


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


def setup_two_crews(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    linus = register(client, "b", "Linus")
    gilt = create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = create_crew(client, linus["token"], "crew-create-moth", "The Moth Choir")
    return client, ada, linus, gilt, moth


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


def lock_preview(client: TestClient, player: dict, key: str, hours_elapsed: int = 6):
    return client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(player["token"], key),
        json={"hours_elapsed": hours_elapsed},
    )


def test_auction_preview_reveal_scores_crews_without_hidden_truth_leak(tmp_path):
    client, ada, linus, gilt, moth = setup_two_crews(tmp_path)
    set_claim(client, ada, gilt, "claim-gilt", "The finger is likely a false relic.")
    submit_action(
        client,
        ada,
        gilt,
        "action-gilt",
        "Quietly compare the red ledger date to the chapel timestamp for forged provenance.",
    )
    set_claim(client, linus, moth, "claim-moth", "The reliquary has occult resonance.")
    submit_action(
        client,
        linus,
        moth,
        "action-moth",
        "Observe the moth jar door omen near the auction room for occult resonance.",
    )

    response = lock_preview(client, ada, "phase-lock-1")

    assert response.status_code == 200
    reveal = response.json()
    standings = reveal["standings"]
    assert standings[0]["crew_id"] == gilt["crew_id"]
    assert standings[0]["standing"] == "Strong lead"
    assert standings[1]["crew_id"] == moth["crew_id"]
    assert standings[1]["standing"] == "Viable but unstable"
    assert "clean provenance contradiction" in standings[0]["strengths"]
    assert "occult clue may unlock alternate lane" in standings[1]["strengths"]
    assert "saint-bone forgery" not in str(reveal)
    assert "real debtor's omen" not in str(reveal)


def test_phase_lock_replay_and_duplicate_lock_do_not_append_duplicate_reveals(tmp_path):
    client, ada, _, gilt, _ = setup_two_crews(tmp_path)
    submit_action(client, ada, gilt, "action-gilt", "Inspect the ledger for forged provenance.")

    first = lock_preview(client, ada, "phase-lock-1")
    replay = lock_preview(client, ada, "phase-lock-1")
    duplicate = lock_preview(client, ada, "phase-lock-2")
    events = client.get("/events", headers=auth(ada["token"])).json()["events"]

    assert first.status_code == 200
    assert replay.status_code == 200
    assert duplicate.status_code == 200
    assert replay.json() == first.json()
    assert duplicate.json() == first.json()
    assert [event["type"] for event in events].count("contract.phase.resolved") == 1
    assert [event["type"] for event in events].count("contract.phase.locked") == 1
    assert "truth_false_finger_forgery" not in str(events)
    assert "saint-bone forgery" not in str(events)


def test_phase_resolution_records_server_only_oracle_audit_events(tmp_path):
    client, ada, linus, gilt, moth = setup_two_crews(tmp_path)
    submit_action(client, ada, gilt, "action-gilt", "Inspect the ledger for forged provenance.")
    submit_action(client, linus, moth, "action-moth", "Observe the moth jar door omen.")

    response = lock_preview(client, ada, "phase-lock-1")
    events = client.app.state.event_store.read()

    requested = [event for event in events if event.type == "oracle.resolution.requested"]
    completed = [event for event in events if event.type == "oracle.resolution.completed"]

    assert response.status_code == 200
    assert requested
    assert completed
    assert requested[0].visibility == EventVisibility.server_only()
    assert completed[0].visibility == EventVisibility.server_only()
    assert completed[0].payload["provider"] == "deterministic"
    assert completed[0].payload["fallback"] is False


def test_actions_can_be_canceled_before_lock_and_cannot_mutate_after_lock(tmp_path):
    client, ada, _, gilt, _ = setup_two_crews(tmp_path)
    submitted = submit_action(client, ada, gilt, "action-gilt", "Inspect the ledger.")
    canceled = client.delete(
        f"/actions/{submitted['action_id']}",
        headers=command_auth(ada["token"], "cancel-gilt"),
    )
    locked = lock_preview(client, ada, "phase-lock-1")
    late_submit = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-late"),
        json={"crew_id": gilt["crew_id"], "intent": "Submit at lock.", "confirmed": True},
    )
    late_cancel = client.delete(
        f"/actions/{submitted['action_id']}",
        headers=command_auth(ada["token"], "cancel-late"),
    )

    assert canceled.status_code == 200
    assert locked.status_code == 200
    assert late_submit.status_code == 409
    assert late_cancel.status_code == 409
    assert submitted["action_id"] not in locked.text


def test_pre_lock_edit_replay_survives_phase_lock(tmp_path):
    client, ada, _, gilt, _ = setup_two_crews(tmp_path)
    submitted = submit_action(client, ada, gilt, "action-gilt", "Inspect the ledger.")
    first_edit = client.patch(
        f"/actions/{submitted['action_id']}",
        headers=command_auth(ada["token"], "edit-gilt"),
        json={"intent": "Inspect the ledger for forged provenance."},
    )
    locked = lock_preview(client, ada, "phase-lock-1")
    replay_edit = client.patch(
        f"/actions/{submitted['action_id']}",
        headers=command_auth(ada["token"], "edit-gilt"),
        json={"intent": "Inspect the ledger for forged provenance."},
    )

    assert first_edit.status_code == 200
    assert locked.status_code == 200
    assert replay_edit.status_code == 200
    assert replay_edit.json() == first_edit.json()


def test_resolved_board_survives_restart_without_hidden_truth(tmp_path):
    client, ada, _, gilt, _ = setup_two_crews(tmp_path)
    submit_action(client, ada, gilt, "action-gilt", "Inspect the ledger for forged provenance.")
    lock_preview(client, ada, "phase-lock-1")

    restarted = TestClient(create_app(data_dir=tmp_path, invite_codes=[]))
    board = restarted.get("/contracts", headers=auth(ada["token"]))
    inbox = restarted.get("/inbox", headers=auth(ada["token"]))

    assert board.status_code == 200
    assert inbox.status_code == 200
    assert board.json()["contracts"][0]["phase"]["status"] == "resolved"
    assert board.json()["contracts"][0]["phase_result"]["standings"][0]["standing"] in {
        "Strong lead",
        "Viable",
    }
    assert "truth_false_finger_forgery" not in str(board.json())
    assert "saint-bone forgery" not in str(inbox.json())


def test_locked_only_phase_state_projects_and_recovers_to_resolution(tmp_path):
    client, ada, _, _, _ = setup_two_crews(tmp_path)
    client.app.state.event_store.append_command(
        event_type="contract.phase.locked",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload={
            "contract_id": "contract_false_finger",
            "phase": "Auction Preview",
            "hours_elapsed": 6,
        },
        idempotency_key="phase-lock.contract_false_finger.auction-preview",
    )

    locked_board = client.get("/contracts", headers=auth(ada["token"]))
    recovered = lock_preview(client, ada, "phase-lock-recover", hours_elapsed=7)
    events = client.get("/events", headers=auth(ada["token"])).json()["events"]

    assert locked_board.status_code == 200
    assert locked_board.json()["contracts"][0]["phase"]["status"] == "locked"
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "resolved"
    assert [event["type"] for event in events].count("contract.phase.locked") == 1
    assert [event["type"] for event in events].count("contract.phase.resolved") == 1


def test_completed_oracle_audit_recovers_without_calling_oracle_again(tmp_path):
    client, ada, linus, gilt, moth = setup_two_crews(tmp_path)
    submit_action(client, ada, gilt, "action-gilt", "Inspect the ledger for forged provenance.")
    submit_action(client, linus, moth, "action-moth", "Observe the moth jar door omen.")
    event_store = client.app.state.event_store
    contract_service = client.app.state.contract_service

    event_store.append_command(
        event_type="contract.phase.locked",
        actor_id="server",
        visibility=EventVisibility.public(),
        payload={
            "contract_id": "contract_false_finger",
            "phase": "Auction Preview",
            "hours_elapsed": 6,
        },
        idempotency_key="phase-lock.contract_false_finger.auction-preview",
    )
    packet = contract_service._build_auction_preview_packet(contract_id="contract_false_finger")
    input_packet_hash = contract_service._oracle_packet_hash(packet)
    accepted_output = DeterministicResolutionOracle().resolve_auction_preview(packet)
    event_store.append_command(
        event_type="oracle.resolution.requested",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={
            "contract_id": "contract_false_finger",
            "phase": "Auction Preview",
            "input_packet_hash": input_packet_hash,
        },
        idempotency_key="oracle.resolution.contract_false_finger.auction-preview.requested",
    )
    event_store.append_command(
        event_type="oracle.resolution.completed",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={
            "contract_id": "contract_false_finger",
            "phase": "Auction Preview",
            "provider": "deterministic",
            "model": None,
            "prompt_version": "deterministic-v1",
            "fallback": False,
            "fallback_reason": None,
            "input_packet_hash": input_packet_hash,
            "accepted_output": accepted_output.model_dump(mode="json"),
        },
        idempotency_key="oracle.resolution.contract_false_finger.auction-preview.completed",
    )

    class RaisingOracle:
        called = False

        def resolve_auction_preview(self, packet):
            _ = packet
            self.called = True
            raise AssertionError("oracle should not be called during completed-audit recovery")

    raising_oracle = RaisingOracle()
    client.app.state.contract_service = ContractService(
        event_store=event_store,
        resolution_oracle=raising_oracle,
    )

    recovered = lock_preview(client, ada, "phase-lock-recover", hours_elapsed=7)
    events = event_store.read()

    assert recovered.status_code == 200
    assert recovered.json() == contract_service._auction_preview_reveal_from_oracle_result(
        contract_id="contract_false_finger",
        result=accepted_output,
    )
    assert raising_oracle.called is False
    assert [event.type for event in events].count("oracle.resolution.requested") == 1
    assert [event.type for event in events].count("oracle.resolution.completed") == 1
    assert [event.type for event in events].count("contract.phase.resolved") == 1


def test_equivalent_valid_frames_resolve_through_rules_not_crew_name(tmp_path):
    client, ada, linus, gilt, moth = setup_two_crews(tmp_path)
    submit_action(client, ada, gilt, "action-gilt", "Inspect the ledger for forged provenance.")
    submit_action(client, linus, moth, "action-moth", "Inspect the ledger for forged provenance.")

    reveal = lock_preview(client, ada, "phase-lock-1").json()

    scores = {standing["crew_id"]: standing["score"] for standing in reveal["standings"]}
    assert scores[gilt["crew_id"]] == scores[moth["crew_id"]]


def test_early_lock_requires_meaningful_supported_actions(tmp_path):
    client, ada, linus, gilt, moth = setup_two_crews(tmp_path)
    submit_action(client, ada, gilt, "action-gilt", "Talk loudly about rumors.")
    submit_action(client, linus, moth, "action-moth", "Invent an unsupported theory.")

    rejected = lock_preview(client, ada, "phase-lock-early", hours_elapsed=1)

    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "phase still active"


def test_dossier_mutations_are_rejected_after_phase_lock(tmp_path):
    client, ada, _, gilt, _ = setup_two_crews(tmp_path)
    submit_action(client, ada, gilt, "action-gilt", "Inspect the ledger for forged provenance.")
    locked = lock_preview(client, ada, "phase-lock-1")
    late_claim = client.patch(
        f"/proofs/dossiers/{gilt['crew_id']}/framing",
        headers=command_auth(ada["token"], "claim-late"),
        json={"claim": "Change the packet after scoring."},
    )

    assert locked.status_code == 200
    assert late_claim.status_code == 409
