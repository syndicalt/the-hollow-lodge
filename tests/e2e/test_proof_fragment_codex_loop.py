import importlib.util
from pathlib import Path


def _load_run_mock():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "mock_proof_fragment_codex_loop.py"
    )
    spec = importlib.util.spec_from_file_location(
        "mock_proof_fragment_codex_loop",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_mock


def test_codex_proof_fragment_transfer_check_and_dossier_loop(tmp_path):
    run_mock = _load_run_mock()
    result = run_mock(str(tmp_path))
    copied_fragment_id = result["copied_fragment_id"]

    assert result["transfer_preview"]["agent_context"] == {
        "operation": "transfer_proof_fragment",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "fragment_id": "fragment_starter_ledger",
            "recipient_player_id": result["recipient_player_id"],
        },
    }
    assert result["transferred"]["agent_context"] == {
        "operation": "transfer_proof_fragment",
        "mutation": True,
        "confirmed": True,
        "result": {
            "fragment_id": copied_fragment_id,
            "content_summary": "A red ledger rubric names three prior owners.",
            "source_chain": [
                "archive:lot-card",
                f"transfer:player_0001->{result['recipient_player_id']}",
            ],
            "provenance_checked": False,
        },
    }
    assert "copied-hand" not in str(result["transferred"])
    assert "ink-after-binding" not in str(result["transferred"])

    assert result["grace_inbox"]["agent_context"]["incoming_proof_fragments"] == [
        {
            "fragment_id": copied_fragment_id,
            "summary": "A red ledger rubric names three prior owners.",
        }
    ]
    assert result["grace_inbox"]["agent_context"]["urgent_items"][-1] == {
        "kind": "proof_fragment",
        "fragment_id": copied_fragment_id,
    }
    assert f"- {copied_fragment_id}: A red ledger rubric names three prior owners." in (
        result["grace_inbox"]["player_markdown"]
    )
    assert "copied-hand" not in str(result["grace_inbox"])
    assert "ink-after-binding" not in str(result["grace_inbox"])

    before = result["fragment_before_check"]
    assert before["surface"] == "proof_fragment"
    assert before["agent_context"]["fragment"] == {
        "fragment_id": copied_fragment_id,
        "content_summary": "A red ledger rubric names three prior owners.",
        "source_chain": [
            "archive:lot-card",
            f"transfer:player_0001->{result['recipient_player_id']}",
        ],
        "provenance_checked": False,
    }
    assert "Provenance checked: false" in before["player_markdown"]
    assert "copied-hand" not in str(before)
    assert "ink-after-binding" not in str(before)

    assert result["provenance_preview"]["agent_context"] == {
        "operation": "check_provenance",
        "mutation": False,
        "confirmed": False,
        "preview": {
            "fragment_id": copied_fragment_id,
            "check_type": "provenance",
        },
    }
    assert result["provenance"]["agent_context"] == {
        "operation": "check_provenance",
        "mutation": True,
        "confirmed": True,
        "result": {
            "fragment_id": copied_fragment_id,
            "content_summary": "A red ledger rubric names three prior owners.",
            "source_chain": [
                "archive:lot-card",
                f"transfer:player_0001->{result['recipient_player_id']}",
            ],
            "provenance_checked": True,
            "provenance_flags": ["copied-hand", "ink-after-binding"],
        },
    }
    assert "copied-hand" in result["provenance"]["player_markdown"]

    after = result["fragment_after_check"]
    assert after["agent_context"]["fragment"]["provenance_checked"] is False
    assert "copied-hand" not in str(after)
    assert "ink-after-binding" not in str(after)

    assert result["contribution_preview"]["agent_context"]["preview"] == {
        "crew_id": result["crew_id"],
        "note": "Ledger provenance flags show the copied hand and later ink.",
        "evidence_ids": [copied_fragment_id],
    }
    dossier = result["dossier"]
    assert dossier["agent_context"]["dossier"]["member_contributions"] == [
        {
            "player_id": result["recipient_player_id"],
            "note": "Ledger provenance flags show the copied hand and later ink.",
            "evidence_ids": [copied_fragment_id],
        }
    ]
    assert f"- {result['recipient_player_id']}: Ledger provenance flags" in (
        dossier["player_markdown"]
    )

    activity = result["activity"]
    assert activity["agent_context"]["event_type_counts"]["proof.fragment.transferred"] == 1
    assert activity["agent_context"]["event_type_counts"]["proof.provenance.checked"] == 1
    assert activity["agent_context"]["event_type_counts"]["proof.dossier.contribution.added"] == 1
    assert f"proof fragment {copied_fragment_id}" in activity["player_markdown"]
    assert f"provenance {copied_fragment_id}: copied-hand, ink-after-binding" in (
        activity["player_markdown"]
    )

    assert "proof.fragment.transferred.internal" not in str(result["grace_events"])
    for packet_name in (
        "transfer_preview",
        "transferred",
        "grace_inbox",
        "fragment_before_check",
        "provenance_preview",
        "provenance",
        "fragment_after_check",
        "contribution_preview",
        "contribution",
        "dossier",
        "activity",
    ):
        serialized = str(result[packet_name])
        for forbidden in (
            "hidden_truth",
            "hidden_truth_summary",
            "contract.hidden_truth.seeded",
            "server_only",
            "server_notes",
            "visibility",
            "proof.fragment.transferred.internal",
            "source_fragment_id",
            "transfer_idempotency_key",
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
