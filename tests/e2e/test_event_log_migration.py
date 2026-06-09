import importlib.util
import json
from pathlib import Path

import pytest

import hollow_lodge.client.event_log_migration as event_log_migration
from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.eventlog.jsonl_store import EventLogIntegrityError, JsonlEventStore


def _load_migration_module():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "migrate_event_log_to_postgres.py"
    )
    spec = importlib.util.spec_from_file_location("migrate_event_log_to_postgres", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_event_log_migration_dry_run_accepts_admin_export(tmp_path):
    module = _load_migration_module()
    store = JsonlEventStore(tmp_path / "server-events.jsonl")
    store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    source = tmp_path / "export.json"
    source.write_text(
        json.dumps(
            {"events": [event.model_dump(mode="json") for event in store.read()]},
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = module.migrate_event_log(
        source=source,
        database_url="",
        dry_run=True,
    )

    assert result == {"dry_run": True, "event_count": 1}


def test_event_log_manifest_summarizes_validated_chain_without_payloads(tmp_path):
    store = JsonlEventStore(tmp_path / "server-events.jsonl")
    store.append_command(
        event_type="action.submitted",
        actor_id="player_ada",
        visibility=EventVisibility.players(["player_ada"]),
        payload={"intent": "secret inspection plan"},
        idempotency_key="submit-action-1",
    )
    source = tmp_path / "export.json"
    source.write_text(
        json.dumps(
            {"events": [event.model_dump(mode="json") for event in store.read()]},
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    manifest = event_log_migration.create_event_log_manifest(source)

    [event] = store.read()
    assert manifest["manifest_type"] == "hollow_lodge_event_log_backup"
    assert manifest["manifest_version"] == 1
    assert manifest["event_count"] == 1
    assert manifest["first_sequence"] == 1
    assert manifest["last_sequence"] == 1
    assert manifest["first_event_hash"] == event.event_hash
    assert manifest["last_event_hash"] == event.event_hash
    assert manifest["schema_versions"] == [1]
    assert len(manifest["event_hash_chain_sha256"]) == 64
    assert "secret inspection plan" not in json.dumps(manifest)
    assert "player_ada" not in json.dumps(manifest)
    assert "submit-action-1" not in json.dumps(manifest)


def test_event_log_migration_imports_jsonl_without_leaking_password(
    tmp_path,
    monkeypatch,
):
    module = _load_migration_module()
    store = JsonlEventStore(tmp_path / "server-events.jsonl")
    store.append_command(
        event_type="action.submitted",
        actor_id="player_ada",
        visibility=EventVisibility.players(["player_ada"]),
        payload={"intent": "inspect the ledger"},
        idempotency_key="submit-action-1",
    )
    source = tmp_path / "events.jsonl"
    source.write_text(
        "\n".join(
            json.dumps(event.model_dump(mode="json"), sort_keys=True)
            for event in store.read()
        )
        + "\n",
        encoding="utf-8",
    )
    fake = FakePostgresConnector()
    monkeypatch.setattr(
        event_log_migration.PostgresEventStore,
        "_connect",
        lambda self: fake(),
    )

    result = module.migrate_event_log(
        source=source,
        database_url="postgresql://user:secret@example.com:5432/hollow_lodge",
    )

    assert result == {
        "dry_run": False,
        "event_count": 1,
        "database_url": "postgresql://user:***@example.com:5432/hollow_lodge",
    }
    assert "secret" not in str(result)


def test_event_log_migration_rejects_corrupted_chain(tmp_path):
    module = _load_migration_module()
    store = JsonlEventStore(tmp_path / "server-events.jsonl")
    store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    row = store.read()[0].model_dump(mode="json")
    row["payload"]["contract_id"] = "tampered"
    source = tmp_path / "export.json"
    source.write_text(json.dumps({"events": [row]}), encoding="utf-8")

    with pytest.raises(EventLogIntegrityError, match="invalid event hash"):
        module.migrate_event_log(source=source, database_url="", dry_run=True)


class FakePostgresConnector:
    def __init__(self):
        self.event_rows: list[str] = []
        self.connections: list[FakePostgresConnection] = []

    def __call__(self) -> "FakePostgresConnection":
        connection = FakePostgresConnection(self)
        self.connections.append(connection)
        return connection


class FakePostgresConnection:
    def __init__(self, connector: FakePostgresConnector):
        self.connector = connector
        self.statements: list[tuple[str, tuple]] = []
        self.committed = False

    def __enter__(self) -> "FakePostgresConnection":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> "FakePostgresCursor":
        self.statements.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if normalized.startswith("select event_json from event_log"):
            return FakePostgresCursor(rows=[(row,) for row in self.connector.event_rows])
        if normalized.startswith("insert into event_log"):
            self.connector.event_rows.append(params[-1])
            return FakePostgresCursor()
        return FakePostgresCursor()

    def commit(self) -> None:
        self.committed = True


class FakePostgresCursor:
    def __init__(self, *, rows: list[tuple] | None = None):
        self._rows = rows or []

    def fetchall(self) -> list[tuple]:
        return self._rows
