from hollow_lodge.client.artifact_render import (
    build_artifact_graph_packet,
    build_artifact_packet,
)


def test_artifact_packet_renders_source_material_and_agent_context():
    packet = build_artifact_packet(
        {
            "artifact_id": "artifact_ledger_rubric",
            "title": "Red Ledger Rubric",
            "kind": "ledger",
            "public_summary": "A copied rubric marks prior ownership.",
            "full_text": "Lot 19 passed under chapel seal.",
            "source_chain": ["archive:lot-card"],
            "visible_flags": ["copied-hand"],
            "proof_lanes": ["provenance"],
        }
    )

    assert packet.surface == "artifact"
    assert "Red Ledger Rubric" in packet.player_markdown
    assert "Lot 19 passed under chapel seal." in packet.player_markdown
    assert packet.agent_context["artifact"]["artifact_id"] == "artifact_ledger_rubric"
    assert "dossier citation" not in " ".join(packet.suggested_prompts).lower()
    assert "transfer" not in " ".join(packet.suggested_prompts).lower()
    assert {action.intent for action in packet.actions}.isdisjoint(
        {"cite_artifact", "transfer_artifact"}
    )


def test_artifact_graph_packet_renders_known_artifacts_and_edges():
    packet = build_artifact_graph_packet(
        {
            "contract_id": "contract_false_finger",
            "artifacts": [
                {
                    "artifact_id": "artifact_lot_card",
                    "title": "Auction Lot Card",
                    "kind": "lot_card",
                    "public_summary": "Public lot card.",
                },
                {
                    "artifact_id": "artifact_ledger_rubric",
                    "title": "Red Ledger Rubric",
                    "kind": "ledger",
                    "public_summary": "Copied rubric.",
                },
            ],
            "edges": [
                {
                    "source_id": "artifact_lot_card",
                    "target_id": "artifact_ledger_rubric",
                    "relation": "contradicts",
                    "public_summary": "The dates do not agree.",
                }
            ],
        }
    )

    assert packet.surface == "artifact_graph"
    assert "Auction Lot Card" in packet.player_markdown
    assert "contradicts" in packet.player_markdown
    assert "dossier citation" not in " ".join(packet.suggested_prompts).lower()
    assert "transfer" not in " ".join(packet.suggested_prompts).lower()
    assert {action.intent for action in packet.actions}.isdisjoint(
        {"cite_artifact", "transfer_artifact"}
    )
