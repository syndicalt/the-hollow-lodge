from __future__ import annotations

from typer.testing import CliRunner

from hollow_lodge.client import cli
from hollow_lodge.client.config import ClientConfig, save_config
from hollow_lodge.client.render import render_contract_board, render_inbox


BOARD = {
    "campaign": {"campaign_id": "campaign_saints_ledgers", "title": "Saints & Ledgers"},
    "contracts": [
        {
            "contract_id": "contract_false_finger",
            "title": "The Saint's False Finger",
            "phase": {"name": "Auction Preview", "remaining_hours": 6},
            "crew_heat": 0,
            "proof_dossier_needs": [
                "provenance chain",
                "material authenticity",
                "auction leverage",
            ],
        }
    ],
}

INBOX = {
    "player_id": "player_0001",
    "active_contracts": BOARD["contracts"],
    "incoming_proof_fragments": [],
}


class FakeApi:
    def __init__(self, *, server_url: str, token: str | None = None):
        self.server_url = server_url
        self.token = token

    def contracts(self):
        return BOARD

    def inbox(self):
        return INBOX


def test_contract_board_render_contains_starter_state():
    rendered = render_contract_board(BOARD)

    assert "The Saint's False Finger" in rendered
    assert "Auction Preview" in rendered
    assert "Crew Heat: 0" in rendered
    assert "provenance chain" in rendered


def test_inbox_render_contains_contract_and_notices():
    rendered = render_inbox(INBOX)

    assert "The Saint's False Finger" in rendered
    assert "incoming proof fragments: none" in rendered


def test_contracts_and_inbox_cli_render_api_results(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )

    contracts = runner.invoke(cli.app, ["contracts", "--config", str(config_path)])
    inbox = runner.invoke(cli.app, ["inbox", "--config", str(config_path)])

    assert contracts.exit_code == 0
    assert inbox.exit_code == 0
    assert "The Saint's False Finger" in contracts.output
    assert "incoming proof fragments: none" in inbox.output
