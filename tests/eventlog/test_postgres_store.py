import pytest
from fastapi.testclient import TestClient

from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.eventlog.jsonl_store import (
    EventLogIntegrityError,
    IdempotencyConflictError,
    JsonlEventStore,
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
    }
    assert "secret" not in str(diagnostics)


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
        if normalized.startswith("select event_json from event_log"):
            return FakePostgresCursor(rows=[(row,) for row in self.connector.event_rows])
        if normalized.startswith("insert into event_log"):
            self.connector.event_rows.append(params[-1])
            return FakePostgresCursor()
        if normalized.startswith("select count(*) from event_log"):
            return FakePostgresCursor(row=(len(self.connector.event_rows),))
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
