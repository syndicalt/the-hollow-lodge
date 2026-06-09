import importlib.util
from pathlib import Path


def _load_run_mock():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "mock_full_game_loop.py"
    spec = importlib.util.spec_from_file_location("mock_full_game_loop", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_mock


def test_full_game_loop_with_escrow_trade(tmp_path):
    run_mock = _load_run_mock()
    result = run_mock(str(tmp_path))

    assert result["deal"]["status"] == "fulfilled"
    assert result["deal"]["proposer_received_artifact_ids"]
    assert result["deal"]["recipient_received_artifact_ids"]
    assert {deal["status"] for deal in result["gilt_board"]["deals"]} == {"fulfilled"}
    assert {deal["status"] for deal in result["moth_board"]["deals"]} == {"fulfilled"}
    assert result["gilt_board"]["dossier"]["artifact_citations"]
    assert result["moth_board"]["dossier"]["artifact_citations"]
    assert result["gilt_board"]["dossier"]["typed_claims"]
    assert result["moth_board"]["dossier"]["typed_claims"]
    assert result["reveal"]["standings"]
    assert result["codex_packets"][0] == "what_now"
    assert result["codex_packets"][1:3] == ["contract_board", "artifact_graph"]
    assert result["codex_packets"] == [
        "what_now",
        "contract_board",
        "artifact_graph",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "conversations",
        "thread",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "deals",
        "deal_preview",
        "inbox",
        "deal_preview",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "mutation",
        "crew_board",
        "dossier",
        "mutation",
        "mutation",
        "activity_delta",
        "what_now",
        "contract_board",
        "crew_activity",
        "activity",
    ]
    assert result["codex_mutations"] == [
        {"operation": "inspect_artifact", "confirmed": False},
        {"operation": "inspect_artifact", "confirmed": True},
        {"operation": "send_message", "confirmed": False},
        {"operation": "send_message", "confirmed": True},
        {"operation": "send_message", "confirmed": False},
        {"operation": "send_message", "confirmed": True},
        {"operation": "submit_action", "confirmed": False},
        {"operation": "submit_action", "confirmed": True},
        {"operation": "propose_deal", "confirmed": False},
        {"operation": "propose_deal", "confirmed": True},
        {"operation": "accept_deal", "confirmed": True},
        {"operation": "dossier_cite_artifact", "confirmed": False},
        {"operation": "dossier_cite_artifact", "confirmed": True},
        {"operation": "dossier_cite_artifact", "confirmed": False},
        {"operation": "dossier_cite_artifact", "confirmed": True},
        {"operation": "dossier_add_typed_claim", "confirmed": False},
        {"operation": "dossier_add_typed_claim", "confirmed": True},
        {"operation": "dossier_add_typed_claim", "confirmed": False},
        {"operation": "dossier_add_typed_claim", "confirmed": True},
        {"operation": "dossier_contribute", "confirmed": False},
        {"operation": "dossier_contribute", "confirmed": True},
        {"operation": "dossier_update_framing", "confirmed": False},
        {"operation": "dossier_update_framing", "confirmed": True},
        {"operation": "dossier_update_framing", "confirmed": False},
        {"operation": "dossier_update_framing", "confirmed": True},
        {"operation": "vote_packet_lead", "confirmed": False},
        {"operation": "vote_packet_lead", "confirmed": True},
        {"operation": "vote_packet_lead", "confirmed": False},
        {"operation": "vote_packet_lead", "confirmed": True},
        {"operation": "submit_action", "confirmed": False},
        {"operation": "submit_action", "confirmed": True},
        {"operation": "submit_action", "confirmed": False},
        {"operation": "submit_action", "confirmed": True},
        {"operation": "phase_lock", "confirmed": False},
        {"operation": "phase_lock", "confirmed": True},
    ]
    assert result["initial_what_now"]["surface"] == "what_now"
    assert result["initial_what_now"]["agent_context"]["mutation"] is False
    assert (
        result["initial_what_now"]["agent_context"]["player"]["player_id"]
        == "player_0001"
    )
    assert (
        result["initial_what_now"]["agent_context"]["player"]["display_name"]
        == "Ada Corelumen"
    )
    assert (
        result["initial_what_now"]["agent_context"]["player"]["active_crew_id"]
        == result["gilt_crew_id"]
    )
    assert (
        result["initial_what_now"]["agent_context"]["summary_counts"]["active_contracts"]
        == 1
    )
    assert "What Now: Ada Corelumen" in result["initial_what_now"]["player_markdown"]
    assert "- active contracts: 1" in result["initial_what_now"]["player_markdown"]
    serialized_initial = str(result["initial_what_now"])
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
    ):
        assert forbidden not in serialized_initial
    assert "Acceptance preview:" in "\n".join(result["lines"])
    assert "codex mutation previews/confirms:" in "\n".join(result["lines"])
    assert "The Saint's False Finger" in "\n".join(result["lines"])
    assert "Visible artifacts:" in "\n".join(result["lines"])
    assert "Visible conversations:" in "\n".join(result["lines"])
    assert "Conversation thread:" in "\n".join(result["lines"])
    assert "chapel unlock action: action_" in "\n".join(result["lines"])
    assert "Phase result:" in "\n".join(result["lines"])
    assert "What changed since sequence" in "\n".join(result["lines"])
    assert "What Now: Ada Corelumen" in "\n".join(result["lines"])
    assert result["final_dossier"]["agent_context"]["dossier"]["packet_lead_votes"]
    assert result["final_dossier"]["agent_context"]["dossier"]["packet_lead_replacements"]
    contributions = result["final_dossier"]["agent_context"]["dossier"]["member_contributions"]
    assert contributions == [
        {
            "player_id": result["grace_player_id"],
            "note": "Chapel debt mark matches the auction clerk's corrected lot note.",
            "evidence_ids": [result["gilt_received_artifact_id"]],
        }
    ]
    assert result["final_dossier"]["agent_context"]["contribution_count"] == 1
    assert (
        f"- {result['grace_player_id']}: Chapel debt mark matches"
        in result["final_dossier"]["player_markdown"]
    )
    assert all(
        set(contribution) == {"player_id", "note", "evidence_ids"}
        for contribution in contributions
    )
    assert "visibility" not in str(result["final_dossier"])
    assert "server_only" not in str(result["final_dossier"])
    assert "hidden_truth" not in str(result["final_dossier"])
    assert "accepted_output" not in str(result["final_dossier"])
    assert result["conversations"]["surface"] == "conversations"
    assert result["conversations"]["agent_context"]["conversation_count"] == 1
    conversation = result["conversations"]["agent_context"]["conversations"][0]
    assert conversation["message_count"] == 2
    thread = result["thread"]
    assert thread["surface"] == "thread"
    assert thread["agent_context"]["message_count"] == 2
    assert thread["agent_context"]["conversation_id"] == conversation["conversation_id"]
    assert len(thread["agent_context"]["messages"]) == 2
    assert [
        message["sequence"] for message in thread["agent_context"]["messages"]
    ] == sorted(message["sequence"] for message in thread["agent_context"]["messages"])
    assert {
        message["body"] for message in thread["agent_context"]["messages"]
    } == {
        "We can trade ledger leverage for chapel access before lock.",
        "Send the ledger copy first; no public source claims until lock.",
    }
    assert f"Conversation: {thread['agent_context']['conversation_id']}" in thread["player_markdown"]
    assert "visibility" not in str(thread)
    assert "server_only" not in str(thread)
    assert "hidden" not in str(thread)
    moth_inbox = result["moth_inbox_before_deal_acceptance"]
    assert moth_inbox["surface"] == "inbox"
    assert "Inbox: Bela Moth" in moth_inbox["player_markdown"]
    assert (
        "- Incoming deal needs response: Deal deal_000001 from crew_0001 needs a response."
        in moth_inbox["player_markdown"]
    )
    assert "Incoming deals:" in moth_inbox["player_markdown"]
    assert (
        "- deal_000001 proposed: crew_0001 offers artifact_ledger_rubric for artifact_chapel_debt_mark"
        in moth_inbox["player_markdown"]
    )
    assert "Soft term: Do not cite our crew as source until Auction Lock." in (
        moth_inbox["player_markdown"]
    )
    incoming_deal_decisions = [
        decision
        for decision in moth_inbox["agent_context"]["pending_decisions"]
        if decision["kind"] == "incoming_deal"
    ]
    assert incoming_deal_decisions == [
        {
            "kind": "incoming_deal",
            "label": "Incoming deal needs response",
            "description": "Deal deal_000001 from crew_0001 needs a response.",
            "crew_id": result["moth_crew_id"],
            "contract_id": "contract_false_finger",
            "deal_id": "deal_000001",
        }
    ]
    forbidden_pending_decision_fields = {
        "offered_artifact_ids",
        "requested_artifact_ids",
        "soft_terms",
        "expires_phase",
        "proposer_received_artifact_ids",
        "recipient_received_artifact_ids",
        "proposer_player_id",
        "accepted_by_player_id",
        "idempotency_key",
        "payload",
        "event_id",
        "event_hash",
        "origin",
    }
    assert not (
        set(incoming_deal_decisions[0]) & forbidden_pending_decision_fields
    )
    assert moth_inbox["agent_context"]["urgent_items"][0] == incoming_deal_decisions[0]
    assert moth_inbox["agent_context"]["deals"] == [
        {
            "deal_id": "deal_000001",
            "contract_id": "contract_false_finger",
            "proposer_crew_id": result["gilt_crew_id"],
            "recipient_crew_id": result["moth_crew_id"],
            "status": "proposed",
            "offered_artifact_ids": ["artifact_ledger_rubric"],
            "requested_artifact_ids": ["artifact_chapel_debt_mark"],
            "soft_terms": ["Do not cite our crew as source until Auction Lock."],
            "expires_phase": "Auction Preview",
            "proposer_received_artifact_ids": [],
            "recipient_received_artifact_ids": [],
        }
    ]
    serialized_moth_inbox = str(moth_inbox)
    for forbidden in (
        "hidden_truth",
        "hidden_truth_summary",
        "server_only",
        "server_notes",
        "visibility",
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
        assert forbidden not in serialized_moth_inbox
    assert result["final_what_now"]["surface"] == "what_now"
    assert result["final_contract"]["surface"] == "contract_board"
    final_contracts = result["final_contract"]["agent_context"]["contracts"]
    false_finger = next(
        contract
        for contract in final_contracts
        if contract["contract_id"] == "contract_false_finger"
    )
    expected_standings = [
        {
            "crew_id": standing["crew_id"],
            "standing": standing["standing"],
            "score": standing["score"],
            "score_reasoning": {
                "strengths": standing["strengths"],
                "weaknesses": standing["weaknesses"],
                "penalties": standing["penalties"],
                "revealed_clues": standing["revealed_clues"],
            },
        }
        for standing in result["reveal"]["standings"]
    ]
    assert false_finger["phase"]["status"] == "resolved"
    assert false_finger["phase_result"] == {
        "standings": expected_standings,
        "contract_state": result["reveal"]["contract_state"],
    }
    assert "Phase result:" in result["final_contract"]["player_markdown"]
    serialized_contract = str(result["final_contract"])
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
    ):
        assert forbidden not in serialized_contract
    final_delta = result["final_activity_delta"]
    assert final_delta["surface"] == "activity_delta"
    assert final_delta["agent_context"]["mutation"] is False
    assert final_delta["agent_context"]["checkpoint_sequence"] == 36
    assert final_delta["agent_context"]["max_sequence"] == 44
    assert final_delta["agent_context"]["synced_event_count"] == 6
    assert final_delta["agent_context"]["activity_event_count"] == 6
    assert final_delta["agent_context"]["event_type_counts"] == {
        "contract.phase.locked": 1,
        "contract.phase.resolved": 1,
        "artifact.phase_reward.awarded": 1,
        "artifact.access.granted": 1,
        "crew.legacy.delta.recorded": 2,
    }
    assert [
        event["sequence"]
        for event in final_delta["agent_context"]["recent_events"]
    ] == [37, 40, 41, 42, 43, 44]
    assert [
        event["type"]
        for event in final_delta["agent_context"]["recent_events"]
    ] == [
        "contract.phase.locked",
        "contract.phase.resolved",
        "artifact.phase_reward.awarded",
        "artifact.access.granted",
        "crew.legacy.delta.recorded",
        "crew.legacy.delta.recorded",
    ]
    phase_event = final_delta["agent_context"]["recent_events"][1]
    assert phase_event["phase_result"]["standings"] == expected_standings
    assert phase_event["phase_result"]["contract_state"] == result["reveal"]["contract_state"]
    assert final_delta["agent_context"]["recent_events"][4]["legacy_delta"]["crew_id"] == (
        result["moth_crew_id"]
    )
    assert final_delta["agent_context"]["recent_events"][5]["legacy_delta"]["crew_id"] == (
        result["gilt_crew_id"]
    )
    assert "What changed since sequence 36:" in final_delta["player_markdown"]
    assert "- 37 contract.phase.locked" in final_delta["player_markdown"]
    assert "- 40 phase result: crew_0002 Strong lead 74" in final_delta["player_markdown"]
    assert "- 43 legacy crew_0002: Strong lead" in final_delta["player_markdown"]
    assert "- 44 legacy crew_0001: Weak" in final_delta["player_markdown"]
    serialized_delta = str(final_delta)
    for forbidden in (
        "hidden_truth",
        "hidden_truth_summary",
        "contract.hidden_truth.seeded",
        "server_only",
        "server_only_note",
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
        "event_id",
        "event_hash",
        "origin",
        "payload",
        "idempotency_key",
    ):
        assert forbidden not in serialized_delta
    assert (
        result["final_what_now"]["agent_context"]["summary_counts"]["active_contracts"]
        == 1
    )
    assert result["final_what_now"]["agent_context"]["mutation"] is False
    assert result["final_crew_activity"]["surface"] == "crew_activity"
    assert result["final_crew_activity"]["agent_context"]["crew_id"] == "crew_0001"
    assert result["final_crew_activity"]["agent_context"]["crew_event_count"] > 0
    assert result["final_activity"]["agent_context"]["visible_event_count"] > 0
    assert result["timeline"] == [
        "deal.proposed",
        "deal.accepted",
        "artifact.deal_copied",
        "artifact.deal_copied.internal",
        "artifact.deal_copied",
        "artifact.deal_copied.internal",
        "deal.fulfilled",
    ]
    chapel_awards = result["action_award_timeline"]
    assert chapel_awards
    assert "grant-chapel-to-moth" not in {
        award["idempotency_key"] for award in chapel_awards
    }
    assert all(award["type"] == "artifact.access.granted" for award in chapel_awards)
    assert all(
        award["idempotency_key"].startswith("artifact.award.action_")
        for award in chapel_awards
    )
    assert all(
        award["payload"]["artifact_id"] == "artifact_chapel_debt_mark"
        for award in chapel_awards
    )
    assert any(
        result["moth_crew_id"] in award["payload"]["crew_ids"]
        for award in chapel_awards
    )
