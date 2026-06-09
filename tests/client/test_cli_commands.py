from __future__ import annotations

from typer.testing import CliRunner

from hollow_lodge.client import cli
from hollow_lodge.client.config import (
    ClientConfig,
    OnboardingConfig,
    load_config,
    load_onboarding_config,
    save_config,
)


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
        return {"player_id": "player_0001", "display_name": display_name, "token": "secret-token"}

    def request_access_key(
        self,
        *,
        display_name: str,
        contact: str | None,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "request_access_key",
                {
                    "display_name": display_name,
                    "contact": contact,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {
            "request_id": "key_request_0001",
            "display_name": display_name,
            "status": "pending",
        }

    def health(self):
        self.calls.append(("health", {}))
        return {"status": "ok"}

    def create_invite(self, *, admin_token: str, idempotency_key: str):
        self.calls.append(
            (
                "create_invite",
                {
                    "admin_token": admin_token,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"invite_code": "lodge_invite_0001"}

    def list_key_requests(self, *, admin_token: str):
        self.calls.append(("list_key_requests", {"admin_token": admin_token}))
        return {
            "key_requests": [
                {
                    "request_id": "key_request_0001",
                    "display_name": "Ada",
                    "contact": "ada@example.com",
                    "status": "pending",
                }
            ]
        }

    def approve_key_request(
        self,
        *,
        request_id: str,
        admin_token: str,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "approve_key_request",
                {
                    "request_id": request_id,
                    "admin_token": admin_token,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {
            "request_id": request_id,
            "status": "approved",
            "invite_code": "lodge_invite_0001",
        }

    def list_invites(self, *, admin_token: str):
        self.calls.append(("list_invites", {"admin_token": admin_token}))
        return {"invites": [{"invite_id": "invite_0001", "used": False}]}

    def list_players(self, *, admin_token: str):
        self.calls.append(("list_players", {"admin_token": admin_token}))
        return {
            "players": [
                {
                    "player_id": "player_0001",
                    "display_name": "Ada",
                    "token_revoked": False,
                }
            ]
        }

    def get_player_detail(self, *, player_id: str, admin_token: str):
        self.calls.append(
            (
                "get_player_detail",
                {"player_id": player_id, "admin_token": admin_token},
            )
        )
        return {
            "player_id": player_id,
            "display_name": "Ada",
            "token_revoked": False,
            "crew_ids": ["crew_0001"],
            "crew_count": 1,
            "token_hash": "secret-hash",
            "join_code": "secret-join-code",
        }

    def verify_event_log(self, *, admin_token: str):
        self.calls.append(("verify_event_log", {"admin_token": admin_token}))
        return {"ok": True, "event_count": 7, "repaired_trailing_row": False}

    def export_event_log(self, *, admin_token: str):
        self.calls.append(("export_event_log", {"admin_token": admin_token}))
        return {"events": [{"sequence": 1, "type": "identity.player.registered"}]}

    def list_oracle_audits(self, *, admin_token: str):
        self.calls.append(("list_oracle_audits", {"admin_token": admin_token}))
        return {
            "audits": [
                {
                    "sequence": 9,
                    "event_id": "event_0009",
                    "event_type": "oracle.resolution.completed",
                    "contract_id": "contract_false_finger",
                    "phase": "auction-preview",
                    "provider": "deterministic",
                    "model": "deterministic-v1",
                    "validation_status": "validated",
                    "fallback": False,
                    "crew_count": 2,
                    "standing_count": 2,
                    "warning_count": 1,
                    "input_packet_hash": "input-hash",
                    "accepted_output_hash": "output-hash",
                    "accepted_output": {"raw": "must not print"},
                    "hidden_truth_summary": "must not print",
                }
            ]
        }

    def activate_contract_seed(
        self,
        *,
        seed: dict,
        admin_token: str,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "activate_contract_seed",
                {
                    "seed": seed,
                    "admin_token": admin_token,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"contract_id": seed["contract"]["contract_id"], "lifecycle_status": "active"}

    def archive_contract(
        self,
        *,
        contract_id: str,
        admin_token: str,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "archive_contract",
                {
                    "contract_id": contract_id,
                    "admin_token": admin_token,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"contract_id": contract_id, "lifecycle_status": "archived"}

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
                "event_id": "evt_7",
                "sequence": 7,
                "type": "chat.message.created",
                "payload": {
                    "message_id": "msg_000007",
                    "sender_player_id": "player_0001",
                    "sender_crew_id": "crew_a",
                    "recipient_crew_id": "crew_b",
                    "body": "No public claims until lock.",
                },
            }
        ]

    def visible_events_since(self, *, since_sequence: int):
        self.calls.append(("visible_events_since", {"since_sequence": since_sequence}))
        return [
            {
                "event_id": "evt_8",
                "sequence": 8,
                "type": "chat.message.created",
                "payload": {"sender_player_id": "player_0002", "body": "Ledger moved."},
            }
        ]

    def contracts(self):
        self.calls.append(("contracts", {}))
        return {
            "campaign": {"title": "Saints & Ledgers"},
            "contracts": [
                {
                    "title": "The Saint's False Finger",
                    "phase": {"name": "Auction Preview", "remaining_hours": 6},
                    "crew_heat": 0,
                    "proof_dossier_needs": ["provenance chain"],
                }
            ],
        }

    def inbox(self):
        self.calls.append(("inbox", {}))
        return {
            "player_id": "player_0001",
            "active_contracts": [
                {
                    "title": "The Saint's False Finger",
                    "phase": {"name": "Auction Preview"},
                }
            ],
            "incoming_proof_fragments": [],
        }

    def crew_board(self, *, crew_id: str):
        self.calls.append(("crew_board", {"crew_id": crew_id}))
        return {
            "player_id": "player_0001",
            "crew": {
                "crew_id": crew_id,
                "name": "The Gilt Knives",
                "member_ids": ["player_0001", "player_0002"],
                "member_count": 2,
                "ready_for_full_contracts": False,
                "readiness_warning": "Crews should have 3-5 players for full contracts.",
            },
            "active_contracts": [
                {
                    "title": "The Saint's False Finger",
                    "phase": {"name": "Auction Preview"},
                }
            ],
            "dossier": {
                "dossier_id": "dossier_crew_0001",
                "crew_id": crew_id,
                "packet_lead_player_id": "player_0001",
                "claim": "",
                "evidence_ids": [],
                "member_contributions": [],
            },
        }

    def artifacts(self):
        self.calls.append(("artifacts", {}))
        return {
            "contract_id": "contract_false_finger",
            "artifacts": [
                {
                    "artifact_id": "artifact_lot_card",
                    "title": "Auction Lot Card",
                    "kind": "lot_card",
                    "public_summary": "Public lot card.",
                },
                {
                    "artifact_id": "artifact_ledger_rubric",
                    "title": "Red Ledger Rubric",
                    "kind": "ledger",
                    "public_summary": "Copied rubric.",
                },
            ],
            "edges": [
                {
                    "source_id": "artifact_lot_card",
                    "target_id": "artifact_ledger_rubric",
                    "relation": "contradicts",
                    "public_summary": "The dates do not agree.",
                }
            ],
        }

    def artifact(self, *, artifact_id: str):
        self.calls.append(("artifact", {"artifact_id": artifact_id}))
        return {
            "artifact_id": artifact_id,
            "title": "Red Ledger Rubric",
            "kind": "ledger",
            "public_summary": "A copied rubric marks prior ownership.",
            "full_text": "Lot 19 passed under chapel seal.",
            "source_chain": ["archive:lot-card"],
        }

    def transfer_artifact(
        self,
        *,
        artifact_id: str,
        recipient_player_id: str,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "transfer_artifact",
                {
                    "artifact_id": artifact_id,
                    "recipient_player_id": recipient_player_id,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"artifact_id": f"{artifact_id}.copy.{recipient_player_id}.1"}

    def transfer_proof_fragment(
        self,
        *,
        fragment_id: str,
        recipient_player_id: str,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "transfer_proof_fragment",
                {
                    "fragment_id": fragment_id,
                    "recipient_player_id": recipient_player_id,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"fragment_id": f"{fragment_id}.copy.{recipient_player_id}.1"}

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

    def send_crew_message(self, *, crew_id: str, body: str, idempotency_key: str):
        self.calls.append(
            (
                "send_crew_message",
                {"crew_id": crew_id, "body": body, "idempotency_key": idempotency_key},
            )
        )
        return {"message_id": "msg_crew"}

    def send_crew_to_crew_message(
        self,
        *,
        sender_crew_id: str,
        recipient_crew_id: str,
        body: str,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "send_crew_to_crew_message",
                {
                    "sender_crew_id": sender_crew_id,
                    "recipient_crew_id": recipient_crew_id,
                    "body": body,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"message_id": "msg_crew_to_crew"}

    def dossier(self, *, crew_id: str):
        self.calls.append(("dossier", {"crew_id": crew_id}))
        return {
            "crew_id": crew_id,
            "packet_lead_player_id": "player_0001",
            "claim": "likely false relic",
        }

    def add_dossier_evidence(self, *, crew_id: str, fragment_id: str, idempotency_key: str):
        self.calls.append(
            (
                "add_dossier_evidence",
                {
                    "crew_id": crew_id,
                    "fragment_id": fragment_id,
                    "idempotency_key": idempotency_key,
                },
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

    def update_dossier_framing(
        self,
        *,
        crew_id: str,
        claim: str | None,
        evidence_ids: list[str] | None,
        reasoning: str | None,
        weaknesses: str | None,
        provenance_concerns: str | None,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "update_dossier_framing",
                {
                    "crew_id": crew_id,
                    "claim": claim,
                    "evidence_ids": evidence_ids,
                    "reasoning": reasoning,
                    "weaknesses": weaknesses,
                    "provenance_concerns": provenance_concerns,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"crew_id": crew_id, "claim": claim}

    def cite_artifact_in_dossier(
        self,
        *,
        crew_id: str,
        artifact_id: str,
        claim: str,
        quote: str,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "cite_artifact_in_dossier",
                {
                    "crew_id": crew_id,
                    "artifact_id": artifact_id,
                    "claim": claim,
                    "quote": quote,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"crew_id": crew_id, "artifact_id": artifact_id}

    def vote_packet_lead(self, *, crew_id: str, player_id: str, idempotency_key: str):
        self.calls.append(
            (
                "vote_packet_lead",
                {"crew_id": crew_id, "player_id": player_id, "idempotency_key": idempotency_key},
            )
        )
        return {"crew_id": crew_id, "packet_lead_player_id": player_id}

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

    def lock_auction_preview_phase(
        self,
        *,
        contract_id: str,
        hours_elapsed: int,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "lock_auction_preview_phase",
                {
                    "contract_id": contract_id,
                    "hours_elapsed": hours_elapsed,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"status": "resolved", "standings": [{"crew_id": "crew_0001", "score": 82}]}


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
        display_name="Ada",
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


def test_onboard_with_invite_registers_and_saves_local_config(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")
    config_path = tmp_path / "config.json"
    onboarding_path = tmp_path / "onboarding.json"

    result = runner.invoke(
        cli.app,
        [
            "onboard",
            "--server",
            "http://testserver",
            "--name",
            "Ada",
            "--invite",
            "invite-a",
            "--config",
            str(config_path),
            "--onboarding-state",
            str(onboarding_path),
        ],
    )

    assert result.exit_code == 0
    assert "registered player_0001" in result.output
    assert load_config(config_path) == ClientConfig(
        server_url="http://testserver",
        player_id="player_0001",
        display_name="Ada",
        token="secret-token",
    )
    assert onboarding_path.exists() is False
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


def test_onboard_without_invite_requests_access_key_and_saves_pending_state(
    tmp_path,
    monkeypatch,
):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")
    config_path = tmp_path / "config.json"
    onboarding_path = tmp_path / "onboarding.json"

    result = runner.invoke(
        cli.app,
        [
            "onboard",
            "--server",
            "http://testserver",
            "--name",
            "Ada",
            "--contact",
            "ada@example.com",
            "--config",
            str(config_path),
            "--onboarding-state",
            str(onboarding_path),
        ],
    )

    assert result.exit_code == 0
    assert "pending key_request_0001" in result.output
    assert config_path.exists() is False
    assert load_onboarding_config(onboarding_path) == OnboardingConfig(
        server_url="http://testserver",
        display_name="Ada",
        contact="ada@example.com",
        request_id="key_request_0001",
        status="pending",
    )
    assert created_clients[0].calls == [
        (
            "request_access_key",
            {
                "display_name": "Ada",
                "contact": "ada@example.com",
                "idempotency_key": "key-request-key",
            },
        )
    ]


def test_onboard_defaults_to_official_server_for_access_request(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")

    result = runner.invoke(
        cli.app,
        [
            "onboard",
            "--name",
            "Ada",
            "--onboarding-state",
            str(tmp_path / "onboarding.json"),
            "--config",
            str(tmp_path / "config.json"),
        ],
    )

    assert result.exit_code == 0
    assert cli.DEFAULT_SERVER_URL == "https://server.thehollowlodge.com"
    assert created_clients[0].server_url == cli.DEFAULT_SERVER_URL


def test_doctor_reports_registered_player_and_mcp_without_secret_material(
    tmp_path,
    monkeypatch,
):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    config_path = tmp_path / "config.json"
    onboarding_path = tmp_path / "onboarding.json"
    codex_config = tmp_path / "codex.toml"
    codex_config.write_text(
        '[mcp_servers."the-hollow-lodge"]\ncommand = "hollow-lodge-mcp"\n',
        encoding="utf-8",
    )
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="secret-token",
            display_name="Ada",
            active_crew_id="crew_0001",
        ),
    )

    result = runner.invoke(
        cli.app,
        [
            "doctor",
            "--config",
            str(config_path),
            "--onboarding-state",
            str(onboarding_path),
            "--codex-config",
            str(codex_config),
        ],
    )

    assert result.exit_code == 0
    assert "cli: The Hollow Lodge" in result.output
    assert "server: ok http://testserver" in result.output
    assert "player: registered player_0001 display=Ada active_crew=crew_0001" in result.output
    assert f"mcp: registered {codex_config}" in result.output
    assert "secret-token" not in result.output
    assert created_clients[0].calls == [("health", {})]


def test_doctor_reports_pending_onboarding_without_contact(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    config_path = tmp_path / "missing-config.json"
    onboarding_path = tmp_path / "onboarding.json"
    codex_config = tmp_path / "codex.toml"
    onboarding_path.write_text(
        (
            '{"server_url":"http://pending-server","display_name":"Ada",'
            '"contact":"ada@example.com","request_id":"key_request_0001",'
            '"status":"pending"}\n'
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        cli.app,
        [
            "doctor",
            "--config",
            str(config_path),
            "--onboarding-state",
            str(onboarding_path),
            "--codex-config",
            str(codex_config),
        ],
    )

    assert result.exit_code == 0
    assert "server: ok http://pending-server" in result.output
    assert "player: pending key_request_0001 status=pending display=Ada" in result.output
    assert f"mcp: missing {codex_config}" in result.output
    assert "ada@example.com" not in result.output
    assert created_clients[0].calls == [("health", {})]


def test_doctor_reports_unconfigured_install_and_unreachable_server(tmp_path, monkeypatch):
    runner = CliRunner()

    class FailingApi(FakeApi):
        def health(self):
            self.calls.append(("health", {}))
            raise RuntimeError("connection failed with secret-token")

    monkeypatch.setattr(cli, "HollowLodgeApi", FailingApi)

    result = runner.invoke(
        cli.app,
        [
            "doctor",
            "--server",
            "http://downstream",
            "--config",
            str(tmp_path / "missing-config.json"),
            "--onboarding-state",
            str(tmp_path / "missing-onboarding.json"),
            "--codex-config",
            str(tmp_path / "missing-codex.toml"),
        ],
    )

    assert result.exit_code == 0
    assert "server: unreachable http://downstream" in result.output
    assert "player: not configured" in result.output
    assert "mcp: missing" in result.output
    assert "secret-token" not in result.output


def test_admin_invite_create_command_uses_admin_token_without_player_auth(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "invite-create",
            "--server",
            "http://testserver",
            "--admin-token",
            "admin-secret",
        ],
    )

    assert result.exit_code == 0
    assert result.output == "lodge_invite_0001\n"
    assert created_clients[0].token is None
    assert created_clients[0].calls == [
        (
            "create_invite",
            {
                "admin_token": "admin-secret",
                "idempotency_key": "admin-invite-create-key",
            },
        )
    ]


def test_admin_key_requests_command_lists_requests(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "key-requests",
            "--server",
            "http://testserver",
            "--admin-token",
            "admin-secret",
        ],
    )

    assert result.exit_code == 0
    assert "key_request_0001 pending Ada ada@example.com" in result.output
    assert created_clients[0].token is None
    assert created_clients[0].calls == [
        ("list_key_requests", {"admin_token": "admin-secret"})
    ]


def test_admin_key_request_approve_command_prints_invite(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "key-request-approve",
            "key_request_0001",
            "--server",
            "http://testserver",
            "--admin-token",
            "admin-secret",
        ],
    )

    assert result.exit_code == 0
    assert result.output == "lodge_invite_0001\n"
    assert created_clients[0].token is None
    assert created_clients[0].calls == [
        (
            "approve_key_request",
            {
                "request_id": "key_request_0001",
                "admin_token": "admin-secret",
                "idempotency_key": "admin-key-request-approve-key",
            },
        )
    ]


def test_admin_invites_command_lists_inventory_without_player_auth(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "invites",
            "--server",
            "http://testserver",
            "--admin-token",
            "admin-secret",
        ],
    )

    assert result.exit_code == 0
    assert "invite_0001 unused" in result.output
    assert created_clients[0].token is None
    assert created_clients[0].calls == [("list_invites", {"admin_token": "admin-secret"})]


def test_admin_players_command_lists_player_lookup(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "players",
            "--server",
            "http://testserver",
            "--admin-token",
            "admin-secret",
        ],
    )

    assert result.exit_code == 0
    assert "player_0001 active Ada" in result.output
    assert created_clients[0].calls == [("list_players", {"admin_token": "admin-secret"})]


def test_admin_player_command_shows_sanitized_player_detail(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "player",
            "player_0001",
            "--server",
            "http://testserver",
            "--admin-token",
            "admin-secret",
        ],
    )

    assert result.exit_code == 0
    assert "player_0001 active Ada" in result.output
    assert "crews: crew_0001" in result.output
    assert "secret-hash" not in result.output
    assert "secret-join-code" not in result.output
    assert created_clients[0].calls == [
        (
            "get_player_detail",
            {"player_id": "player_0001", "admin_token": "admin-secret"},
        )
    ]


def test_admin_event_log_commands_verify_and_export(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    output_path = tmp_path / "events.json"

    verify = runner.invoke(
        cli.app,
        [
            "admin",
            "event-log-verify",
            "--server",
            "http://testserver",
            "--admin-token",
            "admin-secret",
        ],
    )
    export = runner.invoke(
        cli.app,
        [
            "admin",
            "event-log-export",
            "--server",
            "http://testserver",
            "--admin-token",
            "admin-secret",
            "--output",
            str(output_path),
        ],
    )

    assert verify.exit_code == 0
    assert "ok 7 events" in verify.output
    assert export.exit_code == 0
    assert f"wrote {output_path}" in export.output
    assert '"identity.player.registered"' in output_path.read_text(encoding="utf-8")
    assert created_clients[0].calls == [("verify_event_log", {"admin_token": "admin-secret"})]
    assert created_clients[1].calls == [("export_event_log", {"admin_token": "admin-secret"})]


def test_admin_oracle_audits_command_lists_redacted_audits(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "oracle-audits",
            "--server",
            "http://testserver",
            "--admin-token",
            "admin-secret",
        ],
    )

    assert result.exit_code == 0
    assert (
        "9 oracle.resolution.completed contract_false_finger auction-preview "
        "deterministic/deterministic-v1 validated primary "
        "crews=2 standings=2 warnings=1 input=input-hash output=output-hash"
    ) in result.output
    assert "accepted_output" not in result.output
    assert "hidden_truth_summary" not in result.output
    assert "must not print" not in result.output
    assert created_clients[0].calls == [
        ("list_oracle_audits", {"admin_token": "admin-secret"})
    ]


def test_admin_contract_activate_command_reads_seed_file(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "contract-activate",
            "--server",
            "http://testserver",
            "--admin-token",
            "admin-secret",
            "--seed-file",
            "tests/fixtures/ash_window_contract.json",
        ],
    )

    assert result.exit_code == 0
    assert result.output == "contract_ash_window active\n"
    assert created_clients[0].token is None
    assert created_clients[0].calls[0][0] == "activate_contract_seed"
    assert created_clients[0].calls[0][1]["seed"]["contract"]["contract_id"] == "contract_ash_window"
    assert created_clients[0].calls[0][1]["admin_token"] == "admin-secret"
    assert created_clients[0].calls[0][1]["idempotency_key"] == "admin-contract-activate-key"


def test_admin_contract_archive_command_calls_server(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "contract-archive",
            "contract_ash_window",
            "--server",
            "http://testserver",
            "--admin-token",
            "admin-secret",
        ],
    )

    assert result.exit_code == 0
    assert result.output == "contract_ash_window archived\n"
    assert created_clients[0].token is None
    assert created_clients[0].calls == [
        (
            "archive_contract",
            {
                "contract_id": "contract_ash_window",
                "admin_token": "admin-secret",
                "idempotency_key": "admin-contract-archive-key",
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


def test_artifact_transfer_command_uses_saved_config(tmp_path, monkeypatch):
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
        [
            "artifact-transfer",
            "artifact_ledger_rubric",
            "player_0002",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    assert result.output == "artifact_ledger_rubric.copy.player_0002.1 transferred\n"
    assert created_clients[0].calls == [
        (
            "transfer_artifact",
            {
                "artifact_id": "artifact_ledger_rubric",
                "recipient_player_id": "player_0002",
                "idempotency_key": "artifact-transfer-key",
            },
        )
    ]


def test_proof_transfer_command_uses_saved_config(tmp_path, monkeypatch):
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
        [
            "proof",
            "transfer",
            "fragment_starter_ledger",
            "player_0002",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    assert result.output == "fragment_starter_ledger.copy.player_0002.1 transferred\n"
    assert created_clients[0].calls == [
        (
            "transfer_proof_fragment",
            {
                "fragment_id": "fragment_starter_ledger",
                "recipient_player_id": "player_0002",
                "idempotency_key": "proof-transfer-key",
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


def test_crew_chat_commands_use_active_crew(tmp_path, monkeypatch):
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

    crew_result = runner.invoke(
        cli.app,
        ["crew", "Meet by the archive.", "--config", str(config_path)],
    )
    crew_msg_result = runner.invoke(
        cli.app,
        ["crew-msg", "crew_0002", "Trade the ledger?", "--config", str(config_path)],
    )

    assert crew_result.exit_code == 0
    assert crew_msg_result.exit_code == 0
    assert created_clients[0].calls == [
        (
            "send_crew_message",
            {
                "crew_id": "crew_0001",
                "body": "Meet by the archive.",
                "idempotency_key": "chat-crew-key",
            },
        )
    ]
    assert created_clients[1].calls == [
        (
            "send_crew_to_crew_message",
            {
                "sender_crew_id": "crew_0001",
                "recipient_crew_id": "crew_0002",
                "body": "Trade the ledger?",
                "idempotency_key": "chat-crew-to-crew-key",
            },
        )
    ]


def test_board_commands_render_contracts_and_inbox(tmp_path, monkeypatch):
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

    contracts_result = runner.invoke(cli.app, ["contracts", "--config", str(config_path)])
    inbox_result = runner.invoke(cli.app, ["inbox", "--config", str(config_path)])

    assert contracts_result.exit_code == 0
    assert "The Saint's False Finger" in contracts_result.output
    assert inbox_result.exit_code == 0
    assert "Inbox: player_0001" in inbox_result.output
    assert created_clients[0].calls == [("contracts", {})]
    assert created_clients[1].calls == [("inbox", {})]


def test_contracts_can_emit_render_packet_json(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )

    result = runner.invoke(cli.app, ["contracts", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    assert '"surface":"contract_board"' in result.output
    assert "The Saint's False Finger" in result.output


def test_inbox_can_emit_render_packet_json(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )

    result = runner.invoke(cli.app, ["inbox", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    assert '"surface":"inbox"' in result.output
    assert '"player_id":"player_0001"' in result.output


def test_crew_board_command_uses_active_crew_and_can_emit_json(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
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

    result = runner.invoke(cli.app, ["crew-board", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    assert '"surface":"crew_board"' in result.output
    assert '"crew_id":"crew_0001"' in result.output


def test_artifacts_command_prints_known_artifact_title(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )

    result = runner.invoke(cli.app, ["artifacts", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "Auction Lot Card" in result.output
    assert "contradicts" in result.output


def test_artifact_command_prints_source_material(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )

    result = runner.invoke(
        cli.app,
        ["artifact", "artifact_ledger_rubric", "--config", str(config_path)],
    )

    assert result.exit_code == 0
    assert "Lot 19 passed under chapel seal." in result.output
    assert "archive:lot-card" in result.output


def test_artifacts_can_emit_render_packet_json(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )

    result = runner.invoke(cli.app, ["artifacts", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    assert '"surface":"artifact_graph"' in result.output
    assert "Auction Lot Card" in result.output


def test_sync_command_fetches_delta_into_local_log(tmp_path, monkeypatch):
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
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )

    result = runner.invoke(
        cli.app,
        ["sync", "--config", str(config_path), "--local-log", str(local_log_path)],
    )

    assert result.exit_code == 0
    assert "synced 1 events" in result.output
    assert created_clients[0].calls == [("visible_events", {})]
    assert "No public claims until lock." in local_log_path.read_text()


def test_replay_command_renders_local_perspective_log(tmp_path):
    runner = CliRunner()
    local_log_path = tmp_path / "local.jsonl"
    LocalEventLog = cli.LocalEventLog
    log = LocalEventLog(local_log_path)
    log.sync_visible_server_events(
        [
            {
                "event_id": "evt_8",
                "sequence": 8,
                "type": "chat.message.created",
                "payload": {"sender_player_id": "player_0002", "body": "Ledger moved."},
            }
        ]
    )

    result = runner.invoke(cli.app, ["replay", "--since", "0", "--local-log", str(local_log_path)])

    assert result.exit_code == 0
    assert "8 player_0002: Ledger moved." in result.output


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


def test_dossier_commands_use_active_or_explicit_crew(tmp_path, monkeypatch):
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

    show_result = runner.invoke(cli.app, ["dossier", "--config", str(config_path)])
    evidence_result = runner.invoke(
        cli.app,
        ["dossier", "add-evidence", "fragment_copy", "--config", str(config_path)],
    )
    claim_result = runner.invoke(
        cli.app,
        ["dossier", "claim", "likely false relic", "--crew-id", "crew_0002", "--config", str(config_path)],
    )

    assert show_result.exit_code == 0
    assert evidence_result.exit_code == 0
    assert claim_result.exit_code == 0
    assert created_clients[0].calls == [("dossier", {"crew_id": "crew_0001"})]
    assert created_clients[1].calls == [
        (
            "add_dossier_evidence",
            {
                "crew_id": "crew_0001",
                "fragment_id": "fragment_copy",
                "idempotency_key": "dossier-evidence-key",
            },
        )
    ]
    assert created_clients[2].calls == [
        (
            "update_dossier_claim",
            {
                "crew_id": "crew_0002",
                "claim": "likely false relic",
                "idempotency_key": "dossier-claim-key",
            },
        )
    ]


def test_dossier_artifact_citation_and_frame_commands_use_active_crew(tmp_path, monkeypatch):
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

    cite_result = runner.invoke(
        cli.app,
        [
            "dossier",
            "cite-artifact",
            "artifact_ledger_rubric",
            "--claim",
            "The ledger contradicts the lot card.",
            "--quote",
            "The last hand is later.",
            "--config",
            str(config_path),
        ],
    )
    frame_result = runner.invoke(
        cli.app,
        [
            "dossier",
            "frame",
            "--claim",
            "The relic is false.",
            "--evidence-id",
            "fragment_1",
            "--evidence-id",
            "artifact_ledger_rubric",
            "--reasoning",
            "The records disagree.",
            "--provenance-concerns",
            "Copied hand.",
            "--config",
            str(config_path),
        ],
    )

    assert cite_result.exit_code == 0
    assert frame_result.exit_code == 0
    assert created_clients[0].calls == [
        (
            "cite_artifact_in_dossier",
            {
                "crew_id": "crew_0001",
                "artifact_id": "artifact_ledger_rubric",
                "claim": "The ledger contradicts the lot card.",
                "quote": "The last hand is later.",
                "idempotency_key": "dossier-cite-artifact-key",
            },
        )
    ]
    assert created_clients[1].calls == [
        (
            "update_dossier_framing",
            {
                "crew_id": "crew_0001",
                "claim": "The relic is false.",
                "evidence_ids": ["fragment_1", "artifact_ledger_rubric"],
                "reasoning": "The records disagree.",
                "weaknesses": None,
                "provenance_concerns": "Copied hand.",
                "idempotency_key": "dossier-frame-key",
            },
        )
    ]


def test_packet_lead_vote_command_uses_active_crew(tmp_path, monkeypatch):
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
        ["packet-lead", "vote", "player_0002", "--config", str(config_path)],
    )

    assert result.exit_code == 0
    assert created_clients[0].calls == [
        (
            "vote_packet_lead",
            {
                "crew_id": "crew_0001",
                "player_id": "player_0002",
                "idempotency_key": "packet-lead-vote-key",
            },
        )
    ]


def test_phase_preview_lock_only_reads_contracts(tmp_path, monkeypatch):
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
        [
            "phase",
            "preview-lock",
            "--hours-elapsed",
            "6",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    assert "preview only" in result.output
    assert "no server mutation occurred" in result.output
    assert created_clients[0].calls == [("contracts", {})]


def test_phase_lock_requires_confirm_before_mutation(tmp_path, monkeypatch):
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

    unconfirmed = runner.invoke(
        cli.app,
        [
            "phase",
            "lock",
            "--hours-elapsed",
            "6",
            "--config",
            str(config_path),
        ],
    )

    assert unconfirmed.exit_code == 0
    assert "no server mutation occurred" in unconfirmed.output
    assert "--confirm" in unconfirmed.output
    assert created_clients == []

    confirmed = runner.invoke(
        cli.app,
        [
            "phase",
            "lock",
            "--hours-elapsed",
            "6",
            "--confirm",
            "--config",
            str(config_path),
        ],
    )

    assert confirmed.exit_code == 0
    assert "resolved" in confirmed.output
    assert created_clients[0].calls == [
        (
            "lock_auction_preview_phase",
            {
                "contract_id": "contract_false_finger",
                "hours_elapsed": 6,
                "idempotency_key": "phase-lock-key",
            },
        )
    ]
