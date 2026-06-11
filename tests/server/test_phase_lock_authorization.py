from __future__ import annotations

import pytest

from tests.server.test_phase_resolution import (
    lock_preview,
    register,
    setup_two_crews,
    submit_action,
)


@pytest.fixture()
def server_phase_clock(monkeypatch):
    monkeypatch.delenv("HOLLOW_LODGE_TRUST_CLIENT_PHASE_CLOCK", raising=False)


def test_player_without_crew_cannot_lock_phase(tmp_path):
    client, ada, linus, gilt, moth = setup_two_crews(tmp_path)
    drifter = register(client, "c", "Drifter")

    response = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers={
            "Authorization": f"Bearer {drifter['token']}",
            "Idempotency-Key": "phase-lock-drifter",
        },
        json={"hours_elapsed": 6},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "not a crew member"


def test_client_clock_cannot_force_early_lock_without_trust_env(
    tmp_path, server_phase_clock
):
    client, ada, linus, gilt, moth = setup_two_crews(tmp_path)

    response = lock_preview(client, ada, "phase-lock-early")

    assert response.status_code == 409
    assert response.json()["detail"] == "phase still active"


def test_lock_succeeds_on_meaningful_actions_without_client_clock(
    tmp_path, server_phase_clock
):
    client, ada, linus, gilt, moth = setup_two_crews(tmp_path)
    submit_action(
        client,
        ada,
        gilt,
        "action-gilt",
        "Quietly compare the red ledger date to the chapel timestamp.",
    )
    submit_action(
        client,
        ada,
        gilt,
        "action-gilt-2",
        "Press the clerk about the ledger custody gap.",
    )

    response = lock_preview(client, ada, "phase-lock-actions")

    assert response.status_code == 200
    assert response.json()["contract_id"] == "contract_false_finger"


def test_production_preset_ignores_trust_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_TRUST_CLIENT_PHASE_CLOCK", "1")
    monkeypatch.setenv("HOLLOW_LODGE_PRODUCTION_POSTGRES", "1")

    from hollow_lodge.server.services import trust_client_phase_clock

    assert trust_client_phase_clock() is False
