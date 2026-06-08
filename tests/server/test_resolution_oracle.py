from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.eventlog.jsonl_store import JsonlEventStore
from hollow_lodge.server.app import create_app
from hollow_lodge.server.services import ContractService
from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewResult,
    AuctionPreviewOracleResult,
    OracleProviderMetadata,
)


class UnknownCrewOracle:
    def __init__(self) -> None:
        self.calls = 0

    def resolve_auction_preview(self, packet):
        self.calls += 1
        return AuctionPreviewOracleResult(
            provider=OracleProviderMetadata(
                provider="test-invalid",
                model="invalid-v1",
                prompt_version="test-v1",
            ),
            standings=(
                AuctionPreviewCrewResult(
                    crew_id="crew_unknown",
                    score=99,
                    standing="Strong lead",
                    strengths=("invalid crew id",),
                    weaknesses=(),
                    penalties=(),
                    revealed_clues=(),
                ),
            ),
            contract_state=(),
            narration="Invalid provider output.",
            validation_warnings=(),
        )


class FalseyOracle:
    def __bool__(self) -> bool:
        return False

    def resolve_auction_preview(self, packet):
        raise AssertionError("falsey oracle identity test should not resolve phases")


class CountingOracle:
    def __init__(self) -> None:
        self.calls = 0

    def resolve_auction_preview(self, packet):
        self.calls += 1
        return DeterministicResolutionOracle().resolve_auction_preview(packet)


class ValueFailingOracle:
    def __init__(self) -> None:
        self.calls = 0

    def resolve_auction_preview(self, packet):
        _ = packet
        self.calls += 1
        raise ValueError("provider returned invalid output")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def command_auth(token: str, key: str) -> dict[str, str]:
    return {**auth(token), "Idempotency-Key": key}


def register(client: TestClient, invite: str, name: str) -> dict[str, str]:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def create_crew(client: TestClient, token: str, key: str, name: str) -> dict:
    response = client.post(
        "/crews",
        headers=command_auth(token, key),
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()


def submit_action(client: TestClient, player: dict, crew: dict) -> dict:
    response = client.post(
        "/actions",
        headers=command_auth(player["token"], "action-ada"),
        json={
            "crew_id": crew["crew_id"],
            "intent": "Inspect the ledger for forged provenance.",
            "confirmed": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_app_preserves_falsey_injected_oracle(tmp_path):
    oracle = FalseyOracle()

    app = create_app(data_dir=tmp_path, invite_codes=["a"], resolution_oracle=oracle)

    assert app.state.resolution_oracle is oracle
    assert app.state.contract_service._resolution_oracle is oracle


def test_contract_service_preserves_falsey_injected_oracle(tmp_path):
    oracle = FalseyOracle()
    event_store = JsonlEventStore(tmp_path / "server-events.jsonl")

    service = ContractService(event_store=event_store, resolution_oracle=oracle)

    assert service._resolution_oracle is oracle


def test_invalid_oracle_result_falls_back_and_is_audited(tmp_path):
    oracle = UnknownCrewOracle()
    client = TestClient(
        create_app(data_dir=tmp_path, invite_codes=["a"], resolution_oracle=oracle)
    )
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-ada", "The Gilt Knives")
    submit_action(client, ada, crew)

    response = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock-1"),
        json={"hours_elapsed": 6},
    )
    events = client.app.state.event_store.read()
    failed = [event for event in events if event.type == "oracle.resolution.failed"]
    completed = [event for event in events if event.type == "oracle.resolution.completed"]

    assert response.status_code == 200
    assert oracle.calls == 1
    assert response.json()["standings"][0]["crew_id"] == crew["crew_id"]
    assert len(failed) == 1
    assert failed[0].visibility == EventVisibility.server_only()
    assert failed[0].payload["fallback_reason"] == "ValueError"
    assert failed[0].payload["input_packet_hash"]
    assert len(completed) == 1
    assert completed[0].visibility == EventVisibility.server_only()
    assert completed[0].payload["fallback"] is True
    assert completed[0].payload["fallback_reason"] == "ValueError"
    assert completed[0].payload["provider"] == "deterministic"


def test_duplicate_phase_lock_does_not_call_oracle_twice(tmp_path):
    oracle = CountingOracle()
    client = TestClient(
        create_app(data_dir=tmp_path, invite_codes=["a"], resolution_oracle=oracle)
    )
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-ada", "The Gilt Knives")
    submit_action(client, ada, crew)

    first = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock"),
        json={"hours_elapsed": 6},
    )
    replay = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock"),
        json={"hours_elapsed": 6},
    )
    duplicate = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock-other"),
        json={"hours_elapsed": 7},
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert duplicate.status_code == 200
    assert replay.json() == first.json()
    assert duplicate.json() == first.json()
    assert oracle.calls == 1


def test_failed_oracle_audit_recovers_without_idempotency_conflict(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-ada", "The Gilt Knives")
    submit_action(client, ada, crew)
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
        event_type="oracle.resolution.failed",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={
            "contract_id": "contract_false_finger",
            "phase": "Auction Preview",
            "input_packet_hash": input_packet_hash,
            "fallback_reason": "RuntimeError",
        },
        idempotency_key="oracle.resolution.contract_false_finger.auction-preview.failed",
    )
    oracle = ValueFailingOracle()
    client.app.state.contract_service = ContractService(
        event_store=event_store,
        resolution_oracle=oracle,
    )

    recovered = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock-recover"),
        json={"hours_elapsed": 7},
    )
    events = event_store.read()
    completed = next(event for event in events if event.type == "oracle.resolution.completed")

    assert recovered.status_code == 200
    assert oracle.calls == 1
    assert [event.type for event in events].count("oracle.resolution.failed") == 1
    assert [event.type for event in events].count("oracle.resolution.completed") == 1
    assert [event.type for event in events].count("contract.phase.resolved") == 1
    assert completed.payload["fallback"] is True
    assert completed.payload["fallback_reason"] == "RuntimeError"


def test_completed_oracle_audit_hash_mismatch_is_not_reused(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = create_crew(client, ada["token"], "crew-create-ada", "The Gilt Knives")
    submit_action(client, ada, crew)
    event_store = client.app.state.event_store
    contract_service = client.app.state.contract_service
    packet = contract_service._build_auction_preview_packet(contract_id="contract_false_finger")
    accepted_output = DeterministicResolutionOracle().resolve_auction_preview(packet)
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
            "input_packet_hash": "stale-packet-hash",
            "accepted_output": accepted_output.model_dump(mode="json"),
        },
        idempotency_key="oracle.resolution.contract_false_finger.auction-preview.completed",
    )

    with pytest.raises(ValueError, match="oracle completed audit hash mismatch"):
        contract_service._build_auction_preview_reveal(contract_id="contract_false_finger")
