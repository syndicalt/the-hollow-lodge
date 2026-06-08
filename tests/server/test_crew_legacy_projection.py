from copy import deepcopy

from hollow_lodge.domain.events import GameEvent, EventVisibility
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
        "rumor_memory": {
            "verified_count": 0,
            "assessment_counts": {},
            "recent": [],
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


def test_weak_outcome_creates_scar_burden_for_future_contracts():
    contracts = [
        {
            "contract_id": "contract_false_finger",
            "title": "The Saint's False Finger",
            "phase": {"name": "Auction Preview", "status": "resolved"},
            "phase_result": {
                "standings": [
                    {
                        "crew_id": "crew_0001",
                        "standing": "Weak",
                        "score": 12,
                        "hidden_tiebreaker": 9,
                    }
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

    assert legacy["debts"] == 1
    assert legacy["scars"] == ["Bruised by The Saint's False Finger"]
    assert legacy["future_opportunities"] == [
        {
            "contract_id": "contract_ash_window",
            "title": "The Ash Window",
            "modifiers": [
                {
                    "kind": "scar_burden",
                    "label": "Scar burden",
                    "description": (
                        "A prior scar makes The Ash Window more dangerous for this crew."
                    ),
                    "value": 1,
                }
            ],
        }
    ]
    assert shaped_contracts[1]["crew_modifiers"] == legacy["future_opportunities"][0]["modifiers"]
    assert "hidden_truth" not in str(legacy)


def test_explicit_legacy_delta_events_drive_legacy_without_double_counting():
    contracts = [
        {
            "contract_id": "contract_false_finger",
            "title": "The Saint's False Finger",
            "phase": {"name": "Auction Preview", "status": "resolved"},
        },
        {
            "contract_id": "contract_ash_window",
            "title": "The Ash Window",
            "phase": {"name": "Cinder Preview", "remaining_hours": 4},
        },
    ]
    events = [
        GameEvent.new(
            sequence=10,
            event_type="crew.legacy.delta.recorded",
            actor_id="server",
            visibility=EventVisibility.public(),
            payload={
                "schema_version": 1,
                "crew_id": "crew_0001",
                "contract_id": "contract_false_finger",
                "contract_title": "The Saint's False Finger",
                "phase": "Auction Preview",
                "standing": "Strong lead",
                "score": 70,
                "outcome": "strong_lead",
                "deltas": {
                    "reputation": 2,
                    "heat": 1,
                    "favors": 1,
                    "debts": 0,
                    "scars": [],
                },
                "summary": (
                    "Strong lead on The Saint's False Finger: reputation +2, "
                    "heat +1, favors +1."
                ),
                "hidden_truth": "server-only should not project",
            },
            previous_hash=None,
            idempotency_key="legacy-delta",
        )
    ]

    legacy = crew_legacy_from_contracts(
        crew_id="crew_0001",
        contracts=contracts,
        events=events,
    )

    assert legacy["reputation"] == 2
    assert legacy["heat"] == 1
    assert legacy["favors"] == 1
    assert legacy["debts"] == 0
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
    assert "server-only" not in str(legacy)


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


def test_verified_rumors_create_safe_long_term_crew_memory():
    contracts = [
        {
            "contract_id": "contract_ash_window",
            "title": "The Ash Window",
            "phase": {"name": "Cinder Preview", "remaining_hours": 4},
        }
    ]
    events = [
        GameEvent.new(
            sequence=10,
            event_type="contract.rumor.verified",
            actor_id="player_0001",
            visibility=EventVisibility.crews(["crew_0001"]),
            payload={
                "schema_version": 1,
                "rumor_id": "rumor_msg_000001",
                "action_id": "action_000001",
                "crew_id": "crew_0001",
                "source_type": "crew_chat",
                "source_id": "message_private_000001",
                "pressure": "artifact_reference_detected",
                "assessment": "credible_artifact_signal",
                "confidence": "medium",
                "summary": (
                    "The investigation found a credible artifact signal, but "
                    "not enough to expose the private source."
                ),
                "contract_id": "contract_false_finger",
                "suspected_crew_ids": ["crew_0002"],
                "artifact_ids": ["artifact_secret_ledger"],
                "private_body": "The ledger proves the forgery.",
            },
            previous_hash=None,
            idempotency_key="rumor-verified-1",
        ),
        GameEvent.new(
            sequence=11,
            event_type="contract.rumor.verified",
            actor_id="player_0002",
            visibility=EventVisibility.crews(["crew_0002"]),
            payload={
                "schema_version": 1,
                "rumor_id": "rumor_msg_000002",
                "action_id": "action_000002",
                "crew_id": "crew_0002",
                "source_type": "deal",
                "source_id": "deal_private_000001",
                "pressure": "escrow_terms_detected",
                "assessment": "credible_arrangement_signal",
                "confidence": "medium",
                "summary": "A different crew found a private arrangement signal.",
                "contract_id": "contract_false_finger",
            },
            previous_hash=None,
            idempotency_key="rumor-verified-2",
        ),
    ]

    legacy = crew_legacy_from_contracts(
        crew_id="crew_0001",
        contracts=contracts,
        events=events,
    )

    assert legacy["rumor_memory"] == {
        "verified_count": 1,
        "assessment_counts": {"credible_artifact_signal": 1},
        "recent": [
            {
                "rumor_id": "rumor_msg_000001",
                "contract_id": "contract_false_finger",
                "pressure": "artifact_reference_detected",
                "assessment": "credible_artifact_signal",
                "confidence": "medium",
                "summary": (
                    "The investigation found a credible artifact signal, but "
                    "not enough to expose the private source."
                ),
            }
        ],
    }
    assert "message_private_000001" not in str(legacy)
    assert "artifact_secret_ledger" not in str(legacy)
    assert "The ledger proves the forgery." not in str(legacy)
    assert "crew_0002" not in str(legacy["rumor_memory"])
