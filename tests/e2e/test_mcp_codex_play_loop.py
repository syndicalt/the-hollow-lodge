import asyncio
from typing import Any

import httpx
from fastapi.testclient import TestClient

from hollow_lodge import mcp_server
from hollow_lodge.client.config import ClientConfig, save_config
from hollow_lodge.server.app import create_app


def _register(client: TestClient, invite: str, name: str) -> dict[str, str]:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _command_auth(token: str, key: str) -> dict[str, str]:
    return {**_auth(token), "Idempotency-Key": key}


def _create_crew(
    client: TestClient,
    *,
    token: str,
    name: str,
    key: str,
) -> dict[str, Any]:
    response = client.post(
        "/crews",
        json={"name": name},
        headers=_command_auth(token, key),
    )
    assert response.status_code == 201
    return response.json()


def _call_tool(name: str, arguments: dict[str, Any] | None = None):
    return asyncio.run(mcp_server.mcp.call_tool(name, arguments or {}))


def _assert_packet(result, *, surface: str) -> dict[str, Any]:
    assert result.content[0].type == "text"
    assert result.content[0].text == result.structuredContent["player_markdown"]
    assert not result.content[0].text.startswith("{")
    assert result.structuredContent["surface"] == surface
    return result.structuredContent


def test_player_can_progress_contract_through_actual_mcp_tools(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path / "server", invite_codes=["ada", "bela"])
    client = TestClient(app)
    ada = _register(client, "ada", "Ada Corelumen")
    bela = _register(client, "bela", "Bela Moth")
    crew = _create_crew(
        client,
        token=ada["token"],
        name="The Gilt Knives",
        key="crew-create-gilt",
    )
    moth = _create_crew(
        client,
        token=bela["token"],
        name="The Moth Lanterns",
        key="crew-create-moth",
    )

    config_path = tmp_path / "config.json"
    local_log_path = tmp_path / "local.jsonl"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id=ada["player_id"],
            token=ada["token"],
            active_crew_id=crew["crew_id"],
            display_name="Ada Corelumen",
        ),
    )
    monkeypatch.setattr(mcp_server, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_LOCAL_LOG_PATH", local_log_path)

    def fake_get(url, headers=None, params=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.get(path, headers=headers, params=params)

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.post(path, headers=headers, json=json)

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)

    landing = _assert_packet(_call_tool("render_what_now"), surface="what_now")
    assert landing["agent_context"]["mutation"] is False
    assert landing["agent_context"]["player"]["player_id"] == ada["player_id"]
    assert landing["agent_context"]["player"]["display_name"] == "Ada Corelumen"
    assert landing["agent_context"]["player"]["active_crew_id"] == crew["crew_id"]
    assert landing["agent_context"]["summary_counts"]["active_contracts"] == 1
    assert "What Now: Ada Corelumen" in landing["player_markdown"]

    message_preview = _assert_packet(
        _call_tool(
            "send_message",
            {
                "scope": "crew_to_crew",
                "sender_crew_id": crew["crew_id"],
                "recipient_crew_id": moth["crew_id"],
                "body": "We can trade ledger leverage before the auction closes.",
                "confirm": False,
            },
        ),
        surface="mutation",
    )
    assert message_preview["agent_context"] == {
        "operation": "send_message",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "scope": "crew_to_crew",
            "sender_crew_id": crew["crew_id"],
            "recipient_crew_id": moth["crew_id"],
            "body": "We can trade ledger leverage before the auction closes.",
            "artifact_ids": [],
        },
    }
    assert "No server mutation was submitted." in message_preview["player_markdown"]

    message_confirm = _assert_packet(
        _call_tool(
            "send_message",
            {
                "scope": "crew_to_crew",
                "sender_crew_id": crew["crew_id"],
                "recipient_crew_id": moth["crew_id"],
                "body": "We can trade ledger leverage before the auction closes.",
                "confirm": True,
            },
        ),
        surface="mutation",
    )
    assert message_confirm["agent_context"]["operation"] == "send_message"
    assert message_confirm["agent_context"]["mutation"] is True
    assert message_confirm["agent_context"]["confirmed"] is True
    assert message_confirm["agent_context"]["result"] == {
        "message_id": "msg_000001",
        "conversation_id": f"{crew['crew_id']}:{moth['crew_id']}",
        "scope": "crew_to_crew",
    }

    conversations = _assert_packet(
        _call_tool("render_conversations"),
        surface="conversations",
    )
    assert conversations["agent_context"]["conversation_count"] == 1
    conversation = conversations["agent_context"]["conversations"][0]
    assert conversation == {
        "conversation_id": f"{crew['crew_id']}:{moth['crew_id']}",
        "message_count": 1,
        "first_sequence": 10,
        "last_sequence": 10,
        "last_sender_player_id": ada["player_id"],
        "last_body": "We can trade ledger leverage before the auction closes.",
        "participant_ids": [crew["crew_id"], moth["crew_id"], ada["player_id"]],
        "artifact_reference_count": 0,
    }
    assert "Visible conversations:" in conversations["player_markdown"]
    assert f"- {crew['crew_id']}:{moth['crew_id']} (1 messages" in (
        conversations["player_markdown"]
    )

    thread = _assert_packet(
        _call_tool(
            "render_thread",
            {"conversation_id": conversation["conversation_id"]},
        ),
        surface="thread",
    )
    assert thread["agent_context"] == {
        "conversation_id": conversation["conversation_id"],
        "message_count": 1,
        "messages": [
            {
                "sequence": 10,
                "message_id": "msg_000001",
                "sender_player_id": ada["player_id"],
                "sender_crew_id": crew["crew_id"],
                "recipient_crew_id": moth["crew_id"],
                "body": "We can trade ledger leverage before the auction closes.",
                "artifact_ids": [],
            }
        ],
    }
    assert f"Conversation: {conversation['conversation_id']}" in thread["player_markdown"]
    assert "- 10 player_0001: We can trade ledger leverage" in (
        thread["player_markdown"]
    )

    action_preview = _assert_packet(
        _call_tool(
            "submit_action",
            {
                "crew_id": crew["crew_id"],
                "intent": "Compare the red ledger's date against the chapel timestamp.",
                "confirm": False,
            },
        ),
        surface="mutation",
    )
    assert action_preview["agent_context"] == {
        "operation": "submit_action",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "crew_id": crew["crew_id"],
            "intent": "Compare the red ledger's date against the chapel timestamp.",
        },
    }
    assert "No server mutation was submitted." in action_preview["player_markdown"]

    action_confirm = _assert_packet(
        _call_tool(
            "submit_action",
            {
                "crew_id": crew["crew_id"],
                "intent": "Compare the red ledger's date against the chapel timestamp.",
                "confirm": True,
            },
        ),
        surface="mutation",
    )
    assert action_confirm["agent_context"]["operation"] == "submit_action"
    assert action_confirm["agent_context"]["mutation"] is True
    assert action_confirm["agent_context"]["confirmed"] is True
    assert action_confirm["agent_context"]["result"] == {
        "action_id": "action_000001",
        "crew_id": crew["crew_id"],
        "intent": "Compare the red ledger's date against the chapel timestamp.",
        "status": "submitted",
    }

    crew_board = _assert_packet(
        _call_tool("render_crew_board", {"crew_id": crew["crew_id"]}),
        surface="crew_board",
    )
    action_decisions = [
        decision
        for decision in crew_board["agent_context"]["pending_decisions"]
        if decision["kind"] == "contract_action"
    ]
    assert action_decisions == [
        {
            "kind": "contract_action",
            "label": "Submitted action open for edits",
            "description": (
                "The Saint's False Finger has submitted action(s) that can still "
                "be reviewed, edited, or canceled before lock."
            ),
            "crew_id": crew["crew_id"],
            "contract_id": "contract_false_finger",
            "action": "review_submitted_action",
            "action_ids": ["action_000001"],
        }
    ]
    assert "Submitted action open for edits" in crew_board["player_markdown"]

    lock_preview = _assert_packet(
        _call_tool(
            "phase_lock",
            {
                "contract_id": "contract_false_finger",
                "hours_elapsed": 6,
                "confirm": False,
            },
        ),
        surface="mutation",
    )
    assert lock_preview["agent_context"]["mutation"] is False
    assert lock_preview["agent_context"]["operation"] == "phase_lock"
    assert lock_preview["agent_context"]["preview"] == {
        "contract_id": "contract_false_finger",
        "title": "The Saint's False Finger",
        "phase": "Auction Preview",
        "remaining_hours": 6,
        "hours_elapsed": 6,
    }

    lock_confirm = _assert_packet(
        _call_tool(
            "phase_lock",
            {
                "contract_id": "contract_false_finger",
                "hours_elapsed": 6,
                "confirm": True,
            },
        ),
        surface="mutation",
    )
    assert lock_confirm["agent_context"]["operation"] == "phase_lock"
    assert lock_confirm["agent_context"]["mutation"] is True
    assert lock_confirm["agent_context"]["result"]["status"] == "resolved"

    contract_board = _assert_packet(
        _call_tool("render_contract_board"),
        surface="contract_board",
    )
    contract = contract_board["agent_context"]["contracts"][0]
    assert contract["contract_id"] == "contract_false_finger"
    assert contract["phase"]["status"] == "resolved"
    assert contract["phase_result"]["standings"] == [
        {
            "crew_id": crew["crew_id"],
            "standing": "Viable",
            "score": 64,
            "score_reasoning": {
                "strengths": ["clean provenance contradiction"],
                "weaknesses": ["no material confirmation"],
                "penalties": [],
                "revealed_clues": ["Auction house provenance is now suspect."],
            },
        },
        {
            "crew_id": moth["crew_id"],
            "standing": "Weak",
            "score": 0,
            "score_reasoning": {
                "strengths": [],
                "weaknesses": ["no resolved proof lane"],
                "penalties": [],
                "revealed_clues": [],
            },
        },
    ]
    assert "Phase result:" in contract_board["player_markdown"]
    assert f"- {crew['crew_id']}: Viable (64)" in contract_board["player_markdown"]

    activity = _assert_packet(_call_tool("render_activity"), surface="activity")
    assert activity["agent_context"]["event_type_counts"]["action.submitted"] == 1
    assert activity["agent_context"]["event_type_counts"]["contract.phase.resolved"] == 1
    assert "phase result:" in activity["player_markdown"]

    serialized_packets = "\n".join(
        str(packet)
        for packet in (
            landing,
            message_preview,
            message_confirm,
            conversations,
            thread,
            crew_board,
            contract_board,
            activity,
        )
    )
    for forbidden in (
        "hidden_truth",
        "hidden_truth_summary",
        "contract.hidden_truth.seeded",
        "server_only",
        "visibility",
        "oracle.resolution",
        "accepted_output",
        "accepted_output_hash",
        "input_packet_hash",
        "provider",
        "model",
        "prompt_version",
        "validation_status",
        "fallback_reason",
        "token",
        "join_code",
        "idempotency_key",
        "event_id",
        "event_hash",
        "origin",
        "payload",
    ):
        assert forbidden not in serialized_packets
