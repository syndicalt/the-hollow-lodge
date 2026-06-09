from __future__ import annotations

from copy import deepcopy
import json
import sqlite3
from pathlib import Path
from typing import Any

from hollow_lodge.domain.deals import deal_rows_from_events
from hollow_lodge.domain.events import GameEvent
from hollow_lodge.domain.proofs import ProofDossier
from hollow_lodge.server.projections import (
    apply_contract_unlock_status,
    artifact_visibility_from_events,
    contract_board_from_events,
    crew_legacy_from_contracts,
    crew_summaries_from_events,
    unlocked_actionable_contracts,
)
from hollow_lodge.server.pending_decisions import pending_decisions_for_player
from hollow_lodge.server.rumors import SAFE_RUMOR_FIELDS


SCHEMA_VERSION = "6"
PROJECTION_SCHEMA_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("1", "initial projection read models"),
    ("2", "proof dossier projection read model"),
    ("3", "chat message projection read model"),
    ("4", "pending decision projection read model"),
    ("5", "current action projection read model"),
    ("6", "visible rumor projection read model"),
)


class SqliteProjectionStore:
    backend = "sqlite"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def rebuild(self, events: list[GameEvent]) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = build_projection_snapshot(events)
        board = snapshot["board"]
        crew_summaries = snapshot["crew_summaries"]
        artifact_visibility = snapshot["artifact_visibility"]
        deals = snapshot["deals"]
        crew_legacies = snapshot["crew_legacies"]
        proof_dossiers = snapshot["proof_dossiers"]
        chat_messages = snapshot["chat_messages"]
        actions_by_crew = snapshot["actions_by_crew"]
        pending_decisions = snapshot["pending_decisions"]
        visible_rumors_by_crew = snapshot["visible_rumors_by_crew"]
        visible_events = snapshot["visible_events"]
        last_sequence = snapshot["last_sequence"]
        with sqlite3.connect(self.path) as connection:
            self._ensure_schema(connection)
            connection.execute("delete from contract_board")
            connection.execute("delete from crew_summary")
            connection.execute("delete from artifact_surface")
            connection.execute("delete from artifact_edge")
            connection.execute("delete from artifact_scoped_surface")
            connection.execute("delete from deal_surface")
            connection.execute("delete from visible_event_surface")
            connection.execute("delete from crew_legacy")
            connection.execute("delete from proof_dossier")
            connection.execute("delete from chat_message_surface")
            connection.execute("delete from action_surface")
            connection.execute("delete from pending_decision_surface")
            connection.execute("delete from visible_rumor_surface")
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
                visibility_json = json.dumps(
                    scoped["visibility"],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                connection.execute(
                    """
                    insert into artifact_scoped_surface (
                        artifact_id,
                        scope_key,
                        payload_json,
                        visibility_json,
                        updated_sequence
                    ) values (?, ?, ?, ?, ?)
                    on conflict(artifact_id, scope_key) do update set
                        payload_json = excluded.payload_json,
                        visibility_json = excluded.visibility_json,
                        updated_sequence = excluded.updated_sequence
                    """,
                    (
                        scoped["artifact_id"],
                        _artifact_scope_key(scoped["visibility"]),
                        json.dumps(
                            scoped["surface"],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        visibility_json,
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
            for crew_id, legacy in crew_legacies.items():
                connection.execute(
                    """
                    insert into crew_legacy (
                        crew_id,
                        payload_json,
                        updated_sequence
                    ) values (?, ?, ?)
                    """,
                    (
                        crew_id,
                        json.dumps(legacy, sort_keys=True, separators=(",", ":")),
                        last_sequence,
                    ),
                )
            for crew_id, dossier in proof_dossiers.items():
                connection.execute(
                    """
                    insert into proof_dossier (
                        crew_id,
                        packet_lead_player_id,
                        payload_json,
                        updated_sequence
                    ) values (?, ?, ?, ?)
                    """,
                    (
                        crew_id,
                        dossier["packet_lead_player_id"],
                        json.dumps(dossier, sort_keys=True, separators=(",", ":")),
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
            for chat_event in chat_messages:
                payload = _chat_event_surface(chat_event)
                message = payload["payload"]
                connection.execute(
                    """
                    insert into chat_message_surface (
                        event_id,
                        message_id,
                        sequence,
                        kind,
                        conversation_id,
                        payload_json,
                        visibility_json,
                        updated_sequence
                    ) values (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chat_event.event_id,
                        message["message_id"],
                        chat_event.sequence,
                        message["kind"],
                        _chat_conversation_id(message),
                        json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        json.dumps(
                            payload["visibility"],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        last_sequence,
                    ),
                )
            action_count = 0
            for crew_id, actions in actions_by_crew.items():
                for action in actions:
                    action_count += 1
                    connection.execute(
                        """
                        insert into action_surface (
                            action_id,
                            crew_id,
                            actor_player_id,
                            status,
                            payload_json,
                            updated_sequence
                        ) values (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            action["action_id"],
                            crew_id,
                            action["actor_player_id"],
                            action["status"],
                            json.dumps(
                                action,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            last_sequence,
                        ),
                    )
            for row in pending_decisions:
                connection.execute(
                    """
                    insert into pending_decision_surface (
                        player_id,
                        crew_id,
                        decision_index,
                        kind,
                        payload_json,
                        updated_sequence
                    ) values (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["player_id"],
                        row["crew_id"],
                        row["decision_index"],
                        row["kind"],
                        json.dumps(
                            row["decision"],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        last_sequence,
                    ),
                )
            rumor_count = 0
            for crew_id, rumors in visible_rumors_by_crew.items():
                for rumor_index, rumor in enumerate(rumors):
                    rumor_count += 1
                    connection.execute(
                        """
                        insert into visible_rumor_surface (
                            crew_id,
                            rumor_id,
                            rumor_index,
                            payload_json,
                            updated_sequence
                        ) values (?, ?, ?, ?, ?)
                        """,
                        (
                            crew_id,
                            rumor["rumor_id"],
                            rumor_index,
                            json.dumps(
                                rumor,
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
            self._set_meta(connection, "crew_legacy_count", str(len(crew_legacies)))
            self._set_meta(connection, "proof_dossier_count", str(len(proof_dossiers)))
            self._set_meta(connection, "chat_message_count", str(len(chat_messages)))
            self._set_meta(connection, "action_count", str(action_count))
            self._set_meta(
                connection,
                "pending_decision_count",
                str(len(pending_decisions)),
            )
            self._set_meta(connection, "visible_rumor_count", str(rumor_count))
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
                "backend": self.backend,
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
                "crew_legacy_count": 0,
                "proof_dossier_count": 0,
                "chat_message_count": 0,
                "action_count": 0,
                "pending_decision_count": 0,
                "visible_rumor_count": 0,
                "schema_migration_count": 0,
                "latest_schema_migration": None,
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
                crew_legacy_count = connection.execute(
                    "select count(*) from crew_legacy"
                ).fetchone()[0]
                proof_dossier_count = connection.execute(
                    "select count(*) from proof_dossier"
                ).fetchone()[0]
                chat_message_count = connection.execute(
                    "select count(*) from chat_message_surface"
                ).fetchone()[0]
                action_count = connection.execute(
                    "select count(*) from action_surface"
                ).fetchone()[0]
                pending_decision_count = connection.execute(
                    "select count(*) from pending_decision_surface"
                ).fetchone()[0]
                visible_rumor_count = connection.execute(
                    "select count(*) from visible_rumor_surface"
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
                schema_migration_count = connection.execute(
                    "select count(*) from projection_schema_migrations"
                ).fetchone()[0]
                latest_schema_migration_row = connection.execute(
                    """
                    select applied_version
                    from projection_schema_migrations
                    order by cast(applied_version as integer) desc
                    limit 1
                    """
                ).fetchone()
        except sqlite3.DatabaseError:
            authoritative = authoritative_last_sequence or 0
            return {
                "backend": self.backend,
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
                "crew_legacy_count": 0,
                "proof_dossier_count": 0,
                "chat_message_count": 0,
                "action_count": 0,
                "pending_decision_count": 0,
                "visible_rumor_count": 0,
                "schema_migration_count": 0,
                "latest_schema_migration": None,
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
            "backend": self.backend,
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
            "crew_legacy_count": int(
                meta.get("crew_legacy_count", str(crew_legacy_count))
            ),
            "proof_dossier_count": int(
                meta.get("proof_dossier_count", str(proof_dossier_count))
            ),
            "chat_message_count": int(
                meta.get("chat_message_count", str(chat_message_count))
            ),
            "action_count": int(meta.get("action_count", str(action_count))),
            "pending_decision_count": int(
                meta.get("pending_decision_count", str(pending_decision_count))
            ),
            "visible_rumor_count": int(
                meta.get("visible_rumor_count", str(visible_rumor_count))
            ),
            "schema_migration_count": int(schema_migration_count),
            "latest_schema_migration": (
                latest_schema_migration_row[0]
                if latest_schema_migration_row is not None
                else None
            ),
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

    def read_crew_legacy(self, crew_id: str) -> dict[str, Any]:
        with sqlite3.connect(self.path) as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "select payload_json from crew_legacy where crew_id = ?",
                (crew_id,),
            ).fetchone()
        if row is None:
            raise KeyError(crew_id)
        return json.loads(row[0])

    def read_proof_dossier(self, crew_id: str) -> dict[str, Any]:
        with sqlite3.connect(self.path) as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "select payload_json from proof_dossier where crew_id = ?",
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
                order by artifact_id, scope_key
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

    def read_visible_chat_events(
        self,
        player_id: str,
        *,
        crew_ids: list[str] | tuple[str, ...] = (),
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        principals = {("player", player_id)}
        principals.update(("crew", crew_id) for crew_id in crew_ids)
        query = """
            select payload_json, visibility_json
            from chat_message_surface
        """
        params: tuple[Any, ...] = ()
        if conversation_id is not None:
            query += " where conversation_id = ? or message_id = ?"
            params = (_normalized_chat_conversation_id(conversation_id), conversation_id)
        query += " order by sequence"
        with sqlite3.connect(self.path) as connection:
            self._ensure_schema(connection)
            rows = connection.execute(query, params).fetchall()
        visible: list[dict[str, Any]] = []
        for payload_json, visibility_json in rows:
            visibility = json.loads(visibility_json)
            if _visibility_matches(visibility, principals):
                visible.append(json.loads(payload_json))
        return visible

    def read_pending_decisions(
        self,
        player_id: str,
        *,
        crew_ids: list[str] | tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        crew_set = set(crew_ids)
        if not crew_set:
            return []
        with sqlite3.connect(self.path) as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                select payload_json
                from pending_decision_surface
                where player_id = ?
                  and crew_id in (
                    select value from json_each(?)
                  )
                order by crew_id, decision_index
                """,
                (
                    player_id,
                    json.dumps(sorted(crew_set), separators=(",", ":")),
                ),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def read_visible_rumors_for_crew(self, crew_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                select payload_json
                from visible_rumor_surface
                where crew_id = ?
                order by rumor_index, rumor_id
                """,
                (crew_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def read_current_actions_for_crew(self, crew_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                select payload_json
                from action_surface
                where crew_id = ?
                order by action_id
                """,
                (crew_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

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
            create table if not exists projection_schema_migrations (
                applied_version text primary key,
                description text not null
            )
            """
        )
        for version, description in PROJECTION_SCHEMA_MIGRATIONS:
            connection.execute(
                """
                insert into projection_schema_migrations (applied_version, description)
                values (?, ?)
                on conflict(applied_version) do update set
                    description = excluded.description
                """,
                (version, description),
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
            create table if not exists crew_legacy (
                crew_id text primary key,
                payload_json text not null,
                updated_sequence integer not null
            )
            """
        )
        connection.execute(
            """
            create table if not exists proof_dossier (
                crew_id text primary key,
                packet_lead_player_id text not null,
                payload_json text not null,
                updated_sequence integer not null
            )
            """
        )
        connection.execute(
            """
            create index if not exists idx_proof_dossier_packet_lead
            on proof_dossier (packet_lead_player_id)
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
        self._ensure_artifact_scoped_surface_schema(connection)
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
        connection.execute(
            """
            create table if not exists chat_message_surface (
                event_id text primary key,
                message_id text not null,
                sequence integer not null,
                kind text not null,
                conversation_id text not null,
                payload_json text not null,
                visibility_json text not null,
                updated_sequence integer not null
            )
            """
        )
        connection.execute(
            """
            create index if not exists idx_chat_message_surface_conversation
            on chat_message_surface (conversation_id, sequence)
            """
        )
        connection.execute(
            """
            create index if not exists idx_chat_message_surface_sequence
            on chat_message_surface (sequence)
            """
        )
        connection.execute(
            """
            create table if not exists action_surface (
                action_id text primary key,
                crew_id text not null,
                actor_player_id text not null,
                status text not null,
                payload_json text not null,
                updated_sequence integer not null
            )
            """
        )
        connection.execute(
            """
            create index if not exists idx_action_surface_crew
            on action_surface (crew_id, status, action_id)
            """
        )
        connection.execute(
            """
            create table if not exists pending_decision_surface (
                player_id text not null,
                crew_id text not null,
                decision_index integer not null,
                kind text not null,
                payload_json text not null,
                updated_sequence integer not null,
                primary key (player_id, crew_id, decision_index)
            )
            """
        )
        connection.execute(
            """
            create index if not exists idx_pending_decision_surface_player
            on pending_decision_surface (player_id, crew_id, kind)
            """
        )
        connection.execute(
            """
            create table if not exists visible_rumor_surface (
                crew_id text not null,
                rumor_id text not null,
                rumor_index integer not null,
                payload_json text not null,
                updated_sequence integer not null,
                primary key (crew_id, rumor_id)
            )
            """
        )
        connection.execute(
            """
            create index if not exists idx_visible_rumor_surface_crew
            on visible_rumor_surface (crew_id, rumor_index)
            """
        )

    def _ensure_artifact_scoped_surface_schema(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            row[1]
            for row in connection.execute(
                "pragma table_info(artifact_scoped_surface)"
            ).fetchall()
        }
        if existing_columns and "scope_key" not in existing_columns:
            connection.execute("drop table artifact_scoped_surface")
        connection.execute(
            """
            create table if not exists artifact_scoped_surface (
                artifact_id text not null,
                scope_key text not null,
                payload_json text not null,
                visibility_json text not null,
                updated_sequence integer not null,
                primary key (artifact_id, scope_key)
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


def build_projection_snapshot(events: list[GameEvent]) -> dict[str, Any]:
    board = contract_board_from_events(events)
    crew_summaries = crew_summaries_from_events(events)
    artifact_visibility = artifact_visibility_from_events(events)
    deals = deal_rows_from_events(events)
    crew_legacies = _crew_legacies_from_projection_inputs(
        crew_ids=crew_summaries.keys(),
        contracts=board["contracts"],
        deals=deals,
        events=events,
    )
    proof_dossiers = proof_dossiers_from_events(events)
    actions_by_crew = _current_actions_by_crew_from_events(events)
    pending_decisions = _pending_decisions_from_projection_inputs(
        board=board,
        deals=deals,
        crew_summaries=crew_summaries,
        proof_dossiers=proof_dossiers,
        crew_legacies=crew_legacies,
        actions_by_crew=actions_by_crew,
        events=events,
    )
    visible_rumors_by_crew = _visible_rumors_by_crew_from_events(events)
    chat_messages = [
        event
        for event in events
        if event.type == "chat.message.created" and _event_is_player_projectable(event)
    ]
    visible_events = [
        event
        for event in events
        if _event_is_player_projectable(event)
    ]
    return {
        "board": board,
        "crew_summaries": crew_summaries,
        "artifact_visibility": artifact_visibility,
        "deals": deals,
        "crew_legacies": crew_legacies,
        "proof_dossiers": proof_dossiers,
        "actions_by_crew": actions_by_crew,
        "pending_decisions": pending_decisions,
        "visible_rumors_by_crew": visible_rumors_by_crew,
        "chat_messages": chat_messages,
        "visible_events": visible_events,
        "last_sequence": events[-1].sequence if events else 0,
    }


def _artifact_scope_key(visibility: dict[str, Any]) -> str:
    return json.dumps(visibility, sort_keys=True, separators=(",", ":"))


def _event_is_player_projectable(event: GameEvent) -> bool:
    return any(
        entry.kind in {"public", "player", "crew"}
        for entry in event.visibility.entries
    )


def _chat_conversation_id(payload: dict[str, Any]) -> str:
    sender_crew_id = payload.get("sender_crew_id")
    recipient_crew_id = payload.get("recipient_crew_id")
    if sender_crew_id and recipient_crew_id:
        participants = sorted((str(sender_crew_id), str(recipient_crew_id)))
        return f"{participants[0]}:{participants[1]}"
    if sender_crew_id:
        return str(sender_crew_id)
    return str(payload["message_id"])


def _normalized_chat_conversation_id(conversation_id: str) -> str:
    if ":" not in conversation_id:
        return conversation_id
    participants = sorted(part for part in conversation_id.split(":") if part)
    if len(participants) != 2:
        return conversation_id
    return f"{participants[0]}:{participants[1]}"


def _chat_event_surface(event: GameEvent) -> dict[str, Any]:
    payload = event.model_dump(mode="json")
    return {
        "event_id": payload["event_id"],
        "sequence": payload["sequence"],
        "type": payload["type"],
        "payload": payload["payload"],
        "visibility": payload["visibility"],
    }


def _pending_decisions_from_projection_inputs(
    *,
    board: dict[str, Any],
    deals: list[dict[str, Any]],
    crew_summaries: dict[str, dict[str, Any]],
    proof_dossiers: dict[str, dict[str, Any]],
    crew_legacies: dict[str, dict[str, Any]],
    actions_by_crew: dict[str, list[dict[str, Any]]],
    events: list[GameEvent],
) -> list[dict[str, Any]]:
    crew_ids_by_player: dict[str, list[str]] = {}
    for crew_id, summary in crew_summaries.items():
        for player_id in summary.get("member_ids", []):
            crew_ids_by_player.setdefault(str(player_id), []).append(crew_id)

    rumors_by_crew = _visible_rumors_by_crew_from_events(events)
    rows: list[dict[str, Any]] = []
    for player_id, player_crew_ids in sorted(crew_ids_by_player.items()):
        for crew_id in sorted(player_crew_ids):
            crew_deals = [
                deal
                for deal in deals
                if crew_id in {deal.get("proposer_crew_id"), deal.get("recipient_crew_id")}
            ]
            crew_contracts = [
                deepcopy(contract)
                for contract in board["contracts"]
                if contract.get("lifecycle_status", "active") != "archived"
            ]
            apply_contract_unlock_status(
                contracts=crew_contracts,
                crew_ids=[crew_id],
                events=events,
                deals_by_crew={crew_id: crew_deals},
            )
            decisions = pending_decisions_for_player(
                player_id=player_id,
                crew_ids=[crew_id],
                active_contracts=unlocked_actionable_contracts(crew_contracts),
                deals=crew_deals,
                crew_summaries={crew_id: crew_summaries.get(crew_id, {})},
                dossiers={crew_id: proof_dossiers.get(crew_id, {})},
                actions_by_crew={crew_id: actions_by_crew.get(crew_id, [])},
                rumors_by_crew={crew_id: rumors_by_crew.get(crew_id, [])},
                crew_legacies={crew_id: crew_legacies.get(crew_id, {})},
            )
            for decision_index, decision in enumerate(decisions):
                rows.append(
                    {
                        "player_id": player_id,
                        "crew_id": crew_id,
                        "decision_index": decision_index,
                        "kind": str(decision.get("kind", "")),
                        "decision": decision,
                    }
                )
    return rows


def _current_actions_by_crew_from_events(
    events: list[GameEvent],
) -> dict[str, list[dict[str, Any]]]:
    current: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.type not in {"action.submitted", "action.edited", "action.canceled"}:
            continue
        action = event.payload["action"]
        current[action["action_id"]] = action
    actions_by_crew: dict[str, list[dict[str, Any]]] = {}
    for action in sorted(current.values(), key=lambda item: item["action_id"]):
        if action.get("status") == "canceled":
            continue
        crew_id = action.get("crew_id")
        if crew_id:
            actions_by_crew.setdefault(str(crew_id), []).append(action)
    return actions_by_crew


def _visible_rumors_by_crew_from_events(
    events: list[GameEvent],
) -> dict[str, list[dict[str, Any]]]:
    rumors_by_crew: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event.type != "contract.rumor.leaked":
            continue
        rumor = {
            key: event.payload[key]
            for key in SAFE_RUMOR_FIELDS
            if key in event.payload
        }
        for entry in event.visibility.entries:
            if entry.kind != "crew":
                continue
            rumors_by_crew.setdefault(entry.id, []).append(dict(rumor))
    return rumors_by_crew


def proof_dossiers_from_events(events: list[GameEvent]) -> dict[str, dict[str, Any]]:
    current: dict[str, ProofDossier] = {}
    current_leads: dict[str, str] = {}
    votes: dict[str, list[dict[str, Any]]] = {}
    replacements: dict[str, list[dict[str, Any]]] = {}

    for event in events:
        if event.type == "crew.created":
            crew_id = event.payload["crew_id"]
            if crew_id not in current:
                lead = event.payload["owner_id"]
                current[crew_id] = ProofDossier.empty(
                    dossier_id=f"dossier_{crew_id}",
                    crew_id=crew_id,
                    packet_lead_player_id=lead,
                )
                current_leads[crew_id] = lead
        elif event.type in {
            "proof.dossier.framing.updated",
            "proof.dossier.contribution.added",
            "artifact.dossier.cited",
            "proof.packet_lead.replaced",
        }:
            dossier = ProofDossier.model_validate(event.payload["dossier"])
            current[dossier.crew_id] = dossier
            if dossier.crew_id not in current_leads:
                current_leads[dossier.crew_id] = dossier.packet_lead_player_id
            if event.type == "proof.packet_lead.replaced":
                previous = current_leads.get(dossier.crew_id)
                next_lead = dossier.packet_lead_player_id
                replacements.setdefault(dossier.crew_id, []).append(
                    {
                        "sequence": event.sequence,
                        "previous_packet_lead_player_id": previous,
                        "packet_lead_player_id": next_lead,
                    }
                )
                current_leads[dossier.crew_id] = next_lead
        elif event.type == "proof.packet_lead.vote.cast":
            crew_id = event.payload["crew_id"]
            votes.setdefault(crew_id, []).append(
                {
                    "sequence": event.sequence,
                    "voter_player_id": event.payload["voter_player_id"],
                    "candidate_player_id": event.payload["candidate_player_id"],
                }
            )

    shaped: dict[str, dict[str, Any]] = {}
    for crew_id, dossier in sorted(current.items()):
        payload = dossier.model_dump(mode="json")
        if votes.get(crew_id):
            payload["packet_lead_votes"] = votes[crew_id]
        if replacements.get(crew_id):
            payload["packet_lead_replacements"] = replacements[crew_id]
        shaped[crew_id] = payload
    return shaped


def _crew_legacies_from_projection_inputs(
    *,
    crew_ids: Any,
    contracts: list[dict[str, Any]],
    deals: list[dict[str, Any]],
    events: list[GameEvent],
) -> dict[str, dict[str, Any]]:
    legacies: dict[str, dict[str, Any]] = {}
    for crew_id in sorted(str(candidate) for candidate in crew_ids):
        crew_deals = [
            deal
            for deal in deals
            if crew_id in {deal.get("proposer_crew_id"), deal.get("recipient_crew_id")}
        ]
        crew_contracts = [
            deepcopy(contract)
            for contract in contracts
            if contract.get("lifecycle_status", "active") != "archived"
        ]
        apply_contract_unlock_status(
            contracts=crew_contracts,
            crew_ids=[crew_id],
            events=events,
            deals_by_crew={crew_id: crew_deals},
        )
        legacies[crew_id] = crew_legacy_from_contracts(
            crew_id=crew_id,
            contracts=unlocked_actionable_contracts(crew_contracts),
            deals=crew_deals,
            events=events,
        )
    return legacies
