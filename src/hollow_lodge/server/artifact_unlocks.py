from __future__ import annotations

from hollow_lodge.domain.artifact_graph import ArtifactGraph, ArtifactUnlockRule


LEADER_FOLLOWUP_ARTIFACT_ID = "artifact_clerk_pencil_note"


def action_unlock_candidates(
    *,
    graph: ArtifactGraph,
    contract_id: str,
    phase: str,
    matched_terms: tuple[str, ...] | list[str] = (),
    exposed_assets: tuple[str, ...] | list[str],
    already_visible_artifact_ids: set[str],
) -> list[ArtifactUnlockRule]:
    normalized_terms = {term.casefold() for term in matched_terms}
    exposed_asset_ids = set(exposed_assets)
    candidates: list[ArtifactUnlockRule] = []

    for rule in graph.unlock_rules:
        if rule.contract_id != contract_id or rule.phase != phase:
            continue
        if rule.artifact_id in already_visible_artifact_ids:
            continue
        if rule.trigger == "action_mentions_tag":
            if {term.casefold() for term in rule.required_terms}.issubset(
                normalized_terms
            ):
                candidates.append(rule)
        elif rule.trigger == "action_exposes_asset":
            if set(rule.required_artifact_ids).issubset(exposed_asset_ids):
                candidates.append(rule)

    return candidates


def auction_preview_phase_reward_artifact_id(reveal: dict) -> str | None:
    standings = reveal.get("standings", [])
    if not standings:
        return None
    return LEADER_FOLLOWUP_ARTIFACT_ID
