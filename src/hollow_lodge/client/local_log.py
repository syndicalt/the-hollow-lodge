from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class LocalEventLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append_local_note(self, *, note_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "origin": "local",
            "type": note_type,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True))
            handle.write("\n")
        return event

    def sync_visible_server_events(self, events: list[dict[str, Any]]) -> int:
        existing_event_ids = {
            event["event_id"]
            for event in self.read()
            if event.get("origin") == "server" and "event_id" in event
        }
        synced = 0
        with self.path.open("a", encoding="utf-8") as handle:
            for event in sorted(events, key=lambda candidate: candidate["sequence"]):
                if event["event_id"] in existing_event_ids:
                    continue
                local_event = {"origin": "server", **event}
                handle.write(json.dumps(local_event, sort_keys=True))
                handle.write("\n")
                existing_event_ids.add(event["event_id"])
                synced += 1
        return synced

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def server_events_to_submit(self) -> list[dict[str, Any]]:
        return [event for event in self.read() if event.get("origin") == "server-submit"]
