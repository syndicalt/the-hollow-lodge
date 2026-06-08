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
