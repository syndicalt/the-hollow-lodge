from fastapi.testclient import TestClient

from hollow_lodge.client.api import HollowLodgeApi
from hollow_lodge.client.codex_session import CodexGameSession
from hollow_lodge.client.config import ClientConfig, save_config
from hollow_lodge.server.app import create_app


def test_codex_render_surfaces_show_player_and_agent_state(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path / "server", invite_codes=["a"])
    client = TestClient(app)
    registered = client.post(
        "/identity/register",
        json={"invite_code": "a", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-a"},
    ).json()
    crew = client.post(
        "/crews",
        json={"name": "The Gilt Knives"},
        headers={
            "Authorization": f"Bearer {registered['token']}",
            "Idempotency-Key": "crew-create-gilt",
        },
    ).json()
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
        path = url.removeprefix("http://testserver")
        return client.get(path, headers=headers, params=params)

    monkeypatch.setattr("httpx.get", fake_get)
    session = CodexGameSession(
        config_path=config_path,
        local_log_path=tmp_path / "local.jsonl",
        api=HollowLodgeApi(server_url="http://testserver", token=registered["token"]),
    )

    inbox = session.render_inbox()
    contracts = session.render_contract_board()
    crew_board = session.render_crew_board()

    assert inbox.surface == "inbox"
    assert contracts.surface == "contract_board"
    assert crew_board.surface == "crew_board"
    assert "The Saint's False Finger" in contracts.player_markdown
    assert crew_board.agent_context["crew"]["crew_id"] == crew["crew_id"]
