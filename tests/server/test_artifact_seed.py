from hollow_lodge.server.artifact_seed import STARTER_ARTIFACT_GRAPH


def test_starter_artifact_graph_has_public_and_hidden_nodes():
    artifact_ids = {
        artifact.artifact_id for artifact in STARTER_ARTIFACT_GRAPH.artifacts
    }

    assert "artifact_lot_card" in artifact_ids
    assert "artifact_ledger_rubric" in artifact_ids
    assert "artifact_chapel_debt_mark" in artifact_ids
    assert "artifact_clerk_pencil_note" in artifact_ids


def test_starter_artifact_graph_has_unlock_rules_for_hidden_artifacts():
    rules = {
        rule.artifact_id: rule for rule in STARTER_ARTIFACT_GRAPH.unlock_rules
    }

    assert rules["artifact_chapel_debt_mark"].trigger == "action_mentions_tag"
    assert "chapel" in rules["artifact_chapel_debt_mark"].required_terms
    assert rules["artifact_clerk_pencil_note"].trigger == "action_mentions_tag"
    assert "clerk" in rules["artifact_clerk_pencil_note"].required_terms
