from __future__ import annotations

import json

from typer.testing import CliRunner

from hollow_lodge.client import cli
from hollow_lodge.client.cli import app


runner = CliRunner()


class FakeApi:
    calls: list[tuple[str, dict]]

    def __init__(self, *, server_url: str, token: str | None = None):
        self.server_url = server_url
        self.token = token
        self.calls = []

    def deals(self):
        self.calls.append(("deals", {}))
        return {
            "deals": [
                {
                    "deal_id": "deal_000001",
                    "contract_id": "contract_false_finger",
                    "proposer_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "status": "proposed",
                    "offered_artifact_ids": ["artifact_ledger_rubric"],
                    "requested_artifact_ids": ["artifact_chapel_debt_mark"],
                    "soft_terms": ["Do not cite us."],
                    "expires_phase": "Auction Preview",
                    "proposer_received_artifact_ids": [],
                    "recipient_received_artifact_ids": [],
                },
                {
                    "deal_id": "deal_000002",
                    "contract_id": "contract_false_finger",
                    "proposer_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "status": "fulfilled",
                    "offered_artifact_ids": ["artifact_ledger_rubric"],
                    "requested_artifact_ids": ["artifact_chapel_debt_mark"],
                    "soft_terms": [],
                    "expires_phase": None,
                    "proposer_received_artifact_ids": [
                        "artifact_chapel_debt_mark.dealcopy.deal_000002.crew_0001.2"
                    ],
                    "recipient_received_artifact_ids": [
                        "artifact_ledger_rubric.dealcopy.deal_000002.crew_0002.1"
                    ],
                },
            ]
        }

    def propose_deal(
        self,
        *,
        contract_id: str,
        proposer_crew_id: str,
        recipient_crew_id: str,
        offered_artifact_ids: list[str] | tuple[str, ...],
        requested_artifact_ids: list[str] | tuple[str, ...],
        soft_terms: list[str] | tuple[str, ...],
        expires_phase: str | None,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "propose_deal",
                {
                    "contract_id": contract_id,
                    "proposer_crew_id": proposer_crew_id,
                    "recipient_crew_id": recipient_crew_id,
                    "offered_artifact_ids": list(offered_artifact_ids),
                    "requested_artifact_ids": list(requested_artifact_ids),
                    "soft_terms": list(soft_terms),
                    "expires_phase": expires_phase,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"deal_id": "deal_000001", "status": "proposed"}

    def accept_deal(self, *, deal_id: str, idempotency_key: str):
        self.calls.append(
            ("accept_deal", {"deal_id": deal_id, "idempotency_key": idempotency_key})
        )
        return {"deal_id": deal_id, "status": "fulfilled"}

    def decline_deal(self, *, deal_id: str, idempotency_key: str):
        self.calls.append(
            ("decline_deal", {"deal_id": deal_id, "idempotency_key": idempotency_key})
        )
        return {"deal_id": deal_id, "status": "declined"}

    def cancel_deal(self, *, deal_id: str, idempotency_key: str):
        self.calls.append(
            ("cancel_deal", {"deal_id": deal_id, "idempotency_key": idempotency_key})
        )
        return {"deal_id": deal_id, "status": "canceled"}


def test_deal_propose_requires_from_crew_when_no_active_crew(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(
        '{"server_url":"http://example.test","player_id":"player_0001","display_name":"Ada","token":"token","active_crew_id":null}\n'
    )

    result = runner.invoke(
        app,
        [
            "deal",
            "propose",
            "--to-crew",
            "crew_0002",
            "--offer",
            "artifact_ledger_rubric",
            "--request",
            "artifact_chapel_debt_mark",
            "--config",
            str(config),
        ],
    )

    assert result.exit_code != 0
    assert "from crew required" in result.output


def test_deal_list_calls_api_and_prints_deal_id_and_status(tmp_path, monkeypatch):
    created_clients: list[FakeApi] = []
    config = _write_config(tmp_path)

    monkeypatch.setattr(cli, "HollowLodgeApi", _fake_client_factory(created_clients))

    result = runner.invoke(app, ["deal", "list", "--config", str(config)])

    assert result.exit_code == 0
    assert "deal_000001 proposed" in result.output
    assert "deal_000002 fulfilled" in result.output
    assert created_clients[0].calls == [("deals", {})]


def test_deal_show_prints_full_terms(tmp_path, monkeypatch):
    created_clients: list[FakeApi] = []
    config = _write_config(tmp_path)

    monkeypatch.setattr(cli, "HollowLodgeApi", _fake_client_factory(created_clients))

    result = runner.invoke(app, ["deal", "show", "deal_000001", "--config", str(config)])

    assert result.exit_code == 0
    assert "deal_000001 proposed: crew_0001 offers artifact_ledger_rubric for artifact_chapel_debt_mark" in result.output
    assert "Soft term: Do not cite us." in result.output
    assert "Expires: Auction Preview" in result.output
    assert created_clients[0].calls == [("deals", {})]


def test_deal_preview_accept_prints_consequences(tmp_path, monkeypatch):
    created_clients: list[FakeApi] = []
    config = _write_config(tmp_path, active_crew_id="crew_0002")

    monkeypatch.setattr(cli, "HollowLodgeApi", _fake_client_factory(created_clients))

    result = runner.invoke(
        app,
        ["deal", "preview-accept", "deal_000001", "--config", str(config)],
    )

    assert result.exit_code == 0
    assert "Acceptance preview: deal_000001" in result.output
    assert "Your crew gives: artifact_chapel_debt_mark" in result.output
    assert "Your crew receives: artifact_ledger_rubric" in result.output
    assert "Soft terms are recorded but not enforced by the server." in result.output
    assert "This preview does not accept the deal." in result.output
    assert created_clients[0].calls == [("deals", {})]


def test_deal_propose_uses_active_crew_and_passes_payload(tmp_path, monkeypatch):
    created_clients: list[FakeApi] = []
    config = _write_config(tmp_path, active_crew_id="crew_0001")

    monkeypatch.setattr(cli, "HollowLodgeApi", _fake_client_factory(created_clients))
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")

    preview = runner.invoke(
        app,
        [
            "deal",
            "propose",
            "--to-crew",
            "crew_0002",
            "--offer",
            "artifact_ledger_rubric",
            "--offer",
            "artifact_archive_photo",
            "--request",
            "artifact_chapel_debt_mark",
            "--soft-term",
            "Do not cite us.",
            "--config",
            str(config),
        ],
    )

    assert preview.exit_code == 0
    assert "Preview: propose_deal" in preview.output
    assert "No server mutation was submitted." in preview.output
    assert "- contract_id: contract_false_finger" in preview.output
    assert "- proposer_crew_id: crew_0001" in preview.output
    assert "- recipient_crew_id: crew_0002" in preview.output
    assert "- offered_artifact_ids: ['artifact_ledger_rubric', 'artifact_archive_photo']" in preview.output
    assert "- requested_artifact_ids: ['artifact_chapel_debt_mark']" in preview.output
    assert "- soft_terms: ['Do not cite us.']" in preview.output
    assert "- expires_phase: None" in preview.output
    assert created_clients == []

    result = runner.invoke(
        app,
        [
            "deal",
            "propose",
            "--to-crew",
            "crew_0002",
            "--offer",
            "artifact_ledger_rubric",
            "--offer",
            "artifact_archive_photo",
            "--request",
            "artifact_chapel_debt_mark",
            "--soft-term",
            "Do not cite us.",
            "--confirm",
            "--config",
            str(config),
        ],
    )

    assert result.exit_code == 0
    assert result.output == "deal_000001 proposed\n"
    assert created_clients[0].calls == [
        (
            "propose_deal",
            {
                "contract_id": "contract_false_finger",
                "proposer_crew_id": "crew_0001",
                "recipient_crew_id": "crew_0002",
                "offered_artifact_ids": ["artifact_ledger_rubric", "artifact_archive_photo"],
                "requested_artifact_ids": ["artifact_chapel_debt_mark"],
                "soft_terms": ["Do not cite us."],
                "expires_phase": None,
                "idempotency_key": "deal-propose-key",
            },
        )
    ]


def test_deal_accept_prints_fulfilled(tmp_path, monkeypatch):
    result, created_clients = _invoke_deal_action(tmp_path, monkeypatch, "accept", confirm=True)

    assert result.exit_code == 0
    assert result.output == "deal_000001 fulfilled\n"
    assert created_clients[0].calls == [
        ("accept_deal", {"deal_id": "deal_000001", "idempotency_key": "deal-accept-key"})
    ]


def test_deal_decline_prints_declined(tmp_path, monkeypatch):
    result, created_clients = _invoke_deal_action(tmp_path, monkeypatch, "decline", confirm=True)

    assert result.exit_code == 0
    assert result.output == "deal_000001 declined\n"
    assert created_clients[0].calls == [
        ("decline_deal", {"deal_id": "deal_000001", "idempotency_key": "deal-decline-key"})
    ]


def test_deal_cancel_prints_canceled(tmp_path, monkeypatch):
    result, created_clients = _invoke_deal_action(tmp_path, monkeypatch, "cancel", confirm=True)

    assert result.exit_code == 0
    assert result.output == "deal_000001 canceled\n"
    assert created_clients[0].calls == [
        ("cancel_deal", {"deal_id": "deal_000001", "idempotency_key": "deal-cancel-key"})
    ]


def _invoke_deal_action(tmp_path, monkeypatch, action: str, *, confirm: bool = False):
    created_clients: list[FakeApi] = []
    config = _write_config(tmp_path)

    monkeypatch.setattr(cli, "HollowLodgeApi", _fake_client_factory(created_clients))
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")

    command = ["deal", action, "deal_000001"]
    if confirm:
        command.append("--confirm")
    command.extend(["--config", str(config)])
    result = runner.invoke(app, command)
    return result, created_clients


def _write_config(tmp_path, *, active_crew_id: str | None = "crew_0001"):
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "server_url": "http://example.test",
                "player_id": "player_0001",
                "display_name": "Ada",
                "token": "token",
                "active_crew_id": active_crew_id,
            }
        )
        + "\n"
    )
    return config


def _fake_client_factory(created_clients: list[FakeApi]):
    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    return fake_client
