from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse

from hollow_lodge.server.projection_store import SqliteProjectionStore


PROJECTION_DATABASE_URL_ENV = "HOLLOW_LODGE_PROJECTION_DATABASE_URL"


def projection_store_from_env(root: Path) -> SqliteProjectionStore:
    database_url = os.environ.get(PROJECTION_DATABASE_URL_ENV, "").strip()
    if not database_url:
        return SqliteProjectionStore(root / "server-projections.sqlite3")

    parsed = urlparse(database_url)
    scheme = parsed.scheme.lower()
    if scheme in {"sqlite", "sqlite3"}:
        return SqliteProjectionStore(_sqlite_path_from_url(database_url))

    if scheme in {"postgres", "postgresql"}:
        raise RuntimeError(
            "Postgres projection backend is not implemented yet; unset "
            f"{PROJECTION_DATABASE_URL_ENV} or use a sqlite:/// URL. "
            f"Configured URL: {_redact_database_url(database_url)}"
        )

    raise RuntimeError(
        "Unsupported projection database URL scheme "
        f"{scheme!r}; expected sqlite:/// or postgresql://. "
        f"Configured URL: {_redact_database_url(database_url)}"
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
