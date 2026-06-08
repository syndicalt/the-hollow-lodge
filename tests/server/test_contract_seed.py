import json
from pathlib import Path

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


def test_starter_contract_seed_is_visible_without_hidden_truth(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    response = client.get("/contracts", headers=auth(ada["token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["campaign"]["title"] == "Saints & Ledgers"
    contract = body["contracts"][0]
    assert contract["title"] == "The Saint's False Finger"
    assert contract["phase"]["name"] == "Auction Preview"
    assert contract["crew_heat"] == 0
    assert "hidden_truth" not in response.text
    assert "finger is a saint-bone forgery" not in response.text


def test_hidden_truth_is_committed_server_only_and_not_in_visible_events(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    event_log = (tmp_path / "server-events.jsonl").read_text()
    assert "contract.hidden_truth.seeded" in event_log
    assert "finger is a saint-bone forgery" in event_log

    visible = client.get("/events", headers=auth(ada["token"]))
    assert visible.status_code == 200
    visible_text = visible.text
    assert "contract.board.published" in visible_text
    assert "contract.hidden_truth.seeded" not in visible_text
    assert "finger is a saint-bone forgery" not in visible_text


def test_inbox_renders_contract_state_and_empty_notices(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    response = client.get("/inbox", headers=auth(ada["token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["player_id"] == ada["player_id"]
    assert body["display_name"] == "Ada"
    assert body["active_contracts"][0]["title"] == "The Saint's False Finger"
    assert body["active_contracts"][0]["proof_dossier_needs"] == [
        "provenance chain",
        "material authenticity",
        "auction leverage",
    ]
    assert body["incoming_proof_fragments"] == []


def test_admin_can_activate_second_contract_seed_and_render_it(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    seed = "tests/fixtures/ash_window_contract.json"

    activated = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": seed},
    )
    contracts = client.get("/contracts", headers=auth(ada["token"]))
    inbox = client.get("/inbox", headers=auth(ada["token"]))
    events = client.get("/events", headers=auth(ada["token"]))

    assert activated.status_code == 201
    assert activated.json() == {
        "contract_id": "contract_ash_window",
        "lifecycle_status": "active",
    }
    rendered = {
        contract["contract_id"]: contract
        for contract in contracts.json()["contracts"]
    }
    assert rendered["contract_ash_window"]["title"] == "The Ash Window"
    assert rendered["contract_ash_window"]["phase"]["name"] == "Cinder Preview"
    assert rendered["contract_ash_window"]["lifecycle_status"] == "active"
    assert any(
        contract["contract_id"] == "contract_ash_window"
        for contract in inbox.json()["active_contracts"]
    )
    assert "cinder oracle" not in contracts.text
    assert "contract.hidden_truth.seeded" not in events.text
    assert "cinder oracle" not in events.text


def test_contract_board_renders_public_campaign_arc_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    seed = json.loads(Path("tests/fixtures/ash_window_contract.json").read_text(encoding="utf-8"))
    seed["contract"]["arc"] = {
        "arc_id": "arc_cinders_below",
        "title": "Cinders Below",
        "chapter": 2,
        "sequence": 20,
        "public_summary": "The Lodge follows fire omens from auction catalogues into old glass.",
        "previous_contract_id": "contract_false_finger",
        "next_contract_hint": "A burned ledger points toward the chapel undercroft.",
    }
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    activated = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-arc-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": seed},
    )
    contracts = client.get("/contracts", headers=auth(ada["token"]))
    visible_events = client.get("/events", headers=auth(ada["token"]))

    assert activated.status_code == 201
    ash = {
        contract["contract_id"]: contract
        for contract in contracts.json()["contracts"]
    }["contract_ash_window"]
    assert ash["arc"] == {
        "arc_id": "arc_cinders_below",
        "title": "Cinders Below",
        "chapter": 2,
        "sequence": 20,
        "public_summary": "The Lodge follows fire omens from auction catalogues into old glass.",
        "previous_contract_id": "contract_false_finger",
        "next_contract_hint": "A burned ledger points toward the chapel undercroft.",
    }
    assert "server-only" not in contracts.text
    assert "cinder oracle" not in contracts.text
    assert "server-only" not in visible_events.text
    assert "cinder oracle" not in visible_events.text


def test_legacy_locked_contract_is_visible_but_not_actionable_until_crew_qualifies(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    seed = json.loads(Path("tests/fixtures/ash_window_contract.json").read_text(encoding="utf-8"))
    seed["unlock_requirements"] = [
        {
            "scope": "crew",
            "metric": "reputation",
            "minimum": 2,
            "label": "Reputation 2+",
            "description": "Complete earlier Lodge work with a strong lead.",
        }
    ]
    seed_path = tmp_path / "locked-ash-window.json"
    seed_path.write_text(json.dumps(seed), encoding="utf-8")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers={
            **auth(ada["token"]),
            "Idempotency-Key": "crew-create",
        },
        json={"name": "The Gilt Knives"},
    ).json()

    activated = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-locked-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": str(seed_path)},
    )
    contracts_before = client.get("/contracts", headers=auth(ada["token"]))
    inbox_before = client.get("/inbox", headers=auth(ada["token"]))
    crew_before = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert activated.status_code == 201
    rendered_before = {
        contract["contract_id"]: contract
        for contract in contracts_before.json()["contracts"]
    }
    locked = rendered_before["contract_ash_window"]
    assert locked["unlock_status"] == {
        "state": "locked",
        "requirements": [
            {
                "scope": "crew",
                "metric": "reputation",
                "minimum": 2,
                "current": 0,
                "label": "Reputation 2+",
                "description": "Complete earlier Lodge work with a strong lead.",
                "satisfied": False,
            }
        ],
    }
    assert "contract_ash_window" not in {
        contract["contract_id"]
        for contract in inbox_before.json()["active_contracts"]
    }
    assert "contract_ash_window" not in {
        contract["contract_id"]
        for contract in crew_before.json()["active_contracts"]
    }
    assert not any(
        decision.get("contract_id") == "contract_ash_window"
        for decision in crew_before.json()["pending_decisions"]
    )

    client.post(
        "/actions",
        headers={
            **auth(ada["token"]),
            "Idempotency-Key": "action-ledger",
        },
        json={
            "crew_id": crew["crew_id"],
            "intent": "Inspect the red ledger timestamp for forged provenance.",
            "confirmed": True,
        },
    )
    client.patch(
        f"/proofs/dossiers/{crew['crew_id']}/framing",
        headers={
            **auth(ada["token"]),
            "Idempotency-Key": "claim-ledger",
        },
        json={"claim": "The finger is a false relic with forged provenance."},
    )
    resolved = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers={
            **auth(ada["token"]),
            "Idempotency-Key": "phase-lock",
        },
        json={"hours_elapsed": 6},
    )
    contracts_after = client.get("/contracts", headers=auth(ada["token"]))
    inbox_after = client.get("/inbox", headers=auth(ada["token"]))
    crew_after = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))
    visible_events = client.get("/events", headers=auth(ada["token"]))

    assert resolved.status_code == 200
    rendered_after = {
        contract["contract_id"]: contract
        for contract in contracts_after.json()["contracts"]
    }
    assert rendered_after["contract_ash_window"]["unlock_status"]["state"] == "unlocked"
    assert "contract_ash_window" in {
        contract["contract_id"]
        for contract in inbox_after.json()["active_contracts"]
    }
    assert "contract_ash_window" in {
        contract["contract_id"]
        for contract in crew_after.json()["active_contracts"]
    }
    assert "unlock_requirements" not in visible_events.text
    assert "hidden_truth" not in visible_events.text


def test_contract_activation_replay_rejects_different_unlock_requirements(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    seed = json.loads(Path("tests/fixtures/ash_window_contract.json").read_text(encoding="utf-8"))
    locked_seed = {
        **seed,
        "unlock_requirements": [
            {
                "scope": "crew",
                "metric": "reputation",
                "minimum": 2,
                "label": "Reputation 2+",
                "description": "Complete earlier Lodge work with a strong lead.",
            }
        ],
    }
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))

    first = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": seed},
    )
    conflict = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": locked_seed},
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "idempotency key conflict"


def test_contract_activation_replay_rejects_different_arc_metadata(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    seed = json.loads(Path("tests/fixtures/ash_window_contract.json").read_text(encoding="utf-8"))
    seed["contract"]["arc"] = {
        "arc_id": "arc_cinders_below",
        "title": "Cinders Below",
        "chapter": 2,
        "sequence": 20,
        "public_summary": "The Lodge follows fire omens from auction catalogues into old glass.",
        "previous_contract_id": "contract_false_finger",
        "next_contract_hint": "A burned ledger points toward the chapel undercroft.",
    }
    changed_seed = json.loads(json.dumps(seed))
    changed_seed["contract"]["arc"]["next_contract_hint"] = (
        "A different hint should not replay under the same key."
    )
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))

    first = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-arc-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": seed},
    )
    conflict = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-arc-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": changed_seed},
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "idempotency key conflict"


def test_admin_can_archive_contract_and_remove_it_from_active_inbox(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
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
    archived = client.post(
        "/contracts/admin/contract_ash_window/archive",
        headers={
            "Idempotency-Key": "archive-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={},
    )
    contracts = client.get("/contracts", headers=auth(ada["token"]))
    inbox = client.get("/inbox", headers=auth(ada["token"]))

    assert activated.status_code == 201
    assert archived.status_code == 200
    assert archived.json() == {
        "contract_id": "contract_ash_window",
        "lifecycle_status": "archived",
    }
    rendered = {
        contract["contract_id"]: contract
        for contract in contracts.json()["contracts"]
    }
    assert rendered["contract_ash_window"]["lifecycle_status"] == "archived"
    assert "contract_ash_window" not in {
        contract["contract_id"]
        for contract in inbox.json()["active_contracts"]
    }


def test_archived_contract_does_not_create_pending_contract_decisions(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers={
            **auth(ada["token"]),
            "Idempotency-Key": "crew-create",
        },
        json={"name": "The Gilt Knives"},
    ).json()
    client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )
    client.post(
        "/contracts/admin/contract_ash_window/archive",
        headers={
            "Idempotency-Key": "archive-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={},
    )

    inbox = client.get("/inbox", headers=auth(ada["token"]))
    crew_board = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert inbox.status_code == 200
    assert crew_board.status_code == 200
    assert "contract_ash_window" not in {
        contract["contract_id"]
        for contract in crew_board.json()["active_contracts"]
    }
    assert not any(
        decision.get("contract_id") == "contract_ash_window"
        and decision.get("kind") in {"dossier_need", "contract_action"}
        for decision in inbox.json()["pending_decisions"]
    )
    assert not any(
        decision.get("contract_id") == "contract_ash_window"
        and decision.get("kind") in {"dossier_need", "contract_action"}
        for decision in crew_board.json()["pending_decisions"]
    )


def test_admin_contract_archive_is_idempotent_and_rejects_unknown_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )

    first = client.post(
        "/contracts/admin/contract_ash_window/archive",
        headers={
            "Idempotency-Key": "archive-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={},
    )
    replay = client.post(
        "/contracts/admin/contract_ash_window/archive",
        headers={
            "Idempotency-Key": "archive-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={},
    )
    missing = client.post(
        "/contracts/admin/no_such_contract/archive",
        headers={
            "Idempotency-Key": "archive-missing",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={},
    )
    event_text = (tmp_path / "server-events.jsonl").read_text(encoding="utf-8")

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert missing.status_code == 404
    assert missing.json()["detail"] == "contract not found"
    assert event_text.count('"status":"archived"') == 1


def test_admin_contract_activation_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))

    first = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )
    replay = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": "tests/fixtures/ash_window_contract.json"},
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()


def test_admin_contract_activation_rejects_invalid_seed(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    bad_seed = tmp_path / "bad.json"
    bad_seed.write_text("{}", encoding="utf-8")
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))

    response = client.post(
        "/contracts/admin/activate",
        headers={
            "Idempotency-Key": "activate-bad",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
        json={"seed": str(bad_seed)},
    )

    assert response.status_code == 422
