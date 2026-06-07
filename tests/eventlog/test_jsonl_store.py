import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.eventlog.jsonl_store import (
    EventLogIntegrityError,
    JsonlEventStore,
    rebuild_projection,
)


def test_append_read_and_hash_chain(tmp_path):
    store = JsonlEventStore(tmp_path / "events.jsonl")

    first = store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    second = store.append(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.crews(["crew_ember", "crew_mirror"]),
        payload={"contract_id": "contract_false_finger"},
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert first.previous_hash is None
    assert second.previous_hash == first.event_hash
    assert first.event_hash != second.event_hash
    assert [event.sequence for event in store.read(start_sequence=1, end_sequence=2)] == [1, 2]
    assert store.verify_integrity().ok is True

    row = json.loads((tmp_path / "events.jsonl").read_text().splitlines()[0])
    assert row["schema_version"] == 1
    assert list(row) == sorted(row)


def test_concurrent_append_does_not_duplicate_sequence_numbers(tmp_path):
    store = JsonlEventStore(tmp_path / "events.jsonl")

    def append_one(index: int) -> int:
        event = store.append(
            event_type="chat.message.created",
            actor_id=f"player_{index}",
            visibility=EventVisibility.players([f"player_{index}"]),
            payload={"index": index},
        )
        return event.sequence

    with ThreadPoolExecutor(max_workers=12) as pool:
        sequences = list(pool.map(append_one, range(50)))

    assert sorted(sequences) == list(range(1, 51))
    assert [event.sequence for event in store.read()] == list(range(1, 51))
    assert store.verify_integrity().ok is True


def test_replayed_idempotency_key_returns_original_event_without_duplicate(tmp_path):
    store = JsonlEventStore(tmp_path / "events.jsonl")

    first = store.append_command(
        event_type="action.submitted",
        actor_id="player_ada",
        visibility=EventVisibility.players(["player_ada"]),
        payload={"intent": "inspect the ledger"},
        idempotency_key="submit-action-1",
    )
    replayed = store.append_command(
        event_type="action.submitted",
        actor_id="player_ada",
        visibility=EventVisibility.players(["player_ada"]),
        payload={"intent": "inspect the ledger again"},
        idempotency_key="submit-action-1",
    )

    assert replayed == first
    assert len(store.read()) == 1


def test_command_events_require_idempotency_keys(tmp_path):
    store = JsonlEventStore(tmp_path / "events.jsonl")

    with pytest.raises(ValueError, match="idempotency"):
        store.append_command(
            event_type="action.submitted",
            actor_id="player_ada",
            visibility=EventVisibility.players(["player_ada"]),
            payload={"intent": "inspect the ledger"},
            idempotency_key="",
        )


def test_projection_can_rebuild_current_state_from_authoritative_events(tmp_path):
    store = JsonlEventStore(tmp_path / "events.jsonl")
    store.append(
        event_type="crew.heat.changed",
        actor_id="server",
        visibility=EventVisibility.crews(["crew_ember"]),
        payload={"crew_id": "crew_ember", "heat": 1},
    )
    store.append(
        event_type="crew.heat.changed",
        actor_id="server",
        visibility=EventVisibility.crews(["crew_ember"]),
        payload={"crew_id": "crew_ember", "heat": 3},
    )

    def apply_heat(state: dict[str, int], event):
        if event.type == "crew.heat.changed":
            state[event.payload["crew_id"]] = event.payload["heat"]
        return state

    assert rebuild_projection(store.read(), {}, apply_heat) == {"crew_ember": 3}


def test_verifier_rejects_corrupted_hash_chain(tmp_path):
    store = JsonlEventStore(tmp_path / "events.jsonl")
    store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    store.append(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.crews(["crew_ember"]),
        payload={"contract_id": "contract_false_finger"},
    )

    rows = (tmp_path / "events.jsonl").read_text().splitlines()
    corrupted = json.loads(rows[0])
    corrupted["payload"]["contract_id"] = "tampered"
    rows[0] = json.dumps(corrupted, sort_keys=True)
    (tmp_path / "events.jsonl").write_text("\n".join(rows) + "\n")

    with pytest.raises(EventLogIntegrityError, match="hash"):
        store.verify_integrity()


def test_malformed_trailing_json_fails_unless_explicit_repair_mode_is_used(tmp_path):
    store = JsonlEventStore(tmp_path / "events.jsonl")
    store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    with (tmp_path / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"sequence":')

    with pytest.raises(EventLogIntegrityError, match="invalid JSON"):
        store.read()
    with pytest.raises(EventLogIntegrityError, match="invalid JSON"):
        store.verify_integrity()

    assert [event.sequence for event in store.read(repair=True)] == [1]
    assert store.verify_integrity(repair=True).repaired_trailing_row is True


def test_non_trailing_malformed_json_is_never_repaired(tmp_path):
    log_path = tmp_path / "events.jsonl"
    store = JsonlEventStore(log_path)
    store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    valid_row = log_path.read_text()
    log_path.write_text('{"sequence":\n' + valid_row)

    with pytest.raises(EventLogIntegrityError, match="invalid JSON"):
        store.read(repair=True)
