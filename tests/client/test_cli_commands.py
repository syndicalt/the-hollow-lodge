from __future__ import annotations

import json

from typer.testing import CliRunner

from hollow_lodge.client.backend_smoke import (
    CURRENT_PROJECTION_READ_SURFACES,
    CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT,
    CURRENT_PROJECTION_SCHEMA_VERSION,
)
from hollow_lodge.client.event_log_migration import create_event_log_manifest
from hollow_lodge.client import cli, codex_session
from hollow_lodge.client.config import (
    ClientConfig,
    OnboardingConfig,
    load_config,
    load_onboarding_config,
    save_config,
)
from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.eventlog.jsonl_store import JsonlEventStore


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

    def me(self):
        self.calls.append(("me", {}))
        return {"player_id": "player_0001"}

    def diagnostics(self):
        self.calls.append(("diagnostics", {}))
        return {
            "data": {
                "event_log": {
                    "backend": "jsonl",
                    "status": "available",
                    "event_count": 12,
                    "last_sequence": 12,
                    "last_event_hash": "event-hash-12",
                },
                "projection_db": {
                    "backend": "postgres",
                    "status": "available",
                    "lag": 0,
                    "last_sequence": 12,
                    "authoritative_last_sequence": 12,
                    "schema_version": CURRENT_PROJECTION_SCHEMA_VERSION,
                    "schema_migration_count": CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT,
                    "latest_schema_migration": CURRENT_PROJECTION_SCHEMA_VERSION,
                    "database_url": "postgresql://user:***@host:5432/hollow_lodge",
                },
                "projection_reads": {
                    "surfaces": {
                        surface: True for surface in CURRENT_PROJECTION_READ_SURFACES
                    }
                },
                "storage_guards": {
                    "require_postgres_event_log": False,
                    "require_postgres_projection": False,
                    "require_postgres_operational": False,
                },
                "projection_refresh": {
                    "status": "ok",
                    "last_context": "startup",
                    "last_success_sequence": 12,
                    "failure_count": 0,
                    "last_failure": None,
                },
                "identity_replay_store": {
                    "backend": "jsonl-sidecar",
                    "registration_replay_path": "/data/server-events.registration-replays.json",
                    "invite_replay_path": "/data/server-events.invite-replays.json",
                },
            }
        }

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

    def profile(self):
        self.calls.append(("profile", {}))
        return {
            "player_id": "player_0001",
            "display_name": "Ada",
            "crew_count": 1,
            "crews": [
                {
                    "crew_id": "crew_0001",
                    "name": "The Gilt Knives",
                    "active": True,
                }
            ],
        }

    def deals(self):
        self.calls.append(("deals", {}))
        return {"deals": getattr(self, "deals_payload", [])}

    def accept_deal(self, *, deal_id: str, idempotency_key: str):
        self.calls.append(
            (
                "accept_deal",
                {
                    "deal_id": deal_id,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"deal_id": deal_id, "status": "fulfilled"}

    def decline_deal(self, *, deal_id: str, idempotency_key: str):
        self.calls.append(
            (
                "decline_deal",
                {
                    "deal_id": deal_id,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"deal_id": deal_id, "status": "declined"}

    def cancel_deal(self, *, deal_id: str, idempotency_key: str):
        self.calls.append(
            (
                "cancel_deal",
                {
                    "deal_id": deal_id,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"deal_id": deal_id, "status": "canceled"}

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


def test_register_command_clears_pending_onboarding_state(tmp_path, monkeypatch):
    runner = CliRunner()

    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    monkeypatch.setattr(cli, "new_command_key", lambda prefix: f"{prefix}-key")
    config_path = tmp_path / "config.json"
    onboarding_path = tmp_path / "onboarding.json"
    onboarding_path.write_text(
        (
            '{"server_url":"http://testserver","display_name":"Ada",'
            '"contact":"ada@example.com","request_id":"key_request_0001",'
            '"status":"pending"}\n'
        ),
        encoding="utf-8",
    )

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
            "--onboarding-state",
            str(onboarding_path),
        ],
    )

    assert result.exit_code == 0
    assert load_config(config_path).player_id == "player_0001"
    assert onboarding_path.exists() is False


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
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/bin/{command}")
    config_path = tmp_path / "config.json"
    onboarding_path = tmp_path / "onboarding.json"
    codex_config = tmp_path / "codex.toml"
    local_log_path = tmp_path / "local.jsonl"
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
            "--local-log",
            str(local_log_path),
        ],
    )

    assert result.exit_code == 0
    assert "cli: The Hollow Lodge" in result.output
    assert "server: ok http://testserver" in result.output
    assert "player: registered player_0001 display=Ada active_crew=crew_0001" in result.output
    assert "auth: ok player_0001" in result.output
    assert "inbox: ok active_contracts=1" in result.output
    assert "event sync: ok synced=1 max_sequence=7" in result.output
    assert "codex inbox render: ok surface=inbox" in result.output
    assert "codex what-now render: ok surface=what_now" in result.output
    assert f"mcp: registered {codex_config}" in result.output
    assert "mcp config command: ok hollow-lodge-mcp" in result.output
    assert "mcp command: available hollow-lodge-mcp" in result.output
    assert "secret-token" not in result.output
    assert "No public claims until lock." not in result.output
    assert "The Saint's False Finger" not in result.output
    assert created_clients[0].calls == [("health", {})]
    assert created_clients[1].token == "secret-token"
    assert created_clients[1].calls == [("me", {})]
    assert created_clients[2].token == "secret-token"
    assert created_clients[2].calls == [("inbox", {})]
    assert created_clients[3].token == "secret-token"
    assert created_clients[3].calls == [("visible_events", {})]
    assert created_clients[4].token == "secret-token"
    assert created_clients[4].calls == [("visible_events", {}), ("inbox", {})]
    assert created_clients[5].token == "secret-token"
    assert created_clients[5].calls == [
        ("visible_events", {}),
        ("profile", {}),
        ("inbox", {}),
        ("deals", {}),
    ]
    assert "No public claims until lock." in local_log_path.read_text(encoding="utf-8")


def test_doctor_server_override_applies_to_registered_readiness_checks(
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
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/bin/{command}")
    config_path = tmp_path / "config.json"
    codex_config = tmp_path / "codex.toml"
    codex_config.write_text(
        '[mcp_servers."the-hollow-lodge"]\ncommand = "hollow-lodge-mcp"\n',
        encoding="utf-8",
    )
    save_config(
        config_path,
        ClientConfig(
            server_url="http://saved-server",
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
            "--server",
            "http://override-server",
            "--config",
            str(config_path),
            "--onboarding-state",
            str(tmp_path / "missing-onboarding.json"),
            "--codex-config",
            str(codex_config),
            "--local-log",
            str(tmp_path / "local.jsonl"),
        ],
    )

    assert result.exit_code == 0
    assert "server: ok http://override-server" in result.output
    assert [client.server_url for client in created_clients] == [
        "http://override-server",
        "http://override-server",
        "http://override-server",
        "http://override-server",
        "http://override-server",
        "http://override-server",
    ]
    assert "http://saved-server" not in result.output


def test_doctor_strict_passes_for_registered_ready_install(tmp_path, monkeypatch):
    runner = CliRunner()

    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/bin/{command}")
    config_path = tmp_path / "config.json"
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
            "--strict",
            "--config",
            str(config_path),
            "--onboarding-state",
            str(tmp_path / "missing-onboarding.json"),
            "--codex-config",
            str(codex_config),
            "--local-log",
            str(tmp_path / "local.jsonl"),
        ],
    )

    assert result.exit_code == 0
    assert "strict: pass" in result.output
    assert "secret-token" not in result.output


def test_doctor_reports_pending_onboarding_without_contact(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(cli.shutil, "which", lambda command: None)
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
    assert "auth:" not in result.output
    assert "inbox:" not in result.output
    assert "event sync:" not in result.output
    assert "codex inbox render:" not in result.output
    assert "codex what-now render:" not in result.output
    assert f"mcp: missing {codex_config}" in result.output
    assert "mcp config command: missing" in result.output
    assert "mcp command: missing hollow-lodge-mcp" in result.output
    assert "ada@example.com" not in result.output
    assert created_clients[0].calls == [("health", {})]


def test_doctor_strict_fails_for_pending_onboarding_without_contact(tmp_path, monkeypatch):
    runner = CliRunner()

    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    monkeypatch.setattr(cli.shutil, "which", lambda command: None)
    onboarding_path = tmp_path / "onboarding.json"
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
            "--strict",
            "--config",
            str(tmp_path / "missing-config.json"),
            "--onboarding-state",
            str(onboarding_path),
            "--codex-config",
            str(tmp_path / "missing-codex.toml"),
        ],
    )

    assert result.exit_code == 1
    assert "player: pending key_request_0001 status=pending display=Ada" in result.output
    assert "strict: fail" in result.output
    assert "auth:" not in result.output
    assert "ada@example.com" not in result.output


def test_doctor_reports_unconfigured_install_and_unreachable_server(tmp_path, monkeypatch):
    runner = CliRunner()

    class FailingApi(FakeApi):
        def health(self):
            self.calls.append(("health", {}))
            raise RuntimeError("connection failed with secret-token")

    monkeypatch.setattr(cli, "HollowLodgeApi", FailingApi)
    monkeypatch.setattr(cli.shutil, "which", lambda command: None)

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
            "--local-log",
            str(tmp_path / "local.jsonl"),
        ],
    )

    assert result.exit_code == 0
    assert "server: unreachable http://downstream" in result.output
    assert "player: not configured" in result.output
    assert "auth:" not in result.output
    assert "inbox:" not in result.output
    assert "event sync:" not in result.output
    assert "codex inbox render:" not in result.output
    assert "codex what-now render:" not in result.output
    assert "mcp: missing" in result.output
    assert "mcp config command: missing" in result.output
    assert "mcp command: missing hollow-lodge-mcp" in result.output
    assert "secret-token" not in result.output


def test_doctor_strict_fails_for_registered_auth_failure_without_leaking_error(
    tmp_path,
    monkeypatch,
):
    runner = CliRunner()

    class FailingAuthApi(FakeApi):
        def me(self):
            self.calls.append(("me", {}))
            raise RuntimeError("auth failed for secret-token")

    monkeypatch.setattr(cli, "HollowLodgeApi", FailingAuthApi)
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/bin/{command}")
    config_path = tmp_path / "config.json"
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
            active_crew_id=None,
        ),
    )

    result = runner.invoke(
        cli.app,
        [
            "doctor",
            "--strict",
            "--config",
            str(config_path),
            "--onboarding-state",
            str(tmp_path / "missing-onboarding.json"),
            "--codex-config",
            str(codex_config),
            "--local-log",
            str(tmp_path / "local.jsonl"),
        ],
    )

    assert result.exit_code == 1
    assert "auth: failed" in result.output
    assert "strict: fail" in result.output
    assert "secret-token" not in result.output


def test_doctor_reports_mcp_config_command_mismatch_without_leaking_command(
    tmp_path,
    monkeypatch,
):
    runner = CliRunner()

    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/bin/{command}")
    codex_config = tmp_path / "codex.toml"
    codex_config.write_text(
        '[mcp_servers."the-hollow-lodge"]\n'
        'command = "old-hollow-lodge-mcp --token secret-token"\n',
        encoding="utf-8",
    )

    result = runner.invoke(
        cli.app,
        [
            "doctor",
            "--server",
            "http://testserver",
            "--config",
            str(tmp_path / "missing-config.json"),
            "--onboarding-state",
            str(tmp_path / "missing-onboarding.json"),
            "--codex-config",
            str(codex_config),
        ],
    )

    assert result.exit_code == 0
    assert f"mcp: registered {codex_config}" in result.output
    assert "mcp config command: mismatch expected hollow-lodge-mcp" in result.output
    assert "mcp command: available hollow-lodge-mcp" in result.output
    assert "old-hollow-lodge-mcp" not in result.output
    assert "secret-token" not in result.output


def test_doctor_reports_failed_saved_auth_without_leaking_error(tmp_path, monkeypatch):
    runner = CliRunner()

    class FailingAuthApi(FakeApi):
        def me(self):
            self.calls.append(("me", {}))
            raise RuntimeError("auth failed for secret-token")

    monkeypatch.setattr(cli, "HollowLodgeApi", FailingAuthApi)
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/bin/{command}")
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="secret-token",
            display_name="Ada",
            active_crew_id=None,
        ),
    )

    result = runner.invoke(
        cli.app,
        [
            "doctor",
            "--config",
            str(config_path),
            "--onboarding-state",
            str(tmp_path / "missing-onboarding.json"),
            "--codex-config",
            str(tmp_path / "missing-codex.toml"),
            "--local-log",
            str(tmp_path / "local.jsonl"),
        ],
    )

    assert result.exit_code == 0
    assert "server: ok http://testserver" in result.output
    assert "player: registered player_0001 display=Ada active_crew=-" in result.output
    assert "auth: failed" in result.output
    assert "inbox: ok active_contracts=1" in result.output
    assert "event sync: ok synced=1 max_sequence=7" in result.output
    assert "codex inbox render: ok surface=inbox" in result.output
    assert "codex what-now render: ok surface=what_now" in result.output
    assert "secret-token" not in result.output


def test_doctor_reports_saved_auth_player_mismatch_without_leaking_token(tmp_path, monkeypatch):
    runner = CliRunner()

    class MismatchAuthApi(FakeApi):
        def me(self):
            self.calls.append(("me", {}))
            return {"player_id": "player_9999"}

    monkeypatch.setattr(cli, "HollowLodgeApi", MismatchAuthApi)
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/bin/{command}")
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="secret-token",
            display_name="Ada",
            active_crew_id=None,
        ),
    )

    result = runner.invoke(
        cli.app,
        [
            "doctor",
            "--config",
            str(config_path),
            "--onboarding-state",
            str(tmp_path / "missing-onboarding.json"),
            "--codex-config",
            str(tmp_path / "missing-codex.toml"),
            "--local-log",
            str(tmp_path / "local.jsonl"),
        ],
    )

    assert result.exit_code == 0
    assert "server: ok http://testserver" in result.output
    assert "auth: mismatch" in result.output
    assert "inbox: ok active_contracts=1" in result.output
    assert "event sync: ok synced=1 max_sequence=7" in result.output
    assert "codex inbox render: ok surface=inbox" in result.output
    assert "codex what-now render: ok surface=what_now" in result.output
    assert "player_9999" not in result.output
    assert "secret-token" not in result.output


def test_doctor_reports_failed_inbox_without_leaking_error_or_payload(tmp_path, monkeypatch):
    runner = CliRunner()

    class FailingInboxApi(FakeApi):
        def inbox(self):
            self.calls.append(("inbox", {}))
            raise RuntimeError("inbox failed for secret-token and The Saint's False Finger")

    monkeypatch.setattr(cli, "HollowLodgeApi", FailingInboxApi)
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/bin/{command}")
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="secret-token",
            display_name="Ada",
            active_crew_id=None,
        ),
    )

    result = runner.invoke(
        cli.app,
        [
            "doctor",
            "--config",
            str(config_path),
            "--onboarding-state",
            str(tmp_path / "missing-onboarding.json"),
            "--codex-config",
            str(tmp_path / "missing-codex.toml"),
            "--local-log",
            str(tmp_path / "local.jsonl"),
        ],
    )

    assert result.exit_code == 0
    assert "auth: ok player_0001" in result.output
    assert "inbox: failed" in result.output
    assert "event sync: ok synced=1 max_sequence=7" in result.output
    assert "codex inbox render: failed" in result.output
    assert "codex what-now render: failed" in result.output
    assert "secret-token" not in result.output
    assert "The Saint's False Finger" not in result.output


def test_doctor_reports_inbox_player_mismatch_without_leaking_returned_player(tmp_path, monkeypatch):
    runner = CliRunner()

    class MismatchInboxApi(FakeApi):
        def inbox(self):
            self.calls.append(("inbox", {}))
            return {
                "player_id": "player_9999",
                "active_contracts": [{"title": "The Saint's False Finger"}],
            }

    monkeypatch.setattr(cli, "HollowLodgeApi", MismatchInboxApi)
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/bin/{command}")
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="secret-token",
            display_name="Ada",
            active_crew_id=None,
        ),
    )

    result = runner.invoke(
        cli.app,
        [
            "doctor",
            "--config",
            str(config_path),
            "--onboarding-state",
            str(tmp_path / "missing-onboarding.json"),
            "--codex-config",
            str(tmp_path / "missing-codex.toml"),
            "--local-log",
            str(tmp_path / "local.jsonl"),
        ],
    )

    assert result.exit_code == 0
    assert "auth: ok player_0001" in result.output
    assert "inbox: mismatch" in result.output
    assert "event sync: ok synced=1 max_sequence=7" in result.output
    assert "codex inbox render: failed" in result.output
    assert "codex what-now render: failed" in result.output
    assert "player_9999" not in result.output
    assert "The Saint's False Finger" not in result.output


def test_doctor_reports_failed_event_sync_without_leaking_event_payload(tmp_path, monkeypatch):
    runner = CliRunner()

    class FailingEventsApi(FakeApi):
        def visible_events(self):
            self.calls.append(("visible_events", {}))
            raise RuntimeError("event sync failed for secret-token and No public claims until lock.")

    monkeypatch.setattr(cli, "HollowLodgeApi", FailingEventsApi)
    monkeypatch.setattr(cli.shutil, "which", lambda command: f"/bin/{command}")
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="secret-token",
            display_name="Ada",
            active_crew_id=None,
        ),
    )

    result = runner.invoke(
        cli.app,
        [
            "doctor",
            "--config",
            str(config_path),
            "--onboarding-state",
            str(tmp_path / "missing-onboarding.json"),
            "--codex-config",
            str(tmp_path / "missing-codex.toml"),
            "--local-log",
            str(tmp_path / "local.jsonl"),
        ],
    )

    assert result.exit_code == 0
    assert "auth: ok player_0001" in result.output
    assert "inbox: ok active_contracts=1" in result.output
    assert "event sync: failed" in result.output
    assert "codex inbox render: failed" in result.output
    assert "codex what-now render: failed" in result.output
    assert "secret-token" not in result.output
    assert "No public claims until lock." not in result.output


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


def test_admin_event_log_export_writes_safe_manifest(tmp_path, monkeypatch):
    runner = CliRunner()
    store = JsonlEventStore(tmp_path / "server-events.jsonl")
    event = store.append_command(
        event_type="action.submitted",
        actor_id="player_ada",
        visibility=EventVisibility.players(["player_ada"]),
        payload={"intent": "secret backup payload"},
        idempotency_key="submit-action-1",
    )

    class ExportApi(FakeApi):
        def export_event_log(self, *, admin_token: str):
            self.calls.append(("export_event_log", {"admin_token": admin_token}))
            return {"events": [row.model_dump(mode="json") for row in store.read()]}

    created_clients: list[ExportApi] = []

    def fake_client(**kwargs):
        client = ExportApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    output_path = tmp_path / "events.json"
    manifest_path = tmp_path / "events.manifest.json"

    result = runner.invoke(
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
            "--manifest-output",
            str(manifest_path),
        ],
    )

    assert result.exit_code == 0
    assert f"wrote {output_path}" in result.output
    assert f"wrote manifest {manifest_path}" in result.output
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["event_count"] == 1
    assert manifest["last_sequence"] == 1
    assert manifest["last_event_hash"] == event.event_hash
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert "secret backup payload" not in manifest_text
    assert "player_ada" not in manifest_text
    assert "submit-action-1" not in manifest_text
    assert created_clients[0].calls == [("export_event_log", {"admin_token": "admin-secret"})]


def test_admin_event_log_manifest_command_writes_safe_summary(tmp_path):
    runner = CliRunner()
    store = JsonlEventStore(tmp_path / "server-events.jsonl")
    event = store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"hidden_truth": "do not include this"},
    )
    source = tmp_path / "events.json"
    source.write_text(
        json.dumps(
            {"events": [row.model_dump(mode="json") for row in store.read()]},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "events.manifest.json"
    manifest.write_text(
        json.dumps(create_event_log_manifest(source), sort_keys=True),
        encoding="utf-8",
    )
    output_path = tmp_path / "manifest.json"

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "event-log-manifest",
            "--source",
            str(source),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert "manifest ok: 1 events last_sequence=1" in result.output
    assert f"last_hash={event.event_hash}" in result.output
    manifest = json.loads(output_path.read_text(encoding="utf-8"))
    assert manifest["manifest_type"] == "hollow_lodge_event_log_backup"
    assert manifest["event_count"] == 1
    assert manifest["last_event_hash"] == event.event_hash
    assert "do not include this" not in output_path.read_text(encoding="utf-8")


def test_admin_event_log_manifest_rejects_corrupted_export(tmp_path):
    runner = CliRunner()
    store = JsonlEventStore(tmp_path / "server-events.jsonl")
    row = store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    ).model_dump(mode="json")
    row["payload"]["contract_id"] = "tampered"
    source = tmp_path / "events.json"
    source.write_text(json.dumps({"events": [row]}), encoding="utf-8")
    output_path = tmp_path / "manifest.json"

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "event-log-manifest",
            "--source",
            str(source),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code != 0
    assert "invalid event hash" in result.output
    assert not output_path.exists()
    assert "Traceback" not in result.output


def test_admin_event_log_restore_jsonl_writes_empty_destination_with_manifest(tmp_path):
    runner = CliRunner()
    store = JsonlEventStore(tmp_path / "source-events.jsonl")
    event = store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    source = tmp_path / "events.json"
    source.write_text(
        json.dumps(
            {"events": [row.model_dump(mode="json") for row in store.read()]},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "events.manifest.json"
    manifest.write_text(
        json.dumps(create_event_log_manifest(source), sort_keys=True),
        encoding="utf-8",
    )
    destination = tmp_path / "restored" / "server-events.jsonl"

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "event-log-restore-jsonl",
            "--source",
            str(source),
            "--destination",
            str(destination),
            "--manifest",
            str(manifest),
        ],
    )

    assert result.exit_code == 0
    assert f"event log restore ok: 1 events into {destination}" in result.output
    assert "manifest verified" in result.output
    assert f"last_hash={event.event_hash}" in result.output
    assert JsonlEventStore(destination).read() == [event]


def test_admin_event_log_restore_jsonl_refuses_non_empty_destination(tmp_path):
    runner = CliRunner()
    source_store = JsonlEventStore(tmp_path / "source-events.jsonl")
    source_store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    source = tmp_path / "events.json"
    source.write_text(
        json.dumps(
            {"events": [row.model_dump(mode="json") for row in source_store.read()]},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    destination = tmp_path / "server-events.jsonl"
    destination_store = JsonlEventStore(destination)
    destination_store.append(
        event_type="identity.player.registered",
        actor_id="server",
        visibility=EventVisibility.players(["player_0001"]),
        payload={"player_id": "player_0001"},
    )

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "event-log-restore-jsonl",
            "--source",
            str(source),
            "--destination",
            str(destination),
        ],
    )

    assert result.exit_code != 0
    assert "destination event log is not empty; refusing restore" in result.output
    assert JsonlEventStore(destination).read() == destination_store.read()
    assert "Traceback" not in result.output


def test_admin_event_log_import_postgres_dry_run_uses_packaged_migration(
    tmp_path,
    monkeypatch,
):
    runner = CliRunner()
    source = tmp_path / "events.json"
    source.write_text('{"events":[]}', encoding="utf-8")
    calls: list[dict] = []

    def fake_migrate_event_log_to_postgres(*, source, database_url, manifest, dry_run):
        calls.append(
            {
                "source": source,
                "database_url": database_url,
                "manifest": manifest,
                "dry_run": dry_run,
            }
        )
        return {"dry_run": True, "event_count": 0, "manifest_verified": False}

    monkeypatch.setattr(
        cli,
        "migrate_event_log_to_postgres",
        fake_migrate_event_log_to_postgres,
    )

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "event-log-import-postgres",
            "--source",
            str(source),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "event log import dry-run ok: 0 events" in result.output
    assert calls == [
        {"source": source, "database_url": "", "manifest": None, "dry_run": True}
    ]


def test_admin_event_log_import_postgres_dry_run_verifies_manifest(
    tmp_path,
    monkeypatch,
):
    runner = CliRunner()
    source = tmp_path / "events.json"
    source.write_text('{"events":[]}', encoding="utf-8")
    manifest = tmp_path / "events.manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    calls: list[dict] = []

    def fake_migrate_event_log_to_postgres(*, source, database_url, manifest, dry_run):
        calls.append(
            {
                "source": source,
                "database_url": database_url,
                "manifest": manifest,
                "dry_run": dry_run,
            }
        )
        return {"dry_run": True, "event_count": 0, "manifest_verified": True}

    monkeypatch.setattr(
        cli,
        "migrate_event_log_to_postgres",
        fake_migrate_event_log_to_postgres,
    )

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "event-log-import-postgres",
            "--source",
            str(source),
            "--manifest",
            str(manifest),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "event log import dry-run ok: 0 events manifest verified" in result.output
    assert calls == [
        {"source": source, "database_url": "", "manifest": manifest, "dry_run": True}
    ]


def test_admin_event_log_import_postgres_prints_redacted_destination(
    tmp_path,
    monkeypatch,
):
    runner = CliRunner()
    source = tmp_path / "events.json"
    source.write_text('{"events":[]}', encoding="utf-8")
    calls: list[dict] = []

    def fake_migrate_event_log_to_postgres(*, source, database_url, manifest, dry_run):
        calls.append(
            {
                "source": source,
                "database_url": database_url,
                "manifest": manifest,
                "dry_run": dry_run,
            }
        )
        return {
            "dry_run": False,
            "event_count": 3,
            "database_url": "postgresql://user:***@host:5432/hollow_lodge",
            "manifest_verified": False,
        }

    monkeypatch.setattr(
        cli,
        "migrate_event_log_to_postgres",
        fake_migrate_event_log_to_postgres,
    )

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "event-log-import-postgres",
            "--source",
            str(source),
            "--database-url",
            "postgresql://user:secret@host:5432/hollow_lodge",
        ],
    )

    assert result.exit_code == 0
    assert (
        "event log import ok: 3 events into "
        "postgresql://user:***@host:5432/hollow_lodge"
    ) in result.output
    assert "postgresql://user:secret" not in result.output
    assert calls == [
        {
            "source": source,
            "database_url": "postgresql://user:secret@host:5432/hollow_lodge",
            "manifest": None,
            "dry_run": False,
        }
    ]


def test_admin_event_log_import_postgres_reports_safe_migration_error(
    tmp_path,
    monkeypatch,
):
    runner = CliRunner()
    source = tmp_path / "events.json"
    source.write_text('{"events":[]}', encoding="utf-8")

    def fake_migrate_event_log_to_postgres(*, source, database_url, manifest, dry_run):
        raise RuntimeError("HOLLOW_LODGE_EVENT_DATABASE_URL or --database-url is required")

    monkeypatch.setattr(
        cli,
        "migrate_event_log_to_postgres",
        fake_migrate_event_log_to_postgres,
    )

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "event-log-import-postgres",
            "--source",
            str(source),
        ],
    )

    assert result.exit_code != 0
    assert "HOLLOW_LODGE_EVENT_DATABASE_URL or --database-url is required" in result.output


def test_admin_event_log_import_postgres_reports_invalid_jsonl_row(tmp_path):
    runner = CliRunner()
    source = tmp_path / "events.jsonl"
    source.write_text('{"events":[]}\nnot-json\n', encoding="utf-8")

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "event-log-import-postgres",
            "--source",
            str(source),
            "--dry-run",
        ],
    )

    assert result.exit_code != 0
    assert "invalid JSONL row 2" in result.output
    assert "Traceback" not in result.output


def test_admin_backend_smoke_command_reports_safe_backend_status(monkeypatch):
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
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--expected-event-backend",
            "jsonl",
            "--require-projection-reads",
            "--require-current-projection-read-surfaces",
            "--require-current-projection-schema",
            "--require-sequence-alignment",
            "--require-projection-refresh-ok",
        ],
    )

    assert result.exit_code == 0
    assert (
        "backend readiness ok: event=jsonl event_status=available events=12 "
        "projection=postgres projection_status=available projection_lag=0 "
        f"sequence=12 schema={CURRENT_PROJECTION_SCHEMA_VERSION} "
        f"migrations={CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT}"
    ) in result.output
    assert "secret" not in result.output
    assert created_clients[0].calls == [("health", {}), ("diagnostics", {})]


def test_admin_backend_smoke_command_accepts_required_maintenance_read_only(
    monkeypatch,
):
    class MaintenanceApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["maintenance"] = {
                "read_only": True,
                "env": "HOLLOW_LODGE_MAINTENANCE_READ_ONLY",
            }
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", MaintenanceApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--expected-event-backend",
            "jsonl",
            "--require-maintenance-read-only",
        ],
    )

    assert result.exit_code == 0
    assert "backend readiness ok: event=jsonl" in result.output


def test_admin_backend_smoke_command_rejects_missing_required_maintenance(
    monkeypatch,
):
    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--expected-event-backend",
            "jsonl",
            "--require-maintenance-read-only",
        ],
    )

    assert result.exit_code != 0
    assert "diagnostics response did not include data.maintenance" in result.output
    assert "maintenance read-only mode is not enabled" in result.output


def test_admin_backend_smoke_command_accepts_required_maintenance_read_write(
    monkeypatch,
):
    class MaintenanceApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["event_log"]["backend"] = "postgres"
            payload["data"]["maintenance"] = {
                "read_only": False,
                "env": "HOLLOW_LODGE_MAINTENANCE_READ_ONLY",
            }
            payload["data"]["identity_replay_store"] = {
                "backend": "postgres",
                "database_url": "postgresql://operational:***@host:5432/hollow_lodge",
                "database_url_env": "HOLLOW_LODGE_OPERATIONAL_DATABASE_URL",
            }
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", MaintenanceApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--expected-event-backend",
            "postgres",
            "--require-maintenance-read-write",
        ],
    )

    assert result.exit_code == 0
    assert "backend readiness ok: event=postgres" in result.output


def test_admin_backend_smoke_command_rejects_frozen_required_read_write(
    monkeypatch,
):
    class MaintenanceApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["event_log"]["backend"] = "postgres"
            payload["data"]["maintenance"] = {
                "read_only": True,
                "env": "HOLLOW_LODGE_MAINTENANCE_READ_ONLY",
            }
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", MaintenanceApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--expected-event-backend",
            "postgres",
            "--require-maintenance-read-write",
        ],
    )

    assert result.exit_code != 0
    assert "maintenance read/write mode is not enabled" in result.output


def test_admin_backend_smoke_command_rejects_conflicting_maintenance_requirements(
    monkeypatch,
):
    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--require-maintenance-read-only",
            "--require-maintenance-read-write",
        ],
    )

    assert result.exit_code != 0
    assert "--require-maintenance-read-only" in result.output
    assert "--require-maintenance-read-write" in result.output


def test_admin_backend_smoke_command_accepts_production_postgres_preset(monkeypatch):
    class ProductionPostgresApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["event_log"]["backend"] = "postgres"
            payload["data"]["storage_guards"] = {
                "require_postgres_event_log": True,
                "require_postgres_projection": True,
                "require_postgres_operational": True,
            }
            payload["data"]["maintenance"] = {
                "read_only": False,
                "env": "HOLLOW_LODGE_MAINTENANCE_READ_ONLY",
            }
            payload["data"]["identity_replay_store"] = {
                "backend": "postgres",
                "database_url": "postgresql://operational:***@host:5432/hollow_lodge",
                "database_url_env": "HOLLOW_LODGE_OPERATIONAL_DATABASE_URL",
            }
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", ProductionPostgresApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--production-postgres",
        ],
    )

    assert result.exit_code == 0
    assert "backend readiness ok: event=postgres" in result.output
    assert "projection=postgres" in result.output
    assert "operational=postgres" in result.output
    assert "secret" not in result.output


def test_admin_backend_smoke_command_rejects_conflicting_production_preset(
    monkeypatch,
):
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--production-postgres",
            "--expected-event-backend",
            "jsonl",
        ],
    )

    assert result.exit_code != 0
    assert (
        "--production-postgres requires --expected-event-backend postgres"
        in result.output
    )
    assert created_clients == []


def test_admin_backend_smoke_command_rejects_failed_projection_refresh(monkeypatch):
    class FailedRefreshApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["projection_refresh"] = {
                "status": "failed",
                "last_context": "contracts",
                "last_success_sequence": 11,
                "failure_count": 1,
                "last_failure": {
                    "context": "contracts",
                    "error_type": "OperationalError",
                    "message": "password=secret raw database failure",
                },
            }
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", FailedRefreshApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--require-projection-refresh-ok",
        ],
    )

    assert result.exit_code != 0
    assert (
        "projection refresh status is failed; expected ok "
        "(context=contracts, error_type=OperationalError)"
    ) in result.output
    assert "password=secret" not in result.output
    assert "raw database failure" not in result.output


def test_admin_backend_smoke_command_verifies_event_log_manifest(
    tmp_path,
    monkeypatch,
):
    store = JsonlEventStore(tmp_path / "server-events.jsonl")
    event = store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    source = tmp_path / "events.json"
    source.write_text(
        json.dumps(
            {"events": [row.model_dump(mode="json") for row in store.read()]},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "events.manifest.json"
    manifest.write_text(
        json.dumps(create_event_log_manifest(source), sort_keys=True),
        encoding="utf-8",
    )

    class ManifestApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["event_log"]["event_count"] = 1
            payload["data"]["event_log"]["last_sequence"] = 1
            payload["data"]["event_log"]["last_event_hash"] = event.event_hash
            payload["data"]["event_log"]["event_hash_chain_sha256"] = json.loads(
                manifest.read_text(encoding="utf-8")
            )["event_hash_chain_sha256"]
            payload["data"]["projection_db"]["last_sequence"] = 1
            payload["data"]["projection_db"]["authoritative_last_sequence"] = 1
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", ManifestApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--expected-event-backend",
            "jsonl",
            "--event-log-manifest",
            str(manifest),
        ],
    )

    assert result.exit_code == 0
    assert "backend readiness ok: event=jsonl event_status=available events=1" in (
        result.output
    )
    assert "secret" not in result.output


def test_admin_backend_smoke_command_rejects_malformed_event_log_manifest(
    tmp_path,
    monkeypatch,
):
    manifest = tmp_path / "events.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_type": "wrong",
                "manifest_version": 1,
                "event_count": 0,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--event-log-manifest",
            str(manifest),
        ],
    )

    assert result.exit_code != 0
    assert "event manifest type does not match Hollow Lodge event logs" in result.output
    assert "Traceback" not in result.output
    assert "secret" not in result.output


def test_admin_backend_smoke_command_verifies_required_storage_guards(monkeypatch):
    class GuardedStorageApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["event_log"]["backend"] = "postgres"
            payload["data"]["storage_guards"] = {
                "require_postgres_event_log": True,
                "require_postgres_projection": True,
                "require_postgres_operational": True,
            }
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", GuardedStorageApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--expected-event-backend",
            "postgres",
            "--require-postgres-event-log-guard",
            "--require-postgres-projection-guard",
        ],
    )

    assert result.exit_code == 0
    assert "backend readiness ok: event=postgres" in result.output
    assert "secret" not in result.output


def test_admin_backend_smoke_command_rejects_event_log_guard_backend_mismatch(
    monkeypatch,
):
    class GuardedJsonlApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["storage_guards"] = {
                "require_postgres_event_log": True,
                "require_postgres_projection": True,
                "require_postgres_operational": True,
            }
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", GuardedJsonlApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--expected-event-backend",
            "jsonl",
            "--require-postgres-event-log-guard",
            "--require-postgres-projection-guard",
        ],
    )

    assert result.exit_code != 0
    assert (
        "Postgres event-log guard is enabled but event-log backend is jsonl"
        in result.output
    )


def test_admin_backend_smoke_command_rejects_disabled_event_log_guard(monkeypatch):
    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--expected-event-backend",
            "jsonl",
            "--require-postgres-event-log-guard",
        ],
    )

    assert result.exit_code != 0
    assert "Postgres event-log startup guard is not enabled" in result.output


def test_admin_backend_smoke_command_rejects_disabled_operational_guard(monkeypatch):
    class DisabledOperationalGuardApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["identity_replay_store"] = {
                "backend": "postgres",
                "database_url": "postgresql://operational:***@host:5432/hollow_lodge",
                "database_url_env": "HOLLOW_LODGE_OPERATIONAL_DATABASE_URL",
            }
            payload["data"]["storage_guards"] = {
                "require_postgres_event_log": True,
                "require_postgres_projection": True,
                "require_postgres_operational": False,
            }
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", DisabledOperationalGuardApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--expected-operational-backend",
            "postgres",
            "--require-postgres-operational-guard",
        ],
    )

    assert result.exit_code != 0
    assert "Postgres operational startup guard is not enabled" in result.output
    assert "operational:***" not in result.output


def test_admin_backend_smoke_command_rejects_disabled_production_postgres_preset(
    monkeypatch,
):
    class DisabledProductionPresetApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["event_log"]["backend"] = "postgres"
            payload["data"]["identity_replay_store"] = {
                "backend": "postgres",
                "database_url": "postgresql://operational:***@host:5432/hollow_lodge",
                "database_url_env": "HOLLOW_LODGE_OPERATIONAL_DATABASE_URL",
            }
            payload["data"]["storage_guards"] = {
                "production_postgres": False,
                "require_postgres_event_log": True,
                "require_postgres_projection": True,
                "require_postgres_operational": True,
            }
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", DisabledProductionPresetApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--expected-event-backend",
            "postgres",
            "--expected-operational-backend",
            "postgres",
            "--require-production-postgres-preset",
        ],
    )

    assert result.exit_code != 0
    assert "production Postgres server preset is not enabled" in result.output
    assert "operational:***" not in result.output


def test_admin_backend_smoke_command_rejects_unredacted_database_url(monkeypatch):
    class UnsafeDiagnosticsApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["projection_db"][
                "database_url"
            ] = "postgresql://user:secret@host:5432/hollow_lodge"
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", UnsafeDiagnosticsApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
        ],
    )

    assert result.exit_code != 0
    assert "projection diagnostics expose an unredacted database URL password" in result.output
    assert "postgresql://user:secret" not in result.output


def test_admin_backend_smoke_command_rejects_unredacted_operational_database_url(
    monkeypatch,
):
    class UnsafeOperationalDiagnosticsApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["identity_replay_store"] = {
                "backend": "postgres",
                "database_url": "postgresql://user:secret@host:5432/hollow_lodge",
            }
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", UnsafeOperationalDiagnosticsApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--expected-operational-backend",
            "postgres",
        ],
    )

    assert result.exit_code != 0
    assert "operational diagnostics expose an unredacted database URL password" in result.output
    assert "postgresql://user:secret" not in result.output


def test_admin_backend_smoke_command_rejects_stale_projection_schema(monkeypatch):
    class StaleSchemaApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["projection_db"][
                "schema_version"
            ] = CURRENT_PROJECTION_SCHEMA_VERSION - 1
            payload["data"]["projection_db"][
                "schema_migration_count"
            ] = CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT - 1
            payload["data"]["projection_db"][
                "latest_schema_migration"
            ] = CURRENT_PROJECTION_SCHEMA_VERSION - 1
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", StaleSchemaApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--require-current-projection-schema",
        ],
    )

    assert result.exit_code != 0
    assert (
        "projection schema_version is "
        f"{CURRENT_PROJECTION_SCHEMA_VERSION - 1}; "
        f"expected {CURRENT_PROJECTION_SCHEMA_VERSION}"
    ) in result.output
    assert (
        "projection schema_migration_count is "
        f"{CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT - 1}; "
        f"expected {CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT}"
    ) in result.output
    assert (
        "projection latest_schema_migration is "
        f"{CURRENT_PROJECTION_SCHEMA_VERSION - 1}; "
        f"expected {CURRENT_PROJECTION_SCHEMA_VERSION}"
    ) in result.output


def test_admin_backend_smoke_command_rejects_missing_projection_read_surface(monkeypatch):
    class MissingSurfaceApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["projection_reads"]["surfaces"].pop("visible_events")
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", MissingSurfaceApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--require-current-projection-read-surfaces",
        ],
    )

    assert result.exit_code != 0
    assert (
        "projection read surfaces missing from diagnostics: visible_events"
        in result.output
    )


def test_admin_backend_smoke_command_rejects_sequence_mismatch(monkeypatch):
    class MisalignedSequenceApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["event_log"]["event_count"] = 13
            payload["data"]["projection_db"]["last_sequence"] = 11
            payload["data"]["projection_db"]["authoritative_last_sequence"] = 12
            payload["data"]["projection_db"]["lag"] = 0
            return payload

    monkeypatch.setattr(cli, "HollowLodgeApi", MisalignedSequenceApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
            "--require-sequence-alignment",
        ],
    )

    assert result.exit_code != 0
    assert (
        "event log event_count 13 does not match projection "
        "authoritative_last_sequence 12"
    ) in result.output
    assert (
        "projection last_sequence 11 does not match "
        "authoritative_last_sequence 12"
    ) in result.output
    assert "projection lag 0 does not match authoritative-last delta 1" in result.output


def test_admin_backend_smoke_command_rejects_unhealthy_server(monkeypatch):
    class UnhealthyApi(FakeApi):
        def health(self):
            self.calls.append(("health", {}))
            return {"status": "starting"}

    monkeypatch.setattr(cli, "HollowLodgeApi", UnhealthyApi)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "admin",
            "backend-smoke",
            "--server",
            "http://testserver",
            "--expected-backend",
            "postgres",
        ],
    )

    assert result.exit_code != 0
    assert "unexpected health response" in result.output
    assert "starting" in result.output


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


def test_what_now_command_renders_codex_landing_surface(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(cli, "HollowLodgeApi", fake_client)
    monkeypatch.setattr(codex_session, "HollowLodgeApi", fake_client)
    config_path = tmp_path / "config.json"
    local_log_path = tmp_path / "local.jsonl"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            display_name="Ada",
            active_crew_id="crew_0001",
        ),
    )

    result = runner.invoke(
        cli.app,
        [
            "what-now",
            "--config",
            str(config_path),
            "--local-log",
            str(local_log_path),
        ],
    )

    assert result.exit_code == 0
    assert "What Now: Ada" in result.output
    assert "Player ID: player_0001" in result.output
    assert "The Saint's False Finger" in result.output
    assert created_clients[0].calls == [
        ("visible_events", {}),
        ("profile", {}),
        ("inbox", {}),
        ("deals", {}),
    ]


def test_what_now_command_can_emit_render_packet_json(tmp_path, monkeypatch):
    runner = CliRunner()

    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    monkeypatch.setattr(codex_session, "HollowLodgeApi", FakeApi)
    config_path = tmp_path / "config.json"
    local_log_path = tmp_path / "local.jsonl"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            display_name="Ada",
            active_crew_id="crew_0001",
        ),
    )

    result = runner.invoke(
        cli.app,
        [
            "what-now",
            "--json",
            "--config",
            str(config_path),
            "--local-log",
            str(local_log_path),
        ],
    )

    assert result.exit_code == 0
    assert '"surface":"what_now"' in result.output
    assert '"mutation":false' in result.output


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


def test_deal_accept_previews_until_confirmed(tmp_path, monkeypatch):
    runner = CliRunner()
    created_clients: list[FakeApi] = []
    visible_deals = [
        {
            "deal_id": "deal_000001",
            "contract_id": "contract_false_finger",
            "status": "proposed",
            "proposer_crew_id": "crew_0002",
            "recipient_crew_id": "crew_0001",
            "offered_artifact_ids": ["artifact_chapel_debt_mark"],
            "requested_artifact_ids": ["artifact_ledger_rubric"],
            "soft_terms": ["Do not cite our crew as source."],
        }
    ]

    def fake_client(**kwargs):
        client = FakeApi(**kwargs)
        client.deals_payload = visible_deals
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

    preview = runner.invoke(
        cli.app,
        ["deal", "accept", "deal_000001", "--config", str(config_path)],
    )

    assert preview.exit_code == 0
    assert "preview only" in preview.output
    assert "no server mutation occurred" in preview.output
    assert "--confirm" in preview.output
    assert "artifact_chapel_debt_mark" in preview.output
    assert created_clients[0].calls == [("deals", {})]

    confirmed = runner.invoke(
        cli.app,
        ["deal", "accept", "deal_000001", "--confirm", "--config", str(config_path)],
    )

    assert confirmed.exit_code == 0
    assert "deal_000001 fulfilled" in confirmed.output
    assert created_clients[1].calls == [
        (
            "accept_deal",
            {
                "deal_id": "deal_000001",
                "idempotency_key": "deal-accept-key",
            },
        )
    ]


def test_deal_decline_and_cancel_require_confirm_before_mutation(tmp_path, monkeypatch):
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

    decline_preview = runner.invoke(
        cli.app,
        ["deal", "decline", "deal_000001", "--config", str(config_path)],
    )
    cancel_preview = runner.invoke(
        cli.app,
        ["deal", "cancel", "deal_000001", "--config", str(config_path)],
    )

    assert decline_preview.exit_code == 0
    assert "no server mutation occurred" in decline_preview.output
    assert "--confirm" in decline_preview.output
    assert cancel_preview.exit_code == 0
    assert "no server mutation occurred" in cancel_preview.output
    assert "--confirm" in cancel_preview.output
    assert created_clients == []

    decline_confirmed = runner.invoke(
        cli.app,
        ["deal", "decline", "deal_000001", "--confirm", "--config", str(config_path)],
    )
    cancel_confirmed = runner.invoke(
        cli.app,
        ["deal", "cancel", "deal_000001", "--confirm", "--config", str(config_path)],
    )

    assert decline_confirmed.exit_code == 0
    assert "deal_000001 declined" in decline_confirmed.output
    assert cancel_confirmed.exit_code == 0
    assert "deal_000001 canceled" in cancel_confirmed.output
    assert created_clients[0].calls == [
        (
            "decline_deal",
            {
                "deal_id": "deal_000001",
                "idempotency_key": "deal-decline-key",
            },
        )
    ]
    assert created_clients[1].calls == [
        (
            "cancel_deal",
            {
                "deal_id": "deal_000001",
                "idempotency_key": "deal-cancel-key",
            },
        )
    ]
