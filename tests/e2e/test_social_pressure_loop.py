import importlib.util
from pathlib import Path


def _load_run_mock():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "mock_social_pressure_loop.py"
    )
    spec = importlib.util.spec_from_file_location("mock_social_pressure_loop", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_mock


def test_private_escrow_deal_leaks_sanitized_rumor_to_bystander(tmp_path):
    run_mock = _load_run_mock()
    result = run_mock(str(tmp_path))

    assert result["deal"]["status"] == "fulfilled"
    assert result["deal"]["proposer_received_artifact_ids"]
    assert result["deal"]["recipient_received_artifact_ids"]
    assert result["participant_deals"]["agent_context"]["visible_deal_count"] == 1
    assert result["bystander_deals"]["agent_context"] == {
        "deals": [],
        "visible_deal_count": 0,
    }
    assert "deal_000001 fulfilled" in result["participant_deals"]["player_markdown"]
    assert "Soft term: Do not cite our crew as source until Auction Lock." in (
        result["participant_deals"]["player_markdown"]
    )
    assert "Visible deals:\n- none" == result["bystander_deals"]["player_markdown"]

    rumor = result["bystander_board"]["agent_context"]["rumors"][0]
    assert rumor == {
        "rumor_id": "rumor_deal_000001",
        "source_type": "deal.proposed",
        "source_id": "deal_000001",
        "contract_id": "contract_false_finger",
        "suspected_crew_ids": [result["gilt_crew_id"], result["moth_crew_id"]],
        "summary": "A side arrangement is circulating around contract_false_finger.",
        "pressure": "escrow_terms_detected",
        "leak_vector": "soft_term_reference",
    }
    assert "- rumor_deal_000001: A side arrangement is circulating" in (
        result["bystander_board"]["player_markdown"]
    )

    rumor_decisions = [
        decision
        for decision in result["bystander_inbox"]["agent_context"]["pending_decisions"]
        if decision["kind"] == "rumor_response"
    ]
    assert rumor_decisions == [
        {
            "kind": "rumor_response",
            "label": "Rumor needs response",
            "description": (
                "Rumor rumor_deal_000001 suggests escrow_terms_detected. "
                "Decide whether to verify, ignore, or answer with a crew action."
            ),
            "crew_id": result["ash_crew_id"],
            "rumor_id": "rumor_deal_000001",
            "source_type": "deal.proposed",
            "source_id": "deal_000001",
            "pressure": "escrow_terms_detected",
            "leak_vector": "soft_term_reference",
            "action": "review_rumor",
        }
    ]
    assert result["bystander_inbox"]["agent_context"]["urgent_items"][0] == (
        rumor_decisions[0]
    )
    assert "Rumor needs response" in result["bystander_inbox"]["player_markdown"]
    assert "Incoming deals:\n- none" in result["bystander_inbox"]["player_markdown"]

    forbidden_rumor_fields = {
        "offered_artifact_ids",
        "requested_artifact_ids",
        "soft_terms",
        "expires_phase",
        "proposer_received_artifact_ids",
        "recipient_received_artifact_ids",
        "accepted_by_player_id",
        "idempotency_key",
        "payload",
        "event_id",
        "event_hash",
        "origin",
    }
    assert not (set(rumor) & forbidden_rumor_fields)
    assert not (set(rumor_decisions[0]) & forbidden_rumor_fields)
    assert "artifact_chapel_debt_mark" not in str(rumor)
    assert "artifact_chapel_debt_mark" not in str(rumor_decisions)
    assert "Do not cite our crew" not in str(rumor)
    assert "Do not cite our crew" not in str(rumor_decisions)

    investigation = result["investigation"]["agent_context"]["result"]
    assert investigation == {
        "action_id": "action_000001",
        "crew_id": result["ash_crew_id"],
        "intent": "Ask a night clerk whether the side arrangement is real.",
        "status": "submitted",
        "responds_to_rumor_id": "rumor_deal_000001",
        "rumor_response_mode": "investigate",
    }
    activity = result["post_investigation_activity"]
    assert activity["surface"] == "activity"
    assert activity["agent_context"]["event_type_counts"] == {
        "campaign.seeded": 1,
        "contract.board.published": 1,
        "crew.created": 1,
        "contract.rumor.leaked": 1,
        "action.submitted": 1,
        "contract.rumor.responded": 1,
        "contract.rumor.verified": 1,
    }
    assert "rumor response action_000001" in activity["player_markdown"]
    assert "credible soft-term signal" in activity["player_markdown"]
    verification = activity["agent_context"]["recent_events"][-1]["rumor_verification"]
    assert verification == {
        "schema_version": 1,
        "rumor_id": "rumor_deal_000001",
        "action_id": "action_000001",
        "crew_id": result["ash_crew_id"],
        "source_type": "deal.proposed",
        "source_id": "deal_000001",
        "contract_id": "contract_false_finger",
        "pressure": "escrow_terms_detected",
        "leak_vector": "soft_term_reference",
        "assessment": "credible_soft_term_signal",
        "confidence": "medium",
        "summary": (
            "The investigation found a credible soft-term signal, but not enough "
            "to expose the private source."
        ),
    }
    assert "artifact_chapel_debt_mark" not in str(verification)
    assert "Do not cite our crew" not in str(verification)

    final_legacy = result["bystander_final_board"]["agent_context"]["legacy"]
    assert final_legacy["counterintelligence"]["investigations_started"] == 1
    assert final_legacy["rumor_memory"]["verified_count"] == 1
    assert final_legacy["rumor_memory"]["assessment_counts"] == {
        "credible_soft_term_signal": 1,
    }
