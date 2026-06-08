import subprocess
import sys

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

    def contracts(self):
        self.calls.append("contracts")
        return {"campaign": {"title": "Saints & Ledgers"}, "contracts": []}

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

    def submit_action(
        self,
        *,
        crew_id: str,
        intent: str,
        idempotency_key: str,
        rumor_id: str | None = None,
    ):
        self.calls.append(
            (
                "submit_action",
                {
                    "crew_id": crew_id,
                    "intent": intent,
                    "idempotency_key": idempotency_key,
                    "rumor_id": rumor_id,
                },
            )
        )
        result = {"action_id": "action_000001", "crew_id": crew_id, "intent": intent}
        if rumor_id is not None:
            result["responds_to_rumor_id"] = rumor_id
        return result

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
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

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

    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)
    packet = session.render_inbox()

    assert fake_api.calls == ["me", "visible_events", "inbox"]
    assert load_config(config_path).display_name == "corelumen"
    assert "Inbox: corelumen" in packet.player_markdown
    assert packet.agent_context["player_id"] == "player_0001"


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
    assert fake_api.calls == ["visible_events"]
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
    )

    assert packet.surface == "mutation"
    assert packet.agent_context["mutation"] is False
    assert packet.agent_context["preview"] == {
        "crew_id": "crew_0001",
        "intent": "Inspect the red ledger.",
        "rumor_id": "rumor_msg_000001",
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
    )

    assert packet.agent_context["mutation"] is True
    assert packet.agent_context["result"] == {
        "action_id": "action_000001",
        "crew_id": "crew_0001",
        "intent": "Inspect the red ledger.",
        "responds_to_rumor_id": "rumor_msg_000001",
    }
    assert fake_api.calls == [
        (
            "submit_action",
            {
                "crew_id": "crew_0001",
                "intent": "Inspect the red ledger.",
                "idempotency_key": "action-submit.fixed",
                "rumor_id": "rumor_msg_000001",
            },
        ),
        "visible_events",
    ]


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
        session.propose_deal(
            recipient_crew_id="crew_0002",
            offered_artifact_ids=["artifact_ledger_rubric"],
            requested_artifact_ids=["artifact_chapel_debt_mark"],
            confirm=True,
        ),
        session.accept_deal(deal_id="deal_000001", confirm=True),
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
    assert packets[3].agent_context["result"]["recipient_received_artifact_ids"] == [
        "artifact_ledger_rubric.dealcopy.deal_000001.crew_0002.1"
    ]
    assert keys == [
        "dossier-contribute",
        "dossier-cite-artifact",
        "deal-propose",
        "deal-accept",
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
