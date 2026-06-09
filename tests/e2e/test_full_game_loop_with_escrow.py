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
    assert result["reveal"]["standings"]
    assert result["codex_packets"] == [
        "contract_board",
        "artifact_graph",
        "deals",
        "deal_preview",
        "inbox",
        "crew_board",
        "dossier",
        "what_now",
        "contract_board",
        "crew_activity",
        "activity",
    ]
    assert "Acceptance preview:" in "\n".join(result["lines"])
    assert "The Saint's False Finger" in "\n".join(result["lines"])
    assert "Visible artifacts:" in "\n".join(result["lines"])
    assert "Phase result:" in "\n".join(result["lines"])
    assert "What Now: Ada Corelumen" in "\n".join(result["lines"])
    assert result["final_what_now"]["surface"] == "what_now"
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
