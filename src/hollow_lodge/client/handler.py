from __future__ import annotations

from hollow_lodge.client.local_log import LocalEventLog
from hollow_lodge.domain.actions import NormalizedAction


def normalize_action_draft(
    *,
    local_log: LocalEventLog,
    intent: str,
    actor_player_id: str,
    crew_id: str,
) -> NormalizedAction:
    frame = NormalizedAction.from_intent(
        intent=intent,
        actor_player_id=actor_player_id,
        crew_id=crew_id,
    )
    local_log.append_local_note(
        note_type="action.draft.normalized",
        payload=frame.model_dump(mode="json"),
    )
    return frame
