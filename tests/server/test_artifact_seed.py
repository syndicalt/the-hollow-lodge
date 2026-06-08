from hollow_lodge.server.artifact_seed import (
    STARTER_ARTIFACT_GRAPH,
    STARTER_PUBLIC_ARTIFACT_IDS,
)


def test_starter_artifact_graph_has_public_and_hidden_nodes():
    artifact_ids = {
        artifact.artifact_id for artifact in STARTER_ARTIFACT_GRAPH.artifacts
    }

    assert "artifact_lot_card" in artifact_ids
    assert "artifact_ledger_rubric" in artifact_ids
    assert "artifact_chapel_debt_mark" in artifact_ids
    assert "artifact_clerk_pencil_note" in artifact_ids


def test_starter_public_artifacts_are_the_planned_public_nodes():
    assert STARTER_PUBLIC_ARTIFACT_IDS == (
        "artifact_lot_card",
        "artifact_ledger_rubric",
    )

    assert "artifact_chapel_debt_mark" not in STARTER_PUBLIC_ARTIFACT_IDS
    assert "artifact_clerk_pencil_note" not in STARTER_PUBLIC_ARTIFACT_IDS

    artifacts = {
        artifact.artifact_id: artifact
        for artifact in STARTER_ARTIFACT_GRAPH.artifacts
    }

    assert artifacts["artifact_lot_card"].visible_flags == ("public-lot",)
    assert artifacts["artifact_ledger_rubric"].visible_flags == ("copied-hand",)


def test_starter_artifacts_keep_planned_hidden_flags_and_text():
    artifacts = {
        artifact.artifact_id: artifact
        for artifact in STARTER_ARTIFACT_GRAPH.artifacts
    }

    assert artifacts["artifact_lot_card"].full_text == (
        "Lot 19. Reliquary finger of Saint Aint. Held under sealed preview by "
        "Venn & Bell, with chapel seal affixed."
    )
    assert artifacts["artifact_ledger_rubric"].full_text == (
        "Rubric copy: Armitage, then Venn, then a chapel debt mark. The last "
        "hand is redder and later than the binding."
    )
    assert artifacts["artifact_ledger_rubric"].hidden_flags == (
        "ink-after-binding",
    )
    assert artifacts["artifact_chapel_debt_mark"].full_text == (
        "The rubbing shows the same chapel mark named in the ledger, but it is "
        "a debt sign rather than a saintly custody seal."
    )
    assert artifacts["artifact_chapel_debt_mark"].hidden_flags == (
        "debtor-omen",
    )
    assert artifacts["artifact_clerk_pencil_note"].full_text == (
        "Pencil note: 'Do not read the chapel mark as custody. Date was "
        "corrected after the preview catalogue was copied.'"
    )


def test_starter_artifact_graph_has_unlock_rules_for_hidden_artifacts():
    rules = {
        rule.artifact_id: rule for rule in STARTER_ARTIFACT_GRAPH.unlock_rules
    }

    assert rules["artifact_chapel_debt_mark"].trigger == "action_mentions_tag"
    assert "chapel" in rules["artifact_chapel_debt_mark"].required_terms
    assert rules["artifact_chapel_debt_mark"].award_scope == "crew"
    assert rules["artifact_chapel_debt_mark"].award_reason == (
        "Followed the chapel mark from the ledger."
    )
    assert rules["artifact_clerk_pencil_note"].trigger == "action_mentions_tag"
    assert "clerk" in rules["artifact_clerk_pencil_note"].required_terms
    assert "catalogue" in rules["artifact_clerk_pencil_note"].required_terms
    assert rules["artifact_clerk_pencil_note"].award_scope == "crew"
    assert rules["artifact_clerk_pencil_note"].award_reason == (
        "Pressed the auction clerk on the catalogue correction."
    )
