from pathlib import Path

from hollow_lodge.client.codex_session import CodexGameSession
from hollow_lodge.client.config import ClientConfig, save_config


class FakeApi:
    def __init__(self):
        self.synced = False

    def visible_events(self):
        self.synced = True
        return [
            {
                "event_id": "evt_1",
                "sequence": 1,
                "type": "chat.message.created",
                "payload": {"sender_player_id": "player_0002", "body": "The bell moved."},
            }
        ]

    def inbox(self):
        return {
            "player_id": "player_0001",
            "active_contracts": [],
            "incoming_proof_fragments": [],
        }

    def contracts(self):
        return {"campaign": {"title": "Saints & Ledgers"}, "contracts": []}

    def crew_board(self, *, crew_id: str):
        return {
            "player_id": "player_0001",
            "crew": {
                "crew_id": crew_id,
                "name": "The Gilt Knives",
                "member_ids": ["player_0001"],
                "member_count": 1,
                "ready_for_full_contracts": False,
                "readiness_warning": "Crews should have 3-5 players for full contracts.",
            },
            "active_contracts": [],
            "dossier": {
                "dossier_id": f"dossier_{crew_id}",
                "crew_id": crew_id,
                "packet_lead_player_id": "player_0001",
                "claim": "",
                "evidence_ids": [],
                "member_contributions": [],
            },
        }


def test_codex_session_syncs_before_rendering_inbox(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    fake_api = FakeApi()
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_inbox()

    assert fake_api.synced is True
    assert packet.surface == "inbox"
    assert "Inbox: player_0001" in packet.player_markdown
    assert "chat.message.created" in log_path.read_text()


def test_codex_session_uses_active_crew_for_crew_board(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=FakeApi())

    packet = session.render_crew_board()

    assert packet.surface == "crew_board"
    assert packet.agent_context["crew"]["crew_id"] == "crew_0001"
