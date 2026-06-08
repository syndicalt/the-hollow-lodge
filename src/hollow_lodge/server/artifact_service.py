from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any

from hollow_lodge.domain.artifacts import ArtifactCopy
from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.eventlog.jsonl_store import JsonlEventStore
from hollow_lodge.eventlog.visibility import Principal
from hollow_lodge.server.artifact_seed import (
    STARTER_ARTIFACT_GRAPH,
    STARTER_PUBLIC_ARTIFACT_IDS,
)


@dataclass(frozen=True)
class _PlannedDealCopy:
    surface: dict[str, Any]
    public_actor_id: str
    public_visibility: EventVisibility
    public_payload: dict[str, Any]
    public_idempotency_key: str
    internal_payload: dict[str, Any]
    internal_idempotency_key: str


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
        visible_ids = self._visible_artifact_ids(player_id, crew_ids=crew_ids)
        visible = STARTER_ARTIFACT_GRAPH.visible_slice(visible_ids)
        visible["artifacts"].extend(
            surface
            for surface in self._visible_copy_surfaces(player_id, crew_ids=crew_ids)
            if surface["artifact_id"] in visible_ids
        )
        return visible

    def inspect_artifact(
        self,
        *,
        artifact_id: str,
        player_id: str,
        idempotency_key: str | None = None,
        crew_ids: list[str] | tuple[str, ...] = (),
    ) -> dict:
        if artifact_id not in self._visible_artifact_ids(
            player_id,
            crew_ids=crew_ids,
        ):
            raise KeyError(artifact_id)
        try:
            artifact = STARTER_ARTIFACT_GRAPH.artifact_by_id(artifact_id)
        except KeyError:
            copied = self._copy_surface(artifact_id)
            if copied is None:
                raise
            return copied
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

    def transfer_artifact(
        self,
        *,
        artifact_id: str,
        sender_player_id: str,
        recipient_player_id: str,
        idempotency_key: str,
        sender_crew_ids: list[str] | tuple[str, ...] = (),
    ) -> dict:
        with self._lock:
            replay = self._matching_transfer_replay(
                idempotency_key=idempotency_key,
                source_artifact_id=artifact_id,
                sender_player_id=sender_player_id,
                recipient_player_id=recipient_player_id,
            )
            if replay is not None:
                return replay

            artifact = STARTER_ARTIFACT_GRAPH.artifact_by_id(artifact_id)
            if artifact.artifact_id not in self._visible_artifact_ids(
                sender_player_id,
                crew_ids=sender_crew_ids,
            ):
                raise KeyError(artifact_id)
            if artifact.copy_policy == "sealed":
                raise ValueError("artifact cannot be transferred")

            artifact_copy = ArtifactCopy.from_source(
                source_artifact_id=artifact.artifact_id,
                copy_artifact_id=(
                    f"{artifact.artifact_id}.copy."
                    f"{recipient_player_id}.{self._next_transfer_number()}"
                ),
                contract_id=artifact.contract_id,
                sender_player_id=sender_player_id,
                recipient_player_id=recipient_player_id,
                title=artifact.title,
                public_summary=artifact.public_summary,
            )
            surface = artifact_copy.surface_view()
            self._event_store.append_command(
                event_type="artifact.transferred",
                actor_id=sender_player_id,
                visibility=EventVisibility.players([sender_player_id, recipient_player_id]),
                payload={
                    "sender_player_id": sender_player_id,
                    "recipient_player_id": recipient_player_id,
                    "source_artifact_id": artifact.artifact_id,
                    "surface": surface,
                },
                idempotency_key=idempotency_key,
            )
            self._event_store.append_command(
                event_type="artifact.transferred.internal",
                actor_id="server",
                visibility=EventVisibility.server_only(),
                payload={
                    "transfer_idempotency_key": idempotency_key,
                    "artifact_copy": artifact_copy.model_dump(mode="json"),
                },
                idempotency_key=f"{idempotency_key}.internal",
            )
            return surface

    def copy_artifact_for_deal(
        self,
        *,
        source_artifact_id: str,
        source_crew_id: str,
        recipient_crew_id: str,
        actor_id: str,
        deal_id: str,
        idempotency_key: str,
    ) -> dict:
        with self._lock:
            replay = self._matching_deal_copy_replay(
                idempotency_key=idempotency_key,
                source_artifact_id=source_artifact_id,
                source_crew_id=source_crew_id,
                recipient_crew_id=recipient_crew_id,
                deal_id=deal_id,
            )
            if replay is not None:
                return replay

            planned = self._plan_deal_copy(
                source_artifact_id=source_artifact_id,
                source_crew_id=source_crew_id,
                recipient_crew_id=recipient_crew_id,
                actor_id=actor_id,
                deal_id=deal_id,
                idempotency_key=idempotency_key,
            )
            self._event_store.append_command(
                event_type="artifact.deal_copied",
                actor_id=planned.public_actor_id,
                visibility=planned.public_visibility,
                payload=planned.public_payload,
                idempotency_key=planned.public_idempotency_key,
            )
            self._event_store.append_command(
                event_type="artifact.deal_copied.internal",
                actor_id="server",
                visibility=EventVisibility.server_only(),
                payload=planned.internal_payload,
                idempotency_key=planned.internal_idempotency_key,
            )
            return planned.surface

    def preflight_copy_artifact_for_deal(
        self,
        *,
        source_artifact_id: str,
        source_crew_id: str,
        recipient_crew_id: str,
        actor_id: str,
        deal_id: str,
        idempotency_key: str,
        copy_number: int | None = None,
    ) -> dict:
        with self._lock:
            self._matching_deal_copy_replay(
                idempotency_key=idempotency_key,
                source_artifact_id=source_artifact_id,
                source_crew_id=source_crew_id,
                recipient_crew_id=recipient_crew_id,
                deal_id=deal_id,
            )
            planned = self._plan_deal_copy(
                source_artifact_id=source_artifact_id,
                source_crew_id=source_crew_id,
                recipient_crew_id=recipient_crew_id,
                actor_id=actor_id,
                deal_id=deal_id,
                idempotency_key=idempotency_key,
                copy_number=copy_number,
            )
            self._preflight_command_idempotency(
                idempotency_key=planned.public_idempotency_key,
                event_type="artifact.deal_copied",
                actor_id=planned.public_actor_id,
                visibility=planned.public_visibility,
                payload=planned.public_payload,
            )
            self._preflight_command_idempotency(
                idempotency_key=planned.internal_idempotency_key,
                event_type="artifact.deal_copied.internal",
                actor_id="server",
                visibility=EventVisibility.server_only(),
                payload=planned.internal_payload,
            )
            return planned.surface

    def next_deal_copy_number(self) -> int:
        with self._lock:
            return self._next_deal_copy_number()

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
                elif event.type in {"artifact.transferred", "artifact.deal_copied"}:
                    visible_ids.add(event.payload["surface"]["artifact_id"])
        return visible_ids

    def _visible_copy_surfaces(
        self,
        player_id: str,
        *,
        crew_ids: list[str] | tuple[str, ...] = (),
    ) -> list[dict]:
        surfaces_by_id: dict[str, dict] = {}
        principals = [Principal.player(player_id)]
        principals.extend(Principal.crew(crew_id) for crew_id in crew_ids)
        for principal in principals:
            for event in self._event_store.read_for_principal(principal):
                if event.type not in {"artifact.transferred", "artifact.deal_copied"}:
                    continue
                surface = event.payload["surface"]
                surfaces_by_id[surface["artifact_id"]] = surface
        return list(surfaces_by_id.values())

    def _copy_surface(self, artifact_id: str) -> dict | None:
        for event in self._event_store.read():
            if event.type not in {
                "artifact.transferred.internal",
                "artifact.deal_copied.internal",
            }:
                continue
            copied = ArtifactCopy.model_validate(event.payload["artifact_copy"])
            if copied.artifact_id == artifact_id:
                return copied.surface_view()
        return None

    def _matching_transfer_replay(
        self,
        *,
        idempotency_key: str,
        source_artifact_id: str,
        sender_player_id: str,
        recipient_player_id: str,
    ) -> dict | None:
        for event in self._event_store.read():
            if event.idempotency_key != idempotency_key:
                continue
            if event.type != "artifact.transferred":
                raise ValueError("idempotency key conflict")
            if (
                event.payload.get("source_artifact_id") != source_artifact_id
                or event.payload.get("sender_player_id") != sender_player_id
                or event.payload.get("recipient_player_id") != recipient_player_id
            ):
                raise ValueError("idempotency key conflict")
            return event.payload["surface"]
        return None

    def _matching_deal_copy_replay(
        self,
        *,
        idempotency_key: str,
        source_artifact_id: str,
        source_crew_id: str,
        recipient_crew_id: str,
        deal_id: str,
    ) -> dict | None:
        for event in self._event_store.read():
            if event.idempotency_key != idempotency_key:
                continue
            if event.type != "artifact.deal_copied":
                raise ValueError("idempotency key conflict")
            if (
                event.payload.get("source_artifact_id") != source_artifact_id
                or event.payload.get("source_crew_id") != source_crew_id
                or event.payload.get("recipient_crew_id") != recipient_crew_id
                or event.payload.get("deal_id") != deal_id
            ):
                raise ValueError("idempotency key conflict")
            return event.payload["surface"]
        return None

    def _plan_deal_copy(
        self,
        *,
        source_artifact_id: str,
        source_crew_id: str,
        recipient_crew_id: str,
        actor_id: str,
        deal_id: str,
        idempotency_key: str,
        copy_number: int | None = None,
    ) -> _PlannedDealCopy:
        artifact = STARTER_ARTIFACT_GRAPH.artifact_by_id(source_artifact_id)
        if artifact.copy_policy == "sealed":
            raise ValueError("artifact cannot be transferred")

        artifact_copy = ArtifactCopy.from_deal_source(
            source_artifact_id=artifact.artifact_id,
            copy_artifact_id=(
                f"{artifact.artifact_id}.dealcopy."
                f"{deal_id}.{recipient_crew_id}.{copy_number or self._next_deal_copy_number()}"
            ),
            contract_id=artifact.contract_id,
            source_crew_id=source_crew_id,
            recipient_crew_id=recipient_crew_id,
            deal_id=deal_id,
            title=artifact.title,
            public_summary=artifact.public_summary,
        )
        surface = artifact_copy.surface_view()
        return _PlannedDealCopy(
            surface=surface,
            public_actor_id=actor_id,
            public_visibility=EventVisibility.crews([source_crew_id, recipient_crew_id]),
            public_payload={
                "deal_id": deal_id,
                "source_crew_id": source_crew_id,
                "recipient_crew_id": recipient_crew_id,
                "source_artifact_id": artifact.artifact_id,
                "surface": surface,
            },
            public_idempotency_key=idempotency_key,
            internal_payload={
                "deal_copy_idempotency_key": idempotency_key,
                "artifact_copy": artifact_copy.model_dump(mode="json"),
            },
            internal_idempotency_key=f"{idempotency_key}.internal",
        )

    def _preflight_command_idempotency(
        self,
        *,
        idempotency_key: str,
        event_type: str,
        actor_id: str,
        visibility: EventVisibility,
        payload: dict[str, Any],
    ) -> None:
        for event in self._event_store.read():
            if event.idempotency_key != idempotency_key:
                continue
            if (
                event.type != event_type
                or event.actor_id != actor_id
                or event.visibility != visibility
                or event.payload != payload
            ):
                raise ValueError("idempotency key conflict")
            return

    def _next_transfer_number(self) -> int:
        return 1 + sum(
            1
            for event in self._event_store.read()
            if event.type == "artifact.transferred.internal"
        )

    def _next_deal_copy_number(self) -> int:
        return 1 + sum(
            1
            for event in self._event_store.read()
            if event.type == "artifact.deal_copied.internal"
        )
