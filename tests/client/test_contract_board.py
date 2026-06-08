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


def test_contract_board_render_preserves_legacy_text():
    rendered = render_contract_board(BOARD)

    assert rendered == (
        "Saints & Ledgers\n"
        "The Saint's False Finger\n"
        "Phase: Auction Preview (6h remaining)\n"
        "Crew Heat: 0\n"
        "Proof dossier needs:\n"
        "- provenance chain\n"
        "- material authenticity\n"
        "- auction leverage"
    )


def test_inbox_render_preserves_legacy_text():
    rendered = render_inbox(INBOX)

    assert rendered == (
        "Inbox: player_0001\n"
        "The Saint's False Finger\n"
        "Phase: Auction Preview\n"
        "incoming proof fragments: none"
    )


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
    assert contracts.output == (
        "Saints & Ledgers\n"
        "The Saint's False Finger\n"
        "Phase: Auction Preview (6h remaining)\n"
        "Crew Heat: 0\n"
        "Proof dossier needs:\n"
        "- provenance chain\n"
        "- material authenticity\n"
        "- auction leverage\n"
    )
    assert inbox.output == (
        "Inbox: player_0001\n"
        "The Saint's False Finger\n"
        "Phase: Auction Preview\n"
        "incoming proof fragments: none\n"
    )
