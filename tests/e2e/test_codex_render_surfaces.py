from fastapi.testclient import TestClient

from hollow_lodge.server.contract_seed import load_contract_seed_file
from hollow_lodge.client.codex_session import CodexGameSession
from hollow_lodge.client.config import ClientConfig, save_config
from hollow_lodge.server.app import create_app


def test_codex_render_surfaces_show_player_and_agent_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ADMIN_TOKEN", "admin-secret")
    app = create_app(data_dir=tmp_path / "server", invite_codes=["a"])
    client = TestClient(app)
    seed = load_contract_seed_file("tests/fixtures/ash_window_contract.json")
    activate_response = client.post(
        "/contracts/admin/activate",
        json={"seed": seed.model_dump(mode="json")},
        headers={
            "Idempotency-Key": "activate-ash-window",
            "X-Hollow-Lodge-Admin-Token": "admin-secret",
        },
    )
    assert activate_response.status_code == 201
    register_response = client.post(
        "/identity/register",
        json={"invite_code": "a", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-a"},
    )
    assert register_response.status_code == 201
    registered = register_response.json()
    crew_response = client.post(
        "/crews",
        json={"name": "The Gilt Knives"},
        headers={
            "Authorization": f"Bearer {registered['token']}",
            "Idempotency-Key": "crew-create-gilt",
        },
    )
    assert crew_response.status_code == 201
    crew = crew_response.json()
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id=registered["player_id"],
            token=registered["token"],
            active_crew_id=crew["crew_id"],
        ),
    )

    def fake_get(url, headers=None, params=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.get(path, headers=headers, params=params)

    monkeypatch.setattr("httpx.get", fake_get)
    local_log_path = tmp_path / "local.jsonl"
    session = CodexGameSession(
        config_path=config_path,
        local_log_path=local_log_path,
    )

    inbox = session.render_inbox()
    contracts = session.render_contract_board()
    crew_board = session.render_crew_board()
    artifacts = session.render_artifacts()

    assert inbox.surface == "inbox"
    assert contracts.surface == "contract_board"
    assert crew_board.surface == "crew_board"
    assert artifacts.surface == "artifact_graph"
    assert "Inbox: Ada" in inbox.player_markdown
    assert inbox.agent_context["player_id"] == registered["player_id"]
    assert inbox.agent_context["display_name"] == "Ada"
    assert "The Saint's False Finger" in contracts.player_markdown
    assert "The Ash Window" in contracts.player_markdown
    assert "cinder oracle" not in contracts.player_markdown
    assert contracts.agent_context["visible_contract_count"] == 2
    assert {contract["title"] for contract in contracts.agent_context["contracts"]} == {
        "The Saint's False Finger",
        "The Ash Window",
    }
    assert "Ash Lot Notice" in artifacts.player_markdown
    assert "Soot Caught Beneath the Brass" not in artifacts.player_markdown
    assert "Crew Board: The Gilt Knives" in crew_board.player_markdown
    assert crew_board.agent_context["crew"]["crew_id"] == crew["crew_id"]
    assert local_log_path.exists()
    local_log_text = local_log_path.read_text(encoding="utf-8")
    assert "contract.board.published" in local_log_text
    assert "contract.hidden_truth.seeded" not in local_log_text
    assert "crew.created" in local_log_text
