import importlib.util
from pathlib import Path


def _load_run_smokes():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "smoke_shipped_contracts.py"
    )
    spec = importlib.util.spec_from_file_location("smoke_shipped_contracts", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_smokes


def test_all_shipped_contracts_have_playthrough_smokes(tmp_path):
    run_smokes = _load_run_smokes()

    result = run_smokes(str(tmp_path))

    assert {smoke["contract_id"] for smoke in result["smokes"]} == {
        "contract_false_finger",
        "contract_ash_window",
    }
    for smoke in result["smokes"]:
        assert smoke["resolved_standings"]
        assert smoke["contract_board_surface"] == "contract_board"
        assert smoke["artifact_surface"] == "artifact_graph"
        assert smoke["visible_artifact_count"] >= 1
        assert not smoke["hidden_leak_detected"]
    assert any(
        line.startswith("contract_false_finger: resolved")
        for line in result["lines"]
    )
    assert any(
        line.startswith("contract_ash_window: resolved")
        for line in result["lines"]
    )
