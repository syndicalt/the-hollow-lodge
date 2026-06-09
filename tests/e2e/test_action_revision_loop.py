import importlib.util
from pathlib import Path


def _load_run_mock():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "mock_action_revision_loop.py"
    )
    spec = importlib.util.spec_from_file_location("mock_action_revision_loop", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_mock


def _contract_action_decision(packet: dict):
    decisions = [
        decision
        for decision in packet["agent_context"]["pending_decisions"]
        if decision["kind"] == "contract_action"
    ]
    assert len(decisions) == 1
    return decisions[0]


def test_action_revision_loop_scores_only_current_submitted_action(tmp_path):
    run_mock = _load_run_mock()
    result = run_mock(str(tmp_path))

    assert result["first_action"]["agent_context"]["result"] == {
        "action_id": "action_000001",
        "crew_id": result["crew_id"],
        "intent": (
            "Inspect the ledger entry under candlelight without drawing a source "
            "conclusion."
        ),
        "status": "submitted",
    }
    assert result["second_action"]["agent_context"]["result"] == {
        "action_id": "action_000002",
        "crew_id": result["crew_id"],
        "intent": "Pressure the auction clerk loudly about the debt mark.",
        "status": "submitted",
    }

    pre_revision_decision = _contract_action_decision(result["pre_revision_board"])
    assert pre_revision_decision["action_ids"] == ["action_000001", "action_000002"]
    assert "Submitted action open for edits" in (
        result["pre_revision_board"]["player_markdown"]
    )

    assert result["edited_preview"]["agent_context"] == {
        "operation": "edit_action",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "action_id": "action_000001",
            "intent": (
                "Inspect the ledger for forged provenance before the chapel timestamp."
            ),
        },
    }
    assert "No server mutation was submitted." in result["edited_preview"]["player_markdown"]
    assert result["edited"]["agent_context"] == {
        "operation": "edit_action",
        "mutation": True,
        "confirmed": True,
        "result": {
            "action_id": "action_000001",
            "crew_id": result["crew_id"],
            "intent": (
                "Inspect the ledger for forged provenance before the chapel timestamp."
            ),
            "status": "submitted",
        },
    }

    assert result["canceled_preview"]["agent_context"] == {
        "operation": "cancel_action",
        "mutation": False,
        "confirmed": False,
        "preview": {"action_id": "action_000002"},
    }
    assert result["canceled"]["agent_context"] == {
        "operation": "cancel_action",
        "mutation": True,
        "confirmed": True,
        "result": {
            "action_id": "action_000002",
            "crew_id": result["crew_id"],
            "intent": "Pressure the auction clerk loudly about the debt mark.",
            "status": "canceled",
        },
    }

    revision_delta = result["revision_delta"]
    assert revision_delta["surface"] == "activity_delta"
    assert revision_delta["agent_context"]["mutation"] is False
    assert revision_delta["agent_context"]["event_type_counts"] == {
        "action.edited": 1,
        "action.canceled": 1,
    }
    assert "action.edited" in revision_delta["player_markdown"]
    assert "action.canceled" in revision_delta["player_markdown"]

    post_revision_decision = _contract_action_decision(result["post_revision_board"])
    assert post_revision_decision["action_ids"] == ["action_000001"]
    assert "action_000002" not in str(post_revision_decision)

    contract = result["contract_board"]["agent_context"]["contracts"][0]
    assert contract["phase"]["status"] == "resolved"
    assert contract["phase_result"]["standings"] == [
        {
            "crew_id": result["crew_id"],
            "standing": "Viable",
            "score": 64,
            "score_reasoning": {
                "strengths": ["clean provenance contradiction"],
                "weaknesses": ["no material confirmation"],
                "penalties": [],
                "revealed_clues": ["Auction house provenance is now suspect."],
            },
        }
    ]
    assert f"- {result['crew_id']}: Viable (64)" in (
        result["contract_board"]["player_markdown"]
    )
    assert "minor heat trace" not in str(result["contract_board"])
    assert "Pressure the auction clerk loudly" not in str(result["contract_board"])

    activity = result["activity"]
    assert activity["agent_context"]["event_type_counts"]["action.submitted"] == 2
    assert activity["agent_context"]["event_type_counts"]["action.edited"] == 1
    assert activity["agent_context"]["event_type_counts"]["action.canceled"] == 1
    assert activity["agent_context"]["event_type_counts"]["contract.phase.resolved"] == 1
    assert f"phase result: {result['crew_id']} Viable 64" in activity["player_markdown"]

    for packet_name in (
        "edited_preview",
        "edited",
        "canceled_preview",
        "canceled",
        "revision_delta",
        "post_revision_board",
        "contract_board",
        "activity",
    ):
        serialized = str(result[packet_name])
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
            assert forbidden not in serialized
