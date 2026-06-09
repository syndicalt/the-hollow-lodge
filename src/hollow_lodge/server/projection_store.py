from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from hollow_lodge.domain.deals import deal_rows_from_events
from hollow_lodge.domain.events import GameEvent
from hollow_lodge.server.projections import (
    artifact_visibility_from_events,
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
        artifact_visibility = artifact_visibility_from_events(events)
        deals = deal_rows_from_events(events)
        visible_events = [
            event
            for event in events
            if _event_is_player_projectable(event)
        ]
        last_sequence = events[-1].sequence if events else 0
        with sqlite3.connect(self.path) as connection:
            self._ensure_schema(connection)
            connection.execute("delete from contract_board")
            connection.execute("delete from crew_summary")
            connection.execute("delete from artifact_surface")
            connection.execute("delete from artifact_edge")
            connection.execute("delete from artifact_scoped_surface")
            connection.execute("delete from deal_surface")
            connection.execute("delete from visible_event_surface")
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
            for artifact_id, artifact in artifact_visibility["public_artifacts"].items():
                connection.execute(
                    """
                    insert into artifact_surface (
                        artifact_id,
                        contract_id,
                        payload_json,
                        updated_sequence
                    ) values (?, ?, ?, ?)
                    """,
                    (
                        artifact_id,
                        artifact["contract_id"],
                        json.dumps(artifact, sort_keys=True, separators=(",", ":")),
                        last_sequence,
                    ),
                )
            for edge in artifact_visibility["public_edges"].values():
                connection.execute(
                    """
                    insert into artifact_edge (
                        source_id,
                        target_id,
                        relation,
                        payload_json,
                        updated_sequence
                    ) values (?, ?, ?, ?, ?)
                    """,
                    (
                        edge["source_id"],
                        edge["target_id"],
                        edge["relation"],
                        json.dumps(edge, sort_keys=True, separators=(",", ":")),
                        last_sequence,
                    ),
                )
            for scoped in artifact_visibility["scoped_surfaces"]:
                connection.execute(
                    """
                    insert into artifact_scoped_surface (
                        artifact_id,
                        payload_json,
                        visibility_json,
                        updated_sequence
                    ) values (?, ?, ?, ?)
                    """,
                    (
                        scoped["artifact_id"],
                        json.dumps(
                            scoped["surface"],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        json.dumps(
                            scoped["visibility"],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        last_sequence,
                    ),
                )
            for deal in deals:
                connection.execute(
                    """
                    insert into deal_surface (
                        deal_id,
                        proposer_crew_id,
                        recipient_crew_id,
                        status,
                        payload_json,
                        updated_sequence
                    ) values (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        deal["deal_id"],
                        deal["proposer_crew_id"],
                        deal["recipient_crew_id"],
                        deal["status"],
                        json.dumps(deal, sort_keys=True, separators=(",", ":")),
                        last_sequence,
                    ),
                )
            for event in visible_events:
                payload = event.model_dump(mode="json")
                connection.execute(
                    """
                    insert into visible_event_surface (
                        event_id,
                        sequence,
                        event_type,
                        payload_json,
                        visibility_json,
                        updated_sequence
                    ) values (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.sequence,
                        event.type,
                        json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        json.dumps(
                            payload["visibility"],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        last_sequence,
                    ),
                )
            self._set_meta(connection, "schema_version", SCHEMA_VERSION)
            self._set_meta(connection, "last_sequence", str(last_sequence))
            self._set_meta(connection, "contract_count", str(len(board["contracts"])))
            self._set_meta(connection, "crew_count", str(len(crew_summaries)))
            self._set_meta(connection, "deal_count", str(len(deals)))
            self._set_meta(connection, "visible_event_count", str(len(visible_events)))
            self._set_meta(
                connection,
                "public_artifact_count",
                str(len(artifact_visibility["public_artifacts"])),
            )
            self._set_meta(
                connection,
                "scoped_artifact_count",
                str(len(artifact_visibility["scoped_surfaces"])),
            )
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
                "deal_count": 0,
                "visible_event_count": 0,
                "public_artifact_count": 0,
                "scoped_artifact_count": 0,
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
                deal_count = connection.execute(
                    "select count(*) from deal_surface"
                ).fetchone()[0]
                visible_event_count = connection.execute(
                    "select count(*) from visible_event_surface"
                ).fetchone()[0]
                public_artifact_count = connection.execute(
                    "select count(*) from artifact_surface"
                ).fetchone()[0]
                scoped_artifact_count = connection.execute(
                    "select count(*) from artifact_scoped_surface"
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
                "deal_count": 0,
                "visible_event_count": 0,
                "public_artifact_count": 0,
                "scoped_artifact_count": 0,
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
            "deal_count": int(meta.get("deal_count", str(deal_count))),
            "visible_event_count": int(
                meta.get("visible_event_count", str(visible_event_count))
            ),
            "public_artifact_count": int(
                meta.get("public_artifact_count", str(public_artifact_count))
            ),
            "scoped_artifact_count": int(
                meta.get("scoped_artifact_count", str(scoped_artifact_count))
            ),
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

    def read_visible_artifacts(
        self,
        player_id: str,
        *,
        crew_ids: list[str] | tuple[str, ...] = (),
    ) -> dict[str, Any]:
        principals = {("player", player_id)}
        principals.update(("crew", crew_id) for crew_id in crew_ids)
        with sqlite3.connect(self.path) as connection:
            self._ensure_schema(connection)
            artifact_rows = connection.execute(
                "select payload_json from artifact_surface order by artifact_id"
            ).fetchall()
            edge_rows = connection.execute(
                """
                select payload_json
                from artifact_edge
                order by source_id, target_id, relation
                """
            ).fetchall()
            scoped_rows = connection.execute(
                """
                select artifact_id, payload_json, visibility_json
                from artifact_scoped_surface
                order by artifact_id
                """
            ).fetchall()
        artifacts_by_id = {
            json.loads(row[0])["artifact_id"]: json.loads(row[0])
            for row in artifact_rows
        }
        for _, payload_json, visibility_json in scoped_rows:
            visibility = json.loads(visibility_json)
            if _visibility_matches(visibility, principals):
                artifact = json.loads(payload_json)
                artifacts_by_id[artifact["artifact_id"]] = artifact
        return {
            "contract_id": "multiple",
            "artifacts": [
                artifacts_by_id[artifact_id]
                for artifact_id in sorted(artifacts_by_id)
            ],
            "edges": [json.loads(row[0]) for row in edge_rows],
        }

    def read_visible_deals(
        self,
        player_id: str,
        *,
        crew_ids: list[str] | tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        del player_id
        crew_set = set(crew_ids)
        if not crew_set:
            return []
        with sqlite3.connect(self.path) as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                select payload_json
                from deal_surface
                where proposer_crew_id in (
                    select value from json_each(?)
                )
                or recipient_crew_id in (
                    select value from json_each(?)
                )
                order by deal_id
                """,
                (
                    json.dumps(sorted(crew_set), separators=(",", ":")),
                    json.dumps(sorted(crew_set), separators=(",", ":")),
                ),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def read_visible_events(
        self,
        player_id: str,
        *,
        crew_ids: list[str] | tuple[str, ...] = (),
        since_sequence: int = 0,
    ) -> list[dict[str, Any]]:
        principals = {("player", player_id)}
        principals.update(("crew", crew_id) for crew_id in crew_ids)
        with sqlite3.connect(self.path) as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                select payload_json, visibility_json
                from visible_event_surface
                where sequence > ?
                order by sequence
                """,
                (since_sequence,),
            ).fetchall()
        visible: list[dict[str, Any]] = []
        for payload_json, visibility_json in rows:
            visibility = json.loads(visibility_json)
            if _visibility_matches(visibility, principals):
                visible.append(json.loads(payload_json))
        return visible

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
        connection.execute(
            """
            create table if not exists artifact_surface (
                artifact_id text primary key,
                contract_id text not null,
                payload_json text not null,
                updated_sequence integer not null
            )
            """
        )
        connection.execute(
            """
            create table if not exists artifact_edge (
                source_id text not null,
                target_id text not null,
                relation text not null,
                payload_json text not null,
                updated_sequence integer not null,
                primary key (source_id, target_id, relation)
            )
            """
        )
        connection.execute(
            """
            create table if not exists artifact_scoped_surface (
                artifact_id text primary key,
                payload_json text not null,
                visibility_json text not null,
                updated_sequence integer not null
            )
            """
        )
        connection.execute(
            """
            create table if not exists deal_surface (
                deal_id text primary key,
                proposer_crew_id text not null,
                recipient_crew_id text not null,
                status text not null,
                payload_json text not null,
                updated_sequence integer not null
            )
            """
        )
        connection.execute(
            """
            create index if not exists idx_deal_surface_proposer
            on deal_surface (proposer_crew_id, status)
            """
        )
        connection.execute(
            """
            create index if not exists idx_deal_surface_recipient
            on deal_surface (recipient_crew_id, status)
            """
        )
        connection.execute(
            """
            create table if not exists visible_event_surface (
                event_id text primary key,
                sequence integer not null,
                event_type text not null,
                payload_json text not null,
                visibility_json text not null,
                updated_sequence integer not null
            )
            """
        )
        connection.execute(
            """
            create index if not exists idx_visible_event_surface_sequence
            on visible_event_surface (sequence)
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


def _visibility_matches(
    visibility: dict[str, Any],
    principals: set[tuple[str, str]],
) -> bool:
    for entry in visibility.get("principals", visibility.get("entries", [])):
        kind = entry.get("kind")
        principal_id = entry.get("id")
        if kind == "public":
            return True
        if principal_id is not None and (kind, principal_id) in principals:
            return True
    return False


def _event_is_player_projectable(event: GameEvent) -> bool:
    return any(
        entry.kind in {"public", "player", "crew"}
        for entry in event.visibility.entries
    )
