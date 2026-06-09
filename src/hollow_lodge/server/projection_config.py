from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse

from hollow_lodge.server.projection_postgres_store import PostgresProjectionStore
from hollow_lodge.server.projection_store import SqliteProjectionStore


PROJECTION_DATABASE_URL_ENV = "HOLLOW_LODGE_PROJECTION_DATABASE_URL"
PLATFORM_DATABASE_URL_ENV = "DATABASE_URL"
REQUIRE_POSTGRES_PROJECTION_ENV = "HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION"
PROJECTION_READS_ENV = "HOLLOW_LODGE_PROJECTION_READS"
PROJECTION_READ_SURFACE_ENVS = {
    "actions": "HOLLOW_LODGE_ACTION_PROJECTION_READS",
    "artifacts": "HOLLOW_LODGE_ARTIFACT_PROJECTION_READS",
    "chat": "HOLLOW_LODGE_CHAT_PROJECTION_READS",
    "contract_board": "HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS",
    "crew_legacy": "HOLLOW_LODGE_CREW_LEGACY_PROJECTION_READS",
    "crew_summary": "HOLLOW_LODGE_CREW_SUMMARY_PROJECTION_READS",
    "deals": "HOLLOW_LODGE_DEAL_PROJECTION_READS",
    "pending_decisions": "HOLLOW_LODGE_PENDING_DECISION_PROJECTION_READS",
    "proof_dossiers": "HOLLOW_LODGE_PROOF_DOSSIER_PROJECTION_READS",
    "visible_events": "HOLLOW_LODGE_VISIBLE_EVENT_PROJECTION_READS",
}


def projection_store_from_env(root: Path) -> SqliteProjectionStore | PostgresProjectionStore:
    database_url, database_url_env = _projection_database_url_from_env()
    require_postgres = _env_flag(REQUIRE_POSTGRES_PROJECTION_ENV)
    if not database_url:
        if require_postgres:
            raise RuntimeError(
                f"{REQUIRE_POSTGRES_PROJECTION_ENV}=1 requires "
                f"{PROJECTION_DATABASE_URL_ENV}=postgresql://... or "
                f"{PLATFORM_DATABASE_URL_ENV}=postgresql://..."
            )
        return SqliteProjectionStore(root / "server-projections.sqlite3")

    parsed = urlparse(database_url)
    scheme = parsed.scheme.lower()
    if scheme in {"sqlite", "sqlite3"}:
        if require_postgres:
            raise RuntimeError(
                f"{REQUIRE_POSTGRES_PROJECTION_ENV}=1 rejects SQLite projection "
                f"URLs; configured URL: {_redact_database_url(database_url)}"
            )
        return SqliteProjectionStore(_sqlite_path_from_url(database_url))

    if scheme in {"postgres", "postgresql"}:
        return PostgresProjectionStore(
            database_url,
            database_url_env=database_url_env or PROJECTION_DATABASE_URL_ENV,
        )

    raise RuntimeError(
        "Unsupported projection database URL scheme "
        f"{scheme!r}; expected sqlite:/// or postgresql://. "
        f"Configured URL: {_redact_database_url(database_url)}"
    )


def _projection_database_url_from_env() -> tuple[str, str | None]:
    explicit_url = os.environ.get(PROJECTION_DATABASE_URL_ENV, "").strip()
    if explicit_url:
        return explicit_url, PROJECTION_DATABASE_URL_ENV
    platform_url = os.environ.get(PLATFORM_DATABASE_URL_ENV, "").strip()
    if platform_url:
        return platform_url, PLATFORM_DATABASE_URL_ENV
    return "", None


def projection_read_enabled(surface_env: str) -> bool:
    if os.environ.get(surface_env) is not None:
        return _env_flag(surface_env)
    return _env_flag(PROJECTION_READS_ENV)


def projection_read_diagnostics() -> dict[str, object]:
    return {
        "global_enabled": _env_flag(PROJECTION_READS_ENV),
        "surfaces": {
            surface: projection_read_enabled(env_name)
            for surface, env_name in PROJECTION_READ_SURFACE_ENVS.items()
        },
    }


def _env_flag(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if value in {"", "0", "false", "no", "off"}:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    raise RuntimeError(
        f"{name} must be one of 1, true, yes, on, 0, false, no, or off; "
        f"got {value!r}"
    )


def _sqlite_path_from_url(database_url: str) -> Path:
    parsed = urlparse(database_url)
    if parsed.netloc not in {"", "localhost"}:
        raise RuntimeError(
            "SQLite projection database URLs must use a local file path; "
            f"configured URL: {_redact_database_url(database_url)}"
        )
    path = unquote(parsed.path)
    if not path:
        raise RuntimeError("SQLite projection database URL must include a file path")
    return Path(path).resolve()


def _redact_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if parsed.password is None:
        return database_url
    netloc = parsed.hostname or ""
    if parsed.username:
        netloc = f"{parsed.username}:***@{netloc}"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))
