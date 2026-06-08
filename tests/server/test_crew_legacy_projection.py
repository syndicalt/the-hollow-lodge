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
        "deal_conduct": {
            "score": 0,
            "fulfilled_count": 0,
            "canceled_count": 0,
            "declined_count": 0,
            "open_count": 0,
            "reliability": "unproven",
        },
        "counterintelligence": {
            "investigations_started": 0,
            "containments_started": 0,
            "heat_from_containment": 0,
        },
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


def test_fulfilled_deals_create_reliable_broker_context_without_terms_or_artifact_ids():
    contracts = [
        {
            "contract_id": "contract_ash_window",
            "title": "The Ash Window",
            "phase": {"name": "Cinder Preview", "remaining_hours": 4},
        }
    ]
    deals = [
        {
            "deal_id": "deal_000001",
            "contract_id": "contract_false_finger",
            "proposer_crew_id": "crew_0001",
            "recipient_crew_id": "crew_0002",
            "status": "fulfilled",
            "offered_artifact_ids": ["artifact_secret_ledger"],
            "requested_artifact_ids": ["artifact_private_mark"],
            "soft_terms": ["Do not cite us."],
        },
        {
            "deal_id": "deal_000002",
            "contract_id": "contract_false_finger",
            "proposer_crew_id": "crew_0001",
            "recipient_crew_id": "crew_0002",
            "status": "canceled",
            "offered_artifact_ids": ["artifact_other"],
            "requested_artifact_ids": [],
        },
        {
            "deal_id": "deal_000003",
            "contract_id": "contract_false_finger",
            "proposer_crew_id": "crew_0002",
            "recipient_crew_id": "crew_0001",
            "status": "declined",
            "offered_artifact_ids": [],
            "requested_artifact_ids": [],
        },
        {
            "deal_id": "deal_000004",
            "contract_id": "contract_false_finger",
            "proposer_crew_id": "crew_0001",
            "recipient_crew_id": "crew_0002",
            "status": "proposed",
            "offered_artifact_ids": [],
            "requested_artifact_ids": [],
        },
    ]

    legacy = crew_legacy_from_contracts(
        crew_id="crew_0001",
        contracts=contracts,
        deals=deals,
    )
    shaped_contracts = deepcopy(contracts)
    apply_crew_modifiers_to_contracts(
        contracts=shaped_contracts,
        opportunities=legacy["future_opportunities"],
    )

    assert legacy["deal_conduct"] == {
        "score": 1,
        "fulfilled_count": 1,
        "canceled_count": 1,
        "declined_count": 1,
        "open_count": 1,
        "reliability": "reliable_escrow_partner",
    }
    assert shaped_contracts[0]["crew_modifiers"] == [
        {
            "kind": "deal_reliability",
            "label": "Deal reliability",
            "description": (
                "Recent escrowed trades make this crew easier to trust on side "
                "arrangements for The Ash Window."
            ),
            "value": 1,
        }
    ]
    assert "artifact_secret_ledger" not in str(legacy)
    assert "Do not cite us." not in str(legacy)
