from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlparse, urlunparse

from hollow_lodge.server.production_postgres import production_postgres_enabled


REGISTRATION_REPLAY_SCOPE = "registration"
INVITE_REPLAY_SCOPE = "invite"
IDENTITY_REPLAY_DATABASE_URL_ENV = "HOLLOW_LODGE_OPERATIONAL_DATABASE_URL"
PLATFORM_DATABASE_URL_ENV = "DATABASE_URL"
REQUIRE_POSTGRES_OPERATIONAL_ENV = "HOLLOW_LODGE_REQUIRE_POSTGRES_OPERATIONAL"


class IdentityReplayStore(Protocol):
    def remember_registration_token(
        self,
        *,
        idempotency_key: str,
        token: str,
        created_at: datetime,
        ttl: timedelta,
    ) -> None:
        ...

    def load_registration_tokens(
        self,
        *,
        now: datetime,
        ttl: timedelta,
    ) -> dict[str, str]:
        ...

    def remember_invite_code(
        self,
        *,
        idempotency_key: str,
        invite_code: str,
        created_at: datetime,
        ttl: timedelta,
    ) -> None:
        ...

    def load_invite_codes(
        self,
        *,
        now: datetime,
        ttl: timedelta,
    ) -> dict[str, str]:
        ...

    def diagnostics(self) -> dict[str, object]:
        ...


class JsonFileIdentityReplayStore:
    backend = "jsonl-sidecar"

    def __init__(self, replay_dir: str | Path):
        self.registration_replay_path = (
            Path(replay_dir) / "server-events.registration-replays.json"
        )
        self.invite_replay_path = Path(replay_dir) / "server-events.invite-replays.json"

    def remember_registration_token(
        self,
        *,
        idempotency_key: str,
        token: str,
        created_at: datetime,
        ttl: timedelta,
    ) -> None:
        replay_tokens = self.load_registration_tokens(
            now=created_at,
            ttl=ttl,
        )
        replay_tokens[idempotency_key] = token
        self._write_secret_file(
            self.registration_replay_path,
            {
                key: {
                    "created_at": created_at.isoformat().replace("+00:00", "Z"),
                    "token": value,
                }
                for key, value in replay_tokens.items()
            },
        )

    def load_registration_tokens(
        self,
        *,
        now: datetime,
        ttl: timedelta,
    ) -> dict[str, str]:
        return self._load_secret_file(
            self.registration_replay_path,
            now=now,
            ttl=ttl,
            secret_key="token",
        )

    def remember_invite_code(
        self,
        *,
        idempotency_key: str,
        invite_code: str,
        created_at: datetime,
        ttl: timedelta,
    ) -> None:
        replay_invites = self.load_invite_codes(
            now=created_at,
            ttl=ttl,
        )
        replay_invites[idempotency_key] = invite_code
        self._write_secret_file(
            self.invite_replay_path,
            {
                key: {
                    "created_at": created_at.isoformat().replace("+00:00", "Z"),
                    "invite_code": value,
                }
                for key, value in replay_invites.items()
            },
        )

    def load_invite_codes(
        self,
        *,
        now: datetime,
        ttl: timedelta,
    ) -> dict[str, str]:
        return self._load_secret_file(
            self.invite_replay_path,
            now=now,
            ttl=ttl,
            secret_key="invite_code",
        )

    def diagnostics(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "registration_replay_path": str(self.registration_replay_path),
            "invite_replay_path": str(self.invite_replay_path),
        }

    def _load_secret_file(
        self,
        path: Path,
        *,
        now: datetime,
        ttl: timedelta,
        secret_key: str,
    ) -> dict[str, str]:
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        valid: dict[str, str] = {}
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            created_at = datetime.fromisoformat(
                str(value["created_at"]).replace("Z", "+00:00")
            )
            if now - created_at <= ttl:
                valid[str(key)] = str(value[secret_key])
        return valid

    def _write_secret_file(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        os.chmod(path, 0o600)


class SqliteIdentityReplayStore:
    backend = "sqlite"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._ensure_schema()

    def remember_registration_token(
        self,
        *,
        idempotency_key: str,
        token: str,
        created_at: datetime,
        ttl: timedelta,
    ) -> None:
        self._put_secret(
            scope=REGISTRATION_REPLAY_SCOPE,
            idempotency_key=idempotency_key,
            secret=token,
            created_at=created_at,
            ttl=ttl,
        )

    def load_registration_tokens(
        self,
        *,
        now: datetime,
        ttl: timedelta,
    ) -> dict[str, str]:
        return self._load_secrets(
            scope=REGISTRATION_REPLAY_SCOPE,
            now=now,
            ttl=ttl,
        )

    def remember_invite_code(
        self,
        *,
        idempotency_key: str,
        invite_code: str,
        created_at: datetime,
        ttl: timedelta,
    ) -> None:
        self._put_secret(
            scope=INVITE_REPLAY_SCOPE,
            idempotency_key=idempotency_key,
            secret=invite_code,
            created_at=created_at,
            ttl=ttl,
        )

    def load_invite_codes(
        self,
        *,
        now: datetime,
        ttl: timedelta,
    ) -> dict[str, str]:
        return self._load_secrets(
            scope=INVITE_REPLAY_SCOPE,
            now=now,
            ttl=ttl,
        )

    def diagnostics(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "path": str(self.path),
            "database_url_env": IDENTITY_REPLAY_DATABASE_URL_ENV,
        }

    def _put_secret(
        self,
        *,
        scope: str,
        idempotency_key: str,
        secret: str,
        created_at: datetime,
        ttl: timedelta,
    ) -> None:
        import sqlite3

        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                delete from identity_replay_secrets
                where scope = ? and created_at < ?
                """,
                (scope, _format_instant(created_at - ttl)),
            )
            connection.execute(
                """
                insert into identity_replay_secrets (
                    scope, idempotency_key, secret, created_at
                )
                values (?, ?, ?, ?)
                on conflict(scope, idempotency_key)
                do update set secret = excluded.secret, created_at = excluded.created_at
                """,
                (
                    scope,
                    idempotency_key,
                    secret,
                    _format_instant(created_at),
                ),
            )

    def _load_secrets(
        self,
        *,
        scope: str,
        now: datetime,
        ttl: timedelta,
    ) -> dict[str, str]:
        import sqlite3

        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                select idempotency_key, secret, created_at
                from identity_replay_secrets
                where scope = ?
                """,
                (scope,),
            ).fetchall()
        valid: dict[str, str] = {}
        for idempotency_key, secret, created_at in rows:
            if now - _parse_instant(str(created_at)) <= ttl:
                valid[str(idempotency_key)] = str(secret)
        return valid

    def _ensure_schema(self) -> None:
        import sqlite3

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                create table if not exists identity_replay_secrets (
                    scope text not null,
                    idempotency_key text not null,
                    secret text not null,
                    created_at text not null,
                    primary key(scope, idempotency_key)
                )
                """
            )


class PostgresIdentityReplayStore:
    backend = "postgres"

    def __init__(
        self,
        database_url: str,
        *,
        database_url_env: str = IDENTITY_REPLAY_DATABASE_URL_ENV,
    ):
        self.database_url = database_url
        self.safe_database_url = _redact_database_url(database_url)
        self.database_url_env = database_url_env
        self._ensure_schema()

    def remember_registration_token(
        self,
        *,
        idempotency_key: str,
        token: str,
        created_at: datetime,
        ttl: timedelta,
    ) -> None:
        self._put_secret(
            scope=REGISTRATION_REPLAY_SCOPE,
            idempotency_key=idempotency_key,
            secret=token,
            created_at=created_at,
            ttl=ttl,
        )

    def load_registration_tokens(
        self,
        *,
        now: datetime,
        ttl: timedelta,
    ) -> dict[str, str]:
        return self._load_secrets(
            scope=REGISTRATION_REPLAY_SCOPE,
            now=now,
            ttl=ttl,
        )

    def remember_invite_code(
        self,
        *,
        idempotency_key: str,
        invite_code: str,
        created_at: datetime,
        ttl: timedelta,
    ) -> None:
        self._put_secret(
            scope=INVITE_REPLAY_SCOPE,
            idempotency_key=idempotency_key,
            secret=invite_code,
            created_at=created_at,
            ttl=ttl,
        )

    def load_invite_codes(
        self,
        *,
        now: datetime,
        ttl: timedelta,
    ) -> dict[str, str]:
        return self._load_secrets(
            scope=INVITE_REPLAY_SCOPE,
            now=now,
            ttl=ttl,
        )

    def diagnostics(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "database_url": self.safe_database_url,
            "database_url_env": self.database_url_env,
        }

    def _put_secret(
        self,
        *,
        scope: str,
        idempotency_key: str,
        secret: str,
        created_at: datetime,
        ttl: timedelta,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                delete from identity_replay_secrets
                where scope = %s and created_at < %s
                """,
                (scope, _format_instant(created_at - ttl)),
            )
            connection.execute(
                """
                insert into identity_replay_secrets (
                    scope, idempotency_key, secret, created_at
                )
                values (%s, %s, %s, %s)
                on conflict(scope, idempotency_key)
                do update set secret = excluded.secret, created_at = excluded.created_at
                """,
                (
                    scope,
                    idempotency_key,
                    secret,
                    _format_instant(created_at),
                ),
            )

    def _load_secrets(
        self,
        *,
        scope: str,
        now: datetime,
        ttl: timedelta,
    ) -> dict[str, str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                select idempotency_key, secret, created_at
                from identity_replay_secrets
                where scope = %s
                """,
                (scope,),
            ).fetchall()
        valid: dict[str, str] = {}
        for idempotency_key, secret, created_at in rows:
            if now - _parse_instant(str(created_at)) <= ttl:
                valid[str(idempotency_key)] = str(secret)
        return valid

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                create table if not exists identity_replay_secrets (
                    scope text not null,
                    idempotency_key text not null,
                    secret text not null,
                    created_at text not null,
                    primary key(scope, idempotency_key)
                )
                """
            )

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - dependency is required
            raise RuntimeError(
                "Postgres identity replay store requires the psycopg package"
            ) from exc
        return psycopg.connect(self.database_url)


def identity_replay_store_from_env(root: Path) -> IdentityReplayStore:
    database_url, database_url_env = _identity_replay_database_url_from_env()
    require_postgres = (
        _env_flag(REQUIRE_POSTGRES_OPERATIONAL_ENV) or production_postgres_enabled()
    )
    if not database_url:
        if require_postgres:
            raise RuntimeError(
                f"{REQUIRE_POSTGRES_OPERATIONAL_ENV}=1 requires "
                f"{IDENTITY_REPLAY_DATABASE_URL_ENV}=postgresql://... or "
                f"{PLATFORM_DATABASE_URL_ENV}=postgresql://..."
            )
        return JsonFileIdentityReplayStore(root)

    parsed = urlparse(database_url)
    scheme = parsed.scheme.lower()
    if scheme in {"sqlite", "sqlite3"}:
        if require_postgres:
            raise RuntimeError(
                f"{REQUIRE_POSTGRES_OPERATIONAL_ENV}=1 rejects SQLite operational "
                f"URLs; configured URL: {_redact_database_url(database_url)}"
            )
        return SqliteIdentityReplayStore(_sqlite_path_from_url(database_url))
    if scheme in {"postgres", "postgresql"}:
        return PostgresIdentityReplayStore(
            database_url,
            database_url_env=database_url_env or IDENTITY_REPLAY_DATABASE_URL_ENV,
        )
    if require_postgres:
        raise RuntimeError(
            f"{REQUIRE_POSTGRES_OPERATIONAL_ENV}=1 rejects non-Postgres "
            "operational URLs; configured URL: "
            f"{_redact_database_url(database_url)}"
        )
    raise RuntimeError(
        "Unsupported operational database URL scheme "
        f"{scheme!r}; expected sqlite:/// or postgresql://. "
        f"Configured URL: {_redact_database_url(database_url)}"
    )


def _identity_replay_database_url_from_env() -> tuple[str, str | None]:
    explicit_url = os.environ.get(IDENTITY_REPLAY_DATABASE_URL_ENV, "").strip()
    if explicit_url:
        return explicit_url, IDENTITY_REPLAY_DATABASE_URL_ENV
    platform_url = os.environ.get(PLATFORM_DATABASE_URL_ENV, "").strip()
    if platform_url:
        return platform_url, PLATFORM_DATABASE_URL_ENV
    return "", None


def identity_replay_store_guard_diagnostics() -> dict[str, object]:
    return {
        "require_postgres_operational": (
            _env_flag(REQUIRE_POSTGRES_OPERATIONAL_ENV)
            or production_postgres_enabled()
        ),
    }


def _format_instant(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _sqlite_path_from_url(database_url: str) -> Path:
    parsed = urlparse(database_url)
    if parsed.netloc not in {"", "localhost"}:
        raise RuntimeError(
            "SQLite operational database URLs must use a local file path; "
            f"configured URL: {_redact_database_url(database_url)}"
        )
    path = unquote(parsed.path)
    if not path:
        raise RuntimeError("SQLite operational database URL must include a file path")
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
