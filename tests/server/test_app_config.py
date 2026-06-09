from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app
from hollow_lodge.server.projection_config import (
    PROJECTION_READ_SURFACE_ENVS,
    projection_read_enabled,
)
from hollow_lodge.server.projection_store import SCHEMA_VERSION


def test_default_data_dir_can_be_set_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_DATA_DIR", str(tmp_path / "data"))

    app = create_app()

    assert app.state.event_store.path == tmp_path / "data" / "server-events.jsonl"


def test_default_app_keeps_artifact_and_deal_services_lazy(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_DATA_DIR", str(tmp_path / "data"))

    app = create_app()

    assert not hasattr(app.state, "artifact_service")
    assert not hasattr(app.state, "deal_service")
    assert app.state.chat_service._artifact_service is None
    assert app.state.action_service._artifact_service is None


def test_health_response_stays_backward_compatible(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_diagnostics_reports_safe_operational_status(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ORACLE_PROVIDER", "openai")
    monkeypatch.delenv("HOLLOW_LODGE_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("HOLLOW_LODGE_DATA_DIR", str(tmp_path))

    client = TestClient(create_app(invite_codes=["secret-invite"]))

    response = client.get("/diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["server"]["version"] == "0.1.0"
    assert body["data"]["directory"] == str(tmp_path)
    assert body["data"]["event_log"]["backend"] == "jsonl"
    assert body["data"]["event_log"]["path"] == str(tmp_path / "server-events.jsonl")
    assert body["data"]["event_log"]["exists"] is False
    assert body["data"]["event_log"]["status"] == "not_created"
    assert body["data"]["event_log"]["event_count"] == 0
    assert body["data"]["event_log"]["last_sequence"] is None
    assert body["data"]["event_log"]["last_event_hash"] is None
    assert len(body["data"]["event_log"]["event_hash_chain_sha256"]) == 64
    assert body["data"]["storage_guards"] == {
        "require_postgres_event_log": False,
        "require_postgres_projection": False,
    }
    assert body["data"]["projection_refresh"] == {
        "status": "ok",
        "last_context": "startup",
        "last_success_sequence": 0,
        "failure_count": 0,
        "last_failure": None,
    }
    assert body["oracle"]["configured_provider"] == "openai"
    assert body["oracle"]["active_provider"] == "deterministic"
    assert body["oracle"]["ready"] is False
    assert body["oracle"]["fallback_active"] is True
    assert body["oracle"]["warnings"] == [
        "openai provider requested but HOLLOW_LODGE_OPENAI_API_KEY is not set; using deterministic fallback"
    ]
    assert "secret-invite" not in response.text


def test_diagnostics_reports_existing_event_log(tmp_path):
    event_log = tmp_path / "server-events.jsonl"
    event_log.write_text("", encoding="utf-8")
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/diagnostics")

    assert response.status_code == 200
    event_log_diagnostics = response.json()["data"]["event_log"]
    assert event_log_diagnostics["backend"] == "jsonl"
    assert event_log_diagnostics["path"] == str(event_log)
    assert event_log_diagnostics["exists"] is True
    assert event_log_diagnostics["status"] == "available"
    assert event_log_diagnostics["event_count"] > 0
    assert event_log_diagnostics["last_sequence"] == event_log_diagnostics["event_count"]
    assert isinstance(event_log_diagnostics["last_event_hash"], str)
    assert len(event_log_diagnostics["event_hash_chain_sha256"]) == 64


def test_projection_store_defaults_to_sqlite_backend(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))

    projection = client.get("/diagnostics").json()["data"]["projection_db"]

    assert client.app.state.projection_store.backend == "sqlite"
    assert projection["backend"] == "sqlite"
    assert projection["path"] == str(tmp_path / "server-projections.sqlite3")


def test_sqlite_projection_database_url_selects_explicit_path(tmp_path, monkeypatch):
    projection_path = tmp_path / "configured" / "projection.sqlite3"
    monkeypatch.setenv(
        "HOLLOW_LODGE_PROJECTION_DATABASE_URL",
        f"sqlite:///{projection_path}",
    )

    client = TestClient(create_app(data_dir=tmp_path))

    projection = client.get("/diagnostics").json()["data"]["projection_db"]
    assert client.app.state.projection_store.backend == "sqlite"
    assert client.app.state.projection_store.path == projection_path
    assert projection["path"] == str(projection_path)


def test_postgres_projection_database_url_selects_postgres_backend(
    tmp_path,
    monkeypatch,
):
    from hollow_lodge.server.projection_postgres_store import PostgresProjectionStore

    monkeypatch.setenv(
        "HOLLOW_LODGE_PROJECTION_DATABASE_URL",
        "postgresql://user:secret@example.com:5432/hollow_lodge",
    )
    fake = FakePostgresConnector(
        meta_rows=[
            ("schema_version", SCHEMA_VERSION),
            ("last_sequence", "100"),
            ("contract_count", "1"),
            ("crew_count", "0"),
            ("deal_count", "0"),
            ("crew_legacy_count", "0"),
            ("visible_event_count", "1"),
            ("public_artifact_count", "2"),
            ("scoped_artifact_count", "0"),
        ]
    )
    monkeypatch.setattr(PostgresProjectionStore, "_connect", lambda self: fake())

    client = TestClient(create_app(data_dir=tmp_path))

    projection = client.get("/diagnostics").json()["data"]["projection_db"]
    all_sql = "\n".join(
        sql for connection in fake.connections for sql, _ in connection.statements
    ).lower()

    assert client.app.state.projection_store.backend == "postgres"
    assert projection["backend"] == "postgres"
    assert projection["database_url"] == "postgresql://user:***@example.com:5432/hollow_lodge"
    assert projection["database_url_env"] == "HOLLOW_LODGE_PROJECTION_DATABASE_URL"
    assert projection["status"] == "available"
    assert projection["lag"] == 0
    assert "secret" not in str(projection)
    assert "create table if not exists projection_meta" in all_sql
    assert "create table if not exists projection_schema_migrations" in all_sql
    assert "insert into projection_schema_migrations" in all_sql
    assert "insert into contract_board" in all_sql
    assert any(connection.committed for connection in fake.connections)


def test_platform_database_url_selects_postgres_projection_backend(
    tmp_path,
    monkeypatch,
):
    from hollow_lodge.server.projection_postgres_store import PostgresProjectionStore

    monkeypatch.delenv("HOLLOW_LODGE_PROJECTION_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://platform:secret@example.com:5432/hollow_lodge",
    )
    fake = FakePostgresConnector(
        meta_rows=[
            ("schema_version", SCHEMA_VERSION),
            ("last_sequence", "100"),
            ("contract_count", "1"),
            ("crew_count", "0"),
            ("deal_count", "0"),
            ("crew_legacy_count", "0"),
            ("visible_event_count", "1"),
            ("public_artifact_count", "2"),
            ("scoped_artifact_count", "0"),
        ]
    )
    monkeypatch.setattr(PostgresProjectionStore, "_connect", lambda self: fake())

    client = TestClient(create_app(data_dir=tmp_path))

    projection = client.get("/diagnostics").json()["data"]["projection_db"]
    assert client.app.state.projection_store.backend == "postgres"
    assert projection["backend"] == "postgres"
    assert projection["database_url"] == (
        "postgresql://platform:***@example.com:5432/hollow_lodge"
    )
    assert projection["database_url_env"] == "DATABASE_URL"
    assert "secret" not in str(projection)


def test_explicit_projection_database_url_overrides_platform_database_url(
    tmp_path,
    monkeypatch,
):
    from hollow_lodge.server.projection_postgres_store import PostgresProjectionStore

    monkeypatch.setenv(
        "HOLLOW_LODGE_PROJECTION_DATABASE_URL",
        "postgresql://explicit:secret@example.com:5432/hollow_lodge",
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://platform:secret@example.com:5432/other",
    )
    fake = FakePostgresConnector(
        meta_rows=[
            ("schema_version", SCHEMA_VERSION),
            ("last_sequence", "100"),
            ("contract_count", "1"),
            ("crew_count", "0"),
            ("deal_count", "0"),
            ("crew_legacy_count", "0"),
            ("visible_event_count", "1"),
            ("public_artifact_count", "2"),
            ("scoped_artifact_count", "0"),
        ]
    )
    monkeypatch.setattr(PostgresProjectionStore, "_connect", lambda self: fake())

    client = TestClient(create_app(data_dir=tmp_path))

    projection = client.get("/diagnostics").json()["data"]["projection_db"]
    assert projection["database_url"] == (
        "postgresql://explicit:***@example.com:5432/hollow_lodge"
    )
    assert projection["database_url_env"] == "HOLLOW_LODGE_PROJECTION_DATABASE_URL"


def test_require_postgres_projection_rejects_missing_database_url(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION", "1")
    monkeypatch.delenv("HOLLOW_LODGE_PROJECTION_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        create_app(data_dir=tmp_path)

    assert "HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION=1 requires" in str(exc_info.value)
    assert "HOLLOW_LODGE_PROJECTION_DATABASE_URL=postgresql://..." in str(
        exc_info.value
    )
    assert "DATABASE_URL=postgresql://..." in str(exc_info.value)


def test_require_postgres_projection_accepts_platform_database_url(
    tmp_path,
    monkeypatch,
):
    from hollow_lodge.server.projection_postgres_store import PostgresProjectionStore

    monkeypatch.setenv("HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION", "1")
    monkeypatch.delenv("HOLLOW_LODGE_PROJECTION_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://platform:secret@example.com:5432/hollow_lodge",
    )
    fake = FakePostgresConnector(
        meta_rows=[
            ("schema_version", SCHEMA_VERSION),
            ("last_sequence", "100"),
            ("contract_count", "1"),
            ("crew_count", "0"),
            ("deal_count", "0"),
            ("crew_legacy_count", "0"),
            ("visible_event_count", "1"),
            ("public_artifact_count", "2"),
            ("scoped_artifact_count", "0"),
        ]
    )
    monkeypatch.setattr(PostgresProjectionStore, "_connect", lambda self: fake())

    client = TestClient(create_app(data_dir=tmp_path))

    projection = client.get("/diagnostics").json()["data"]["projection_db"]
    assert projection["backend"] == "postgres"
    assert projection["database_url_env"] == "DATABASE_URL"


def test_require_postgres_projection_rejects_sqlite_url_without_secret_leak(
    tmp_path,
    monkeypatch,
):
    projection_path = tmp_path / "projection.sqlite3"
    monkeypatch.setenv("HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION", "true")
    monkeypatch.setenv(
        "HOLLOW_LODGE_PROJECTION_DATABASE_URL",
        f"sqlite:///{projection_path}",
    )

    with pytest.raises(RuntimeError) as exc_info:
        create_app(data_dir=tmp_path)

    message = str(exc_info.value)
    assert "rejects SQLite projection URLs" in message
    assert str(projection_path) in message


def test_require_postgres_projection_allows_postgres_backend(
    tmp_path,
    monkeypatch,
):
    from hollow_lodge.server.projection_postgres_store import PostgresProjectionStore

    monkeypatch.setenv("HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION", "yes")
    monkeypatch.setenv(
        "HOLLOW_LODGE_PROJECTION_DATABASE_URL",
        "postgresql://user:secret@example.com:5432/hollow_lodge",
    )
    fake = FakePostgresConnector(
        meta_rows=[
            ("schema_version", SCHEMA_VERSION),
            ("last_sequence", "100"),
            ("contract_count", "1"),
            ("crew_count", "0"),
            ("deal_count", "0"),
            ("crew_legacy_count", "0"),
            ("visible_event_count", "1"),
            ("public_artifact_count", "2"),
            ("scoped_artifact_count", "0"),
        ]
    )
    monkeypatch.setattr(PostgresProjectionStore, "_connect", lambda self: fake())

    client = TestClient(create_app(data_dir=tmp_path))

    projection = client.get("/diagnostics").json()["data"]["projection_db"]
    assert client.app.state.projection_store.backend == "postgres"
    assert projection["backend"] == "postgres"
    assert projection["database_url"] == "postgresql://user:***@example.com:5432/hollow_lodge"


def test_require_postgres_projection_rejects_invalid_flag_value(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION", "sometimes")

    with pytest.raises(RuntimeError) as exc_info:
        create_app(data_dir=tmp_path)

    assert "HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION must be one of" in str(
        exc_info.value
    )


def test_global_projection_read_flag_enables_all_surfaces(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_PROJECTION_READS", "1")

    client = TestClient(create_app(data_dir=tmp_path))

    projection_reads = client.get("/diagnostics").json()["data"]["projection_reads"]
    assert projection_reads["global_enabled"] is True
    assert projection_reads["surfaces"]
    assert set(projection_reads["surfaces"]) == set(PROJECTION_READ_SURFACE_ENVS)
    assert all(projection_reads["surfaces"].values())
    assert projection_read_enabled("HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS") is True


def test_surface_projection_read_flag_overrides_global_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_PROJECTION_READS", "1")
    monkeypatch.setenv("HOLLOW_LODGE_CHAT_PROJECTION_READS", "0")

    client = TestClient(create_app(data_dir=tmp_path))

    projection_reads = client.get("/diagnostics").json()["data"]["projection_reads"]
    assert projection_reads["global_enabled"] is True
    assert projection_reads["surfaces"]["chat"] is False
    assert projection_reads["surfaces"]["contract_board"] is True
    assert projection_read_enabled("HOLLOW_LODGE_CHAT_PROJECTION_READS") is False


def test_projection_read_flag_rejects_invalid_values(monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_PROJECTION_READS", "sometimes")

    with pytest.raises(RuntimeError) as exc_info:
        projection_read_enabled("HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS")

    assert "HOLLOW_LODGE_PROJECTION_READS must be one of" in str(exc_info.value)


def test_server_docker_image_installs_openai_client_for_openai_oracle():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert '"openai>=' in dockerfile
    assert '"psycopg[binary]>=' in dockerfile


class FakePostgresConnector:
    def __init__(self, *, meta_rows: list[tuple[str, str]]):
        self.meta_rows = meta_rows
        self.connections: list[FakePostgresConnection] = []

    def __call__(self) -> "FakePostgresConnection":
        connection = FakePostgresConnection(meta_rows=self.meta_rows)
        self.connections.append(connection)
        return connection


class FakePostgresConnection:
    def __init__(self, *, meta_rows: list[tuple[str, str]]):
        self.meta_rows = meta_rows
        self.statements: list[tuple[str, tuple]] = []
        self.committed = False

    def __enter__(self) -> "FakePostgresConnection":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> "FakePostgresCursor":
        self.statements.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "select key, value from projection_meta" in normalized:
            return FakePostgresCursor(rows=self.meta_rows)
        if normalized.startswith("select count(*)"):
            return FakePostgresCursor(row=(0,))
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
