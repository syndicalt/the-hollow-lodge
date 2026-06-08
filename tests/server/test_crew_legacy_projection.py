from copy import deepcopy

from hollow_lodge.server.projections import (
    apply_crew_modifiers_to_contracts,
    crew_legacy_from_contracts,
)


def test_crew_legacy_is_empty_before_resolved_contracts():
    contracts = [
        {
            "contract_id": "contract_ash_window",
            "title": "The Ash Window",
            "phase": {"name": "Cinder Preview", "remaining_hours": 4},
        }
    ]

    legacy = crew_legacy_from_contracts(crew_id="crew_0001", contracts=contracts)

    assert legacy == {
        "crew_id": "crew_0001",
        "reputation": 0,
        "heat": 0,
        "favors": 0,
        "debts": 0,
        "scars": [],
        "completed_contracts": [],
        "future_opportunities": [],
    }


def test_strong_lead_creates_reputation_heat_and_future_modifiers():
    contracts = [
        {
            "contract_id": "contract_false_finger",
            "title": "The Saint's False Finger",
            "phase": {"name": "Auction Preview", "status": "resolved"},
            "phase_result": {
                "standings": [
                    {
                        "crew_id": "crew_0001",
                        "standing": "Strong lead",
                        "score": 70,
                        "hidden_tiebreaker": 9,
                    },
                    {
                        "crew_id": "crew_0002",
                        "standing": "Weak",
                        "score": 12,
                    },
                ],
                "hidden_truth": "do not project",
            },
        },
        {
            "contract_id": "contract_ash_window",
            "title": "The Ash Window",
            "phase": {"name": "Cinder Preview", "remaining_hours": 4},
        },
    ]

    legacy = crew_legacy_from_contracts(crew_id="crew_0001", contracts=contracts)
    shaped_contracts = deepcopy(contracts)
    apply_crew_modifiers_to_contracts(
        contracts=shaped_contracts,
        opportunities=legacy["future_opportunities"],
    )

    assert legacy["completed_contracts"] == [
        {
            "contract_id": "contract_false_finger",
            "title": "The Saint's False Finger",
            "phase": "Auction Preview",
            "standing": "Strong lead",
            "score": 70,
            "outcome": "strong_lead",
        }
    ]
    assert legacy["reputation"] == 2
    assert legacy["heat"] == 1
    assert legacy["favors"] == 1
    assert "hidden_truth" not in str(legacy)
    assert shaped_contracts[1]["crew_modifiers"] == legacy["future_opportunities"][0]["modifiers"]
