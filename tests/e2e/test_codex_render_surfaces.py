from fastapi.testclient import TestClient

from hollow_lodge.client.codex_session import CodexGameSession
from hollow_lodge.client.config import ClientConfig, save_config
from hollow_lodge.server.app import create_app


def test_codex_render_surfaces_show_player_and_agent_state(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path / "server", invite_codes=["a"])
    client = TestClient(app)
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

    assert inbox.surface == "inbox"
    assert contracts.surface == "contract_board"
    assert crew_board.surface == "crew_board"
    assert f"Inbox: {registered['player_id']}" in inbox.player_markdown
    assert inbox.agent_context["player_id"] == registered["player_id"]
    assert "The Saint's False Finger" in contracts.player_markdown
    assert contracts.agent_context["visible_contract_count"] == 1
    assert contracts.agent_context["contracts"][0]["title"] == "The Saint's False Finger"
    assert "Crew Board: The Gilt Knives" in crew_board.player_markdown
    assert crew_board.agent_context["crew"]["crew_id"] == crew["crew_id"]
    assert local_log_path.exists()
    local_log_text = local_log_path.read_text(encoding="utf-8")
    assert "contract.board.published" in local_log_text
    assert "crew.created" in local_log_text
