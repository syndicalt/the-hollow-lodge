from __future__ import annotations

from hollow_lodge.domain.actions import NormalizedAction
from hollow_lodge.workflows.llmff_boundary import HandlerNormalizationFrame


def deterministic_provenance_read(fragment_id: str) -> dict:
    return {
        "fragment_id": fragment_id,
        "authority": "local-guidance",
        "guidance": "This may merit a provenance check; spend a side action for an official result.",
    }


def handler_provenance_summary(fragment_id: str) -> dict:
    return {
        "origin": "handler",
        "type": "handler.provenance_summary",
        "fragment_id": fragment_id,
        "summary": "This local read can inform player intent but is not an official result.",
    }


def normalize_action_intent(
    intent: str,
    *,
    actor_player_id: str,
    crew_id: str,
) -> HandlerNormalizationFrame:
    return HandlerNormalizationFrame(
        origin="handler",
        type="action.draft.normalized",
        normalized=NormalizedAction.from_intent(
            intent=intent,
            actor_player_id=actor_player_id,
            crew_id=crew_id,
        ),
    )
