from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app
from hollow_lodge.server.autopilot import (
    CONTRACT_RELEASE_ORDER,
    packaged_contract_seeds,
    run_autopilot_pass,
    start_autopilot,
)
from hollow_lodge.server.contract_seed import ContractSeed
from tests.server.test_phase_resolution import (
    command_auth,
    create_crew,
    register,
)

SEED_DIR = Path(__file__).resolve().parents[2] / "src" / "hollow_lodge" / "contract_seeds"


def load_seed(name: str) -> ContractSeed:
    return ContractSeed.model_validate(
        json.loads((SEED_DIR / f"{name}.json").read_text(encoding="utf-8"))
    )


def make_client(tmp_path) -> TestClient:
    return TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"]))


def expire_all_phases(client: TestClient, monkeypatch) -> None:
    service = client.app.state.contract_service
    monkeypatch.setattr(
        service,
        "_auction_preview_hours_elapsed",
        lambda contract_id: 999,
    )


def test_packaged_seeds_follow_release_order():
    seeds = packaged_contract_seeds()
    names = [seed.contract.contract_id for seed in seeds]

    assert names[: len(CONTRACT_RELEASE_ORDER)] == [
        f"contract_{name}" for name in CONTRACT_RELEASE_ORDER
    ]


def test_resolve_due_phases_skips_active_timers(tmp_path):
    client = make_client(tmp_path)

    assert client.app.state.contract_service.resolve_due_phases() == []


def test_resolve_due_phases_resolves_expired_contracts(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    service = client.app.state.contract_service
    service.activate_contract_seed(
        seed=load_seed("ash_window"),
        actor_id="server",
        idempotency_key="test-activate-ash",
    )
    expire_all_phases(client, monkeypatch)

    resolved = service.resolve_due_phases()

    assert "contract_ash_window" in resolved
    assert service.resolve_due_phases() == []


def test_ensure_active_contracts_publishes_next_seed_when_board_empties(
    tmp_path, monkeypatch
):
    client = make_client(tmp_path)
    service = client.app.state.contract_service

    untouched = service.ensure_active_contracts(seeds=packaged_contract_seeds())
    assert untouched == []

    expire_all_phases(client, monkeypatch)
    service.resolve_due_phases()
    activated = service.ensure_active_contracts(seeds=packaged_contract_seeds())

    assert activated == ["contract_ash_window"]
    assert service.ensure_active_contracts(seeds=packaged_contract_seeds()) == []


def test_autopilot_pass_runs_full_cycle_with_rubric_scoring(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    service = client.app.state.contract_service
    service.activate_contract_seed(
        seed=load_seed("ash_window"),
        actor_id="server",
        idempotency_key="test-activate-ash",
    )

    ada = register(client, "a", "Ada")
    linus = register(client, "b", "Linus")
    gilt = create_crew(client, ada["token"], "crew-gilt", "The Gilt Knives")
    create_crew(client, linus["token"], "crew-moth", "The Moth Choir")

    # Gilt investigates: unlock the soot sample, cite both artifacts, and
    # establish the fire-chronology rubric fact with a cited typed claim.
    response = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-soot"),
        json={
            "crew_id": gilt["crew_id"],
            "intent": "Follow the ash notice into the soot cooling pattern.",
            "confirmed": True,
        },
    )
    assert response.status_code == 201
    for key, artifact_id in (
        ("cite-notice", "artifact_ash_notice"),
        ("cite-soot", "artifact_soot_sample"),
    ):
        response = client.post(
            f"/proofs/dossiers/{gilt['crew_id']}/artifact-citations",
            headers=command_auth(ada["token"], key),
            json={
                "artifact_id": artifact_id,
                "claim": "The recovery timestamp precedes the fire.",
                "quote": "timestamped two hours before the fire",
            },
        )
        assert response.status_code in (200, 201), response.text
    response = client.post(
        f"/proofs/dossiers/{gilt['crew_id']}/typed-claims",
        headers=command_auth(ada["token"], "claim-chronology"),
        json={
            "subject_id": "artifact_ash_notice",
            "predicate": "contradicts_fire_chronology",
            "object_id": "artifact_soot_sample",
            "citation_artifact_ids": [
                "artifact_ash_notice",
                "artifact_soot_sample",
            ],
        },
    )
    assert response.status_code in (200, 201), response.text

    expire_all_phases(client, monkeypatch)
    outcome = run_autopilot_pass(client.app)

    assert "contract_ash_window" in outcome["resolved_contract_ids"]
    # The board emptied, so the queue releases the next packaged contract.
    assert outcome["activated_contract_ids"] == ["contract_ninth_mourner_receipt"]

    reveal = service._resolved_auction_preview(
        contract_id="contract_ash_window",
        phase="Cinder Preview",
    )
    standings = {row["crew_id"]: row for row in reveal["standings"]}
    gilt_row = standings[gilt["crew_id"]]
    other_rows = [
        row for crew_id, row in standings.items() if crew_id != gilt["crew_id"]
    ]
    assert all(gilt_row["score"] > row["score"] for row in other_rows)
    assert "Fire chronology is now suspect." in gilt_row["revealed_clues"]
    assert "established" in " ".join(gilt_row["strengths"])
    assert "Ties break on established key facts" in reveal["narration"]

    # A second pass is a no-op until the new contract's timer expires.
    followup = run_autopilot_pass(client.app)
    assert followup["resolved_contract_ids"] == ["contract_ninth_mourner_receipt"]
    assert followup["activated_contract_ids"] == ["contract_wax_eclipse_bond"]


def test_start_autopilot_disabled_by_default(tmp_path):
    client = make_client(tmp_path)

    assert client.app.state.autopilot_thread is None


def test_start_autopilot_runs_and_stops(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_AUTOPILOT_INTERVAL_SECONDS", "30")
    client = make_client(tmp_path)
    thread = client.app.state.autopilot_thread

    assert thread is not None and thread.is_alive()

    client.app.state.autopilot_stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_start_autopilot_rejects_invalid_interval(monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_AUTOPILOT_INTERVAL_SECONDS", "soon")

    class FakeApp:
        class state:
            pass

    assert start_autopilot(FakeApp()) is None
