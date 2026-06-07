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

    def max_server_sequence(self) -> int:
        return max(
            (
                int(event["sequence"])
                for event in self.read()
                if event.get("origin") == "server" and "sequence" in event
            ),
            default=0,
        )

    def render_replay(self, *, since_sequence: int = 0) -> list[str]:
        lines: list[str] = []
        events = [
            event
            for event in self.read()
            if event.get("origin") == "server" and int(event["sequence"]) > since_sequence
        ]
        for event in sorted(events, key=lambda item: int(item["sequence"])):
            rendered = _render_server_event(event)
            if rendered is not None:
                lines.append(rendered)
        return lines

    def server_events_to_submit(self) -> list[dict[str, Any]]:
        return [event for event in self.read() if event.get("origin") == "server-submit"]


def _render_server_event(event: dict[str, Any]) -> str | None:
    payload = event.get("payload", {})
    sequence = event["sequence"]
    if event["type"] == "chat.message.created":
        return f"{sequence} {payload.get('sender_player_id')}: {payload.get('body')}"
    if event["type"] == "proof.fragment.transferred":
        surface = payload.get("surface", {})
        return f"{sequence} proof fragment {surface.get('fragment_id')}: {surface.get('content_summary')}"
    if event["type"] == "proof.provenance.checked":
        result = payload.get("result", {})
        flags = ", ".join(result.get("provenance_flags", [])) or "clear"
        return f"{sequence} provenance {result.get('fragment_id')}: {flags}"
    if event["type"] == "action.submitted":
        action = payload.get("action", {})
        return f"{sequence} action {action.get('action_id')}: {action.get('intent')}"
    if event["type"] == "contract.phase.resolved":
        standings = payload.get("reveal", {}).get("standings", [])
        if not standings:
            return f"{sequence} phase result"
        leader = standings[0]
        return (
            f"{sequence} phase result: {leader.get('crew_id')} "
            f"{leader.get('standing')} {leader.get('score')}"
        )
    return None
