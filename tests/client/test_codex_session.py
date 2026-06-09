import subprocess
import sys

import httpx
import pytest

from hollow_lodge.client.backend_smoke import (
    CURRENT_PROJECTION_READ_SURFACES,
    CURRENT_PROJECTION_SCHEMA_MIGRATION_COUNT,
    CURRENT_PROJECTION_SCHEMA_VERSION,
)
from hollow_lodge.client.codex_session import CodexGameSession
from hollow_lodge.client.config import ClientConfig, load_config, save_config


class FakeApi:
    def __init__(self):
        self.synced = False
        self.calls = []

    def visible_events(self):
        self.synced = True
        self.calls.append("visible_events")
        return [
            {
                "event_id": "evt_1",
                "sequence": 1,
                "type": "chat.message.created",
                "payload": {
                    "message_id": "msg_1",
                    "sender_player_id": "player_0002",
                    "sender_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "body": "The bell moved.",
                    "server_only_note": "hidden",
                },
            }
        ]

    def visible_events_since(self, *, since_sequence: int):
        self.calls.append(("visible_events_since", since_sequence))
        return [
            {
                "event_id": f"evt_{since_sequence + 1}",
                "sequence": since_sequence + 1,
                "type": "chat.message.created",
                "payload": {
                    "message_id": f"msg_{since_sequence + 1}",
                    "sender_player_id": "player_0002",
                    "sender_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "body": "New after checkpoint.",
                    "server_only_note": "hidden",
                },
            },
            {
                "event_id": f"evt_{since_sequence + 2}",
                "sequence": since_sequence + 2,
                "type": "chat.message.created",
                "payload": {
                    "message_id": f"msg_{since_sequence + 2}",
                    "sender_player_id": "player_0009",
                    "sender_crew_id": "crew_9999",
                    "recipient_crew_id": "crew_8888",
                    "body": "Other crew delta.",
                },
            },
        ]

    def visible_chat_events(self, *, conversation_id=None):
        self.calls.append(("visible_chat_events", conversation_id))
        return [
            {
                "event_id": "evt_1",
                "sequence": 1,
                "type": "chat.message.created",
                "payload": {
                    "message_id": "msg_1",
                    "sender_player_id": "player_0002",
                    "sender_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "body": "The bell moved.",
                    "server_only_note": "hidden",
                },
            }
        ]

    def health(self):
        self.calls.append("health")
        return {"status": "ok"}

    def send_direct_message(
        self,
        *,
        recipient_player_id: str,
        body: str,
        idempotency_key: str,
        artifact_ids=None,
    ):
        self.calls.append(
            (
                "send_direct_message",
                {
                    "recipient_player_id": recipient_player_id,
                    "body": body,
                    "artifact_ids": list(artifact_ids or []),
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"message_id": "msg_direct_000001", "conversation_id": "msg_direct_000001"}

    def send_crew_message(
        self,
        *,
        crew_id: str,
        body: str,
        idempotency_key: str,
        artifact_ids=None,
    ):
        self.calls.append(
            (
                "send_crew_message",
                {
                    "crew_id": crew_id,
                    "body": body,
                    "artifact_ids": list(artifact_ids or []),
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {"message_id": "msg_crew_000001", "conversation_id": crew_id}

    def send_crew_to_crew_message(
        self,
        *,
        sender_crew_id: str,
        recipient_crew_id: str,
        body: str,
        idempotency_key: str,
        artifact_ids=None,
    ):
        self.calls.append(
            (
                "send_crew_to_crew_message",
                {
                    "sender_crew_id": sender_crew_id,
                    "recipient_crew_id": recipient_crew_id,
                    "body": body,
                    "artifact_ids": list(artifact_ids or []),
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {
            "message_id": "msg_crew_to_crew_000001",
            "conversation_id": f"{sender_crew_id}:{recipient_crew_id}",
        }

    def inbox(self):
        self.calls.append("inbox")
        return {
            "player_id": "player_0001",
            "active_contracts": [],
            "incoming_proof_fragments": [],
            "visible_artifacts": [
                {
                    "artifact_id": "artifact_lot_card",
                    "title": "Auction Lot Card",
                    "kind": "lot_card",
                    "public_summary": "Public lot card.",
                }
            ],
        }

    def profile(self):
        self.calls.append("profile")
        return {
            "player_id": "player_0001",
            "display_name": "Ada",
            "crew_count": 1,
            "crews": [
                {
                    "crew_id": "crew_0001",
                    "name": "The Gilt Knives",
                    "member_count": 1,
                    "ready_for_full_contracts": False,
                    "join_code": "hidden",
                }
            ],
        }

    def contracts(self):
        self.calls.append("contracts")
        return {
            "campaign": {"title": "Saints & Ledgers"},
            "contracts": [
                {
                    "contract_id": "contract_false_finger",
                    "title": "The Saint's False Finger",
                    "phase": {"name": "Auction Preview", "remaining_hours": 6},
                }
            ],
        }

    def crew_board(self, *, crew_id: str):
        self.calls.append(f"crew_board:{crew_id}")
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
            "visible_artifacts": [
                {
                    "artifact_id": "artifact_lot_card",
                    "title": "Auction Lot Card",
                    "kind": "lot_card",
                    "public_summary": "Public lot card.",
                }
            ],
        }

    def dossier(self, *, crew_id: str):
        self.calls.append(f"dossier:{crew_id}")
        return {
            "dossier_id": f"dossier_{crew_id}",
            "crew_id": crew_id,
            "packet_lead_player_id": "player_0001",
            "claim": "The reliquary finger is a later devotional forgery.",
            "evidence_ids": ["fragment_ledger_hand"],
            "artifact_citations": [
                {
                    "player_id": "player_0002",
                    "artifact_id": "artifact_ledger_rubric",
                    "claim": "The ledger contradicts the public lot card.",
                    "quote": "The last hand is redder and later than the binding.",
                }
            ],
            "member_contributions": [
                {
                    "player_id": "player_0003",
                    "note": "Auction leverage depends on proving the chapel debt mark.",
                    "evidence_ids": ["fragment_ledger_hand"],
                }
            ],
            "server_notes": "hidden",
        }

    def artifacts(self):
        self.calls.append("artifacts")
        return {
            "contract_id": "contract_false_finger",
            "artifacts": [
                {
                    "artifact_id": "artifact_ledger_rubric",
                    "title": "Red Ledger Rubric",
                    "kind": "ledger",
                    "public_summary": "A copied rubric marks prior ownership.",
                }
            ],
            "edges": [],
        }

    def artifact(self, *, artifact_id: str):
        self.calls.append(f"artifact:{artifact_id}")
        return {
            "artifact_id": artifact_id,
            "title": "Red Ledger Rubric",
            "kind": "ledger",
            "public_summary": "A copied rubric marks prior ownership.",
            "full_text": "Lot 19 passed under chapel seal.",
            "source_chain": ["archive:lot-card"],
        }

    def inspect_artifact(self, *, artifact_id: str, idempotency_key: str):
        self.calls.append(
            (
                "inspect_artifact",
                {
                    "artifact_id": artifact_id,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {
            "artifact_id": artifact_id,
            "title": "Red Ledger Rubric",
            "kind": "ledger",
            "public_summary": "A copied rubric marks prior ownership.",
            "full_text": "Lot 19 passed under chapel seal.",
            "source_chain": ["archive:lot-card"],
            "server_notes": "hidden",
        }

    def deals(self):
        self.calls.append("deals")
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
                }
            ]
        }

    def diagnostics(self):
        self.calls.append("diagnostics")
        return {
            "status": "ok",
            "data": {
                "oracle": {"provider": "deterministic"},
                "event_log": {
                    "backend": "postgres",
                    "status": "available",
                    "event_count": 12,
                    "last_sequence": 12,
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
                },
                "projection_reads": {
                    "surfaces": {
                        surface: True for surface in CURRENT_PROJECTION_READ_SURFACES
                    }
                },
                "projection_refresh": {
                    "status": "ok",
                    "last_context": "startup",
                    "last_success_sequence": 12,
                    "failure_count": 0,
                },
                "storage_guards": {
                    "require_postgres_event_log": True,
                    "require_postgres_projection": True,
                    "require_postgres_operational": True,
                },
                "maintenance": {"read_only": False},
                "identity_replay_store": {"backend": "postgres"},
            },
        }

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
        result = {"action_id": "action_000001", "crew_id": crew_id, "intent": intent}
        if rumor_id is not None:
            result["responds_to_rumor_id"] = rumor_id
        if rumor_response_mode is not None:
            result["rumor_response_mode"] = rumor_response_mode
        if responds_to_rumor_escalation:
            result["responds_to_rumor_escalation"] = True
        if rumor_escalation_mode is not None:
            result["rumor_escalation_mode"] = rumor_escalation_mode
        return result

    def edit_action(self, *, action_id: str, intent: str, idempotency_key: str):
        self.calls.append(
            (
                "edit_action",
                {
                    "action_id": action_id,
                    "intent": intent,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {
            "action_id": action_id,
            "crew_id": "crew_0001",
            "intent": intent,
            "status": "edited",
            "server_notes": "hidden",
        }

    def cancel_action(self, *, action_id: str, idempotency_key: str):
        self.calls.append(
            (
                "cancel_action",
                {
                    "action_id": action_id,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {
            "action_id": action_id,
            "crew_id": "crew_0001",
            "intent": "Inspect the ledger.",
            "status": "canceled",
            "server_notes": "hidden",
        }

    def add_dossier_evidence(
        self,
        *,
        crew_id: str,
        fragment_id: str,
        idempotency_key: str,
    ):
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
        return {
            "dossier_id": f"dossier_{crew_id}",
            "crew_id": crew_id,
            "packet_lead_player_id": "player_0001",
            "evidence_ids": [fragment_id],
            "member_contributions": [
                {
                    "player_id": "player_0001",
                    "note": "Added evidence fragment.",
                    "evidence_ids": [fragment_id],
                }
            ],
        }

    def add_dossier_contribution(
        self,
        *,
        crew_id: str,
        note: str,
        evidence_ids,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "add_dossier_contribution",
                {
                    "crew_id": crew_id,
                    "note": note,
                    "evidence_ids": list(evidence_ids),
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {
            "dossier_id": f"dossier_{crew_id}",
            "crew_id": crew_id,
            "packet_lead_player_id": "player_0001",
            "evidence_ids": list(evidence_ids),
            "member_contributions": [
                {
                    "player_id": "player_0001",
                    "note": note,
                    "evidence_ids": list(evidence_ids),
                }
            ],
        }

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
        return {
            "dossier_id": f"dossier_{crew_id}",
            "crew_id": crew_id,
            "packet_lead_player_id": "player_0001",
            "artifact_citations": [
                {
                    "player_id": "player_0001",
                    "artifact_id": artifact_id,
                    "claim": claim,
                    "quote": quote,
                }
            ],
        }

    def update_dossier_framing(
        self,
        *,
        crew_id: str,
        claim: str | None = None,
        evidence_ids=None,
        reasoning: str | None = None,
        weaknesses: str | None = None,
        provenance_concerns: str | None = None,
        idempotency_key: str,
    ):
        self.calls.append(
            (
                "update_dossier_framing",
                {
                    "crew_id": crew_id,
                    "claim": claim,
                    "evidence_ids": list(evidence_ids or []),
                    "reasoning": reasoning,
                    "weaknesses": weaknesses,
                    "provenance_concerns": provenance_concerns,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {
            "dossier_id": f"dossier_{crew_id}",
            "crew_id": crew_id,
            "packet_lead_player_id": "player_0001",
            "claim": claim or "",
            "evidence_ids": list(evidence_ids or []),
            "reasoning": reasoning or "",
            "weaknesses": weaknesses or "",
            "provenance_concerns": provenance_concerns or "",
            "server_notes": "hidden",
        }

    def propose_deal(
        self,
        *,
        contract_id: str,
        proposer_crew_id: str,
        recipient_crew_id: str,
        offered_artifact_ids,
        requested_artifact_ids,
        soft_terms,
        expires_phase,
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
        return {
            "deal_id": "deal_000002",
            "contract_id": contract_id,
            "proposer_crew_id": proposer_crew_id,
            "recipient_crew_id": recipient_crew_id,
            "status": "proposed",
            "offered_artifact_ids": list(offered_artifact_ids),
            "requested_artifact_ids": list(requested_artifact_ids),
            "soft_terms": list(soft_terms),
            "expires_phase": expires_phase,
        }

    def accept_deal(self, *, deal_id: str, idempotency_key: str):
        self.calls.append(("accept_deal", {"deal_id": deal_id, "idempotency_key": idempotency_key}))
        return {
            "deal_id": deal_id,
            "contract_id": "contract_false_finger",
            "proposer_crew_id": "crew_0001",
            "recipient_crew_id": "crew_0002",
            "status": "fulfilled",
            "offered_artifact_ids": ["artifact_ledger_rubric"],
            "requested_artifact_ids": ["artifact_chapel_debt_mark"],
            "soft_terms": [],
            "expires_phase": None,
            "proposer_received_artifact_ids": [
                "artifact_chapel_debt_mark.dealcopy.deal_000001.crew_0001.2"
            ],
            "recipient_received_artifact_ids": [
                "artifact_ledger_rubric.dealcopy.deal_000001.crew_0002.1"
            ],
        }

    def decline_deal(self, *, deal_id: str, idempotency_key: str):
        self.calls.append(("decline_deal", {"deal_id": deal_id, "idempotency_key": idempotency_key}))
        return {
            "deal_id": deal_id,
            "contract_id": "contract_false_finger",
            "proposer_crew_id": "crew_0001",
            "recipient_crew_id": "crew_0002",
            "status": "declined",
            "offered_artifact_ids": ["artifact_ledger_rubric"],
            "requested_artifact_ids": ["artifact_chapel_debt_mark"],
            "soft_terms": [],
            "expires_phase": None,
        }

    def cancel_deal(self, *, deal_id: str, idempotency_key: str):
        self.calls.append(("cancel_deal", {"deal_id": deal_id, "idempotency_key": idempotency_key}))
        return {
            "deal_id": deal_id,
            "contract_id": "contract_false_finger",
            "proposer_crew_id": "crew_0001",
            "recipient_crew_id": "crew_0002",
            "status": "canceled",
            "offered_artifact_ids": ["artifact_ledger_rubric"],
            "requested_artifact_ids": ["artifact_chapel_debt_mark"],
            "soft_terms": [],
            "expires_phase": None,
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
        return {
            "artifact_id": f"{artifact_id}.copy",
            "title": "Red Ledger Rubric",
            "kind": "ledger",
            "public_summary": "Copied rubric.",
            "server_notes": "hidden",
        }

    def vote_packet_lead(self, *, crew_id: str, player_id: str, idempotency_key: str):
        self.calls.append(
            (
                "vote_packet_lead",
                {
                    "crew_id": crew_id,
                    "player_id": player_id,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {
            "dossier_id": f"dossier_{crew_id}",
            "crew_id": crew_id,
            "packet_lead_player_id": player_id,
            "member_contributions": [],
            "artifact_citations": [],
        }

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
        return {
            "status": "resolved",
            "standings": [{"crew_id": "crew_0001", "standing": "Strong lead", "score": 82}],
            "contract_state": ["Auction house provenance is now suspect."],
            "hidden_truth_summary": "hidden",
        }


def test_codex_session_does_not_import_cli_module():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import hollow_lodge.client.codex_session; "
                "print('hollow_lodge.client.cli' in sys.modules)"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


def test_codex_session_syncs_before_rendering_inbox(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    fake_api = FakeApi()
    session = CodexGameSession(
        config_path=config_path,
        local_log_path=log_path,
        api=fake_api,
    )

    packet = session.render_inbox()

    assert fake_api.synced is True
    assert fake_api.calls == ["visible_events", "inbox"]
    assert packet.surface == "inbox"
    assert "Inbox: player_0001" in packet.player_markdown
    assert "artifact_lot_card: Auction Lot Card" in packet.player_markdown
    assert "chat.message.created" in log_path.read_text()


def test_codex_session_refreshes_missing_display_name(tmp_path):
    class IdentityApi(FakeApi):
        def me(self):
            self.calls.append("me")
            return {"player_id": "player_0001", "display_name": "corelumen"}

    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    fake_api = IdentityApi()

    session = CodexGameSession(
        config_path=config_path,
        local_log_path=log_path,
        api=fake_api,
    )
    packet = session.render_inbox()

    assert fake_api.calls == ["me", "visible_events", "inbox"]
    assert load_config(config_path).display_name == "corelumen"
    assert "Inbox: corelumen" in packet.player_markdown
    assert packet.agent_context["player_id"] == "player_0001"


def test_codex_session_renders_what_now_landing_surface(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            display_name="corelumen",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_what_now()

    assert fake_api.calls == ["visible_events", "profile", "inbox", "deals"]
    assert packet.surface == "what_now"
    assert "What Now: corelumen" in packet.player_markdown
    assert packet.agent_context["player"]["active_crew_id"] == "crew_0001"
    assert packet.agent_context["summary_counts"]["open_deals"] == 1
    assert packet.agent_context["recent_events"][0]["message"]["message_id"] == "msg_1"
    assert "hidden" not in packet.player_markdown


def test_codex_session_renders_profile(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_profile()

    assert fake_api.calls == ["visible_events", "profile"]
    assert packet.surface == "profile"
    assert "Profile: Ada" in packet.player_markdown
    assert packet.agent_context["crews"][0]["crew_id"] == "crew_0001"
    assert "join_code" not in str(packet.agent_context)


def test_codex_session_renders_backend_status_without_event_sync(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_backend_status()

    assert fake_api.calls == ["diagnostics"]
    assert packet.surface == "backend_status"
    assert "- event log: postgres (available)" in packet.player_markdown
    assert "event on; projection on; operational on" in packet.player_markdown
    assert packet.agent_context["backend_status"]["identity_replay_store"] == {
        "backend": "postgres"
    }
    assert not log_path.exists()


def test_codex_session_backend_status_returns_transport_failure_packet(tmp_path):
    class UnreachableApi(FakeApi):
        def diagnostics(self):
            self.calls.append("diagnostics")
            request = httpx.Request(
                "GET",
                "https://server.thehollowlodge.com/diagnostics",
            )
            raise httpx.ConnectError(
                "database_url=postgresql://user:secret@host",
                request=request,
            )

    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = UnreachableApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_backend_status()

    assert fake_api.calls == ["diagnostics"]
    assert packet.surface == "backend_status"
    assert "- unavailable: server request failed: ConnectError" in packet.player_markdown
    assert "secret" not in packet.player_markdown
    assert "postgresql://" not in packet.player_markdown
    assert packet.agent_context["backend_status"] == {
        "status": "unavailable",
        "reason": "server request failed: ConnectError",
    }
    assert not log_path.exists()


def test_codex_session_backend_status_returns_malformed_response_packet(tmp_path):
    class MalformedDiagnosticsApi(FakeApi):
        def diagnostics(self):
            self.calls.append("diagnostics")
            raise ValueError("password=secret malformed JSON body")

    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = MalformedDiagnosticsApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_backend_status()

    assert fake_api.calls == ["diagnostics"]
    assert packet.surface == "backend_status"
    assert "server returned malformed diagnostics response" in packet.player_markdown
    assert "secret" not in packet.player_markdown
    assert "malformed JSON body" not in packet.player_markdown
    assert packet.agent_context["backend_status"]["status"] == "unavailable"
    assert not log_path.exists()


def test_codex_session_checks_backend_readiness_with_production_preset(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.check_backend_readiness()

    assert fake_api.calls == ["health", "diagnostics"]
    assert packet.surface == "backend_readiness"
    assert "Backend Readiness: pass (production_postgres)" in packet.player_markdown
    assert packet.agent_context["backend_readiness"]["ok"] is True
    assert not log_path.exists()


def test_codex_session_backend_readiness_returns_failure_packet(tmp_path):
    class DriftedApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["storage_guards"][
                "require_postgres_operational"
            ] = False
            return payload

    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = DriftedApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.check_backend_readiness()

    assert fake_api.calls == ["health", "diagnostics"]
    assert packet.surface == "backend_readiness"
    assert "Backend Readiness: fail (production_postgres)" in packet.player_markdown
    assert "Postgres operational startup guard is not enabled" in packet.player_markdown
    assert packet.agent_context["backend_readiness"]["ok"] is False


def test_codex_session_backend_readiness_can_require_server_production_preset(tmp_path):
    class PresetDisabledApi(FakeApi):
        def diagnostics(self):
            payload = super().diagnostics()
            payload["data"]["storage_guards"]["production_postgres"] = False
            return payload

    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = PresetDisabledApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.check_backend_readiness(
        require_production_postgres_preset=True,
    )

    assert fake_api.calls == ["health", "diagnostics"]
    assert packet.surface == "backend_readiness"
    assert "Backend Readiness: fail (production_postgres)" in packet.player_markdown
    assert "production Postgres server preset is not enabled" in packet.player_markdown
    assert packet.agent_context["backend_readiness"]["ok"] is False


def test_codex_session_backend_readiness_returns_transport_failure_packet(tmp_path):
    class UnreachableApi(FakeApi):
        def health(self):
            self.calls.append("health")
            request = httpx.Request("GET", "https://server.thehollowlodge.com/health")
            raise httpx.ConnectError("database_url=postgresql://user:secret@host", request=request)

    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = UnreachableApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.check_backend_readiness()

    assert fake_api.calls == ["health"]
    assert packet.surface == "backend_readiness"
    assert "Backend Readiness: fail (production_postgres)" in packet.player_markdown
    assert "server request failed: ConnectError" in packet.player_markdown
    assert "secret" not in packet.player_markdown
    assert "postgresql://" not in packet.player_markdown
    assert packet.agent_context["backend_readiness"]["ok"] is False


def test_codex_session_backend_readiness_returns_malformed_response_packet(tmp_path):
    class MalformedDiagnosticsApi(FakeApi):
        def diagnostics(self):
            self.calls.append("diagnostics")
            raise ValueError("password=secret malformed JSON body")

    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = MalformedDiagnosticsApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.check_backend_readiness()

    assert fake_api.calls == ["health", "diagnostics"]
    assert packet.surface == "backend_readiness"
    assert "server returned malformed readiness response" in packet.player_markdown
    assert "secret" not in packet.player_markdown
    assert "malformed JSON body" not in packet.player_markdown
    assert packet.agent_context["backend_readiness"]["ok"] is False


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
    assert packet.agent_context["visible_artifacts"][0]["artifact_id"] == "artifact_lot_card"


def test_codex_session_crew_board_accepts_explicit_crew_override(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_crew_board("crew_0002")

    assert fake_api.calls == ["visible_events", "crew_board:crew_0002"]
    assert packet.agent_context["crew"]["crew_id"] == "crew_0002"


def test_codex_session_renders_dossier_with_active_crew(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_dossier()

    assert fake_api.calls == ["visible_events", "dossier:crew_0001"]
    assert packet.surface == "dossier"
    assert "Proof Dossier: crew_0001" in packet.player_markdown
    assert packet.agent_context["dossier"]["crew_id"] == "crew_0001"
    assert packet.agent_context["artifact_citation_count"] == 1
    assert "server_notes" not in str(packet.agent_context)


def test_codex_session_crew_board_requires_crew_id_without_active_crew(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=FakeApi())

    try:
        session.render_crew_board()
    except ValueError as exc:
        assert str(exc) == "crew id required when no active crew is configured"
    else:
        raise AssertionError("expected ValueError")


def test_codex_session_renders_artifacts(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_artifacts()

    assert fake_api.synced is True
    assert fake_api.calls == ["visible_events", "artifacts"]
    assert packet.surface == "artifact_graph"


def test_codex_session_renders_artifact(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_artifact("artifact_ledger_rubric")

    assert packet.surface == "artifact"
    assert fake_api.calls == ["visible_events", "artifact:artifact_ledger_rubric"]


def test_codex_session_renders_deals(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_deals()

    assert packet.surface == "deals"
    assert fake_api.calls == ["visible_events", "deals"]
    assert "deal_000001 proposed" in packet.player_markdown


def test_codex_session_previews_deal_acceptance(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0002",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.preview_deal_acceptance("deal_000001")

    assert packet.surface == "deal_preview"
    assert fake_api.calls == ["visible_events", "deals"]
    assert "Your crew gives: artifact_chapel_debt_mark" in packet.player_markdown


def test_codex_session_renders_activity_from_synced_visible_events(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_activity()

    assert packet.surface == "activity"
    assert fake_api.calls == ["visible_events"]
    assert "1 chat player_0002: The bell moved." in packet.player_markdown
    assert "hidden" not in packet.player_markdown
    assert packet.agent_context["visible_event_count"] == 1
    assert packet.agent_context["recent_events"][0]["message"]["message_id"] == "msg_1"


def test_codex_session_renders_activity_delta_since_local_checkpoint(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)
    session.local_log.sync_visible_server_events(
        [
            {
                "event_id": "evt_5",
                "sequence": 5,
                "type": "chat.message.created",
                "payload": {
                    "message_id": "msg_5",
                    "sender_player_id": "player_0001",
                    "body": "already synced",
                },
            }
        ]
    )

    packet = session.render_activity_delta()

    assert packet.surface == "activity_delta"
    assert fake_api.calls == [("visible_events_since", 5)]
    assert "What changed since sequence 5:" in packet.player_markdown
    assert "6 chat player_0002: New after checkpoint." in packet.player_markdown
    assert packet.agent_context["checkpoint_sequence"] == 5
    assert packet.agent_context["max_sequence"] == 7
    assert packet.agent_context["synced_event_count"] == 2
    assert session.local_log.max_server_sequence() == 7
    assert "hidden" not in packet.player_markdown


def test_codex_session_renders_crew_activity_with_active_crew(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_crew_activity()

    assert packet.surface == "crew_activity"
    assert fake_api.calls == ["visible_events"]
    assert "Crew activity: crew_0001" in packet.player_markdown
    assert packet.agent_context["crew_id"] == "crew_0001"
    assert packet.agent_context["crew_event_count"] == 1
    assert "hidden" not in packet.player_markdown


def test_codex_session_renders_crew_activity_delta_with_active_crew(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)
    session.local_log.sync_visible_server_events(
        [
            {
                "event_id": "evt_3",
                "sequence": 3,
                "type": "chat.message.created",
                "payload": {
                    "message_id": "msg_3",
                    "sender_player_id": "player_0001",
                    "body": "already synced",
                },
            }
        ]
    )

    packet = session.render_crew_activity_delta()

    assert packet.surface == "activity_delta"
    assert fake_api.calls == [("visible_events_since", 3)]
    assert "Crew changes since sequence 3: crew_0001" in packet.player_markdown
    assert "4 chat player_0002: New after checkpoint." in packet.player_markdown
    assert "Other crew delta." not in packet.player_markdown
    assert packet.agent_context["crew_id"] == "crew_0001"
    assert packet.agent_context["synced_event_count"] == 2
    assert packet.agent_context["activity_event_count"] == 1


def test_codex_session_renders_thread_with_cli_compatible_matching(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_thread("crew_0002:crew_0001")

    assert packet.surface == "thread"
    assert fake_api.calls == ["visible_events", ("visible_chat_events", "crew_0002:crew_0001")]
    assert "Conversation: crew_0002:crew_0001" in packet.player_markdown
    assert "1 player_0002: The bell moved." in packet.player_markdown
    assert "hidden" not in packet.player_markdown
    assert packet.agent_context["messages"] == [
        {
            "sequence": 1,
            "message_id": "msg_1",
            "sender_player_id": "player_0002",
            "sender_crew_id": "crew_0001",
            "recipient_crew_id": "crew_0002",
            "body": "The bell moved.",
            "artifact_ids": [],
        }
    ]


def test_codex_session_renders_conversations_from_synced_visible_events(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_conversations()

    assert packet.surface == "conversations"
    assert fake_api.calls == ["visible_events", ("visible_chat_events", None)]
    assert "Visible conversations:" in packet.player_markdown
    assert "crew_0001:crew_0002" in packet.player_markdown
    assert packet.agent_context["conversation_count"] == 1
    assert packet.agent_context["conversations"][0]["conversation_id"] == (
        "crew_0001:crew_0002"
    )
    assert "hidden" not in packet.player_markdown


def test_codex_session_preview_submit_action_does_not_call_mutating_api(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.submit_action(
        intent="Inspect the red ledger.",
        confirm=False,
        rumor_id="rumor_msg_000001",
        rumor_response_mode="contain",
        responds_to_rumor_escalation=True,
        rumor_escalation_mode="exploit",
    )

    assert packet.surface == "mutation"
    assert packet.agent_context["mutation"] is False
    assert packet.agent_context["preview"] == {
        "crew_id": "crew_0001",
        "intent": "Inspect the red ledger.",
        "rumor_id": "rumor_msg_000001",
        "rumor_response_mode": "contain",
        "responds_to_rumor_escalation": True,
        "rumor_escalation_mode": "exploit",
    }
    assert fake_api.calls == []


def test_codex_session_confirm_submit_action_calls_api_with_active_crew(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    monkeypatch.setattr(
        "hollow_lodge.client.codex_session.new_command_key",
        lambda prefix: f"{prefix}.fixed",
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.submit_action(
        intent="Inspect the red ledger.",
        confirm=True,
        rumor_id="rumor_msg_000001",
        rumor_response_mode="contain",
        responds_to_rumor_escalation=True,
        rumor_escalation_mode="exploit",
    )

    assert packet.agent_context["mutation"] is True
    assert packet.agent_context["result"] == {
        "action_id": "action_000001",
        "crew_id": "crew_0001",
        "intent": "Inspect the red ledger.",
        "responds_to_rumor_id": "rumor_msg_000001",
        "rumor_response_mode": "contain",
        "responds_to_rumor_escalation": True,
        "rumor_escalation_mode": "exploit",
    }
    assert fake_api.calls == [
        (
            "submit_action",
            {
                "crew_id": "crew_0001",
                "intent": "Inspect the red ledger.",
                "idempotency_key": "action-submit.fixed",
                "rumor_id": "rumor_msg_000001",
                "rumor_response_mode": "contain",
                "responds_to_rumor_escalation": True,
                "rumor_escalation_mode": "exploit",
            },
        ),
        "visible_events",
    ]


def test_codex_session_edit_action_preview_does_not_mutate(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.edit_action(
        action_id="action_000001",
        intent="  Inspect under candlelight.  ",
        confirm=False,
    )

    assert packet.surface == "mutation"
    assert "Preview: edit_action" in packet.player_markdown
    assert packet.agent_context["mutation"] is False
    assert packet.agent_context["preview"] == {
        "action_id": "action_000001",
        "intent": "Inspect under candlelight.",
    }
    assert fake_api.calls == []


def test_codex_session_edit_and_cancel_action_confirm_dispatch_and_syncs(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    monkeypatch.setattr(
        "hollow_lodge.client.codex_session.new_command_key",
        lambda prefix: f"{prefix}.fixed",
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    edited = session.edit_action(
        action_id="action_000001",
        intent=" Inspect under candlelight. ",
        confirm=True,
    )
    canceled = session.cancel_action(action_id="action_000001", confirm=True)

    assert edited.agent_context["result"] == {
        "action_id": "action_000001",
        "crew_id": "crew_0001",
        "intent": "Inspect under candlelight.",
        "status": "edited",
    }
    assert canceled.agent_context["result"] == {
        "action_id": "action_000001",
        "crew_id": "crew_0001",
        "intent": "Inspect the ledger.",
        "status": "canceled",
    }
    assert "server_notes" not in str(edited.agent_context)
    assert "server_notes" not in str(canceled.agent_context)
    assert fake_api.calls == [
        (
            "edit_action",
            {
                "action_id": "action_000001",
                "intent": "Inspect under candlelight.",
                "idempotency_key": "action-edit.fixed",
            },
        ),
        "visible_events",
        (
            "cancel_action",
            {
                "action_id": "action_000001",
                "idempotency_key": "action-cancel.fixed",
            },
        ),
        "visible_events",
    ]


def test_codex_session_edit_action_validates_replacement_intent_before_mutation(
    tmp_path,
):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    with pytest.raises(ValueError, match="replacement action intent is required"):
        session.edit_action(
            action_id="action_000001",
            intent="   ",
            confirm=True,
        )

    assert fake_api.calls == []


def test_codex_session_accept_deal_preview_shows_consequences_without_accepting(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0002",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.accept_deal(deal_id="deal_000001", confirm=False)

    assert packet.surface == "deal_preview"
    assert "Your side: recipient" in packet.player_markdown
    assert "Your crew gives: artifact_chapel_debt_mark" in packet.player_markdown
    assert "Your crew receives: artifact_ledger_rubric" in packet.player_markdown
    assert packet.agent_context["mutation"] is False
    assert fake_api.calls == ["visible_events", "deals"]


def test_codex_session_deal_decline_and_cancel_preview_without_mutation(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    decline = session.decline_deal(deal_id="deal_000001", confirm=False)
    cancel = session.cancel_deal(deal_id="deal_000001", confirm=False)

    assert decline.surface == "mutation"
    assert "Preview: decline_deal" in decline.player_markdown
    assert "- deal_id: deal_000001" in decline.player_markdown
    assert decline.agent_context == {
        "operation": "decline_deal",
        "mutation": False,
        "confirmed": False,
        "preview": {"deal_id": "deal_000001"},
    }
    assert cancel.surface == "mutation"
    assert "Preview: cancel_deal" in cancel.player_markdown
    assert "- deal_id: deal_000001" in cancel.player_markdown
    assert cancel.agent_context == {
        "operation": "cancel_deal",
        "mutation": False,
        "confirmed": False,
        "preview": {"deal_id": "deal_000001"},
    }
    assert fake_api.calls == []


def test_codex_session_send_message_preview_does_not_mutate(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.send_message(
        scope="crew_to_crew",
        recipient_crew_id="crew_0002",
        body="  Trade the ledger?  ",
        artifact_ids=["artifact_ledger_rubric"],
        confirm=False,
    )

    assert packet.surface == "mutation"
    assert "Preview: send_message" in packet.player_markdown
    assert packet.agent_context["mutation"] is False
    assert packet.agent_context["preview"] == {
        "scope": "crew_to_crew",
        "sender_crew_id": "crew_0001",
        "recipient_crew_id": "crew_0002",
        "body": "Trade the ledger?",
        "artifact_ids": ["artifact_ledger_rubric"],
    }
    assert fake_api.calls == []


def test_codex_session_send_message_confirm_dispatches_and_syncs(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    monkeypatch.setattr(
        "hollow_lodge.client.codex_session.new_command_key",
        lambda prefix: f"{prefix}.fixed",
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    direct = session.send_message(
        scope="direct",
        recipient_player_id="player_0002",
        body="Trade the ledger?",
        artifact_ids=["artifact_ledger_rubric"],
        confirm=True,
    )
    crew = session.send_message(
        scope="crew",
        body="Meet by the archive.",
        confirm=True,
    )
    crew_to_crew = session.send_message(
        scope="crew_to_crew",
        recipient_crew_id="crew_0002",
        body="Trade the ledger?",
        confirm=True,
    )

    assert direct.agent_context["result"] == {
        "message_id": "msg_direct_000001",
        "conversation_id": "msg_direct_000001",
        "scope": "direct",
    }
    assert crew.agent_context["result"]["conversation_id"] == "crew_0001"
    assert crew_to_crew.agent_context["result"]["conversation_id"] == "crew_0001:crew_0002"
    assert fake_api.calls == [
        (
            "send_direct_message",
            {
                "recipient_player_id": "player_0002",
                "body": "Trade the ledger?",
                "artifact_ids": ["artifact_ledger_rubric"],
                "idempotency_key": "chat-direct.fixed",
            },
        ),
        "visible_events",
        (
            "send_crew_message",
            {
                "crew_id": "crew_0001",
                "body": "Meet by the archive.",
                "artifact_ids": [],
                "idempotency_key": "chat-crew.fixed",
            },
        ),
        "visible_events",
        (
            "send_crew_to_crew_message",
            {
                "sender_crew_id": "crew_0001",
                "recipient_crew_id": "crew_0002",
                "body": "Trade the ledger?",
                "artifact_ids": [],
                "idempotency_key": "chat-crew-to-crew.fixed",
            },
        ),
        "visible_events",
    ]


def test_codex_session_send_message_validates_required_fields_before_mutation(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    try:
        session.send_message(scope="direct", body="Hello.", confirm=True)
    except ValueError as exc:
        assert "recipient_player_id is required" in str(exc)
    else:
        raise AssertionError("missing direct recipient should fail")

    try:
        session.send_message(scope="crew_to_crew", body="Hello.", confirm=True)
    except ValueError as exc:
        assert "recipient_crew_id is required" in str(exc)
    else:
        raise AssertionError("missing recipient crew should fail")

    assert fake_api.calls == []


def test_codex_session_confirmed_mutations_use_expected_api_calls(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    keys: list[str] = []

    def fake_key(prefix: str) -> str:
        keys.append(prefix)
        return f"{prefix}.fixed"

    monkeypatch.setattr("hollow_lodge.client.codex_session.new_command_key", fake_key)
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packets = [
        session.dossier_contribute(
            note="The ledger hand changes after the chapel seal.",
            evidence_ids=["fragment_1", "artifact_ledger_rubric"],
            confirm=True,
        ),
        session.dossier_cite_artifact(
            artifact_id="artifact_ledger_rubric",
            claim="The ledger contradicts the lot card.",
            quote="The last hand is later.",
            confirm=True,
        ),
        session.inspect_artifact(
            artifact_id="artifact_ledger_rubric",
            confirm=True,
        ),
        session.dossier_update_framing(
            claim="The finger is false.",
            evidence_ids=["artifact_ledger_rubric"],
            reasoning="The ledger and chapel mark undermine the lot story.",
            weaknesses="Material testing remains incomplete.",
            provenance_concerns="Traded copy requires source caution.",
            confirm=True,
        ),
        session.propose_deal(
            recipient_crew_id="crew_0002",
            offered_artifact_ids=["artifact_ledger_rubric"],
            requested_artifact_ids=["artifact_chapel_debt_mark"],
            confirm=True,
        ),
        session.accept_deal(deal_id="deal_000001", confirm=True),
        session.decline_deal(deal_id="deal_000001", confirm=True),
        session.cancel_deal(deal_id="deal_000001", confirm=True),
        session.transfer_artifact(
            artifact_id="artifact_ledger_rubric",
            recipient_player_id="player_0002",
            confirm=True,
        ),
        session.vote_packet_lead(player_id="player_0002", confirm=True),
    ]

    assert all(packet.surface == "mutation" for packet in packets)
    assert all(packet.agent_context["mutation"] is True for packet in packets)
    assert packets[0].agent_context["result"]["member_contributions"] == [
        {
            "player_id": "player_0001",
            "note": "The ledger hand changes after the chapel seal.",
            "evidence_ids": ["fragment_1", "artifact_ledger_rubric"],
        }
    ]
    assert packets[2].agent_context["result"] == {
        "artifact_id": "artifact_ledger_rubric",
        "title": "Red Ledger Rubric",
        "kind": "ledger",
        "public_summary": "A copied rubric marks prior ownership.",
    }
    assert "server_notes" not in str(packets[2].agent_context)
    assert "Lot 19 passed under chapel seal" not in str(packets[2].agent_context)
    assert packets[5].agent_context["result"]["recipient_received_artifact_ids"] == [
        "artifact_ledger_rubric.dealcopy.deal_000001.crew_0002.1"
    ]
    assert packets[6].agent_context["result"]["status"] == "declined"
    assert packets[7].agent_context["result"]["status"] == "canceled"
    assert keys == [
        "dossier-contribute",
        "dossier-cite-artifact",
        "artifact-inspect",
        "dossier-framing",
        "deal-propose",
        "deal-accept",
        "deal-decline",
        "deal-cancel",
        "artifact-transfer",
        "packet-lead-vote",
    ]
    assert fake_api.calls == [
        (
            "add_dossier_contribution",
            {
                "crew_id": "crew_0001",
                "note": "The ledger hand changes after the chapel seal.",
                "evidence_ids": ["fragment_1", "artifact_ledger_rubric"],
                "idempotency_key": "dossier-contribute.fixed",
            },
        ),
        "visible_events",
        (
            "cite_artifact_in_dossier",
            {
                "crew_id": "crew_0001",
                "artifact_id": "artifact_ledger_rubric",
                "claim": "The ledger contradicts the lot card.",
                "quote": "The last hand is later.",
                "idempotency_key": "dossier-cite-artifact.fixed",
            },
        ),
        "visible_events",
        (
            "inspect_artifact",
            {
                "artifact_id": "artifact_ledger_rubric",
                "idempotency_key": "artifact-inspect.fixed",
            },
        ),
        "visible_events",
        (
            "update_dossier_framing",
            {
                "crew_id": "crew_0001",
                "claim": "The finger is false.",
                "evidence_ids": ["artifact_ledger_rubric"],
                "reasoning": "The ledger and chapel mark undermine the lot story.",
                "weaknesses": "Material testing remains incomplete.",
                "provenance_concerns": "Traded copy requires source caution.",
                "idempotency_key": "dossier-framing.fixed",
            },
        ),
        "visible_events",
        (
            "propose_deal",
            {
                "contract_id": "contract_false_finger",
                "proposer_crew_id": "crew_0001",
                "recipient_crew_id": "crew_0002",
                "offered_artifact_ids": ["artifact_ledger_rubric"],
                "requested_artifact_ids": ["artifact_chapel_debt_mark"],
                "soft_terms": [],
                "expires_phase": None,
                "idempotency_key": "deal-propose.fixed",
            },
        ),
        "visible_events",
        ("accept_deal", {"deal_id": "deal_000001", "idempotency_key": "deal-accept.fixed"}),
        "visible_events",
        ("decline_deal", {"deal_id": "deal_000001", "idempotency_key": "deal-decline.fixed"}),
        "visible_events",
        ("cancel_deal", {"deal_id": "deal_000001", "idempotency_key": "deal-cancel.fixed"}),
        "visible_events",
        (
            "transfer_artifact",
            {
                "artifact_id": "artifact_ledger_rubric",
                "recipient_player_id": "player_0002",
                "idempotency_key": "artifact-transfer.fixed",
            },
        ),
        "visible_events",
        (
            "vote_packet_lead",
            {
                "crew_id": "crew_0001",
                "player_id": "player_0002",
                "idempotency_key": "packet-lead-vote.fixed",
            },
        ),
        "visible_events",
    ]


def test_codex_session_inspect_artifact_preview_does_not_call_api(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.inspect_artifact(
        artifact_id="artifact_ledger_rubric",
        confirm=False,
    )

    assert packet.surface == "mutation"
    assert packet.agent_context == {
        "operation": "inspect_artifact",
        "mutation": False,
        "confirmed": False,
        "preview": {"artifact_id": "artifact_ledger_rubric"},
    }
    assert fake_api.calls == []


def test_codex_session_dossier_update_framing_rejects_empty_update(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    with pytest.raises(ValueError, match="at least one dossier framing field is required"):
        session.dossier_update_framing(confirm=True)

    assert fake_api.calls == []


def test_codex_session_phase_lock_preview_reads_board_without_mutation(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.phase_lock(
        contract_id="contract_false_finger",
        hours_elapsed=6,
        confirm=False,
    )

    assert packet.surface == "mutation"
    assert "Preview: phase_lock" in packet.player_markdown
    assert "No server mutation was submitted." in packet.player_markdown
    assert packet.agent_context["mutation"] is False
    assert packet.agent_context["preview"] == {
        "contract_id": "contract_false_finger",
        "title": "The Saint's False Finger",
        "phase": "Auction Preview",
        "remaining_hours": 6,
        "hours_elapsed": 6,
    }
    assert fake_api.calls == ["contracts"]


def test_codex_session_phase_lock_confirm_calls_api_and_syncs(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    fake_api = FakeApi()
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    monkeypatch.setattr(
        "hollow_lodge.client.codex_session.new_command_key",
        lambda prefix: f"{prefix}.fixed",
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.phase_lock(
        contract_id="contract_false_finger",
        hours_elapsed=6,
        confirm=True,
    )

    assert packet.surface == "mutation"
    assert "Submitted: phase_lock" in packet.player_markdown
    assert packet.agent_context["mutation"] is True
    assert packet.agent_context["result"] == {
        "status": "resolved",
        "contract_id": "contract_false_finger",
        "phase": "auction-preview",
        "standings": [{"crew_id": "crew_0001", "standing": "Strong lead", "score": 82}],
        "contract_state": ["Auction house provenance is now suspect."],
    }
    assert "hidden_truth_summary" not in str(packet.agent_context)
    assert fake_api.calls == [
        (
            "lock_auction_preview_phase",
            {
                "contract_id": "contract_false_finger",
                "hours_elapsed": 6,
                "idempotency_key": "phase-lock.fixed",
            },
        ),
        "visible_events",
    ]
