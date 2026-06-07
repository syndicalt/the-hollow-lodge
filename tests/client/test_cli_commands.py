from __future__ import annotations

from typer.testing import CliRunner

from hollow_lodge.client import cli
from hollow_lodge.client.config import ClientConfig, load_config, save_config


class FakeApi:
    calls: list[tuple[str, dict]]

    def __init__(self, *, server_url: str, token: str | None = None):
        self.server_url = server_url
        self.token = token
        self.calls = []

    def register(self, *, invite_code: str, display_name: str, idempotency_key: str):
        self.calls.append(
            (
                "register",
                {
                    "invite_code": invite_code,
                    "display_name": display_name,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"player_id": "player_0001", "token": "secret-token"}

    def create_crew(self, *, name: str, idempotency_key: str):
        self.calls.append(("create_crew", {"name": name, "idempotency_key": idempotency_key}))
        return {"crew_id": "crew_0001", "join_code": "join-secret"}

    def join_crew(self, *, crew_id: str, join_code: str, idempotency_key: str):
        self.calls.append(
            (
                "join_crew",
                {
                    "crew_id": crew_id,
                    "join_code": join_code,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"crew_id": crew_id}

    def send_direct_message(
        self,
        *,
        recipient_player_id: str,
        body: str,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "send_direct_message",
                {
                    "recipient_player_id": recipient_player_id,
                    "body": body,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"message_id": "msg_000001", "conversation_id": "msg_000001"}

    def visible_events(self):
        self.calls.append(("visible_events", {}))
        return [
            {
                "sequence": 7,
                "payload": {
                    "message_id": "msg_000007",
                    "sender_player_id": "player_0001",
                    "sender_crew_id": "crew_a",
                    "recipient_crew_id": "crew_b",
                    "body": "No public claims until lock.",
                },
            }
        ]

    def check_provenance(self, *, fragment_id: str, idempotency_key: str):
        self.calls.append(
            (
                "check_provenance",
                {"fragment_id": fragment_id, "idempotency_key": idempotency_key},
            )
        )
        return {
            "fragment_id": fragment_id,
            "provenance_checked": True,
            "provenance_flags": ["copied-hand", "ink-after-binding"],
        }


def test_register_command_saves_local_config(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")
    config_path = tmp_path / "config.json"

    result = runner.invoke(
        cli.app,
        [
            "register",
            "--server",
            "http://testserver",
            "--invite",
            "invite-a",
            "--name",
            "Ada",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    assert load_config(config_path) == ClientConfig(
        server_url="http://testserver",
        player_id="player_0001",
        token="secret-token",
    )
    assert created_clients[0].calls == [
        (
            "register",
            {
                "invite_code": "invite-a",
                "display_name": "Ada",
                "idempotency_key": "register-key",
            },
        )
    ]


def test_crew_commands_use_saved_config(tmp_path, monkeypatch):
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
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )

    create_result = runner.invoke(
        cli.app,
        ["crew-create", "The Gilt Knives", "--config", str(config_path)],
    )
    join_result = runner.invoke(
        cli.app,
        ["crew-join", "crew_0001", "--join-code", "join-secret", "--config", str(config_path)],
    )

    assert create_result.exit_code == 0
    assert join_result.exit_code == 0
    assert created_clients[0].calls == [
        ("create_crew", {"name": "The Gilt Knives", "idempotency_key": "crew-create-key"})
    ]
    assert created_clients[1].calls == [
        (
            "join_crew",
            {
                "crew_id": "crew_0001",
                "join_code": "join-secret",
                "idempotency_key": "crew-join-key",
            },
        )
    ]


def test_direct_message_command_uses_saved_config(tmp_path, monkeypatch):
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
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )

    result = runner.invoke(
        cli.app,
        ["msg", "player_0002", "Trade the ledger?", "--config", str(config_path)],
    )

    assert result.exit_code == 0
    assert created_clients[0].calls == [
        (
            "send_direct_message",
            {
                "recipient_player_id": "player_0002",
                "body": "Trade the ledger?",
                "idempotency_key": "chat-direct-key",
            },
        )
    ]


def test_thread_command_renders_crew_to_crew_conversation_id(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )

    result = runner.invoke(
        cli.app,
        ["thread", "crew_a:crew_b", "--config", str(config_path)],
    )

    assert result.exit_code == 0
    assert "No public claims until lock." in result.output


def test_check_provenance_command_uses_saved_config(tmp_path, monkeypatch):
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
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )

    result = runner.invoke(
        cli.app,
        ["check", "fragment_starter_ledger", "provenance", "--config", str(config_path)],
    )

    assert result.exit_code == 0
    assert "copied-hand" in result.output
    assert created_clients[0].calls == [
        (
            "check_provenance",
            {
                "fragment_id": "fragment_starter_ledger",
                "idempotency_key": "proof-provenance-key",
            },
        )
    ]
