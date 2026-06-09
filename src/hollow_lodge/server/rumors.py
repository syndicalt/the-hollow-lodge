from __future__ import annotations

from typing import Any

from hollow_lodge.eventlog.jsonl_store import JsonlEventStore
from hollow_lodge.eventlog.visibility import Principal


SAFE_RUMOR_FIELDS = (
    "rumor_id",
    "source_type",
    "source_id",
    "conversation_scope",
    "contract_id",
    "suspected_crew_ids",
    "summary",
    "pressure",
    "leak_vector",
)


def visible_rumors_for_crew(event_store: JsonlEventStore, crew_id: str) -> list[dict[str, Any]]:
    rumors: list[dict[str, Any]] = []
    for event in event_store.read_for_principal(Principal.crew(crew_id)):
        if event.type != "contract.rumor.leaked":
            continue
        rumors.append(
            {
                key: event.payload[key]
                for key in SAFE_RUMOR_FIELDS
                if key in event.payload
            }
        )
    return rumors
