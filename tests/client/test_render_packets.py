from hollow_lodge.client import render_packets
from hollow_lodge.client.render_packets import (
    build_mutation_result_packet,
    build_contract_board_packet,
    build_crew_board_packet,
    build_inbox_packet,
)


BOARD = {
    "campaign": {"campaign_id": "campaign_saints_ledgers", "title": "Saints & Ledgers"},
    "contracts": [
        {
            "contract_id": "contract_false_finger",
            "title": "The Saint's False Finger",
            "phase": {"name": "Auction Preview", "remaining_hours": 6},
            "crew_heat": 0,
            "proof_dossier_needs": [
                "provenance chain",
                "material authenticity",
                "auction leverage",
            ],
        }
    ],
}


INBOX = {
    "player_id": "player_0001",
    "active_contracts": BOARD["contracts"],
    "incoming_proof_fragments": [],
    "visible_artifacts": [
        {
            "artifact_id": "artifact_lot_card",
            "title": "Auction Lot Card",
            "kind": "lot_card",
            "public_summary": "A vellum card attributes the reliquary finger.",
            "hidden_note": "server-only",
        }
    ],
}


def test_contract_board_packet_has_player_markdown_and_agent_context():
    packet = build_contract_board_packet(BOARD)

    assert packet.surface == "contract_board"
    assert "Saints & Ledgers" in packet.player_markdown
    assert "The Saint's False Finger" in packet.player_markdown
    assert packet.agent_context["contracts"][0]["contract_id"] == "contract_false_finger"
    assert packet.agent_context["contracts"][0]["phase"]["name"] == "Auction Preview"
    assert packet.suggested_prompts == [
        "Open the contested contract",
        "Review crew packet status",
        "Draft a contract action",
    ]


def test_contract_board_packet_renders_archived_lifecycle_status():
    packet = build_contract_board_packet(
        {
            "campaign": BOARD["campaign"],
            "contracts": [
                {
                    **BOARD["contracts"][0],
                    "lifecycle_status": "archived",
                }
            ],
        }
    )

    assert "Status: archived" in packet.player_markdown
    assert packet.agent_context["contracts"][0]["lifecycle_status"] == "archived"


def test_contract_board_packet_renders_locked_contract_requirements():
    packet = build_contract_board_packet(
        {
            "campaign": BOARD["campaign"],
            "contracts": [
                {
                    **BOARD["contracts"][0],
                    "contract_id": "contract_ash_window",
                    "title": "The Ash Window",
                    "phase": {"name": "Cinder Preview", "remaining_hours": 4},
                    "proof_dossier_needs": ["fire chronology"],
                    "unlock_status": {
                        "state": "locked",
                        "requirements": [
                            {
                                "scope": "crew",
                                "metric": "reputation",
                                "minimum": 2,
                                "current": 0,
                                "label": "Reputation 2+",
                                "description": "Complete earlier Lodge work with a strong lead.",
                                "satisfied": False,
                                "hidden_truth": "server-only",
                            }
                        ],
                        "server_notes": "hidden",
                    },
                }
            ],
        }
    )

    assert "## The Ash Window" in packet.player_markdown
    assert "Unlock: locked" in packet.player_markdown
    assert "- Reputation 2+: 0/2" in packet.player_markdown
    assert "hidden" not in packet.player_markdown
    assert packet.agent_context["contracts"][0]["unlock_status"] == {
        "state": "locked",
        "requirements": [
            {
                "scope": "crew",
                "metric": "reputation",
                "minimum": 2,
                "current": 0,
                "label": "Reputation 2+",
                "description": "Complete earlier Lodge work with a strong lead.",
                "satisfied": False,
            }
        ],
    }


def test_inbox_packet_prioritizes_actionable_items_for_codex():
    packet = build_inbox_packet(
        {
            **INBOX,
            "pending_decisions": [
                {
                    "kind": "incoming_deal",
                    "label": "Incoming deal needs response",
                    "description": "Deal deal_000001 from crew_0002 needs a response.",
                    "crew_id": "crew_0001",
                    "contract_id": "contract_false_finger",
                    "deal_id": "deal_000001",
                    "hidden_note": "server-only",
                }
            ],
        }
    )

    assert packet.surface == "inbox"
    assert "Inbox: player_0001" in packet.player_markdown
    assert "Pending decisions:" in packet.player_markdown
    assert "- Incoming deal needs response: Deal deal_000001 from crew_0002 needs a response." in packet.player_markdown
    assert "incoming proof fragments: none" in packet.player_markdown
    assert "visible artifacts:" in packet.player_markdown
    assert "- artifact_lot_card: Auction Lot Card" in packet.player_markdown
    assert "server-only" not in packet.player_markdown
    assert packet.agent_context["player_id"] == "player_0001"
    assert packet.agent_context["pending_decisions"] == [
        {
            "kind": "incoming_deal",
            "label": "Incoming deal needs response",
            "description": "Deal deal_000001 from crew_0002 needs a response.",
            "crew_id": "crew_0001",
            "contract_id": "contract_false_finger",
            "deal_id": "deal_000001",
        }
    ]
    assert packet.agent_context["visible_artifacts"] == [
        {
            "artifact_id": "artifact_lot_card",
            "title": "Auction Lot Card",
            "kind": "lot_card",
            "public_summary": "A vellum card attributes the reliquary finger.",
        }
    ]
    assert packet.agent_context["urgent_items"] == packet.agent_context["pending_decisions"]
    assert packet.suggested_prompts == [
        "Open the contract board",
        "Review crew board",
    ]


def test_inbox_packet_uses_display_name_without_losing_player_id():
    packet = build_inbox_packet({**INBOX, "display_name": "corelumen"})

    assert "Inbox: corelumen" in packet.player_markdown
    assert packet.agent_context["display_name"] == "corelumen"
    assert packet.agent_context["player_id"] == "player_0001"


def test_mutation_preview_packet_is_explicit_and_non_mutating():
    packet = build_mutation_result_packet(
        operation="submit_action",
        confirmed=False,
        preview_fields={"crew_id": "crew_0001", "intent": "Inspect the red ledger."},
    )

    assert packet.surface == "mutation"
    assert "Preview: submit_action" in packet.player_markdown
    assert "No server mutation was submitted." in packet.player_markdown
    assert packet.agent_context == {
        "operation": "submit_action",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "crew_id": "crew_0001",
            "intent": "Inspect the red ledger.",
        },
    }


def test_mutation_result_packet_uses_visible_shaped_result_only():
    packet = build_mutation_result_packet(
        operation="dossier_cite_artifact",
        confirmed=True,
        result={
            "dossier_id": "dossier_crew_0001",
            "crew_id": "crew_0001",
            "packet_lead_player_id": "player_0001",
            "claim": "The finger is false.",
            "artifact_citations": [
                {
                    "player_id": "player_0001",
                    "artifact_id": "artifact_ledger_rubric",
                    "claim": "The ledger contradicts the lot card.",
                    "quote": "The last hand is later.",
                    "server_notes": "hidden",
                }
            ],
            "server_notes": "hidden",
        },
    )

    assert "Submitted: dossier_cite_artifact" in packet.player_markdown
    assert "server_notes" not in packet.player_markdown
    assert "server_notes" not in str(packet.agent_context)
    assert packet.agent_context == {
        "operation": "dossier_cite_artifact",
        "mutation": True,
        "confirmed": True,
        "result": {
            "dossier_id": "dossier_crew_0001",
            "crew_id": "crew_0001",
            "packet_lead_player_id": "player_0001",
            "claim": "The finger is false.",
            "artifact_citations": [
                {
                    "player_id": "player_0001",
                    "artifact_id": "artifact_ledger_rubric",
                    "claim": "The ledger contradicts the lot card.",
                    "quote": "The last hand is later.",
                }
            ],
            "member_contributions": [],
        },
    }


def test_submit_action_mutation_result_includes_safe_rumor_response_mode():
    packet = build_mutation_result_packet(
        operation="submit_action",
        confirmed=True,
        result={
            "action_id": "action_000001",
            "crew_id": "crew_0001",
            "intent": "Contain the rumor.",
            "responds_to_rumor_id": "rumor_msg_000001",
            "rumor_response_mode": "contain",
            "body": "The ledger proves our leverage.",
            "artifact_ids": ["artifact_ledger_rubric"],
        },
    )

    assert packet.agent_context["result"] == {
        "action_id": "action_000001",
        "crew_id": "crew_0001",
        "intent": "Contain the rumor.",
        "responds_to_rumor_id": "rumor_msg_000001",
        "rumor_response_mode": "contain",
    }
    assert "artifact_ledger_rubric" not in str(packet.agent_context)
    assert "The ledger proves our leverage" not in str(packet.agent_context)


def test_accept_deal_mutation_packet_renders_received_artifacts():
    packet = build_mutation_result_packet(
        operation="accept_deal",
        confirmed=True,
        result={
            "deal_id": "deal_000001",
            "contract_id": "contract_false_finger",
            "proposer_crew_id": "crew_0001",
            "recipient_crew_id": "crew_0002",
            "status": "fulfilled",
            "offered_artifact_ids": ["artifact_ledger_rubric"],
            "requested_artifact_ids": ["artifact_chapel_debt_mark"],
            "soft_terms": ["Do not cite us."],
            "expires_phase": None,
            "proposer_received_artifact_ids": [
                "artifact_chapel_debt_mark.dealcopy.deal_000001.crew_0001.2"
            ],
            "recipient_received_artifact_ids": [
                "artifact_ledger_rubric.dealcopy.deal_000001.crew_0002.1"
            ],
        },
    )

    assert "Received by proposer: artifact_chapel_debt_mark.dealcopy.deal_000001.crew_0001.2" in packet.player_markdown
    assert "Received by recipient: artifact_ledger_rubric.dealcopy.deal_000001.crew_0002.1" in packet.player_markdown
    assert packet.agent_context["result"]["proposer_received_artifact_ids"] == [
        "artifact_chapel_debt_mark.dealcopy.deal_000001.crew_0001.2"
    ]


def test_crew_board_packet_shows_packet_lead_and_dossier_status():
    packet = build_crew_board_packet(
        {
            "player_id": "player_0001",
            "crew": {
                "crew_id": "crew_0001",
                "name": "The Gilt Knives",
                "member_ids": ["player_0001", "player_0002"],
                "member_count": 2,
                "ready_for_full_contracts": False,
                "readiness_warning": "Crews should have 3-5 players for full contracts.",
                "join_code": "hidden",
            },
            "active_contracts": [
                {
                    **BOARD["contracts"][0],
                    "hidden_truth": "saint-bone forgery",
                }
            ],
            "dossier": {
                "dossier_id": "dossier_crew_0001",
                "crew_id": "crew_0001",
                "packet_lead_player_id": "player_0001",
                "claim": "",
                "evidence_ids": [],
                "artifact_citations": [
                    {
                        "player_id": "player_0001",
                        "artifact_id": "artifact_ledger_rubric",
                        "claim": "The ledger contradicts the public lot card.",
                        "quote": "The last hand is redder and later than the binding.",
                        "hidden_note": "server-only",
                    }
                ],
                "member_contributions": [],
                "server_notes": "hidden",
            },
            "visible_artifacts": [
                {
                    "artifact_id": "artifact_lot_card",
                    "title": "Auction Lot Card",
                    "kind": "lot_card",
                    "public_summary": "A vellum card attributes the reliquary finger.",
                    "hidden_note": "server-only",
                }
            ],
            "rumors": [
                {
                    "rumor_id": "rumor_msg_000001",
                    "source_type": "chat.message.created",
                    "source_id": "msg_000001",
                    "conversation_scope": "crew_to_crew",
                    "suspected_crew_ids": ["crew_0002", "crew_0003"],
                    "summary": "A private artifact discussion is echoing between crews.",
                    "pressure": "artifact_reference_detected",
                    "offered_artifact_ids": ["artifact_private_escrow"],
                    "soft_terms": ["Do not cite us."],
                    "server_notes": "hidden",
                }
            ],
            "pending_decisions": [
                {
                    "kind": "dossier_need",
                    "label": "Dossier needs provenance chain",
                    "description": "The Saint's False Finger still needs dossier coverage for provenance chain.",
                    "crew_id": "crew_0001",
                    "contract_id": "contract_false_finger",
                    "missing_need": "provenance chain",
                    "server_notes": "hidden",
                },
                {
                    "kind": "rumor_response",
                    "label": "Rumor needs response",
                    "description": (
                        "Rumor rumor_msg_000001 suggests artifact_reference_detected. "
                        "Decide whether to verify, ignore, or answer with a crew action."
                    ),
                    "crew_id": "crew_0001",
                    "rumor_id": "rumor_msg_000001",
                    "source_type": "chat.message.created",
                    "source_id": "msg_000001",
                    "pressure": "artifact_reference_detected",
                    "action": "review_rumor",
                    "artifact_ids": ["artifact_private_escrow"],
                    "body": "The ledger proves our leverage.",
                }
            ],
        }
    )

    assert packet.surface == "crew_board"
    assert "Crew Board: The Gilt Knives" in packet.player_markdown
    assert "Packet Lead: player_0001" in packet.player_markdown
    assert "Artifact citations:" in packet.player_markdown
    assert "- artifact_ledger_rubric: The ledger contradicts the public lot card." in packet.player_markdown
    assert "Artifacts:" in packet.player_markdown
    assert "- artifact_lot_card: Auction Lot Card" in packet.player_markdown
    assert "Rumors:" in packet.player_markdown
    assert "- rumor_msg_000001: A private artifact discussion is echoing between crews." in packet.player_markdown
    assert "Pending decisions:" in packet.player_markdown
    assert "- Dossier needs provenance chain: The Saint's False Finger still needs dossier coverage for provenance chain." in packet.player_markdown
    assert "- Rumor needs response: Rumor rumor_msg_000001 suggests artifact_reference_detected. Decide whether to verify, ignore, or answer with a crew action." in packet.player_markdown
    assert "artifact_private_escrow" not in packet.player_markdown
    assert "Do not cite us." not in packet.player_markdown
    assert "The ledger proves our leverage" not in packet.player_markdown
    assert "hidden" not in packet.player_markdown
    assert "hidden_truth" not in packet.player_markdown
    assert "server_notes" not in packet.player_markdown
    assert packet.agent_context["crew"]["crew_id"] == "crew_0001"
    assert "join_code" not in packet.agent_context["crew"]
    assert "hidden_truth" not in packet.agent_context["active_contracts"][0]
    assert "server_notes" not in packet.agent_context["dossier"]
    assert packet.agent_context["dossier"]["artifact_citations"] == [
        {
            "player_id": "player_0001",
            "artifact_id": "artifact_ledger_rubric",
            "claim": "The ledger contradicts the public lot card.",
            "quote": "The last hand is redder and later than the binding.",
        }
    ]
    assert packet.agent_context["visible_artifacts"] == [
        {
            "artifact_id": "artifact_lot_card",
            "title": "Auction Lot Card",
            "kind": "lot_card",
            "public_summary": "A vellum card attributes the reliquary finger.",
        }
    ]
    assert packet.agent_context["rumors"] == [
        {
            "rumor_id": "rumor_msg_000001",
            "source_type": "chat.message.created",
            "source_id": "msg_000001",
            "conversation_scope": "crew_to_crew",
            "suspected_crew_ids": ["crew_0002", "crew_0003"],
            "summary": "A private artifact discussion is echoing between crews.",
            "pressure": "artifact_reference_detected",
        }
    ]
    assert packet.agent_context["pending_decisions"] == [
        {
            "kind": "dossier_need",
            "label": "Dossier needs provenance chain",
            "description": "The Saint's False Finger still needs dossier coverage for provenance chain.",
            "crew_id": "crew_0001",
            "contract_id": "contract_false_finger",
            "missing_need": "provenance chain",
        },
        {
            "kind": "rumor_response",
            "label": "Rumor needs response",
            "description": (
                "Rumor rumor_msg_000001 suggests artifact_reference_detected. "
                "Decide whether to verify, ignore, or answer with a crew action."
            ),
            "crew_id": "crew_0001",
            "rumor_id": "rumor_msg_000001",
            "source_type": "chat.message.created",
            "source_id": "msg_000001",
            "pressure": "artifact_reference_detected",
            "action": "review_rumor",
        }
    ]
    assert packet.agent_context["urgent_items"] == packet.agent_context["pending_decisions"]


def test_crew_board_packet_renders_legacy_and_future_modifiers_without_hidden_fields():
    packet = build_crew_board_packet(
        {
            "player_id": "player_0001",
            "crew": {
                "crew_id": "crew_0001",
                "name": "The Gilt Knives",
                "member_ids": ["player_0001"],
                "member_count": 1,
                "ready_for_full_contracts": False,
                "readiness_warning": "Crews should have 3-5 players for full contracts.",
            },
            "legacy": {
                "reputation": 2,
                "heat": 1,
                "favors": 1,
                "debts": 0,
                "scars": [],
                "deal_conduct": {
                    "score": 2,
                    "fulfilled_count": 1,
                    "canceled_count": 0,
                    "declined_count": 0,
                    "open_count": 0,
                    "reliability": "reliable_escrow_partner",
                    "offered_artifact_ids": ["artifact_private_ledger"],
                    "soft_terms": ["Do not cite us."],
                },
                "counterintelligence": {
                    "investigations_started": 1,
                    "containments_started": 1,
                    "heat_from_containment": 1,
                    "artifact_ids": ["artifact_private_ledger"],
                },
                "completed_contracts": [
                    {
                        "contract_id": "contract_false_finger",
                        "title": "The Saint's False Finger",
                        "phase": "Auction Preview",
                        "standing": "Strong lead",
                        "score": 82,
                        "outcome": "strong_lead",
                        "hidden_truth": "forgery",
                    }
                ],
                "future_opportunities": [
                    {
                        "contract_id": "contract_ash_window",
                        "title": "The Ash Window",
                        "modifiers": [
                            {
                                "kind": "reputation_leverage",
                                "label": "Reputation leverage",
                                "description": "Prior strong work gives this crew an opening on The Ash Window.",
                                "value": 2,
                                "server_notes": "hidden",
                            },
                            {
                                "kind": "heat_attention",
                                "label": "Heat attention",
                                "description": "Prior heat makes The Ash Window riskier for this crew.",
                                "value": 1,
                            },
                            {
                                "kind": "deal_reliability",
                                "label": "Deal reliability",
                                "description": (
                                    "Recent escrowed trades make this crew easier to trust "
                                    "on side arrangements for The Ash Window."
                                ),
                                "value": 2,
                                "offered_artifact_ids": ["artifact_private_ledger"],
                            },
                        ],
                    }
                ],
                "server_notes": "hidden",
            },
            "active_contracts": [
                {
                    "contract_id": "contract_ash_window",
                    "title": "The Ash Window",
                    "phase": {"name": "Cinder Preview", "remaining_hours": 4},
                    "crew_heat": 0,
                    "proof_dossier_needs": ["fire chronology"],
                    "crew_modifiers": [
                        {
                            "kind": "reputation_leverage",
                            "label": "Reputation leverage",
                            "description": "Prior strong work gives this crew an opening on The Ash Window.",
                            "value": 2,
                        },
                        {
                            "kind": "deal_reliability",
                            "label": "Deal reliability",
                            "description": (
                                "Recent escrowed trades make this crew easier to trust "
                                "on side arrangements for The Ash Window."
                            ),
                            "value": 2,
                        },
                    ],
                }
            ],
            "dossier": {
                "dossier_id": "dossier_crew_0001",
                "crew_id": "crew_0001",
                "packet_lead_player_id": "player_0001",
                "claim": "",
                "evidence_ids": [],
                "artifact_citations": [],
                "member_contributions": [],
            },
            "visible_artifacts": [],
            "deals": [],
            "pending_decisions": [],
        }
    )

    assert "Legacy:" in packet.player_markdown
    assert "Reputation: 2" in packet.player_markdown
    assert "Heat: 1" in packet.player_markdown
    assert "Deal conduct:" in packet.player_markdown
    assert "Conduct score: 2" in packet.player_markdown
    assert "Reliability: reliable_escrow_partner" in packet.player_markdown
    assert "Fulfilled: 1; Canceled: 0; Declined: 0; Open: 0" in packet.player_markdown
    assert "Counterintelligence:" in packet.player_markdown
    assert "Investigations: 1; Containments: 1; Heat from containment: 1" in packet.player_markdown
    assert "- The Saint's False Finger: Strong lead (82)" in packet.player_markdown
    assert "Future modifiers:" in packet.player_markdown
    assert (
        "- The Ash Window: Reputation leverage +2; Heat attention +1; Deal reliability +2"
        in packet.player_markdown
    )
    assert "hidden" not in packet.player_markdown
    assert "artifact_private_ledger" not in packet.player_markdown
    assert "Do not cite us." not in packet.player_markdown
    assert packet.agent_context["legacy"] == {
        "reputation": 2,
        "heat": 1,
        "favors": 1,
        "debts": 0,
        "scars": [],
        "deal_conduct": {
            "score": 2,
            "fulfilled_count": 1,
            "canceled_count": 0,
            "declined_count": 0,
            "open_count": 0,
            "reliability": "reliable_escrow_partner",
        },
        "counterintelligence": {
            "investigations_started": 1,
            "containments_started": 1,
            "heat_from_containment": 1,
        },
        "completed_contracts": [
            {
                "contract_id": "contract_false_finger",
                "title": "The Saint's False Finger",
                "phase": "Auction Preview",
                "standing": "Strong lead",
                "score": 82,
                "outcome": "strong_lead",
            }
        ],
        "future_opportunities": [
            {
                "contract_id": "contract_ash_window",
                "title": "The Ash Window",
                "modifiers": [
                    {
                        "kind": "reputation_leverage",
                        "label": "Reputation leverage",
                        "description": "Prior strong work gives this crew an opening on The Ash Window.",
                        "value": 2,
                    },
                    {
                        "kind": "heat_attention",
                        "label": "Heat attention",
                        "description": "Prior heat makes The Ash Window riskier for this crew.",
                        "value": 1,
                    },
                    {
                        "kind": "deal_reliability",
                        "label": "Deal reliability",
                        "description": (
                            "Recent escrowed trades make this crew easier to trust on side "
                            "arrangements for The Ash Window."
                        ),
                        "value": 2,
                    },
                ],
            }
        ],
    }


def test_contract_board_agent_context_omits_hidden_upstream_fields():
    board = {
        "campaign": {
            "campaign_id": "campaign_saints_ledgers",
            "title": "Saints & Ledgers",
            "hidden_truth": "auction house is compromised",
        },
        "contracts": [
            {
                "contract_id": "contract_false_finger",
                "title": "The Saint's False Finger",
                "phase": {
                    "name": "Auction Preview",
                    "remaining_hours": 6,
                    "hidden_timer_seed": "server-only",
                },
                "crew_heat": 0,
                "proof_dossier_needs": ["provenance chain"],
                "phase_result": {
                    "standings": [
                        {
                            "crew_id": "crew_0001",
                            "standing": "Strong lead",
                            "score": 82,
                            "strengths": ["clean provenance contradiction"],
                            "weaknesses": ["thin witness chain"],
                            "penalties": ["crew heat drew attention"],
                            "revealed_clues": ["Auction house provenance is now suspect."],
                            "hidden_tiebreaker": 17,
                        }
                    ],
                    "hidden_truth": "saint-bone forgery",
                },
                "hidden_truth": "saint-bone forgery",
                "server_notes": "do not render",
            }
        ],
        "server_notes": "internal campaign notes",
    }

    packet = build_contract_board_packet(board)

    assert "Reasoning:" in packet.player_markdown
    assert "strengths: clean provenance contradiction" in packet.player_markdown
    assert "weaknesses: thin witness chain" in packet.player_markdown
    assert "penalties: crew heat drew attention" in packet.player_markdown
    assert "clues: Auction house provenance is now suspect." in packet.player_markdown
    assert "hidden_tiebreaker" not in packet.player_markdown
    assert "saint-bone forgery" not in packet.player_markdown

    assert packet.agent_context == {
        "campaign": {
            "campaign_id": "campaign_saints_ledgers",
            "title": "Saints & Ledgers",
        },
        "contracts": [
            {
                "contract_id": "contract_false_finger",
                "title": "The Saint's False Finger",
                "phase": {"name": "Auction Preview", "remaining_hours": 6},
                "crew_heat": 0,
                "proof_dossier_needs": ["provenance chain"],
                "phase_result": {
                    "standings": [
                        {
                            "crew_id": "crew_0001",
                            "standing": "Strong lead",
                            "score": 82,
                            "score_reasoning": {
                                "strengths": ["clean provenance contradiction"],
                                "weaknesses": ["thin witness chain"],
                                "penalties": ["crew heat drew attention"],
                                "revealed_clues": ["Auction house provenance is now suspect."],
                            },
                        }
                    ]
                },
            }
        ],
        "visible_artifacts": [],
        "visible_contract_count": 1,
    }


def test_inbox_agent_context_omits_hidden_upstream_fields_and_serializes_actions():
    inbox = {
        "player_id": "player_0001",
        "active_contracts": [
            {
                "contract_id": "contract_false_finger",
                "title": "The Saint's False Finger",
                "phase": {
                    "name": "Auction Preview",
                    "remaining_hours": 6,
                    "hidden_timer_seed": "server-only",
                },
                "crew_heat": 0,
                "proof_dossier_needs": ["provenance chain"],
                "hidden_truth": "saint-bone forgery",
            }
        ],
        "incoming_proof_fragments": [
            {
                "fragment_id": "fragment_0001",
                "summary": "A chipped reliquary seal.",
                "hidden_source": "server-only witness",
            }
        ],
        "server_notes": "internal inbox notes",
    }

    packet = build_inbox_packet(inbox)

    assert packet.model_dump() == {
        "surface": "inbox",
        "player_markdown": (
            "Inbox: player_0001\n\n"
            "Pending decisions:\n"
            "- none\n\n"
            "Active contracts:\n"
            "- The Saint's False Finger (Auction Preview)\n\n"
            "incoming proof fragments:\n"
            "- fragment_0001: A chipped reliquary seal.\n\n"
            "Incoming deals:\n"
            "- none"
        ),
        "agent_context": {
            "player_id": "player_0001",
            "active_contracts": [
                {
                    "contract_id": "contract_false_finger",
                    "title": "The Saint's False Finger",
                    "phase": {"name": "Auction Preview", "remaining_hours": 6},
                    "crew_heat": 0,
                    "proof_dossier_needs": ["provenance chain"],
                }
            ],
            "incoming_proof_fragments": [
                {
                    "fragment_id": "fragment_0001",
                    "summary": "A chipped reliquary seal.",
                }
            ],
            "visible_artifacts": [],
            "deals": [],
            "pending_decisions": [],
            "urgent_items": [{"kind": "proof_fragment", "fragment_id": "fragment_0001"}],
        },
        "suggested_prompts": [
            "Open the contract board",
            "Review crew board",
        ],
        "actions": [],
    }


def test_activity_summary_packet_shapes_visible_events_without_server_only_fields():
    assert hasattr(render_packets, "build_activity_summary_packet")
    packet = render_packets.build_activity_summary_packet(
        [
            {
                "origin": "server",
                "event_id": "evt_1",
                "sequence": 1,
                "type": "chat.message.created",
                "event_hash": "server-only-hash",
                "visibility": {"principals": [{"kind": "server"}]},
                "payload": {
                    "message_id": "msg_1",
                    "sender_player_id": "player_0002",
                    "sender_crew_id": "crew_a",
                    "recipient_crew_id": "crew_b",
                    "body": "No public claims until lock.",
                    "artifact_ids": ["artifact_1"],
                    "server_only_note": "hidden",
                },
            },
            {
                "origin": "server",
                "event_id": "evt_2",
                "sequence": 2,
                "type": "proof.fragment.transferred",
                "payload": {
                    "surface": {
                        "fragment_id": "fragment_1",
                        "content_summary": "A chipped reliquary seal.",
                        "hidden_source": "server-only witness",
                    },
                    "server_notes": "hidden",
                },
            },
            {
                "origin": "server",
                "event_id": "evt_3",
                "sequence": 3,
                "type": "contract.rumor.leaked",
                "payload": {
                    "rumor_id": "rumor_msg_000001",
                    "source_type": "chat.message.created",
                    "source_id": "msg_000001",
                    "conversation_scope": "crew_to_crew",
                    "suspected_crew_ids": ["crew_0001", "crew_0002"],
                    "summary": "A private artifact discussion is echoing between crews.",
                    "pressure": "artifact_reference_detected",
                    "offered_artifact_ids": ["artifact_ledger_rubric"],
                    "soft_terms": ["Do not cite us."],
                },
            },
            {
                "origin": "server",
                "event_id": "evt_4",
                "sequence": 4,
                "type": "contract.rumor.responded",
                "payload": {
                    "rumor_id": "rumor_msg_000001",
                    "action_id": "action_000001",
                    "crew_id": "crew_0003",
                    "source_type": "chat.message.created",
                    "source_id": "msg_000001",
                    "contract_id": "contract_saints_false_finger",
                    "pressure": "artifact_reference_detected",
                    "mode": "contain",
                    "outcome": "containment_started",
                    "heat_delta": 1,
                    "summary": "The crew started counterintelligence to contain a leaked rumor.",
                    "body": "The ledger proves our leverage. Keep quiet.",
                    "artifact_ids": ["artifact_ledger_rubric"],
                    "suspected_crew_ids": ["crew_0001", "crew_0002"],
                },
            },
            {
                "origin": "server",
                "event_id": "evt_5",
                "sequence": 5,
                "type": "contract.rumor.verified",
                "payload": {
                    "schema_version": 1,
                    "rumor_id": "rumor_msg_000001",
                    "action_id": "action_000001",
                    "crew_id": "crew_0003",
                    "source_type": "chat.message.created",
                    "source_id": "msg_000001",
                    "contract_id": "contract_saints_false_finger",
                    "pressure": "artifact_reference_detected",
                    "assessment": "credible_artifact_signal",
                    "confidence": "medium",
                    "summary": (
                        "The investigation found a credible artifact signal, but "
                        "not enough to expose the private source."
                    ),
                    "body": "The ledger proves our leverage. Keep quiet.",
                    "artifact_ids": ["artifact_ledger_rubric"],
                    "suspected_crew_ids": ["crew_0001", "crew_0002"],
                },
            },
            {
                "origin": "server",
                "event_id": "evt_6",
                "sequence": 6,
                "type": "crew.legacy.delta.recorded",
                "payload": {
                    "schema_version": 1,
                    "crew_id": "crew_0001",
                    "contract_id": "contract_false_finger",
                    "contract_title": "The Saint's False Finger",
                    "phase": "Auction Preview",
                    "standing": "Strong lead",
                    "score": 82,
                    "outcome": "strong_lead",
                    "deltas": {
                        "reputation": 2,
                        "heat": 1,
                        "favors": 1,
                        "debts": 0,
                        "scars": [],
                        "hidden_note": "server-only",
                    },
                    "summary": (
                        "Strong lead on The Saint's False Finger: reputation +2, "
                        "heat +1, favors +1."
                    ),
                    "hidden_truth": "saint-bone forgery",
                    "artifact_ids": ["artifact_ledger_rubric"],
                },
            },
        ]
    )

    assert packet.surface == "activity"
    assert "Recent visible activity:" in packet.player_markdown
    assert "1 chat player_0002: No public claims until lock." in packet.player_markdown
    assert "2 proof fragment fragment_1: A chipped reliquary seal." in packet.player_markdown
    assert "3 rumor: A private artifact discussion is echoing between crews." in packet.player_markdown
    assert (
        "4 rumor response action_000001: The crew started counterintelligence "
        "to contain a leaked rumor."
    ) in packet.player_markdown
    assert (
        "5 rumor verification action_000001: The investigation found a credible "
        "artifact signal, but not enough to expose the private source."
    ) in packet.player_markdown
    assert (
        "6 legacy crew_0001: Strong lead on The Saint's False Finger: "
        "reputation +2, heat +1, favors +1."
    ) in packet.player_markdown
    assert "server-only" not in packet.player_markdown
    assert "hidden" not in packet.player_markdown
    assert "artifact_ledger_rubric" not in packet.player_markdown
    assert "Do not cite us." not in packet.player_markdown
    assert "The ledger proves our leverage" not in packet.player_markdown
    assert packet.agent_context == {
        "visible_event_count": 6,
        "event_type_counts": {
            "chat.message.created": 1,
            "proof.fragment.transferred": 1,
            "contract.rumor.leaked": 1,
            "contract.rumor.responded": 1,
            "contract.rumor.verified": 1,
            "crew.legacy.delta.recorded": 1,
        },
        "recent_events": [
            {
                "sequence": 1,
                "type": "chat.message.created",
                "message": {
                    "message_id": "msg_1",
                    "sender_player_id": "player_0002",
                    "sender_crew_id": "crew_a",
                    "recipient_crew_id": "crew_b",
                    "body": "No public claims until lock.",
                    "artifact_ids": ["artifact_1"],
                },
            },
            {
                "sequence": 2,
                "type": "proof.fragment.transferred",
                "proof_fragment": {
                    "fragment_id": "fragment_1",
                    "content_summary": "A chipped reliquary seal.",
                },
            },
            {
                "sequence": 3,
                "type": "contract.rumor.leaked",
                "rumor": {
                    "rumor_id": "rumor_msg_000001",
                    "source_type": "chat.message.created",
                    "source_id": "msg_000001",
                    "conversation_scope": "crew_to_crew",
                    "suspected_crew_ids": ["crew_0001", "crew_0002"],
                    "summary": "A private artifact discussion is echoing between crews.",
                    "pressure": "artifact_reference_detected",
                },
            },
            {
                "sequence": 4,
                "type": "contract.rumor.responded",
                "rumor_response": {
                    "rumor_id": "rumor_msg_000001",
                    "action_id": "action_000001",
                    "crew_id": "crew_0003",
                    "source_type": "chat.message.created",
                    "source_id": "msg_000001",
                    "contract_id": "contract_saints_false_finger",
                    "pressure": "artifact_reference_detected",
                    "mode": "contain",
                    "outcome": "containment_started",
                    "heat_delta": 1,
                    "summary": "The crew started counterintelligence to contain a leaked rumor.",
                },
            },
            {
                "sequence": 5,
                "type": "contract.rumor.verified",
                "rumor_verification": {
                    "schema_version": 1,
                    "rumor_id": "rumor_msg_000001",
                    "action_id": "action_000001",
                    "crew_id": "crew_0003",
                    "source_type": "chat.message.created",
                    "source_id": "msg_000001",
                    "contract_id": "contract_saints_false_finger",
                    "pressure": "artifact_reference_detected",
                    "assessment": "credible_artifact_signal",
                    "confidence": "medium",
                    "summary": (
                        "The investigation found a credible artifact signal, but "
                        "not enough to expose the private source."
                    ),
                },
            },
            {
                "sequence": 6,
                "type": "crew.legacy.delta.recorded",
                "legacy_delta": {
                    "schema_version": 1,
                    "crew_id": "crew_0001",
                    "contract_id": "contract_false_finger",
                    "contract_title": "The Saint's False Finger",
                    "phase": "Auction Preview",
                    "standing": "Strong lead",
                    "score": 82,
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
                },
            },
        ],
    }
    assert packet.suggested_prompts == [
        "Open a conversation thread",
        "Review inbox",
        "Open the contract board",
    ]


def test_thread_packet_matches_cli_conversation_logic_and_omits_hidden_fields():
    events = [
        {
            "sequence": 1,
            "type": "chat.message.created",
            "payload": {
                "message_id": "msg_1",
                "sender_player_id": "player_0002",
                "sender_crew_id": "crew_a",
                "recipient_crew_id": "crew_b",
                "body": "No public claims until lock.",
                "server_only_note": "hidden",
            },
        },
        {
            "sequence": 2,
            "type": "chat.message.created",
            "payload": {
                "message_id": "msg_2",
                "sender_player_id": "player_0003",
                "sender_crew_id": "crew_b",
                "recipient_crew_id": "crew_a",
                "body": "Agreed.",
            },
        },
        {
            "sequence": 3,
            "type": "chat.message.created",
            "payload": {
                "message_id": "msg_3",
                "sender_player_id": "player_0004",
                "sender_crew_id": "crew_c",
                "recipient_crew_id": "crew_d",
                "body": "Not this thread.",
            },
        },
    ]

    assert hasattr(render_packets, "build_thread_packet")
    packet = render_packets.build_thread_packet(events, conversation_id="crew_a:crew_b")

    assert packet.surface == "thread"
    assert "Conversation: crew_a:crew_b" in packet.player_markdown
    assert "1 player_0002: No public claims until lock." in packet.player_markdown
    assert "2 player_0003: Agreed." in packet.player_markdown
    assert "Not this thread" not in packet.player_markdown
    assert "hidden" not in packet.player_markdown
    assert packet.agent_context == {
        "conversation_id": "crew_a:crew_b",
        "message_count": 2,
        "messages": [
            {
                "sequence": 1,
                "message_id": "msg_1",
                "sender_player_id": "player_0002",
                "sender_crew_id": "crew_a",
                "recipient_crew_id": "crew_b",
                "body": "No public claims until lock.",
                "artifact_ids": [],
            },
            {
                "sequence": 2,
                "message_id": "msg_2",
                "sender_player_id": "player_0003",
                "sender_crew_id": "crew_b",
                "recipient_crew_id": "crew_a",
                "body": "Agreed.",
                "artifact_ids": [],
            },
        ],
    }
    assert packet.suggested_prompts == [
        "Reply using the CLI",
        "Review recent activity",
    ]
