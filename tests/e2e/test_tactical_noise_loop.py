import importlib.util
from pathlib import Path


def _load_run_mock():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "mock_tactical_noise_loop.py"
    )
    spec = importlib.util.spec_from_file_location("mock_tactical_noise_loop", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_mock


def test_repeated_crew_actions_render_noise_penalty_after_resolution(tmp_path):
    run_mock = _load_run_mock()
    result = run_mock(str(tmp_path))

    first_action = result["first_action"]
    second_action = result["second_action"]
    assert first_action["surface"] == "mutation"
    assert first_action["agent_context"]["operation"] == "submit_action"
    assert first_action["agent_context"]["confirmed"] is True
    assert first_action["agent_context"]["result"] == {
        "action_id": "action_000001",
        "crew_id": result["crew_id"],
        "intent": (
            "Quietly inspect the ledger provenance date against the chapel timestamp."
        ),
        "status": "submitted",
    }
    assert "Result: action_000001" in first_action["player_markdown"]

    assert second_action["surface"] == "mutation"
    assert second_action["agent_context"]["operation"] == "submit_action"
    assert second_action["agent_context"]["confirmed"] is True
    assert second_action["agent_context"]["result"] == {
        "action_id": "action_000002",
        "crew_id": result["crew_id"],
        "intent": "Pressure the auction clerk about the forged provenance correction.",
        "status": "submitted",
    }
    assert "Result: action_000002" in second_action["player_markdown"]

    resolution = result["resolution"]
    assert resolution["surface"] == "mutation"
    assert resolution["agent_context"]["operation"] == "phase_lock"
    assert resolution["agent_context"]["confirmed"] is True
    assert resolution["agent_context"]["result"]["status"] == "resolved"

    contract_board = result["contract_board"]
    assert contract_board["surface"] == "contract_board"
    contract = next(
        contract
        for contract in contract_board["agent_context"]["contracts"]
        if contract["contract_id"] == "contract_false_finger"
    )
    assert contract["phase"]["status"] == "resolved"
    assert contract["phase_result"]["contract_state"] == [
        "Auction house provenance is now suspect.",
        "Rival alternate clue paths remain open.",
    ]
    assert contract["phase_result"]["standings"] == [
        {
            "crew_id": result["crew_id"],
            "standing": "Viable",
            "score": 60,
            "score_reasoning": {
                "strengths": ["clean provenance contradiction"],
                "weaknesses": ["no material confirmation"],
                "penalties": ["minor heat trace"],
                "revealed_clues": ["Auction house provenance is now suspect."],
            },
        }
    ]
    assert f"- {result['crew_id']}: Viable (60)" in contract_board["player_markdown"]
    assert "penalties: minor heat trace" in contract_board["player_markdown"]
    assert "clues: Auction house provenance is now suspect." in (
        contract_board["player_markdown"]
    )

    activity = result["activity"]
    assert activity["surface"] == "activity"
    assert activity["agent_context"]["event_type_counts"]["action.submitted"] == 2
    assert activity["agent_context"]["event_type_counts"]["contract.phase.resolved"] == 1
    assert (
        activity["agent_context"]["event_type_counts"]["crew.legacy.delta.recorded"]
        == 1
    )
    assert "action action_000001: Quietly inspect" in activity["player_markdown"]
    assert "action action_000002: Pressure the auction clerk" in (
        activity["player_markdown"]
    )
    assert f"phase result: {result['crew_id']} Viable 60" in (
        activity["player_markdown"]
    )

    for packet in (contract_board, activity):
        serialized = str(packet)
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
            assert forbidden not in serialized
