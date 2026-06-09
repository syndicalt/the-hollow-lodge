from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse, urlunparse

from hollow_lodge.domain.events import GameEvent
from hollow_lodge.server.projection_store import (
    PROJECTION_SCHEMA_MIGRATIONS,
    SCHEMA_VERSION,
    _artifact_scope_key,
    _visibility_matches,
    _chat_conversation_id,
    _chat_event_surface,
    _normalized_chat_conversation_id,
    build_projection_snapshot,
)


class PostgresProjectionStore:
    backend = "postgres"

    def __init__(
        self,
        database_url: str,
        *,
        database_url_env: str = "HOLLOW_LODGE_PROJECTION_DATABASE_URL",
    ):
        self.database_url = database_url
        self.safe_database_url = _redact_database_url(database_url)
        self.database_url_env = database_url_env

    def rebuild(self, events: list[GameEvent]) -> dict[str, Any]:
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
        visible_events = snapshot["visible_events"]
        last_sequence = snapshot["last_sequence"]

        with self._connect() as connection:
            self._ensure_schema(connection)
            for table in (
                "contract_board",
                "crew_summary",
                "artifact_surface",
                "artifact_edge",
                "artifact_scoped_surface",
                "deal_surface",
                "visible_event_surface",
                "crew_legacy",
                "proof_dossier",
                "chat_message_surface",
                "action_surface",
                "pending_decision_surface",
            ):
                connection.execute(f"delete from {table}")

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
                    ) values (%s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        contract["contract_id"],
                        contract["campaign_id"],
                        contract.get("lifecycle_status", "active"),
                        contract.get("phase", {}).get("status", "active"),
                        _json_dumps(contract),
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
                    ) values (%s, %s, %s::jsonb, %s)
                    """,
                    (
                        crew_id,
                        crew["member_count"],
                        _json_dumps(crew),
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
                    ) values (%s, %s, %s::jsonb, %s)
                    """,
                    (
                        artifact_id,
                        artifact["contract_id"],
                        _json_dumps(artifact),
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
                    ) values (%s, %s, %s, %s::jsonb, %s)
                    on conflict (source_id, target_id, relation) do update set
                        payload_json = excluded.payload_json,
                        updated_sequence = excluded.updated_sequence
                    """,
                    (
                        edge["source_id"],
                        edge["target_id"],
                        edge["relation"],
                        _json_dumps(edge),
                        last_sequence,
                    ),
                )
            for scoped in artifact_visibility["scoped_surfaces"]:
                connection.execute(
                    """
                    insert into artifact_scoped_surface (
                        artifact_id,
                        scope_key,
                        payload_json,
                        visibility_json,
                        updated_sequence
                    ) values (%s, %s, %s::jsonb, %s::jsonb, %s)
                    on conflict (artifact_id, scope_key) do update set
                        payload_json = excluded.payload_json,
                        visibility_json = excluded.visibility_json,
                        updated_sequence = excluded.updated_sequence
                    """,
                    (
                        scoped["artifact_id"],
                        _artifact_scope_key(scoped["visibility"]),
                        _json_dumps(scoped["surface"]),
                        _json_dumps(scoped["visibility"]),
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
                    ) values (%s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        deal["deal_id"],
                        deal["proposer_crew_id"],
                        deal["recipient_crew_id"],
                        deal["status"],
                        _json_dumps(deal),
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
                    ) values (%s, %s::jsonb, %s)
                    """,
                    (
                        crew_id,
                        _json_dumps(legacy),
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
                    ) values (%s, %s, %s::jsonb, %s)
                    """,
                    (
                        crew_id,
                        dossier["packet_lead_player_id"],
                        _json_dumps(dossier),
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
                    ) values (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
                    """,
                    (
                        event.event_id,
                        event.sequence,
                        event.type,
                        _json_dumps(payload),
                        _json_dumps(payload["visibility"]),
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
                    ) values (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                    """,
                    (
                        chat_event.event_id,
                        message["message_id"],
                        chat_event.sequence,
                        message["kind"],
                        _chat_conversation_id(message),
                        _json_dumps(payload),
                        _json_dumps(payload["visibility"]),
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
                        ) values (%s, %s, %s, %s, %s::jsonb, %s)
                        """,
                        (
                            action["action_id"],
                            crew_id,
                            action["actor_player_id"],
                            action["status"],
                            _json_dumps(action),
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
                    ) values (%s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        row["player_id"],
                        row["crew_id"],
                        row["decision_index"],
                        row["kind"],
                        _json_dumps(row["decision"]),
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
            self._set_meta(connection, "campaign_json", _json_dumps(board["campaign"]))
            connection.commit()
        return self.diagnostics(authoritative_last_sequence=last_sequence)

    def diagnostics(self, *, authoritative_last_sequence: int | None = None) -> dict[str, Any]:
        try:
            with self._connect() as connection:
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
                    order by applied_version::integer desc
                    limit 1
                    """
                ).fetchone()
        except Exception:
            authoritative = authoritative_last_sequence or 0
            return {
                "backend": self.backend,
                "database_url": self.safe_database_url,
                "database_url_env": self.database_url_env,
                "exists": False,
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
            "database_url": self.safe_database_url,
            "database_url_env": self.database_url_env,
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
        with self._connect() as connection:
            self._ensure_schema(connection)
            meta = dict(
                connection.execute("select key, value from projection_meta").fetchall()
            )
            rows = connection.execute(
                "select payload_json from contract_board order by contract_id"
            ).fetchall()
        return {
            "campaign": json.loads(meta["campaign_json"]) if "campaign_json" in meta else None,
            "contracts": [_load_json(row[0]) for row in rows],
        }

    def read_crew_summary(self, crew_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "select payload_json from crew_summary where crew_id = %s",
                (crew_id,),
            ).fetchone()
        if row is None:
            raise KeyError(crew_id)
        return _load_json(row[0])

    def read_crew_legacy(self, crew_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "select payload_json from crew_legacy where crew_id = %s",
                (crew_id,),
            ).fetchone()
        if row is None:
            raise KeyError(crew_id)
        return _load_json(row[0])

    def read_proof_dossier(self, crew_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "select payload_json from proof_dossier where crew_id = %s",
                (crew_id,),
            ).fetchone()
        if row is None:
            raise KeyError(crew_id)
        return _load_json(row[0])

    def read_visible_artifacts(
        self,
        player_id: str,
        *,
        crew_ids: list[str] | tuple[str, ...] = (),
    ) -> dict[str, Any]:
        principals = {("player", player_id)}
        principals.update(("crew", crew_id) for crew_id in crew_ids)
        with self._connect() as connection:
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
                select payload_json, visibility_json
                from artifact_scoped_surface
                order by artifact_id, scope_key
                """
            ).fetchall()
        artifacts_by_id = {
            artifact["artifact_id"]: artifact
            for artifact in (_load_json(row[0]) for row in artifact_rows)
        }
        for payload_json, visibility_json in scoped_rows:
            visibility = _load_json(visibility_json)
            if _visibility_matches(visibility, principals):
                artifact = _load_json(payload_json)
                artifacts_by_id[artifact["artifact_id"]] = artifact
        return {
            "contract_id": "multiple",
            "artifacts": [
                artifacts_by_id[artifact_id]
                for artifact_id in sorted(artifacts_by_id)
            ],
            "edges": [_load_json(row[0]) for row in edge_rows],
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
        with self._connect() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                select payload_json
                from deal_surface
                where proposer_crew_id = any(%s)
                   or recipient_crew_id = any(%s)
                order by deal_id
                """,
                (sorted(crew_set), sorted(crew_set)),
            ).fetchall()
        return [_load_json(row[0]) for row in rows]

    def read_visible_events(
        self,
        player_id: str,
        *,
        crew_ids: list[str] | tuple[str, ...] = (),
        since_sequence: int = 0,
    ) -> list[dict[str, Any]]:
        principals = {("player", player_id)}
        principals.update(("crew", crew_id) for crew_id in crew_ids)
        with self._connect() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                select payload_json, visibility_json
                from visible_event_surface
                where sequence > %s
                order by sequence
                """,
                (since_sequence,),
            ).fetchall()
        visible: list[dict[str, Any]] = []
        for payload_json, visibility_json in rows:
            visibility = _load_json(visibility_json)
            if _visibility_matches(visibility, principals):
                visible.append(_load_json(payload_json))
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
            query += " where conversation_id = %s or message_id = %s"
            params = (_normalized_chat_conversation_id(conversation_id), conversation_id)
        query += " order by sequence"
        with self._connect() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(query, params).fetchall()
        visible: list[dict[str, Any]] = []
        for payload_json, visibility_json in rows:
            visibility = _load_json(visibility_json)
            if _visibility_matches(visibility, principals):
                visible.append(_load_json(payload_json))
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
        with self._connect() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                select payload_json
                from pending_decision_surface
                where player_id = %s
                  and crew_id = any(%s)
                order by crew_id, decision_index
                """,
                (player_id, sorted(crew_set)),
            ).fetchall()
        return [_load_json(row[0]) for row in rows]

    def read_current_actions_for_crew(self, crew_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                select payload_json
                from action_surface
                where crew_id = %s
                order by action_id
                """,
                (crew_id,),
            ).fetchall()
        return [_load_json(row[0]) for row in rows]

    def _connect(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "Postgres projection backend requires the psycopg package"
            ) from exc
        return psycopg.connect(self.database_url)

    def _ensure_schema(self, connection: Any) -> None:
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
                values (%s, %s)
                on conflict (applied_version) do update set
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
                payload_json jsonb not null,
                updated_sequence bigint not null
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
                payload_json jsonb not null,
                updated_sequence bigint not null
            )
            """
        )
        connection.execute(
            """
            create table if not exists crew_legacy (
                crew_id text primary key,
                payload_json jsonb not null,
                updated_sequence bigint not null
            )
            """
        )
        connection.execute(
            """
            create table if not exists proof_dossier (
                crew_id text primary key,
                packet_lead_player_id text not null,
                payload_json jsonb not null,
                updated_sequence bigint not null
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
                payload_json jsonb not null,
                updated_sequence bigint not null
            )
            """
        )
        connection.execute(
            """
            create table if not exists artifact_edge (
                source_id text not null,
                target_id text not null,
                relation text not null,
                payload_json jsonb not null,
                updated_sequence bigint not null,
                primary key (source_id, target_id, relation)
            )
            """
        )
        connection.execute(
            """
            create table if not exists artifact_scoped_surface (
                artifact_id text not null,
                scope_key text not null,
                payload_json jsonb not null,
                visibility_json jsonb not null,
                updated_sequence bigint not null,
                primary key (artifact_id, scope_key)
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
                payload_json jsonb not null,
                updated_sequence bigint not null
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
                sequence bigint not null,
                event_type text not null,
                payload_json jsonb not null,
                visibility_json jsonb not null,
                updated_sequence bigint not null
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
                sequence bigint not null,
                kind text not null,
                conversation_id text not null,
                payload_json jsonb not null,
                visibility_json jsonb not null,
                updated_sequence bigint not null
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
                payload_json jsonb not null,
                updated_sequence bigint not null
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
                payload_json jsonb not null,
                updated_sequence bigint not null,
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

    def _set_meta(self, connection: Any, key: str, value: str) -> None:
        connection.execute(
            """
            insert into projection_meta (key, value)
            values (%s, %s)
            on conflict (key) do update set value = excluded.value
            """,
            (key, value),
        )


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


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
