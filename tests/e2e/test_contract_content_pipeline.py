from fastapi.testclient import TestClient

from hollow_lodge.client.codex_session import CodexGameSession
from hollow_lodge.client.config import ClientConfig, save_config
from hollow_lodge.server.app import create_app


def _register(client: TestClient, invite: str, name: str) -> dict[str, str]:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _command_auth(token: str, key: str) -> dict[str, str]:
    return {**_auth(token), "Idempotency-Key": key}


def _create_crew(client: TestClient, token: str, key: str, name: str) -> dict:
    response = client.post(
        "/crews",
        json={"name": name},
        headers=_command_auth(token, key),
    )
    assert response.status_code == 201
    return response.json()


def test_activated_contract_seed_plays_and_renders_through_codex(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    app = create_app(data_dir=tmp_path / "server", invite_codes=["a", "b"])
    client = TestClient(app)
    activated = client.post(
        "/contracts/admin/activate",
        json={"seed": "tests/fixtures/ash_window_contract.json"},
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )
    assert activated.status_code == 201
    ada = _register(client, "a", "Ada")
    linus = _register(client, "b", "Linus")
    gilt = _create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    moth = _create_crew(client, linus["token"], "crew-create-moth", "The Moth Choir")
    action = client.post(
        "/actions",
        json={
            "crew_id": gilt["crew_id"],
            "intent": "Follow the ash notice into the soot cooling pattern.",
            "confirmed": True,
        },
        headers=_command_auth(ada["token"], "action-gilt-soot"),
    )
    moth_action = client.post(
        "/actions",
        json={
            "crew_id": moth["crew_id"],
            "intent": "Interview the witness about the recovered window frame.",
            "confirmed": True,
        },
        headers=_command_auth(linus["token"], "action-moth-witness"),
    )
    resolved = client.post(
        "/contracts/contract_ash_window/phases/auction-preview/lock",
        json={"hours_elapsed": 4},
        headers=_command_auth(ada["token"], "phase-lock-ash"),
    )
    assert action.status_code == 201
    assert moth_action.status_code == 201
    assert resolved.status_code == 200

    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id=ada["player_id"],
            token=ada["token"],
            active_crew_id=gilt["crew_id"],
        ),
    )

    def fake_get(url, headers=None, params=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.get(path, headers=headers, params=params)

    monkeypatch.setattr("httpx.get", fake_get)
    session = CodexGameSession(
        config_path=config_path,
        local_log_path=tmp_path / "local.jsonl",
    )

    contracts = session.render_contract_board()
    artifacts = session.render_artifacts()

    assert "The Ash Window" in contracts.player_markdown
    assert "Phase result:" in contracts.player_markdown
    assert "Fire chronology is now suspect." in contracts.player_markdown
    assert "Ash Lot Notice" in artifacts.player_markdown
    assert "Soot Sample Receipt" in artifacts.player_markdown
    assert "future-burn" not in artifacts.player_markdown
    assert "cinder oracle" not in contracts.player_markdown
    assert "contract.hidden_truth.seeded" not in (tmp_path / "local.jsonl").read_text(
        encoding="utf-8"
    )


def test_resolved_contract_legacy_changes_codex_crew_board_future_opportunities(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    app = create_app(data_dir=tmp_path / "server", invite_codes=["a"])
    client = TestClient(app)
    assert client.post(
        "/contracts/admin/activate",
        json={"seed": "tests/fixtures/ash_window_contract.json"},
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    ).status_code == 201
    ada = _register(client, "a", "Ada")
    crew = _create_crew(client, ada["token"], "crew-create-gilt", "The Gilt Knives")
    assert client.post(
        "/actions",
        json={
            "crew_id": crew["crew_id"],
            "intent": "Inspect the red ledger timestamp for forged provenance.",
            "confirmed": True,
        },
        headers=_command_auth(ada["token"], "action-ledger"),
    ).status_code == 201
    assert client.patch(
        f"/proofs/dossiers/{crew['crew_id']}/framing",
        json={"claim": "The finger is a false relic with forged provenance."},
        headers=_command_auth(ada["token"], "claim-ledger"),
    ).status_code == 200
    assert client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        json={"hours_elapsed": 6},
        headers=_command_auth(ada["token"], "phase-lock"),
    ).status_code == 200

    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id=ada["player_id"],
            token=ada["token"],
            active_crew_id=crew["crew_id"],
        ),
    )

    def fake_get(url, headers=None, params=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.get(path, headers=headers, params=params)

    monkeypatch.setattr("httpx.get", fake_get)
    session = CodexGameSession(
        config_path=config_path,
        local_log_path=tmp_path / "legacy-local.jsonl",
    )

    crew_board = session.render_crew_board()

    assert "Legacy:" in crew_board.player_markdown
    assert "Reputation: 2" in crew_board.player_markdown
    assert "Heat: 1" in crew_board.player_markdown
    assert "- The Saint's False Finger: Strong lead (70)" in crew_board.player_markdown
    assert "- The Ash Window: Reputation leverage +2; Heat attention +1" in crew_board.player_markdown
    assert crew_board.agent_context["legacy"]["future_opportunities"][0]["contract_id"] == (
        "contract_ash_window"
    )
    assert crew_board.agent_context["active_contracts"][0]["crew_modifiers"]
