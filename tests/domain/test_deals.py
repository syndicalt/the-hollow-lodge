from hollow_lodge.domain.deals import Deal, deal_rows_from_events
from hollow_lodge.domain.events import EventVisibility, GameEvent


def event(sequence: int, event_type: str, payload: dict) -> GameEvent:
    return GameEvent.new(
        sequence=sequence,
        event_type=event_type,
        actor_id=payload.get("actor_id", "player_0001"),
        visibility=EventVisibility.crews(
            [payload["proposer_crew_id"], payload["recipient_crew_id"]]
        ),
        payload=payload,
        previous_hash=None,
        idempotency_key=f"key-{sequence}",
        event_id=f"evt_{sequence:06d}",
    )


def test_deal_projection_tracks_fulfilled_swap():
    rows = deal_rows_from_events(
        [
            event(
                1,
                "deal.proposed",
                {
                    "deal_id": "deal_000001",
                    "contract_id": "contract_false_finger",
                    "proposer_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "offered_artifact_ids": ["artifact_ledger_rubric"],
                    "requested_artifact_ids": ["artifact_chapel_debt_mark"],
                    "soft_terms": ["Do not cite us."],
                    "expires_phase": "Auction Preview",
                    "proposer_player_id": "player_0001",
                    "accepted_by_player_id": None,
                    "status": "proposed",
                },
            ),
            event(
                2,
                "deal.accepted",
                {
                    "deal_id": "deal_000001",
                    "contract_id": "contract_false_finger",
                    "proposer_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "accepted_by_player_id": "player_0002",
                },
            ),
            event(
                3,
                "deal.fulfilled",
                {
                    "deal_id": "deal_000001",
                    "contract_id": "contract_false_finger",
                    "proposer_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "proposer_received_artifact_ids": [
                        "artifact_chapel_debt_mark.dealcopy.deal_000001.crew_0001.1"
                    ],
                    "recipient_received_artifact_ids": [
                        "artifact_ledger_rubric.dealcopy.deal_000001.crew_0002.1"
                    ],
                    "status": "fulfilled",
                },
            ),
        ]
    )

    assert rows == [
        {
            "deal_id": "deal_000001",
            "contract_id": "contract_false_finger",
            "proposer_crew_id": "crew_0001",
            "recipient_crew_id": "crew_0002",
            "status": "fulfilled",
            "offered_artifact_ids": ["artifact_ledger_rubric"],
            "requested_artifact_ids": ["artifact_chapel_debt_mark"],
            "soft_terms": ["Do not cite us."],
            "expires_phase": "Auction Preview",
            "proposer_player_id": "player_0001",
            "accepted_by_player_id": "player_0002",
            "proposer_received_artifact_ids": [
                "artifact_chapel_debt_mark.dealcopy.deal_000001.crew_0001.1"
            ],
            "recipient_received_artifact_ids": [
                "artifact_ledger_rubric.dealcopy.deal_000001.crew_0002.1"
            ],
        }
    ]


def test_deal_projection_tracks_canceled_state():
    rows = deal_rows_from_events(
        [
            event(
                1,
                "deal.proposed",
                {
                    "deal_id": "deal_000001",
                    "contract_id": "contract_false_finger",
                    "proposer_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "offered_artifact_ids": ["artifact_ledger_rubric"],
                    "requested_artifact_ids": ["artifact_chapel_debt_mark"],
                    "soft_terms": [],
                    "expires_phase": None,
                    "proposer_player_id": "player_0001",
                    "accepted_by_player_id": None,
                    "status": "proposed",
                },
            ),
            event(
                2,
                "deal.canceled",
                {
                    "deal_id": "deal_000001",
                    "contract_id": "contract_false_finger",
                    "proposer_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "status": "canceled",
                },
            ),
        ]
    )

    assert rows[0]["status"] == "canceled"
