from __future__ import annotations

import json
from pathlib import Path

import pytest

from hollow_lodge.server.contract_seed import ContractSeed, load_contract_seed_file


FIXTURE = Path("tests/fixtures/ash_window_contract.json")


def test_contract_seed_file_loads_typed_contract_and_artifact_graph():
    seed = load_contract_seed_file(FIXTURE)

    assert seed.contract.contract_id == "contract_ash_window"
    assert seed.contract.phase.name == "Cinder Preview"
    assert seed.hidden_truth.summary.startswith("The window is a cinder oracle")
    assert seed.public_artifact_ids == ("artifact_ash_notice",)
    assert seed.artifact_graph.artifact_by_id("artifact_ash_notice").title == "Ash Lot Notice"
    assert seed.scoring_hints["rubric_hooks"] == [
        "fire chronology",
        "material residue",
        "witness leverage",
    ]
    assert seed.phase_rewards == ()
    assert seed.unlock_requirements == ()


def test_contract_seed_accepts_data_defined_unlock_requirements():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["unlock_requirements"] = [
        {
            "scope": "crew",
            "metric": "reputation",
            "minimum": 2,
            "label": "Reputation 2+",
            "description": "Complete earlier Lodge work with a strong lead.",
        }
    ]

    seed = ContractSeed.model_validate(raw)

    assert seed.unlock_requirements[0].metric == "reputation"
    assert seed.unlock_requirements[0].minimum == 2


def test_contract_seed_rejects_unsupported_unlock_metric():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["unlock_requirements"] = [
        {
            "scope": "crew",
            "metric": "hidden_truth",
            "minimum": 1,
            "label": "Hidden truth",
            "description": "Do not expose server-only truth.",
        }
    ]

    with pytest.raises(ValueError):
        ContractSeed.model_validate(raw)


def test_contract_seed_rejects_contract_campaign_mismatch(tmp_path):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["contract"]["campaign_id"] = "campaign_other"
    seed_path = tmp_path / "bad-contract.json"
    seed_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="contract campaign mismatch"):
        load_contract_seed_file(seed_path)


def test_contract_seed_rejects_public_artifact_outside_graph():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["public_artifact_ids"] = ["artifact_missing"]

    with pytest.raises(ValueError, match="unknown public artifact"):
        ContractSeed.model_validate(raw)


def test_contract_seed_rejects_phase_reward_outside_graph():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["phase_rewards"] = [
        {
            "phase": "Cinder Preview",
            "trigger": "phase_resolved",
            "award_to": "standing_leader",
            "artifact_id": "artifact_missing",
            "reason": "Leader follow-up from cinder preview resolution.",
        }
    ]

    with pytest.raises(ValueError, match="unknown phase reward artifact"):
        ContractSeed.model_validate(raw)


def test_contract_seed_rejects_artifact_graph_contract_mismatch():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["artifact_graph"]["contract_id"] = "contract_other"
    for artifact in raw["artifact_graph"]["artifacts"]:
        artifact["contract_id"] = "contract_other"
    for rule in raw["artifact_graph"]["unlock_rules"]:
        rule["contract_id"] = "contract_other"

    with pytest.raises(ValueError, match="artifact graph contract mismatch"):
        ContractSeed.model_validate(raw)
