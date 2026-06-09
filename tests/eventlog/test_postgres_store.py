import json

import pytest
from fastapi.testclient import TestClient

from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.eventlog.jsonl_store import (
    EventLogIntegrityError,
    IdempotencyConflictError,
    JsonlEventStore,
    event_hash_chain_digest,
)
from hollow_lodge.eventlog.postgres_store import PostgresEventStore
from hollow_lodge.eventlog.visibility import Principal
from hollow_lodge.server.app import create_app


def test_postgres_event_store_appends_reads_and_preserves_hash_chain(monkeypatch):
    fake = FakePostgresConnector()
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())
    store = PostgresEventStore("postgresql://user:secret@example.com:5432/hollow_lodge")

    first = store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    second = store.append(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.crews(["crew_ember"]),
        payload={"contract_id": "contract_false_finger"},
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert second.previous_hash == first.event_hash
    assert [event.sequence for event in store.read(start_sequence=2)] == [2]
    assert store.verify_integrity().event_count == 2
    assert any(
        "pg_advisory_xact_lock" in sql
        for connection in fake.connections
        for sql, _ in connection.statements
    )


def test_postgres_event_store_replays_idempotent_commands(monkeypatch):
    fake = FakePostgresConnector()
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())
    store = PostgresEventStore("postgresql://user:secret@example.com:5432/hollow_lodge")

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
    assert len(store.read()) == 1


def test_postgres_event_store_append_uses_metadata_head_without_full_replay(monkeypatch):
    fake = FakePostgresConnector()
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())
    store = PostgresEventStore("postgresql://user:secret@example.com:5432/hollow_lodge")

    first = store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    second = store.append(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.crews(["crew_ember"]),
        payload={"contract_id": "contract_false_finger"},
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert second.previous_hash == first.event_hash
    append_statements = [
        " ".join(sql.lower().split())
        for connection in fake.connections
        for sql, _ in connection.statements
    ]
    assert any(
        statement.startswith("select sequence, event_id, event_hash, previous_hash")
        for statement in append_statements
    )
    assert not any(
        statement == "select event_json from event_log order by sequence"
        for statement in append_statements
    )


def test_postgres_event_store_idempotent_replay_validates_metadata_chain(monkeypatch):
    fake = FakePostgresConnector()
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())
    store = PostgresEventStore("postgresql://user:secret@example.com:5432/hollow_lodge")
    store.append_command(
        event_type="action.submitted",
        actor_id="player_ada",
        visibility=EventVisibility.players(["player_ada"]),
        payload={"intent": "inspect the ledger"},
        idempotency_key="submit-action-1",
    )
    corrupted = json.loads(fake.event_rows[0])
    corrupted["previous_hash"] = "broken-chain"
    fake.event_rows[0] = json.dumps(corrupted)

    with pytest.raises(EventLogIntegrityError, match="hash chain break"):
        store.append_command(
            event_type="action.submitted",
            actor_id="player_ada",
            visibility=EventVisibility.players(["player_ada"]),
            payload={"intent": "inspect the ledger"},
            idempotency_key="submit-action-1",
        )


def test_postgres_event_store_append_rejects_corrupted_head_payload(monkeypatch):
    fake = FakePostgresConnector()
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())
    store = PostgresEventStore("postgresql://user:secret@example.com:5432/hollow_lodge")
    store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    corrupted = json.loads(fake.event_rows[0])
    corrupted["payload"]["contract_id"] = "tampered"
    fake.event_rows[0] = json.dumps(corrupted)

    with pytest.raises(EventLogIntegrityError, match="invalid event hash"):
        store.append(
            event_type="contract.board.published",
            actor_id="server",
            visibility=EventVisibility.crews(["crew_ember"]),
            payload={"contract_id": "contract_false_finger"},
        )


def test_postgres_event_store_idempotent_replay_rejects_corrupted_payload(
    monkeypatch,
):
    fake = FakePostgresConnector()
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())
    store = PostgresEventStore("postgresql://user:secret@example.com:5432/hollow_lodge")
    store.append_command(
        event_type="action.submitted",
        actor_id="player_ada",
        visibility=EventVisibility.players(["player_ada"]),
        payload={"intent": "inspect the ledger"},
        idempotency_key="submit-action-1",
    )
    corrupted = json.loads(fake.event_rows[0])
    corrupted["payload"]["intent"] = "tampered"
    fake.event_rows[0] = json.dumps(corrupted)

    with pytest.raises(EventLogIntegrityError, match="invalid event hash"):
        store.append_command(
            event_type="action.submitted",
            actor_id="player_ada",
            visibility=EventVisibility.players(["player_ada"]),
            payload={"intent": "inspect the ledger"},
            idempotency_key="submit-action-1",
        )


def test_postgres_event_store_rejects_idempotency_conflicts(monkeypatch):
    fake = FakePostgresConnector()
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())
    store = PostgresEventStore("postgresql://user:secret@example.com:5432/hollow_lodge")
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


def test_postgres_event_store_filters_by_visibility(monkeypatch):
    fake = FakePostgresConnector()
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())
    store = PostgresEventStore("postgresql://user:secret@example.com:5432/hollow_lodge")
    visible = store.append(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.crews(["crew_ember"]),
        payload={"contract_id": "contract_false_finger"},
    )
    store.append(
        event_type="contract.hidden_truth.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"truth": "false_finger"},
    )

    assert store.read_for_principal(Principal.crew("crew_ember")) == [visible]


def test_postgres_event_store_diagnostics_redact_database_url(monkeypatch):
    fake = FakePostgresConnector()
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())
    store = PostgresEventStore(
        "postgresql://user:secret@example.com:5432/hollow_lodge",
        database_url_env="HOLLOW_LODGE_EVENT_DATABASE_URL",
    )

    diagnostics = store.diagnostics()

    assert diagnostics == {
        "backend": "postgres",
        "database_url": "postgresql://user:***@example.com:5432/hollow_lodge",
        "database_url_env": "HOLLOW_LODGE_EVENT_DATABASE_URL",
        "exists": True,
        "status": "available",
        "event_count": 0,
        "last_sequence": None,
        "last_event_hash": None,
        "event_hash_chain_sha256": event_hash_chain_digest([]),
    }
    assert "secret" not in str(diagnostics)


def test_postgres_event_store_diagnostics_include_chain_digest(monkeypatch):
    fake = FakePostgresConnector()
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())
    store = PostgresEventStore("postgresql://user:secret@example.com:5432/hollow_lodge")
    first = store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    second = store.append(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.crews(["crew_ember"]),
        payload={"contract_id": "contract_false_finger"},
    )

    diagnostics = store.diagnostics()

    assert diagnostics["event_count"] == 2
    assert diagnostics["last_sequence"] == 2
    assert diagnostics["last_event_hash"] == second.event_hash
    assert diagnostics["event_hash_chain_sha256"] == event_hash_chain_digest(
        [first, second]
    )
    assert "contract_false_finger" not in str(diagnostics)
    diagnostic_connection = fake.connections[-1]
    assert not any(
        "select event_json from event_log" in " ".join(sql.lower().split())
        for sql, _ in diagnostic_connection.statements
    )


def test_postgres_event_store_diagnostics_reports_unavailable_for_chain_break(
    monkeypatch,
):
    fake = FakePostgresConnector()
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())
    store = PostgresEventStore("postgresql://user:secret@example.com:5432/hollow_lodge")
    first = store.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    second = store.append(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.crews(["crew_ember"]),
        payload={"contract_id": "contract_false_finger"},
    )
    corrupted = json.loads(fake.event_rows[-1])
    corrupted["previous_hash"] = "broken-chain"
    corrupted["event_hash"] = second.event_hash
    fake.event_rows[-1] = json.dumps(corrupted)

    diagnostics = store.diagnostics()

    assert first.event_hash != "broken-chain"
    assert diagnostics["status"] == "unavailable"
    assert diagnostics["event_count"] == 0
    assert diagnostics["last_sequence"] is None
    assert diagnostics["event_hash_chain_sha256"] is None


def test_app_selects_postgres_event_store_from_explicit_event_database_url(
    tmp_path,
    monkeypatch,
):
    fake = FakePostgresConnector()
    monkeypatch.setenv(
        "HOLLOW_LODGE_EVENT_DATABASE_URL",
        "postgresql://user:secret@example.com:5432/hollow_lodge",
    )
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())

    response = TestClient(create_app(data_dir=tmp_path)).get("/diagnostics")

    event_log = response.json()["data"]["event_log"]
    assert event_log["backend"] == "postgres"
    assert event_log["database_url"] == (
        "postgresql://user:***@example.com:5432/hollow_lodge"
    )
    assert event_log["database_url_env"] == "HOLLOW_LODGE_EVENT_DATABASE_URL"
    assert "secret" not in response.text


def test_app_does_not_use_platform_database_url_for_authoritative_events(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("HOLLOW_LODGE_EVENT_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://platform:secret@example.com:5432/hollow_lodge",
    )
    monkeypatch.setenv(
        "HOLLOW_LODGE_PROJECTION_DATABASE_URL",
        f"sqlite:///{tmp_path / 'projection.sqlite3'}",
    )

    response = TestClient(create_app(data_dir=tmp_path)).get("/diagnostics")

    event_log = response.json()["data"]["event_log"]
    assert event_log["backend"] == "jsonl"
    assert event_log["path"] == str(tmp_path / "server-events.jsonl")
    assert "secret" not in response.text


def test_require_postgres_event_log_rejects_missing_event_database_url(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG", "1")
    monkeypatch.delenv("HOLLOW_LODGE_EVENT_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        create_app(data_dir=tmp_path)

    message = str(exc_info.value)
    assert "HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG=1 requires" in message
    assert "HOLLOW_LODGE_EVENT_DATABASE_URL=postgresql://..." in message
    assert "platform" not in message
    assert "secret" not in message


def test_require_postgres_event_log_does_not_accept_platform_database_url(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG", "true")
    monkeypatch.delenv("HOLLOW_LODGE_EVENT_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://platform:secret@example.com:5432/hollow_lodge",
    )
    monkeypatch.setenv(
        "HOLLOW_LODGE_PROJECTION_DATABASE_URL",
        f"sqlite:///{tmp_path / 'projection.sqlite3'}",
    )

    with pytest.raises(RuntimeError) as exc_info:
        create_app(data_dir=tmp_path)

    message = str(exc_info.value)
    assert "HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG=1 requires" in message
    assert "HOLLOW_LODGE_EVENT_DATABASE_URL=postgresql://..." in message
    assert "platform" not in message
    assert "secret" not in message


def test_require_postgres_event_log_allows_explicit_postgres_backend(
    tmp_path,
    monkeypatch,
):
    fake = FakePostgresConnector()
    monkeypatch.setenv("HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG", "yes")
    monkeypatch.setenv(
        "HOLLOW_LODGE_EVENT_DATABASE_URL",
        "postgresql://user:secret@example.com:5432/hollow_lodge",
    )
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())

    response = TestClient(create_app(data_dir=tmp_path)).get("/diagnostics")

    event_log = response.json()["data"]["event_log"]
    assert event_log["backend"] == "postgres"
    assert event_log["database_url_env"] == "HOLLOW_LODGE_EVENT_DATABASE_URL"
    assert "secret" not in response.text


def test_require_postgres_event_log_rejects_non_postgres_url_without_secret_leak(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG", "on")
    monkeypatch.setenv(
        "HOLLOW_LODGE_EVENT_DATABASE_URL",
        "mysql://user:secret@example.com:3306/hollow_lodge",
    )

    with pytest.raises(RuntimeError) as exc_info:
        create_app(data_dir=tmp_path)

    message = str(exc_info.value)
    assert "rejects non-Postgres event log URLs" in message
    assert "mysql://user:***@example.com:3306/hollow_lodge" in message
    assert "secret" not in message


def test_require_postgres_event_log_rejects_invalid_flag_value(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG", "sometimes")

    with pytest.raises(RuntimeError) as exc_info:
        create_app(data_dir=tmp_path)

    assert "HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG must be one of" in str(
        exc_info.value
    )


def test_postgres_event_store_imports_validated_events_exactly(tmp_path, monkeypatch):
    source = JsonlEventStore(tmp_path / "events.jsonl")
    first = source.append_command(
        event_type="action.submitted",
        actor_id="player_ada",
        visibility=EventVisibility.players(["player_ada"]),
        payload={"intent": "inspect the ledger"},
        idempotency_key="submit-action-1",
    )
    second = source.append(
        event_type="contract.board.published",
        actor_id="server",
        visibility=EventVisibility.crews(["crew_ember"]),
        payload={"contract_id": "contract_false_finger"},
    )
    fake = FakePostgresConnector()
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())
    destination = PostgresEventStore(
        "postgresql://user:secret@example.com:5432/hollow_lodge"
    )

    report = destination.import_events(source.read())

    assert report.ok is True
    assert report.event_count == 2
    imported = destination.read()
    assert imported == [first, second]
    assert imported[0].event_id == first.event_id
    assert imported[0].event_hash == first.event_hash
    assert imported[0].idempotency_key == "submit-action-1"


def test_postgres_event_store_import_refuses_non_empty_destination(
    tmp_path,
    monkeypatch,
):
    source = JsonlEventStore(tmp_path / "events.jsonl")
    source.append(
        event_type="contract.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"contract_id": "contract_false_finger"},
    )
    fake = FakePostgresConnector()
    monkeypatch.setattr(PostgresEventStore, "_connect", lambda self: fake())
    destination = PostgresEventStore(
        "postgresql://user:secret@example.com:5432/hollow_lodge"
    )
    destination.append(
        event_type="other.seeded",
        actor_id="server",
        visibility=EventVisibility.server_only(),
        payload={"n": 1},
    )

    with pytest.raises(EventLogIntegrityError, match="destination event log is not empty"):
        destination.import_events(source.read())


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
        if normalized.startswith(
            "select event_json from event_log where idempotency_key"
        ):
            key = params[0]
            rows = [
                (row,)
                for row in self.connector.event_rows
                if json.loads(row).get("idempotency_key") == key
            ]
            return FakePostgresCursor(row=rows[0] if rows else None)
        if normalized.startswith("select event_json from event_log"):
            if "where sequence" in normalized:
                sequence = params[0]
                for row in self.connector.event_rows:
                    payload = json.loads(row)
                    if payload["sequence"] == sequence:
                        return FakePostgresCursor(row=(row,))
                return FakePostgresCursor(row=None)
            return FakePostgresCursor(rows=[(row,) for row in self.connector.event_rows])
        if normalized.startswith("select sequence, event_id, event_hash, previous_hash"):
            return FakePostgresCursor(
                rows=[
                    (
                        payload["sequence"],
                        payload["event_id"],
                        payload["event_hash"],
                        payload["previous_hash"],
                    )
                    for payload in (
                        json.loads(row) for row in self.connector.event_rows
                    )
                ]
            )
        if normalized.startswith("insert into event_log"):
            self.connector.event_rows.append(params[-1])
            return FakePostgresCursor()
        if normalized.startswith("select count(*) from event_log"):
            return FakePostgresCursor(row=(len(self.connector.event_rows),))
        if normalized.startswith("select sequence, event_hash from event_log"):
            if not self.connector.event_rows:
                return FakePostgresCursor(row=None)
            latest = json.loads(self.connector.event_rows[-1])
            return FakePostgresCursor(
                row=(latest["sequence"], latest["event_hash"])
            )
        return FakePostgresCursor()

    def commit(self) -> None:
        self.committed = True


class FakePostgresCursor:
    def __init__(self, *, rows: list[tuple] | None = None, row: tuple | None = None):
        self._rows = rows or []
        self._row = row

    def fetchall(self) -> list[tuple]:
        return self._rows

    def fetchone(self) -> tuple | None:
        return self._row
