from __future__ import annotations

from typer.testing import CliRunner

from hollow_lodge.client import cli
from hollow_lodge.client.config import ClientConfig, save_config


class FakeApi:
    def __init__(self, *, server_url: str, token: str | None = None):
        self.calls = []

    def submit_action(self, *, crew_id: str, intent: str, idempotency_key: str):
        self.calls.append(
            (
                "submit_action",
                {"crew_id": crew_id, "intent": intent, "idempotency_key": idempotency_key},
            )
        )
        return {"action_id": "action_000001", "status": "submitted"}


def test_act_command_stores_draft_without_confirmation(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    config_path = tmp_path / "config.json"
    local_log_path = tmp_path / "local.jsonl"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )

    result = runner.invoke(
        cli.app,
        [
            "act",
            "I inspect the red ledger rubric quietly.",
            "--config",
            str(config_path),
            "--local-log",
            str(local_log_path),
        ],
    )

    assert result.exit_code == 0
    assert "draft" in result.output
    assert created_clients == []
    assert "action.draft.normalized" in local_log_path.read_text()


def test_act_command_confirms_and_submits(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")
    config_path = tmp_path / "config.json"
    local_log_path = tmp_path / "local.jsonl"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )

    result = runner.invoke(
        cli.app,
        [
            "act",
            "I inspect the red ledger rubric quietly.",
            "--confirm",
            "--config",
            str(config_path),
            "--local-log",
            str(local_log_path),
        ],
    )

    assert result.exit_code == 0
    assert "action_000001" in result.output
    assert created_clients[0].calls == [
        (
            "submit_action",
            {
                "crew_id": "crew_0001",
                "intent": "I inspect the red ledger rubric quietly.",
                "idempotency_key": "action-submit-key",
            },
        )
    ]
