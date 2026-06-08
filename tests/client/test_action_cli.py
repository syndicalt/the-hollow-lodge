from __future__ import annotations

from typer.testing import CliRunner

from hollow_lodge.client import cli
from hollow_lodge.client.config import ClientConfig, save_config


class FakeApi:
    def __init__(self, *, server_url: str, token: str | None = None):
        self.calls = []

    def submit_action(
        self,
        *,
        crew_id: str,
        intent: str,
        idempotency_key: str,
        rumor_id: str | None = None,
        rumor_response_mode: str | None = None,
        responds_to_rumor_escalation: bool = False,
        rumor_escalation_mode: str | None = None,
    ):
        self.calls.append(
            (
                "submit_action",
                {
                    "crew_id": crew_id,
                    "intent": intent,
                    "idempotency_key": idempotency_key,
                    "rumor_id": rumor_id,
                    "rumor_response_mode": rumor_response_mode,
                    "responds_to_rumor_escalation": responds_to_rumor_escalation,
                    "rumor_escalation_mode": rumor_escalation_mode,
                },
            )
        )
        result = {"action_id": "action_000001", "status": "submitted"}
        if rumor_id is not None:
            result["responds_to_rumor_id"] = rumor_id
        if responds_to_rumor_escalation:
            result["responds_to_rumor_escalation"] = True
        if rumor_escalation_mode is not None:
            result["rumor_escalation_mode"] = rumor_escalation_mode
        return result

    def edit_action(self, *, action_id: str, intent: str, idempotency_key: str):
        self.calls.append(
            (
                "edit_action",
                {"action_id": action_id, "intent": intent, "idempotency_key": idempotency_key},
            )
        )
        return {"action_id": action_id, "intent": intent, "status": "submitted"}

    def cancel_action(self, *, action_id: str, idempotency_key: str):
        self.calls.append(
            (
                "cancel_action",
                {"action_id": action_id, "idempotency_key": idempotency_key},
            )
        )
        return {"action_id": action_id, "status": "canceled"}


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
            "--rumor-id",
            "rumor_msg_000001",
            "--rumor-response-mode",
            "contain",
            "--responds-to-rumor-escalation",
            "--rumor-escalation-mode",
            "exploit",
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
                "rumor_id": "rumor_msg_000001",
                "rumor_response_mode": "contain",
                "responds_to_rumor_escalation": True,
                "rumor_escalation_mode": "exploit",
            },
        )
    ]


def test_action_edit_and_cancel_commands_call_server_routes_with_confirm(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )

    edited = runner.invoke(
        cli.app,
        [
            "action",
            "edit",
            "action_000001",
            "Inspect the ledger under candlelight.",
            "--config",
            str(config_path),
        ],
    )
    canceled = runner.invoke(
        cli.app,
        ["action", "cancel", "action_000001", "--confirm", "--config", str(config_path)],
    )

    assert edited.exit_code == 0
    assert "action_000001 submitted" in edited.output
    assert canceled.exit_code == 0
    assert "action_000001 canceled" in canceled.output
    assert created_clients[0].calls == [
        (
            "edit_action",
            {
                "action_id": "action_000001",
                "intent": "Inspect the ledger under candlelight.",
                "idempotency_key": "action-edit-key",
            },
        )
    ]
    assert created_clients[1].calls == [
        (
            "cancel_action",
            {
                "action_id": "action_000001",
                "idempotency_key": "action-cancel-key",
            },
        )
    ]


def test_action_cancel_without_confirm_does_not_call_server(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")
    config_path = tmp_path / "config.json"
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
        ["action", "cancel", "action_000001", "--config", str(config_path)],
    )

    assert result.exit_code == 0
    assert "no server mutation occurred" in result.output
    assert "--confirm" in result.output
    assert created_clients == []
