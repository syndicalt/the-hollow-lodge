from __future__ import annotations

from hollow_lodge.domain.artifact_graph import ArtifactGraph, ArtifactUnlockRule


def action_unlock_candidates(
    *,
    graph: ArtifactGraph,
    contract_id: str,
    phase: str,
    intent: str,
    exposed_assets: tuple[str, ...] | list[str],
    already_visible_artifact_ids: set[str],
) -> list[ArtifactUnlockRule]:
    normalized_intent = intent.casefold()
    exposed_asset_ids = set(exposed_assets)
    candidates: list[ArtifactUnlockRule] = []

    for rule in graph.unlock_rules:
        if rule.contract_id != contract_id or rule.phase != phase:
            continue
        if rule.artifact_id in already_visible_artifact_ids:
            continue
        if rule.trigger == "action_mentions_tag":
            if all(term.casefold() in normalized_intent for term in rule.required_terms):
                candidates.append(rule)
        elif rule.trigger == "action_exposes_asset":
            if set(rule.required_artifact_ids).issubset(exposed_asset_ids):
                candidates.append(rule)

    return candidates
