import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from hollow_lodge.domain.events import EventVisibility, canonical_json_bytes, compute_event_hash
from hollow_lodge.eventlog.jsonl_store import (
    EventLogIntegrityError,
    IdempotencyConflictError,
    JsonlEventStore,
    rebuild_projection,
)
from hollow_lodge.eventlog.visibility import Principal


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
        payload={"intent": "inspect the ledger"},
        idempotency_key="submit-action-1",
    )

    assert replayed == first
    assert replayed.payload == {"intent": "inspect the ledger"}
    assert replayed.command_fingerprint is not None
    assert len(store.read()) == 1


def test_replayed_idempotency_key_with_different_command_is_rejected(tmp_path):
    store = JsonlEventStore(tmp_path / "events.jsonl")
    store.append_command(
        event_type="action.submitted",
        actor_id="player_ada",
        visibility=EventVisibility.players(["player_ada"]),
        payload={"intent": "inspect the ledger"},
        idempotency_key="submit-action-1",
    )

    with pytest.raises(IdempotencyConflictError, match="idempotency key conflict"):
        store.append_command(
            event_type="action.submitted",
            actor_id="player_ada",
            visibility=EventVisibility.players(["player_ada"]),
            payload={"intent": "inspect the reliquary"},
            idempotency_key="submit-action-1",
        )


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


def test_jsonl_event_store_diagnostics_include_event_count(tmp_path):
    store = JsonlEventStore(tmp_path / "events.jsonl")

    empty_diagnostics = store.diagnostics()
    assert empty_diagnostics["event_count"] == 0
    assert empty_diagnostics["last_sequence"] is None
    assert empty_diagnostics["last_event_hash"] is None
    event = store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )

    diagnostics = store.diagnostics()

    assert diagnostics["backend"] == "jsonl"
    assert diagnostics["status"] == "available"
    assert diagnostics["event_count"] == 1
    assert diagnostics["last_sequence"] == 1
    assert diagnostics["last_event_hash"] == event.event_hash


def test_jsonl_event_store_import_preserves_exported_chain(tmp_path):
    source = JsonlEventStore(tmp_path / "source-events.jsonl")
    first = source.append_command(
        event_type="action.submitted",
        actor_id="player_ada",
        visibility=EventVisibility.players(["player_ada"]),
        payload={"intent": "inspect the ledger"},
        idempotency_key="submit-action-1",
    )
    second = source.append(
        event_type="contract.rumor.responded",
        actor_id="server",
        visibility=EventVisibility.crews(["crew_0001"]),
        payload={"crew_id": "crew_0001", "summary": "Response recorded."},
    )

    destination = JsonlEventStore(tmp_path / "restored" / "server-events.jsonl")
    report = destination.import_events(source.read())

    assert report.ok is True
    assert report.event_count == 2
    restored = destination.read()
    assert restored == [first, second]
    assert destination.diagnostics()["last_event_hash"] == second.event_hash


def test_jsonl_event_store_import_refuses_non_empty_destination(tmp_path):
    source = JsonlEventStore(tmp_path / "source-events.jsonl")
    source.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    destination = JsonlEventStore(tmp_path / "destination-events.jsonl")
    destination.append(
        event_type="identity.player.registered",
        actor_id="server",
        visibility=EventVisibility.players(["player_0001"]),
        payload={"player_id": "player_0001"},
    )

    with pytest.raises(EventLogIntegrityError, match="destination event log is not empty"):
        destination.import_events(source.read())


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


def test_read_rejects_previous_hash_chain_break(tmp_path):
    log_path = tmp_path / "events.jsonl"
    store = JsonlEventStore(log_path)
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
    rows = log_path.read_text().splitlines()
    second = json.loads(rows[1])
    second["previous_hash"] = "0" * 64
    second["event_hash"] = compute_event_hash(second)
    rows[1] = json.dumps(second, sort_keys=True)
    log_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(EventLogIntegrityError, match="hash chain break"):
        store.read()


def test_append_rejects_existing_hash_chain_break(tmp_path):
    log_path = tmp_path / "events.jsonl"
    store = JsonlEventStore(log_path)
    first = store.append(
        event_type="first",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"n": 1},
    )
    second = store.append(
        event_type="second",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"n": 2},
    )
    rows = [event.model_dump(mode="json") for event in [first, second]]
    rows[1]["previous_hash"] = "0" * 64
    rows[1]["event_hash"] = compute_event_hash(rows[1])
    log_path.write_text(
        "\n".join(canonical_json_bytes(row).decode("utf-8") for row in rows) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(EventLogIntegrityError, match="hash chain break"):
        store.append(
            event_type="third",
            actor_id="server",
            visibility=EventVisibility.server_only(),
            payload={"n": 3},
        )


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
    with pytest.raises(TypeError):
        store.read(repair=True)

    assert store.verify_integrity(repair=True).repaired_trailing_row is True
    assert store.read() == store.read_for_principal(Principal.server())


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
        store.verify_integrity(repair=True)


def test_trailing_schema_invalid_json_is_never_repaired(tmp_path):
    log_path = tmp_path / "events.jsonl"
    store = JsonlEventStore(log_path)
    store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write('{"not":"a game event"}\n')

    with pytest.raises(EventLogIntegrityError, match="invalid event row"):
        store.verify_integrity(repair=True)


def test_persisted_row_without_schema_version_is_rejected(tmp_path):
    log_path = tmp_path / "events.jsonl"
    store = JsonlEventStore(log_path)
    store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    row = json.loads(log_path.read_text().splitlines()[0])
    del row["schema_version"]
    log_path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(EventLogIntegrityError, match="invalid event row"):
        store.verify_integrity()


def test_persisted_row_with_unknown_top_level_field_is_rejected(tmp_path):
    log_path = tmp_path / "events.jsonl"
    store = JsonlEventStore(log_path)
    store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    row = json.loads(log_path.read_text().splitlines()[0])
    row["unexpected"] = "not allowed"
    log_path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(EventLogIntegrityError, match="invalid event row"):
        store.verify_integrity()


def test_principal_scoped_read_excludes_server_only_events(tmp_path):
    store = JsonlEventStore(tmp_path / "events.jsonl")
    visible = store.append(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.crews(["crew_ember"]),
        payload={"contract_id": "contract_false_finger"},
    )
    store.append(
        event_type="contract.hidden_truth.sealed",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"truth": "false_finger"},
    )

    assert store.read_for_principal(Principal.crew("crew_ember")) == [visible]
    assert len(store.read()) == 2
