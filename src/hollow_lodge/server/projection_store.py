from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from hollow_lodge.domain.events import GameEvent
from hollow_lodge.server.projections import (
    contract_board_from_events,
    crew_summaries_from_events,
)


SCHEMA_VERSION = "1"


class SqliteProjectionStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def rebuild(self, events: list[GameEvent]) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        board = contract_board_from_events(events)
        crew_summaries = crew_summaries_from_events(events)
        last_sequence = events[-1].sequence if events else 0
        with sqlite3.connect(self.path) as connection:
            self._ensure_schema(connection)
            connection.execute("delete from contract_board")
            connection.execute("delete from crew_summary")
            for contract in board["contracts"]:
                connection.execute(
                    """
                    insert into contract_board (
                        contract_id,
                        campaign_id,
                        lifecycle_status,
                        phase_status,
                        payload_json,
                        updated_sequence
                    ) values (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        contract["contract_id"],
                        contract["campaign_id"],
                        contract.get("lifecycle_status", "active"),
                        contract.get("phase", {}).get("status", "active"),
                        json.dumps(contract, sort_keys=True, separators=(",", ":")),
                        last_sequence,
                    ),
                )
            for crew_id, crew in crew_summaries.items():
                connection.execute(
                    """
                    insert into crew_summary (
                        crew_id,
                        member_count,
                        payload_json,
                        updated_sequence
                    ) values (?, ?, ?, ?)
                    """,
                    (
                        crew_id,
                        crew["member_count"],
                        json.dumps(crew, sort_keys=True, separators=(",", ":")),
                        last_sequence,
                    ),
                )
            self._set_meta(connection, "schema_version", SCHEMA_VERSION)
            self._set_meta(connection, "last_sequence", str(last_sequence))
            self._set_meta(connection, "contract_count", str(len(board["contracts"])))
            self._set_meta(connection, "crew_count", str(len(crew_summaries)))
            self._set_meta(
                connection,
                "campaign_json",
                json.dumps(
                    board["campaign"],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            connection.commit()
        return self.diagnostics(authoritative_last_sequence=last_sequence)

    def diagnostics(self, *, authoritative_last_sequence: int | None = None) -> dict[str, Any]:
        exists = self.path.exists()
        if not exists:
            authoritative = authoritative_last_sequence or 0
            return {
                "path": str(self.path),
                "exists": False,
                "status": "not_created",
                "schema_version": int(SCHEMA_VERSION),
                "last_sequence": 0,
                "authoritative_last_sequence": authoritative,
                "lag": authoritative,
                "contract_count": 0,
                "crew_count": 0,
            }
        try:
            with sqlite3.connect(self.path) as connection:
                self._ensure_schema(connection)
                meta = dict(
                    connection.execute("select key, value from projection_meta").fetchall()
                )
                contract_count = connection.execute(
                    "select count(*) from contract_board"
                ).fetchone()[0]
                crew_count = connection.execute(
                    "select count(*) from crew_summary"
                ).fetchone()[0]
        except sqlite3.DatabaseError:
            authoritative = authoritative_last_sequence or 0
            return {
                "path": str(self.path),
                "exists": True,
                "status": "unavailable",
                "schema_version": int(SCHEMA_VERSION),
                "last_sequence": 0,
                "authoritative_last_sequence": authoritative,
                "lag": authoritative,
                "contract_count": 0,
                "crew_count": 0,
            }
        last_sequence = int(meta.get("last_sequence", "0"))
        authoritative = (
            last_sequence
            if authoritative_last_sequence is None
            else authoritative_last_sequence
        )
        lag = max(0, authoritative - last_sequence)
        return {
            "path": str(self.path),
            "exists": True,
            "status": "stale" if lag else "available",
            "schema_version": int(meta.get("schema_version", SCHEMA_VERSION)),
            "last_sequence": last_sequence,
            "authoritative_last_sequence": authoritative,
            "lag": lag,
            "contract_count": int(meta.get("contract_count", str(contract_count))),
            "crew_count": int(meta.get("crew_count", str(crew_count))),
        }

    def read_contract_board(self) -> dict[str, Any]:
        with sqlite3.connect(self.path) as connection:
            self._ensure_schema(connection)
            meta = dict(
                connection.execute("select key, value from projection_meta").fetchall()
            )
            rows = connection.execute(
                "select payload_json from contract_board order by contract_id"
            ).fetchall()
        return {
            "campaign": json.loads(meta["campaign_json"]) if "campaign_json" in meta else None,
            "contracts": [json.loads(row[0]) for row in rows],
        }

    def read_crew_summary(self, crew_id: str) -> dict[str, Any]:
        with sqlite3.connect(self.path) as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "select payload_json from crew_summary where crew_id = ?",
                (crew_id,),
            ).fetchone()
        if row is None:
            raise KeyError(crew_id)
        return json.loads(row[0])

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            create table if not exists projection_meta (
                key text primary key,
                value text not null
            )
            """
        )
        connection.execute(
            """
            create table if not exists contract_board (
                contract_id text primary key,
                campaign_id text not null,
                lifecycle_status text not null,
                phase_status text not null,
                payload_json text not null,
                updated_sequence integer not null
            )
            """
        )
        connection.execute(
            """
            create index if not exists idx_contract_board_campaign
            on contract_board (campaign_id, lifecycle_status, phase_status)
            """
        )
        connection.execute(
            """
            create table if not exists crew_summary (
                crew_id text primary key,
                member_count integer not null,
                payload_json text not null,
                updated_sequence integer not null
            )
            """
        )

    def _set_meta(self, connection: sqlite3.Connection, key: str, value: str) -> None:
        connection.execute(
            """
            insert into projection_meta (key, value)
            values (?, ?)
            on conflict(key) do update set value = excluded.value
            """,
            (key, value),
        )
