from __future__ import annotations

import threading

from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.eventlog.jsonl_store import JsonlEventStore
from hollow_lodge.eventlog.visibility import Principal
from hollow_lodge.server.artifact_seed import (
    STARTER_ARTIFACT_GRAPH,
    STARTER_PUBLIC_ARTIFACT_IDS,
)


class ArtifactService:
    def __init__(self, *, event_store: JsonlEventStore):
        self._event_store = event_store
        self._lock = threading.RLock()
        self._seed_starter_graph()

    def visible_artifacts_for_player(
        self,
        player_id: str,
        crew_ids: list[str] | tuple[str, ...] = (),
    ) -> dict:
        return STARTER_ARTIFACT_GRAPH.visible_slice(
            self._visible_artifact_ids(player_id, crew_ids=crew_ids)
        )

    def inspect_artifact(
        self,
        *,
        artifact_id: str,
        player_id: str,
        idempotency_key: str | None = None,
        crew_ids: list[str] | tuple[str, ...] = (),
    ) -> dict:
        artifact = STARTER_ARTIFACT_GRAPH.artifact_by_id(artifact_id)
        if artifact.artifact_id not in self._visible_artifact_ids(
            player_id,
            crew_ids=crew_ids,
        ):
            raise KeyError(artifact_id)
        if idempotency_key is not None:
            self._event_store.append_command(
                event_type="artifact.inspected",
                actor_id=player_id,
                visibility=EventVisibility.players([player_id]),
                payload={
                    "artifact_id": artifact.artifact_id,
                    "surface": artifact.surface_view(),
                },
                idempotency_key=idempotency_key,
            )
        return artifact.inspection_view()

    def grant_artifact_access(
        self,
        *,
        artifact_id: str,
        actor_id: str,
        player_ids: list[str],
        crew_ids: list[str] | tuple[str, ...] = (),
        reason: str,
        idempotency_key: str,
    ) -> dict:
        artifact = STARTER_ARTIFACT_GRAPH.artifact_by_id(artifact_id)
        surface = artifact.surface_view()
        self._event_store.append_command(
            event_type="artifact.access.granted",
            actor_id=actor_id,
            visibility=EventVisibility.principals(
                players=player_ids,
                crews=crew_ids,
            ),
            payload={
                "artifact_id": artifact.artifact_id,
                "contract_id": artifact.contract_id,
                "player_ids": list(player_ids),
                "crew_ids": list(crew_ids),
                "reason": reason,
                "surface": surface,
            },
            idempotency_key=idempotency_key,
        )
        return surface

    def _seed_starter_graph(self) -> None:
        with self._lock:
            self._event_store.append_command(
                event_type="artifact.graph.seeded",
                actor_id="server",
                visibility=EventVisibility.server_only(),
                payload=STARTER_ARTIFACT_GRAPH.model_dump(mode="json"),
                idempotency_key="seed.artifact-graph.contract_false_finger",
            )

    def _visible_artifact_ids(
        self,
        player_id: str,
        *,
        crew_ids: list[str] | tuple[str, ...] = (),
    ) -> set[str]:
        visible_ids = set(STARTER_PUBLIC_ARTIFACT_IDS)
        principals = [Principal.player(player_id)]
        principals.extend(Principal.crew(crew_id) for crew_id in crew_ids)
        for principal in principals:
            for event in self._event_store.read_for_principal(principal):
                if event.type == "artifact.access.granted":
                    visible_ids.add(event.payload["artifact_id"])
        return visible_ids
