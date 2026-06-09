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


def _join_crew(
    client: TestClient,
    *,
    player: dict[str, str],
    crew: dict[str, Any],
    key: str,
) -> None:
    response = client.post(
        f"/crews/{crew['crew_id']}/join",
        json={"join_code": crew["join_code"]},
        headers=_command_auth(player["token"], key),
    )
    assert response.status_code == 200


def _write_config(
    config_path,
    *,
    player: dict[str, str],
    active_crew_id: str,
    display_name: str,
) -> None:
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id=player["player_id"],
            token=player["token"],
            active_crew_id=active_crew_id,
            display_name=display_name,
        ),
    )


def _call_tool(name: str, arguments: dict[str, Any] | None = None):
    return asyncio.run(mcp_server.mcp.call_tool(name, arguments or {}))


def _install_httpx_test_bridge(monkeypatch, client: TestClient) -> None:
    def fake_get(url, headers=None, params=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.get(path, headers=headers, params=params)

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.post(path, headers=headers, json=json)

    def fake_patch(url, headers=None, json=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.patch(path, headers=headers, json=json)

    def fake_delete(url, headers=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.delete(path, headers=headers)

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "patch", fake_patch)
    monkeypatch.setattr(httpx, "delete", fake_delete)


def _assert_packet(result, *, surface: str) -> dict[str, Any]:
    assert result.content[0].type == "text"
    assert result.content[0].text == result.structuredContent["player_markdown"]
    assert not result.content[0].text.startswith("{")
    assert result.structuredContent["surface"] == surface
    return result.structuredContent


def test_player_can_transfer_and_check_proof_fragment_through_actual_mcp_tools(
    tmp_path,
    monkeypatch,
):
    app = create_app(data_dir=tmp_path / "server", invite_codes=["ada", "grace"])
    client = TestClient(app)
    ada = _register(client, "ada", "Ada Corelumen")
    grace = _register(client, "grace", "Grace Ledger")
    crew = _create_crew(
        client,
        token=ada["token"],
        name="The Gilt Knives",
        key="crew-create-gilt",
    )
    _join_crew(client, player=grace, crew=crew, key="crew-join-grace-gilt")

    config_path = tmp_path / "config.json"
    local_log_path = tmp_path / "local.jsonl"
    _write_config(
        config_path,
        player=ada,
        active_crew_id=crew["crew_id"],
        display_name="Ada Corelumen",
    )
    monkeypatch.setattr(mcp_server, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_LOCAL_LOG_PATH", local_log_path)
    _install_httpx_test_bridge(monkeypatch, client)

    transfer_preview = _assert_packet(
        _call_tool(
            "transfer_proof_fragment",
            {
                "fragment_id": "fragment_starter_ledger",
                "recipient_player_id": grace["player_id"],
                "confirm": False,
            },
        ),
        surface="mutation",
    )
    assert transfer_preview["agent_context"] == {
        "operation": "transfer_proof_fragment",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "fragment_id": "fragment_starter_ledger",
            "recipient_player_id": grace["player_id"],
        },
    }
    assert "No server mutation was submitted." in transfer_preview["player_markdown"]

    transfer_confirm = _assert_packet(
        _call_tool(
            "transfer_proof_fragment",
            {
                "fragment_id": "fragment_starter_ledger",
                "recipient_player_id": grace["player_id"],
                "confirm": True,
            },
        ),
        surface="mutation",
    )
    assert transfer_confirm["agent_context"]["operation"] == "transfer_proof_fragment"
    assert transfer_confirm["agent_context"]["mutation"] is True
    assert transfer_confirm["agent_context"]["confirmed"] is True
    copied_fragment_id = transfer_confirm["agent_context"]["result"]["fragment_id"]
    assert transfer_confirm["agent_context"]["result"] == {
        "fragment_id": copied_fragment_id,
        "content_summary": "A red ledger rubric names three prior owners.",
        "source_chain": [
            "archive:lot-card",
            f"transfer:{ada['player_id']}->{grace['player_id']}",
        ],
        "provenance_checked": False,
    }

    _write_config(
        config_path,
        player=grace,
        active_crew_id=crew["crew_id"],
        display_name="Grace Ledger",
    )
    grace_inbox = _assert_packet(_call_tool("render_inbox"), surface="inbox")
    assert grace_inbox["agent_context"]["incoming_proof_fragments"] == [
        {
            "fragment_id": copied_fragment_id,
            "summary": "A red ledger rubric names three prior owners.",
        }
    ]
    assert grace_inbox["agent_context"]["urgent_items"][-1] == {
        "kind": "proof_fragment",
        "fragment_id": copied_fragment_id,
    }
    assert f"- {copied_fragment_id}: A red ledger rubric names three prior owners." in (
        grace_inbox["player_markdown"]
    )

    fragment_before_check = _assert_packet(
        _call_tool("render_proof_fragment", {"fragment_id": copied_fragment_id}),
        surface="proof_fragment",
    )
    assert fragment_before_check["agent_context"]["fragment"] == {
        "fragment_id": copied_fragment_id,
        "content_summary": "A red ledger rubric names three prior owners.",
        "source_chain": [
            "archive:lot-card",
            f"transfer:{ada['player_id']}->{grace['player_id']}",
        ],
        "provenance_checked": False,
    }
    assert "Provenance checked: false" in fragment_before_check["player_markdown"]

    provenance_preview = _assert_packet(
        _call_tool(
            "check_provenance",
            {"fragment_id": copied_fragment_id, "confirm": False},
        ),
        surface="mutation",
    )
    assert provenance_preview["agent_context"] == {
        "operation": "check_provenance",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "fragment_id": copied_fragment_id,
            "check_type": "provenance",
        },
    }

    provenance_confirm = _assert_packet(
        _call_tool(
            "check_provenance",
            {"fragment_id": copied_fragment_id, "confirm": True},
        ),
        surface="mutation",
    )
    assert provenance_confirm["agent_context"] == {
        "operation": "check_provenance",
        "mutation": True,
        "confirmed": True,
        "result": {
            "fragment_id": copied_fragment_id,
            "content_summary": "A red ledger rubric names three prior owners.",
            "source_chain": [
                "archive:lot-card",
                f"transfer:{ada['player_id']}->{grace['player_id']}",
            ],
            "provenance_checked": True,
            "provenance_flags": ["copied-hand", "ink-after-binding"],
        },
    }
    assert "copied-hand, ink-after-binding" in provenance_confirm["player_markdown"]

    fragment_after_check = _assert_packet(
        _call_tool("render_proof_fragment", {"fragment_id": copied_fragment_id}),
        surface="proof_fragment",
    )
    assert fragment_after_check["agent_context"]["fragment"]["provenance_checked"] is False

    activity = _assert_packet(_call_tool("render_activity"), surface="activity")
    assert activity["agent_context"]["event_type_counts"]["proof.fragment.transferred"] == 1
    assert activity["agent_context"]["event_type_counts"]["proof.provenance.checked"] == 1
    assert f"proof fragment {copied_fragment_id}" in activity["player_markdown"]
    assert f"provenance {copied_fragment_id}: copied-hand, ink-after-binding" in (
        activity["player_markdown"]
    )

    serialized_packets = "\n".join(
        str(packet)
        for packet in (
            transfer_preview,
            transfer_confirm,
            grace_inbox,
            fragment_before_check,
            provenance_preview,
            provenance_confirm,
            fragment_after_check,
            activity,
        )
    )
    for forbidden in (
        "hidden_truth",
        "hidden_truth_summary",
        "contract.hidden_truth.seeded",
        "server_only",
        "server_notes",
        "visibility",
        "proof.fragment.transferred.internal",
        "source_fragment_id",
        "transfer_idempotency_key",
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


def test_player_can_decline_and_cancel_deals_through_actual_mcp_tools(
    tmp_path,
    monkeypatch,
):
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
    _write_config(
        config_path,
        player=ada,
        active_crew_id=crew["crew_id"],
        display_name="Ada Corelumen",
    )
    monkeypatch.setattr(mcp_server, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_LOCAL_LOG_PATH", local_log_path)
    _install_httpx_test_bridge(monkeypatch, client)

    decline_deal_confirm = _assert_packet(
        _call_tool(
            "propose_deal",
            {
                "recipient_crew_id": moth["crew_id"],
                "proposer_crew_id": crew["crew_id"],
                "offered_artifact_ids": ["artifact_ledger_rubric"],
                "requested_artifact_ids": ["artifact_lot_card"],
                "soft_terms": ["Let the Moth Lanterns inspect before auction lock."],
                "expires_phase": "Auction Preview",
                "confirm": True,
            },
        ),
        surface="mutation",
    )
    declined_deal_id = decline_deal_confirm["agent_context"]["result"]["deal_id"]
    assert declined_deal_id == "deal_000001"
    assert decline_deal_confirm["agent_context"]["result"]["status"] == "proposed"

    _write_config(
        config_path,
        player=bela,
        active_crew_id=moth["crew_id"],
        display_name="Bela Moth",
    )
    decline_preview = _assert_packet(
        _call_tool(
            "decline_deal",
            {"deal_id": declined_deal_id, "confirm": False},
        ),
        surface="mutation",
    )
    assert decline_preview["agent_context"] == {
        "operation": "decline_deal",
        "mutation": False,
        "confirmed": False,
        "preview": {"deal_id": declined_deal_id},
    }
    assert "No server mutation was submitted." in decline_preview["player_markdown"]

    decline_confirm = _assert_packet(
        _call_tool(
            "decline_deal",
            {"deal_id": declined_deal_id, "confirm": True},
        ),
        surface="mutation",
    )
    assert decline_confirm["agent_context"]["operation"] == "decline_deal"
    assert decline_confirm["agent_context"]["mutation"] is True
    assert decline_confirm["agent_context"]["confirmed"] is True
    assert decline_confirm["agent_context"]["result"]["deal_id"] == declined_deal_id
    assert decline_confirm["agent_context"]["result"]["status"] == "declined"
    assert "deal_000001 declined" in decline_confirm["player_markdown"]

    bela_deals = _assert_packet(_call_tool("render_deals"), surface="deals")
    assert [deal["status"] for deal in bela_deals["agent_context"]["deals"]] == [
        "declined"
    ]
    assert "deal_000001 declined" in bela_deals["player_markdown"]

    _write_config(
        config_path,
        player=ada,
        active_crew_id=crew["crew_id"],
        display_name="Ada Corelumen",
    )
    cancel_deal_confirm = _assert_packet(
        _call_tool(
            "propose_deal",
            {
                "recipient_crew_id": moth["crew_id"],
                "proposer_crew_id": crew["crew_id"],
                "offered_artifact_ids": ["artifact_ledger_rubric"],
                "requested_artifact_ids": ["artifact_lot_card"],
                "soft_terms": ["Withdrawable if the auction heat rises."],
                "expires_phase": "Auction Preview",
                "confirm": True,
            },
        ),
        surface="mutation",
    )
    canceled_deal_id = cancel_deal_confirm["agent_context"]["result"]["deal_id"]
    assert canceled_deal_id == "deal_000002"
    assert cancel_deal_confirm["agent_context"]["result"]["status"] == "proposed"

    cancel_preview = _assert_packet(
        _call_tool(
            "cancel_deal",
            {"deal_id": canceled_deal_id, "confirm": False},
        ),
        surface="mutation",
    )
    assert cancel_preview["agent_context"] == {
        "operation": "cancel_deal",
        "mutation": False,
        "confirmed": False,
        "preview": {"deal_id": canceled_deal_id},
    }
    assert "No server mutation was submitted." in cancel_preview["player_markdown"]

    cancel_confirm = _assert_packet(
        _call_tool(
            "cancel_deal",
            {"deal_id": canceled_deal_id, "confirm": True},
        ),
        surface="mutation",
    )
    assert cancel_confirm["agent_context"]["operation"] == "cancel_deal"
    assert cancel_confirm["agent_context"]["mutation"] is True
    assert cancel_confirm["agent_context"]["confirmed"] is True
    assert cancel_confirm["agent_context"]["result"]["deal_id"] == canceled_deal_id
    assert cancel_confirm["agent_context"]["result"]["status"] == "canceled"
    assert "deal_000002 canceled" in cancel_confirm["player_markdown"]

    ada_deals = _assert_packet(_call_tool("render_deals"), surface="deals")
    assert [deal["status"] for deal in ada_deals["agent_context"]["deals"]] == [
        "declined",
        "canceled",
    ]
    assert "deal_000001 declined" in ada_deals["player_markdown"]
    assert "deal_000002 canceled" in ada_deals["player_markdown"]

    activity = _assert_packet(_call_tool("render_activity"), surface="activity")
    assert activity["agent_context"]["event_type_counts"]["deal.proposed"] == 2
    assert activity["agent_context"]["event_type_counts"]["deal.declined"] == 1
    assert activity["agent_context"]["event_type_counts"]["deal.canceled"] == 1

    serialized_packets = "\n".join(
        str(packet)
        for packet in (
            decline_deal_confirm,
            decline_preview,
            decline_confirm,
            bela_deals,
            cancel_deal_confirm,
            cancel_preview,
            cancel_confirm,
            ada_deals,
            activity,
        )
    )
    for forbidden in (
        "hidden_truth",
        "hidden_truth_summary",
        "contract.hidden_truth.seeded",
        "server_only",
        "server_notes",
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


def test_player_can_progress_contract_through_actual_mcp_tools(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path / "server", invite_codes=["ada", "bela", "grace"])
    client = TestClient(app)
    ada = _register(client, "ada", "Ada Corelumen")
    bela = _register(client, "bela", "Bela Moth")
    grace = _register(client, "grace", "Grace Ledger")
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
    _join_crew(client, player=grace, crew=crew, key="crew-join-grace-gilt")

    config_path = tmp_path / "config.json"
    local_log_path = tmp_path / "local.jsonl"
    _write_config(
        config_path,
        player=ada,
        active_crew_id=crew["crew_id"],
        display_name="Ada Corelumen",
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

    def fake_patch(url, headers=None, json=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.patch(path, headers=headers, json=json)

    def fake_delete(url, headers=None, timeout=None):
        assert url.startswith("http://testserver")
        path = url.removeprefix("http://testserver")
        return client.delete(path, headers=headers)

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "patch", fake_patch)
    monkeypatch.setattr(httpx, "delete", fake_delete)

    landing = _assert_packet(_call_tool("render_what_now"), surface="what_now")
    assert landing["agent_context"]["mutation"] is False
    assert landing["agent_context"]["player"]["player_id"] == ada["player_id"]
    assert landing["agent_context"]["player"]["display_name"] == "Ada Corelumen"
    assert landing["agent_context"]["player"]["active_crew_id"] == crew["crew_id"]
    assert landing["agent_context"]["summary_counts"]["active_contracts"] == 1
    assert "What Now: Ada Corelumen" in landing["player_markdown"]

    artifacts = _assert_packet(_call_tool("render_artifacts"), surface="artifact_graph")
    artifact_graph = artifacts["agent_context"]["artifact_graph"]
    assert artifact_graph["contract_id"] == "multiple"
    assert artifact_graph["artifacts"] == [
        {
            "artifact_id": "artifact_lot_card",
            "contract_id": "contract_false_finger",
            "title": "Auction Lot Card",
            "kind": "lot_card",
            "public_summary": (
                "A vellum card attributes the reliquary finger to Saint Aint."
            ),
            "visible_flags": ["public-lot"],
            "proof_lanes": ["provenance", "leverage"],
            "phase_relevance": ["Auction Preview"],
            "copy_policy": "copyable",
        },
        {
            "artifact_id": "artifact_ledger_rubric",
            "contract_id": "contract_false_finger",
            "title": "Red Ledger Rubric",
            "kind": "ledger",
            "public_summary": (
                "A copied rubric marks three prior owners in an unfamiliar hand."
            ),
            "visible_flags": ["copied-hand"],
            "proof_lanes": ["provenance", "material"],
            "phase_relevance": ["Auction Preview"],
            "copy_policy": "copyable",
        },
    ]
    assert artifact_graph["edges"] == [
        {
            "source_id": "artifact_lot_card",
            "target_id": "artifact_ledger_rubric",
            "relation": "contradicts",
            "public_summary": (
                "The public lot card and copied ledger disagree on custody."
            ),
        }
    ]
    assert "Known Artifacts" in artifacts["player_markdown"]
    assert "Red Ledger Rubric" in artifacts["player_markdown"]
    assert "Rubric copy: Armitage" not in artifacts["player_markdown"]

    artifact_detail = _assert_packet(
        _call_tool("render_artifact", {"artifact_id": "artifact_ledger_rubric"}),
        surface="artifact",
    )
    assert artifact_detail["agent_context"]["artifact"] == {
        **artifact_graph["artifacts"][1],
        "full_text": (
            "Rubric copy: Armitage, then Venn, then a chapel debt mark. The last "
            "hand is redder and later than the binding."
        ),
        "source_chain": ["archive:lot-card"],
    }
    assert "Artifact: Red Ledger Rubric" in artifact_detail["player_markdown"]
    assert "Source: Rubric copy: Armitage" in (
        artifact_detail["player_markdown"]
    )

    artifact_inspect_preview = _assert_packet(
        _call_tool(
            "inspect_artifact",
            {"artifact_id": "artifact_ledger_rubric", "confirm": False},
        ),
        surface="mutation",
    )
    assert artifact_inspect_preview["agent_context"] == {
        "operation": "inspect_artifact",
        "mutation": False,
        "confirmed": False,
        "preview": {"artifact_id": "artifact_ledger_rubric"},
    }
    assert "No server mutation was submitted." in (
        artifact_inspect_preview["player_markdown"]
    )

    artifact_inspect_confirm = _assert_packet(
        _call_tool(
            "inspect_artifact",
            {"artifact_id": "artifact_ledger_rubric", "confirm": True},
        ),
        surface="mutation",
    )
    assert artifact_inspect_confirm["agent_context"] == {
        "operation": "inspect_artifact",
        "mutation": True,
        "confirmed": True,
        "result": {
            "artifact_id": "artifact_ledger_rubric",
            "title": "Red Ledger Rubric",
            "kind": "ledger",
            "public_summary": (
                "A copied rubric marks three prior owners in an unfamiliar hand."
            ),
        },
    }

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
        "first_sequence": 13,
        "last_sequence": 13,
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
                "sequence": 13,
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
    assert "- 13 player_0001: We can trade ledger leverage" in (
        thread["player_markdown"]
    )

    client.app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="mcp escrow setup",
        idempotency_key="mcp-grant-chapel",
    )
    deal_preview = _assert_packet(
        _call_tool(
            "propose_deal",
            {
                "recipient_crew_id": moth["crew_id"],
                "proposer_crew_id": crew["crew_id"],
                "offered_artifact_ids": ["artifact_ledger_rubric"],
                "requested_artifact_ids": ["artifact_chapel_debt_mark"],
                "soft_terms": ["Do not cite the Gilt crew before lock."],
                "expires_phase": "Auction Preview",
                "confirm": False,
            },
        ),
        surface="mutation",
    )
    assert deal_preview["agent_context"] == {
        "operation": "propose_deal",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "contract_id": "contract_false_finger",
            "proposer_crew_id": crew["crew_id"],
            "recipient_crew_id": moth["crew_id"],
            "offered_artifact_ids": ["artifact_ledger_rubric"],
            "requested_artifact_ids": ["artifact_chapel_debt_mark"],
            "soft_terms": ["Do not cite the Gilt crew before lock."],
            "expires_phase": "Auction Preview",
        },
    }
    assert "No server mutation was submitted." in deal_preview["player_markdown"]

    deal_confirm = _assert_packet(
        _call_tool(
            "propose_deal",
            {
                "recipient_crew_id": moth["crew_id"],
                "proposer_crew_id": crew["crew_id"],
                "offered_artifact_ids": ["artifact_ledger_rubric"],
                "requested_artifact_ids": ["artifact_chapel_debt_mark"],
                "soft_terms": ["Do not cite the Gilt crew before lock."],
                "expires_phase": "Auction Preview",
                "confirm": True,
            },
        ),
        surface="mutation",
    )
    assert deal_confirm["agent_context"]["operation"] == "propose_deal"
    assert deal_confirm["agent_context"]["mutation"] is True
    assert deal_confirm["agent_context"]["confirmed"] is True
    proposed_deal = deal_confirm["agent_context"]["result"]
    assert proposed_deal["deal_id"] == "deal_000001"
    assert proposed_deal["status"] == "proposed"
    assert proposed_deal["proposer_crew_id"] == crew["crew_id"]
    assert proposed_deal["recipient_crew_id"] == moth["crew_id"]

    ada_deals = _assert_packet(_call_tool("render_deals"), surface="deals")
    assert ada_deals["agent_context"]["deals"] == [proposed_deal]
    assert "deal_000001 proposed" in ada_deals["player_markdown"]

    _write_config(
        config_path,
        player=bela,
        active_crew_id=moth["crew_id"],
        display_name="Bela Moth",
    )
    moth_inbox = _assert_packet(_call_tool("render_inbox"), surface="inbox")
    incoming_deals = [
        decision
        for decision in moth_inbox["agent_context"]["pending_decisions"]
        if decision["kind"] == "incoming_deal"
    ]
    assert incoming_deals == [
        {
            "kind": "incoming_deal",
            "label": "Incoming deal needs response",
            "description": "Deal deal_000001 from crew_0001 needs a response.",
            "crew_id": moth["crew_id"],
            "contract_id": "contract_false_finger",
            "deal_id": "deal_000001",
        }
    ]
    assert "Incoming deal needs response" in moth_inbox["player_markdown"]

    deal_accept_preview = _assert_packet(
        _call_tool("preview_deal_acceptance", {"deal_id": "deal_000001"}),
        surface="deal_preview",
    )
    assert deal_accept_preview["agent_context"]["deal"]["deal_id"] == "deal_000001"
    assert deal_accept_preview["agent_context"]["viewer_side"] == "recipient"
    assert deal_accept_preview["agent_context"]["gives_artifact_ids"] == [
        "artifact_chapel_debt_mark"
    ]
    assert deal_accept_preview["agent_context"]["receives_artifact_ids"] == [
        "artifact_ledger_rubric"
    ]
    assert "This preview does not accept the deal." in (
        deal_accept_preview["player_markdown"]
    )
    deal_accept_confirm = _assert_packet(
        _call_tool("accept_deal", {"deal_id": "deal_000001", "confirm": True}),
        surface="mutation",
    )
    assert deal_accept_confirm["agent_context"]["operation"] == "accept_deal"
    assert deal_accept_confirm["agent_context"]["mutation"] is True
    fulfilled_deal = deal_accept_confirm["agent_context"]["result"]
    assert fulfilled_deal["deal_id"] == "deal_000001"
    assert fulfilled_deal["status"] == "fulfilled"
    assert fulfilled_deal["proposer_received_artifact_ids"] == [
        "artifact_chapel_debt_mark.dealcopy.deal_000001.crew_0001.2"
    ]
    assert fulfilled_deal["recipient_received_artifact_ids"] == [
        "artifact_ledger_rubric.dealcopy.deal_000001.crew_0002.1"
    ]

    _write_config(
        config_path,
        player=ada,
        active_crew_id=crew["crew_id"],
        display_name="Ada Corelumen",
    )
    gilt_received_artifact_id = fulfilled_deal["proposer_received_artifact_ids"][0]

    citation_preview = _assert_packet(
        _call_tool(
            "dossier_cite_artifact",
            {
                "crew_id": crew["crew_id"],
                "artifact_id": gilt_received_artifact_id,
                "claim": "The chapel mark dates the debt after the public lot story.",
                "quote": "Chapel debt mark, copied through escrow.",
                "confirm": False,
            },
        ),
        surface="mutation",
    )
    assert citation_preview["agent_context"] == {
        "operation": "dossier_cite_artifact",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "crew_id": crew["crew_id"],
            "artifact_id": gilt_received_artifact_id,
            "claim": "The chapel mark dates the debt after the public lot story.",
            "quote": "Chapel debt mark, copied through escrow.",
        },
    }
    assert "No server mutation was submitted." in citation_preview["player_markdown"]

    citation_confirm = _assert_packet(
        _call_tool(
            "dossier_cite_artifact",
            {
                "crew_id": crew["crew_id"],
                "artifact_id": gilt_received_artifact_id,
                "claim": "The chapel mark dates the debt after the public lot story.",
                "quote": "Chapel debt mark, copied through escrow.",
                "confirm": True,
            },
        ),
        surface="mutation",
    )
    assert citation_confirm["agent_context"]["operation"] == "dossier_cite_artifact"
    assert citation_confirm["agent_context"]["mutation"] is True
    assert citation_confirm["agent_context"]["confirmed"] is True
    cited_dossier = citation_confirm["agent_context"]["result"]
    assert cited_dossier["dossier_id"] == f"dossier_{crew['crew_id']}"
    assert cited_dossier["crew_id"] == crew["crew_id"]
    assert cited_dossier["packet_lead_player_id"] == ada["player_id"]
    assert cited_dossier["artifact_citations"] == [
        {
            "player_id": ada["player_id"],
            "artifact_id": gilt_received_artifact_id,
            "claim": "The chapel mark dates the debt after the public lot story.",
            "quote": "Chapel debt mark, copied through escrow.",
        }
    ]

    contribution_preview = _assert_packet(
        _call_tool(
            "dossier_contribute",
            {
                "crew_id": crew["crew_id"],
                "note": "Escrowed chapel mark makes the ledger contradiction actionable.",
                "evidence_ids": [gilt_received_artifact_id],
                "confirm": False,
            },
        ),
        surface="mutation",
    )
    assert contribution_preview["agent_context"] == {
        "operation": "dossier_contribute",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "crew_id": crew["crew_id"],
            "note": "Escrowed chapel mark makes the ledger contradiction actionable.",
            "evidence_ids": [gilt_received_artifact_id],
        },
    }

    contribution_confirm = _assert_packet(
        _call_tool(
            "dossier_contribute",
            {
                "crew_id": crew["crew_id"],
                "note": "Escrowed chapel mark makes the ledger contradiction actionable.",
                "evidence_ids": [gilt_received_artifact_id],
                "confirm": True,
            },
        ),
        surface="mutation",
    )
    assert contribution_confirm["agent_context"]["operation"] == "dossier_contribute"
    assert contribution_confirm["agent_context"]["mutation"] is True
    assert contribution_confirm["agent_context"]["confirmed"] is True
    contributed_dossier = contribution_confirm["agent_context"]["result"]
    assert contributed_dossier["member_contributions"] == [
        {
            "player_id": ada["player_id"],
            "note": "Escrowed chapel mark makes the ledger contradiction actionable.",
            "evidence_ids": [gilt_received_artifact_id],
        }
    ]

    framing_preview = _assert_packet(
        _call_tool(
            "dossier_update_framing",
            {
                "crew_id": crew["crew_id"],
                "claim": "The finger is a staged relic backed by a corrected debt ledger.",
                "evidence_ids": [gilt_received_artifact_id],
                "reasoning": "The escrowed chapel mark confirms the public lot story moved after the debt was recorded.",
                "weaknesses": "Material testing remains incomplete.",
                "provenance_concerns": "Escrow copy needs independent handling notes.",
                "confirm": False,
            },
        ),
        surface="mutation",
    )
    assert framing_preview["agent_context"] == {
        "operation": "dossier_update_framing",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "crew_id": crew["crew_id"],
            "claim": "The finger is a staged relic backed by a corrected debt ledger.",
            "evidence_ids": [gilt_received_artifact_id],
            "reasoning": "The escrowed chapel mark confirms the public lot story moved after the debt was recorded.",
            "weaknesses": "Material testing remains incomplete.",
            "provenance_concerns": "Escrow copy needs independent handling notes.",
        },
    }

    framing_confirm = _assert_packet(
        _call_tool(
            "dossier_update_framing",
            {
                "crew_id": crew["crew_id"],
                "claim": "The finger is a staged relic backed by a corrected debt ledger.",
                "evidence_ids": [gilt_received_artifact_id],
                "reasoning": "The escrowed chapel mark confirms the public lot story moved after the debt was recorded.",
                "weaknesses": "Material testing remains incomplete.",
                "provenance_concerns": "Escrow copy needs independent handling notes.",
                "confirm": True,
            },
        ),
        surface="mutation",
    )
    assert framing_confirm["agent_context"]["operation"] == "dossier_update_framing"
    assert framing_confirm["agent_context"]["mutation"] is True
    assert framing_confirm["agent_context"]["confirmed"] is True
    framed_dossier = framing_confirm["agent_context"]["result"]
    assert framed_dossier["claim"] == (
        "The finger is a staged relic backed by a corrected debt ledger."
    )
    assert framed_dossier["evidence_ids"] == [gilt_received_artifact_id]
    assert framed_dossier["reasoning"] == (
        "The escrowed chapel mark confirms the public lot story moved after the "
        "debt was recorded."
    )
    assert framed_dossier["weaknesses"] == "Material testing remains incomplete."
    assert framed_dossier["provenance_concerns"] == (
        "Escrow copy needs independent handling notes."
    )

    dossier = _assert_packet(
        _call_tool("render_dossier", {"crew_id": crew["crew_id"]}),
        surface="dossier",
    )
    assert dossier["agent_context"]["mutation"] is False
    assert dossier["agent_context"]["artifact_citation_count"] == 1
    assert dossier["agent_context"]["contribution_count"] == 1
    assert dossier["agent_context"]["evidence_count"] == 1
    rendered_dossier = dossier["agent_context"]["dossier"]
    assert rendered_dossier == framed_dossier
    assert set(rendered_dossier["artifact_citations"][0]) == {
        "player_id",
        "artifact_id",
        "claim",
        "quote",
    }
    assert set(rendered_dossier["member_contributions"][0]) == {
        "player_id",
        "note",
        "evidence_ids",
    }
    assert "Proof Dossier:" in dossier["player_markdown"]
    assert "The finger is a staged relic" in dossier["player_markdown"]
    assert "Escrowed chapel mark makes" in dossier["player_markdown"]

    _write_config(
        config_path,
        player=grace,
        active_crew_id=crew["crew_id"],
        display_name="Grace Ledger",
    )
    grace_board = _assert_packet(
        _call_tool("render_crew_board", {"crew_id": crew["crew_id"]}),
        surface="crew_board",
    )
    packet_lead_decisions = [
        decision
        for decision in grace_board["agent_context"]["pending_decisions"]
        if decision["kind"] == "packet_lead_vote"
    ]
    assert packet_lead_decisions == [
        {
            "kind": "packet_lead_vote",
            "label": "Packet Lead vote available",
            "description": (
                "The crew has multiple members and player_0003 is not Packet Lead."
            ),
            "crew_id": crew["crew_id"],
            "candidate_player_id": grace["player_id"],
        }
    ]
    assert "Packet Lead vote available" in grace_board["player_markdown"]

    grace_vote_preview = _assert_packet(
        _call_tool(
            "vote_packet_lead",
            {
                "crew_id": crew["crew_id"],
                "player_id": grace["player_id"],
                "confirm": False,
            },
        ),
        surface="mutation",
    )
    assert grace_vote_preview["agent_context"] == {
        "operation": "vote_packet_lead",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "crew_id": crew["crew_id"],
            "player_id": grace["player_id"],
        },
    }

    grace_vote_confirm = _assert_packet(
        _call_tool(
            "vote_packet_lead",
            {
                "crew_id": crew["crew_id"],
                "player_id": grace["player_id"],
                "confirm": True,
            },
        ),
        surface="mutation",
    )
    assert grace_vote_confirm["agent_context"]["operation"] == "vote_packet_lead"
    assert grace_vote_confirm["agent_context"]["mutation"] is True
    assert grace_vote_confirm["agent_context"]["confirmed"] is True
    assert grace_vote_confirm["agent_context"]["result"]["packet_lead_player_id"] == (
        ada["player_id"]
    )
    assert "packet_lead_replacements" not in grace_vote_confirm["agent_context"]["result"]

    _write_config(
        config_path,
        player=ada,
        active_crew_id=crew["crew_id"],
        display_name="Ada Corelumen",
    )
    ada_vote_preview = _assert_packet(
        _call_tool(
            "vote_packet_lead",
            {
                "crew_id": crew["crew_id"],
                "player_id": grace["player_id"],
                "confirm": False,
            },
        ),
        surface="mutation",
    )
    assert ada_vote_preview["agent_context"] == {
        "operation": "vote_packet_lead",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "crew_id": crew["crew_id"],
            "player_id": grace["player_id"],
        },
    }

    ada_vote_confirm = _assert_packet(
        _call_tool(
            "vote_packet_lead",
            {
                "crew_id": crew["crew_id"],
                "player_id": grace["player_id"],
                "confirm": True,
            },
        ),
        surface="mutation",
    )
    assert ada_vote_confirm["agent_context"]["operation"] == "vote_packet_lead"
    assert ada_vote_confirm["agent_context"]["mutation"] is True
    assert ada_vote_confirm["agent_context"]["confirmed"] is True
    voted_dossier = ada_vote_confirm["agent_context"]["result"]
    assert voted_dossier["packet_lead_player_id"] == grace["player_id"]
    assert "packet_lead_votes" not in voted_dossier
    assert "packet_lead_replacements" not in voted_dossier

    post_vote_dossier = _assert_packet(
        _call_tool("render_dossier", {"crew_id": crew["crew_id"]}),
        surface="dossier",
    )
    assert post_vote_dossier["agent_context"]["dossier"] == {
        **voted_dossier,
        "packet_lead_votes": [
            {
                "sequence": 25,
                "voter_player_id": grace["player_id"],
                "candidate_player_id": grace["player_id"],
            },
            {
                "sequence": 26,
                "voter_player_id": ada["player_id"],
                "candidate_player_id": grace["player_id"],
            },
        ],
        "packet_lead_replacements": [
            {
                "sequence": 27,
                "previous_packet_lead_player_id": ada["player_id"],
                "packet_lead_player_id": grace["player_id"],
            }
        ],
    }
    assert "Packet Lead: player_0003" in post_vote_dossier["player_markdown"]
    assert "Packet Lead votes:" in post_vote_dossier["player_markdown"]
    assert "- 27 player_0001 -> player_0003" in post_vote_dossier["player_markdown"]

    async_update = client.post(
        "/chat/crew",
        json={
            "crew_id": crew["crew_id"],
            "body": "Grace saw the chapel ledger move while Ada was away.",
        },
        headers=_command_auth(grace["token"], "grace-async-crew-update"),
    )
    assert async_update.status_code == 201

    activity_delta = _assert_packet(
        _call_tool("render_activity_delta"),
        surface="activity_delta",
    )
    assert activity_delta["agent_context"]["mutation"] is False
    assert activity_delta["agent_context"]["synced_event_count"] == 1
    assert activity_delta["agent_context"]["activity_event_count"] == 1
    assert activity_delta["agent_context"]["event_type_counts"] == {
        "chat.message.created": 1
    }
    assert activity_delta["agent_context"]["recent_events"] == [
        {
            "sequence": 28,
            "type": "chat.message.created",
            "message": {
                "message_id": "msg_000002",
                "sender_player_id": grace["player_id"],
                "sender_crew_id": crew["crew_id"],
                "body": "Grace saw the chapel ledger move while Ada was away.",
                "artifact_ids": [],
            },
        }
    ]
    assert "What changed since sequence 27:" in activity_delta["player_markdown"]
    assert "Grace saw the chapel ledger move" in activity_delta["player_markdown"]

    another_async_update = client.post(
        "/chat/direct",
        json={
            "recipient_player_id": ada["player_id"],
            "body": "Moth Lanterns compare the copied rubric elsewhere.",
        },
        headers=_command_auth(bela["token"], "bela-async-crew-update"),
    )
    assert another_async_update.status_code == 201
    crew_async_update = client.post(
        "/chat/crew",
        json={
            "crew_id": crew["crew_id"],
            "body": "Grace files a second crew note for the packet room.",
        },
        headers=_command_auth(grace["token"], "grace-second-crew-update"),
    )
    assert crew_async_update.status_code == 201

    crew_activity_delta = _assert_packet(
        _call_tool("render_crew_activity_delta", {"crew_id": crew["crew_id"]}),
        surface="activity_delta",
    )
    assert crew_activity_delta["agent_context"]["mutation"] is False
    assert crew_activity_delta["agent_context"]["crew_id"] == crew["crew_id"]
    assert crew_activity_delta["agent_context"]["synced_event_count"] == 2
    assert crew_activity_delta["agent_context"]["activity_event_count"] == 1
    assert crew_activity_delta["agent_context"]["skipped_visible_event_count"] == 1
    assert crew_activity_delta["agent_context"]["event_type_counts"] == {
        "chat.message.created": 1
    }
    assert crew_activity_delta["agent_context"]["recent_events"] == [
        {
            "sequence": 30,
            "type": "chat.message.created",
            "message": {
                "message_id": "msg_000004",
                "sender_player_id": grace["player_id"],
                "sender_crew_id": crew["crew_id"],
                "body": "Grace files a second crew note for the packet room.",
                "artifact_ids": [],
            },
        }
    ]
    assert "Crew changes since sequence 28: crew_0001" in (
        crew_activity_delta["player_markdown"]
    )
    assert "Moth Lanterns compare" not in crew_activity_delta["player_markdown"]
    assert "Grace files a second crew note" in crew_activity_delta["player_markdown"]

    crew_activity = _assert_packet(
        _call_tool("render_crew_activity", {"crew_id": crew["crew_id"]}),
        surface="crew_activity",
    )
    assert crew_activity["agent_context"]["crew_id"] == crew["crew_id"]
    assert crew_activity["agent_context"]["crew_event_count"] > 0
    assert "Crew activity: crew_0001" in crew_activity["player_markdown"]
    assert "Grace saw the chapel ledger move" in crew_activity["player_markdown"]

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

    second_action_preview = _assert_packet(
        _call_tool(
            "submit_action",
            {
                "crew_id": crew["crew_id"],
                "intent": "Pressure the auction clerk loudly about the debt mark.",
                "confirm": False,
            },
        ),
        surface="mutation",
    )
    assert second_action_preview["agent_context"] == {
        "operation": "submit_action",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "crew_id": crew["crew_id"],
            "intent": "Pressure the auction clerk loudly about the debt mark.",
        },
    }

    second_action_confirm = _assert_packet(
        _call_tool(
            "submit_action",
            {
                "crew_id": crew["crew_id"],
                "intent": "Pressure the auction clerk loudly about the debt mark.",
                "confirm": True,
            },
        ),
        surface="mutation",
    )
    assert second_action_confirm["agent_context"] == {
        "operation": "submit_action",
        "mutation": True,
        "confirmed": True,
        "result": {
            "action_id": "action_000002",
            "crew_id": crew["crew_id"],
            "intent": "Pressure the auction clerk loudly about the debt mark.",
            "status": "submitted",
        },
    }

    pre_revision_board = _assert_packet(
        _call_tool("render_crew_board", {"crew_id": crew["crew_id"]}),
        surface="crew_board",
    )
    action_decisions = [
        decision
        for decision in pre_revision_board["agent_context"]["pending_decisions"]
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
            "action_ids": ["action_000001", "action_000002"],
        }
    ]
    assert "Submitted action open for edits" in pre_revision_board["player_markdown"]

    edit_action_preview = _assert_packet(
        _call_tool(
            "edit_action",
            {
                "action_id": "action_000001",
                "intent": (
                    "Compare the red ledger's provenance date against the chapel "
                    "timestamp."
                ),
                "confirm": False,
            },
        ),
        surface="mutation",
    )
    assert edit_action_preview["agent_context"] == {
        "operation": "edit_action",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "action_id": "action_000001",
            "intent": (
                "Compare the red ledger's provenance date against the chapel "
                "timestamp."
            ),
        },
    }

    edit_action_confirm = _assert_packet(
        _call_tool(
            "edit_action",
            {
                "action_id": "action_000001",
                "intent": (
                    "Compare the red ledger's provenance date against the chapel "
                    "timestamp."
                ),
                "confirm": True,
            },
        ),
        surface="mutation",
    )
    assert edit_action_confirm["agent_context"] == {
        "operation": "edit_action",
        "mutation": True,
        "confirmed": True,
        "result": {
            "action_id": "action_000001",
            "crew_id": crew["crew_id"],
            "intent": (
                "Compare the red ledger's provenance date against the chapel "
                "timestamp."
            ),
            "status": "submitted",
        },
    }

    cancel_action_preview = _assert_packet(
        _call_tool("cancel_action", {"action_id": "action_000002", "confirm": False}),
        surface="mutation",
    )
    assert cancel_action_preview["agent_context"] == {
        "operation": "cancel_action",
        "mutation": False,
        "confirmed": False,
        "preview": {"action_id": "action_000002"},
    }

    cancel_action_confirm = _assert_packet(
        _call_tool("cancel_action", {"action_id": "action_000002", "confirm": True}),
        surface="mutation",
    )
    assert cancel_action_confirm["agent_context"] == {
        "operation": "cancel_action",
        "mutation": True,
        "confirmed": True,
        "result": {
            "action_id": "action_000002",
            "crew_id": crew["crew_id"],
            "intent": "Pressure the auction clerk loudly about the debt mark.",
            "status": "canceled",
        },
    }

    crew_board = _assert_packet(
        _call_tool("render_crew_board", {"crew_id": crew["crew_id"]}),
        surface="crew_board",
    )
    post_revision_decisions = [
        decision
        for decision in crew_board["agent_context"]["pending_decisions"]
        if decision["kind"] == "contract_action"
    ]
    assert post_revision_decisions == [
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
    assert "action_000002" not in str(post_revision_decisions)

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
            "standing": "Strong lead",
            "score": 94,
            "score_reasoning": {
                "strengths": [
                    "clean provenance contradiction",
                    "cited artifact source material",
                ],
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
    assert f"- {crew['crew_id']}: Strong lead (94)" in contract_board["player_markdown"]

    activity = _assert_packet(_call_tool("render_activity"), surface="activity")
    assert activity["agent_context"]["event_type_counts"]["artifact.inspected"] == 1
    assert activity["agent_context"]["event_type_counts"]["action.submitted"] == 2
    assert activity["agent_context"]["event_type_counts"]["action.edited"] == 1
    assert activity["agent_context"]["event_type_counts"]["action.canceled"] == 1
    assert activity["agent_context"]["event_type_counts"]["contract.phase.resolved"] == 1
    assert "phase result:" in activity["player_markdown"]

    serialized_packets = "\n".join(
        str(packet)
        for packet in (
            landing,
            artifacts,
            artifact_detail,
            artifact_inspect_preview,
            artifact_inspect_confirm,
            message_preview,
            message_confirm,
            conversations,
            thread,
            deal_preview,
            deal_confirm,
            ada_deals,
            moth_inbox,
            deal_accept_preview,
            deal_accept_confirm,
            citation_preview,
            citation_confirm,
            contribution_preview,
            contribution_confirm,
            framing_preview,
            framing_confirm,
            dossier,
            grace_board,
            grace_vote_preview,
            grace_vote_confirm,
            ada_vote_preview,
            ada_vote_confirm,
            post_vote_dossier,
            activity_delta,
            crew_activity_delta,
            crew_activity,
            second_action_preview,
            second_action_confirm,
            pre_revision_board,
            edit_action_preview,
            edit_action_confirm,
            cancel_action_preview,
            cancel_action_confirm,
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
        "server_notes",
        "private_reason",
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
