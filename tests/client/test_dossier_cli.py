from __future__ import annotations

from typer.testing import CliRunner

from hollow_lodge.client import cli
from hollow_lodge.client.config import ClientConfig, save_config


class FakeApi:
    def __init__(self, *, server_url: str, token: str | None = None):
        self.calls = []

    def dossier(self, *, crew_id: str):
        self.calls.append(("dossier", {"crew_id": crew_id}))
        return {"crew_id": crew_id, "claim": "The finger is a false relic."}

    def add_dossier_evidence(self, *, crew_id: str, fragment_id: str, idempotency_key: str):
        self.calls.append(
            (
                "add_dossier_evidence",
                {"crew_id": crew_id, "fragment_id": fragment_id, "idempotency_key": idempotency_key},
            )
        )
        return {"crew_id": crew_id, "evidence_ids": [fragment_id]}

    def update_dossier_claim(self, *, crew_id: str, claim: str, idempotency_key: str):
        self.calls.append(
            (
                "update_dossier_claim",
                {"crew_id": crew_id, "claim": claim, "idempotency_key": idempotency_key},
            )
        )
        return {"crew_id": crew_id, "claim": claim}

    def vote_packet_lead(self, *, crew_id: str, player_id: str, idempotency_key: str):
        self.calls.append(
            (
                "vote_packet_lead",
                {"crew_id": crew_id, "player_id": player_id, "idempotency_key": idempotency_key},
            )
        )
        return {"crew_id": crew_id, "packet_lead_player_id": player_id}


def write_config(path):
    save_config(
        path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )


def test_dossier_commands_use_saved_config(tmp_path, monkeypatch):
    runner = CliRunner()
    clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")
    config_path = tmp_path / "config.json"
    write_config(config_path)

    view = runner.invoke(cli.app, ["dossier", "--config", str(config_path)])
    evidence = runner.invoke(
        cli.app,
        ["dossier", "add-evidence", "fragment_1", "--config", str(config_path)],
    )
    claim = runner.invoke(
        cli.app,
        ["dossier", "claim", "The finger is false.", "--config", str(config_path)],
    )
    vote = runner.invoke(
        cli.app,
        ["packet-lead", "vote", "player_0002", "--config", str(config_path)],
    )

    assert view.exit_code == 0
    assert evidence.exit_code == 0
    assert claim.exit_code == 0
    assert vote.exit_code == 0
    assert clients[1].calls == [
        (
            "add_dossier_evidence",
            {
                "crew_id": "crew_0001",
                "fragment_id": "fragment_1",
                "idempotency_key": "dossier-evidence-key",
            },
        )
    ]
    assert clients[2].calls == [
        (
            "update_dossier_claim",
            {
                "crew_id": "crew_0001",
                "claim": "The finger is false.",
                "idempotency_key": "dossier-claim-key",
            },
        )
    ]
    assert clients[3].calls == [
        (
            "vote_packet_lead",
            {
                "crew_id": "crew_0001",
                "player_id": "player_0002",
                "idempotency_key": "packet-lead-vote-key",
            },
        )
    ]
