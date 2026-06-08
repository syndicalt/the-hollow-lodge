from __future__ import annotations

import threading
from typing import Any

from hollow_lodge.domain.deals import deal_rows_from_events
from hollow_lodge.domain.events import EventVisibility, GameEvent
from hollow_lodge.eventlog.jsonl_store import JsonlEventStore
from hollow_lodge.server.artifact_service import ArtifactService
from hollow_lodge.server.services import CrewService


class DealService:
    def __init__(
        self,
        *,
        event_store: JsonlEventStore,
        crew_service: CrewService,
        artifact_service: ArtifactService,
    ):
        self._event_store = event_store
        self._crew_service = crew_service
        self._artifact_service = artifact_service
        self._lock = threading.RLock()

    def list_for_player(self, player_id: str) -> list[dict]:
        crew_ids = set(self._crew_service.crew_ids_for_player(player_id))
        return [
            row
            for row in deal_rows_from_events(self._event_store.read())
            if row["proposer_crew_id"] in crew_ids or row["recipient_crew_id"] in crew_ids
        ]

    def propose(
        self,
        *,
        contract_id: str,
        proposer_crew_id: str,
        recipient_crew_id: str,
        offered_artifact_ids: list[str] | tuple[str, ...],
        requested_artifact_ids: list[str] | tuple[str, ...],
        soft_terms: list[str] | tuple[str, ...],
        expires_phase: str | None,
        proposer_player_id: str,
        idempotency_key: str,
    ) -> dict:
        with self._lock:
            payload = {
                "deal_id": self._next_deal_id(),
                "contract_id": contract_id,
                "proposer_crew_id": proposer_crew_id,
                "recipient_crew_id": recipient_crew_id,
                "offered_artifact_ids": list(offered_artifact_ids),
                "requested_artifact_ids": list(requested_artifact_ids),
                "soft_terms": list(soft_terms),
                "expires_phase": expires_phase,
                "proposer_player_id": proposer_player_id,
            }
            replay = self._matching_propose_replay(
                idempotency_key=idempotency_key,
                payload=payload,
            )
            if replay is not None:
                return replay

            self._require_crew(proposer_crew_id)
            self._require_crew(recipient_crew_id)
            self._require_member(crew_id=proposer_crew_id, player_id=proposer_player_id)
            self._require_visible_artifacts(
                artifact_ids=offered_artifact_ids,
                crew_id=proposer_crew_id,
            )
            self._event_store.append_command(
                event_type="deal.proposed",
                actor_id=proposer_player_id,
                visibility=EventVisibility.crews([proposer_crew_id, recipient_crew_id]),
                payload=payload,
                idempotency_key=idempotency_key,
            )
            self._append_deal_rumor_if_needed(
                deal=payload,
                idempotency_key=idempotency_key,
            )
            return self._deal_by_id(payload["deal_id"])

    def accept(
        self,
        *,
        deal_id: str,
        actor_player_id: str,
        idempotency_key: str,
    ) -> dict:
        with self._lock:
            replay = self._matching_accept_replay(
                idempotency_key=idempotency_key,
                deal_id=deal_id,
                actor_player_id=actor_player_id,
            )
            if replay is not None:
                return replay

            deal = self._deal_by_id(deal_id)
            self._require_member(crew_id=deal["recipient_crew_id"], player_id=actor_player_id)
            if deal["status"] != "proposed":
                raise ValueError("deal not proposed")
            self._require_visible_artifacts(
                artifact_ids=deal["offered_artifact_ids"],
                crew_id=deal["proposer_crew_id"],
            )
            self._require_visible_artifacts(
                artifact_ids=deal["requested_artifact_ids"],
                crew_id=deal["recipient_crew_id"],
            )
            self._preflight_accepted_deal_fulfillment(
                deal=deal,
                actor_player_id=actor_player_id,
                idempotency_key=idempotency_key,
            )

            self._event_store.append_command(
                event_type="deal.accepted",
                actor_id=actor_player_id,
                visibility=EventVisibility.crews(
                    [deal["proposer_crew_id"], deal["recipient_crew_id"]]
                ),
                payload={
                    "deal_id": deal_id,
                    "accepted_by_player_id": actor_player_id,
                },
                idempotency_key=idempotency_key,
            )
            return self._fulfill_accepted_deal(
                deal=deal,
                actor_player_id=actor_player_id,
                idempotency_key=idempotency_key,
            )

    def decline(
        self,
        *,
        deal_id: str,
        actor_player_id: str,
        idempotency_key: str,
    ) -> dict:
        with self._lock:
            deal = self._deal_by_id(deal_id)
            self._require_member(crew_id=deal["recipient_crew_id"], player_id=actor_player_id)
            replay = self._matching_lifecycle_replay(
                idempotency_key=idempotency_key,
                expected_type="deal.declined",
                expected_payload={"deal_id": deal_id},
                expected_actor_id=actor_player_id,
            )
            if replay is not None:
                return self._deal_by_id(deal_id)
            if deal["status"] != "proposed":
                raise ValueError("deal not proposed")
            self._append_simple_lifecycle_event(
                event_type="deal.declined",
                actor_id=actor_player_id,
                deal=deal,
                idempotency_key=idempotency_key,
            )
            return self._deal_by_id(deal_id)

    def cancel(
        self,
        *,
        deal_id: str,
        actor_player_id: str,
        idempotency_key: str,
    ) -> dict:
        with self._lock:
            deal = self._deal_by_id(deal_id)
            self._require_member(crew_id=deal["proposer_crew_id"], player_id=actor_player_id)
            replay = self._matching_lifecycle_replay(
                idempotency_key=idempotency_key,
                expected_type="deal.canceled",
                expected_payload={"deal_id": deal_id},
                expected_actor_id=actor_player_id,
            )
            if replay is not None:
                return self._deal_by_id(deal_id)
            if deal["status"] != "proposed":
                raise ValueError("deal not proposed")
            self._append_simple_lifecycle_event(
                event_type="deal.canceled",
                actor_id=actor_player_id,
                deal=deal,
                idempotency_key=idempotency_key,
            )
            return self._deal_by_id(deal_id)

    def _fulfill_accepted_deal(
        self,
        *,
        deal: dict,
        actor_player_id: str,
        idempotency_key: str,
    ) -> dict:
        recipient_received = [
            self._artifact_service.copy_artifact_for_deal(
                source_artifact_id=artifact_id,
                source_crew_id=deal["proposer_crew_id"],
                recipient_crew_id=deal["recipient_crew_id"],
                actor_id=actor_player_id,
                deal_id=deal["deal_id"],
                idempotency_key=f"{idempotency_key}.recipient.{index}",
            )["artifact_id"]
            for index, artifact_id in enumerate(deal["offered_artifact_ids"])
        ]
        proposer_received = [
            self._artifact_service.copy_artifact_for_deal(
                source_artifact_id=artifact_id,
                source_crew_id=deal["recipient_crew_id"],
                recipient_crew_id=deal["proposer_crew_id"],
                actor_id=actor_player_id,
                deal_id=deal["deal_id"],
                idempotency_key=f"{idempotency_key}.proposer.{index}",
            )["artifact_id"]
            for index, artifact_id in enumerate(deal["requested_artifact_ids"])
        ]
        self._event_store.append_command(
            event_type="deal.fulfilled",
            actor_id=actor_player_id,
            visibility=EventVisibility.crews(
                [deal["proposer_crew_id"], deal["recipient_crew_id"]]
            ),
            payload={
                "deal_id": deal["deal_id"],
                "proposer_received_artifact_ids": proposer_received,
                "recipient_received_artifact_ids": recipient_received,
            },
            idempotency_key=f"{idempotency_key}.fulfilled",
        )
        return self._deal_by_id(deal["deal_id"])

    def _preflight_accepted_deal_fulfillment(
        self,
        *,
        deal: dict,
        actor_player_id: str,
        idempotency_key: str,
    ) -> None:
        next_copy_number = self._artifact_service.next_deal_copy_number()
        recipient_received: list[str] = []
        for index, artifact_id in enumerate(deal["offered_artifact_ids"]):
            surface = self._artifact_service.preflight_copy_artifact_for_deal(
                source_artifact_id=artifact_id,
                source_crew_id=deal["proposer_crew_id"],
                recipient_crew_id=deal["recipient_crew_id"],
                actor_id=actor_player_id,
                deal_id=deal["deal_id"],
                idempotency_key=f"{idempotency_key}.recipient.{index}",
                copy_number=next_copy_number,
            )
            recipient_received.append(surface["artifact_id"])
            next_copy_number += 1
        proposer_received: list[str] = []
        for index, artifact_id in enumerate(deal["requested_artifact_ids"]):
            surface = self._artifact_service.preflight_copy_artifact_for_deal(
                source_artifact_id=artifact_id,
                source_crew_id=deal["recipient_crew_id"],
                recipient_crew_id=deal["proposer_crew_id"],
                actor_id=actor_player_id,
                deal_id=deal["deal_id"],
                idempotency_key=f"{idempotency_key}.proposer.{index}",
                copy_number=next_copy_number,
            )
            proposer_received.append(surface["artifact_id"])
            next_copy_number += 1
        self._preflight_deal_fulfilled_key(
            idempotency_key=f"{idempotency_key}.fulfilled",
            actor_id=actor_player_id,
            visibility=EventVisibility.crews(
                [deal["proposer_crew_id"], deal["recipient_crew_id"]]
            ),
            payload={
                "deal_id": deal["deal_id"],
                "proposer_received_artifact_ids": proposer_received,
                "recipient_received_artifact_ids": recipient_received,
            },
        )

    def _preflight_deal_fulfilled_key(
        self,
        *,
        idempotency_key: str,
        actor_id: str,
        visibility: EventVisibility,
        payload: dict[str, Any],
    ) -> None:
        existing = self._event_by_idempotency_key(idempotency_key)
        if existing is None:
            return
        if (
            existing.type != "deal.fulfilled"
            or existing.actor_id != actor_id
            or existing.visibility != visibility
            or existing.payload != payload
        ):
            raise ValueError("idempotency key conflict")

    def _next_deal_id(self) -> str:
        count = sum(1 for event in self._event_store.read() if event.type == "deal.proposed")
        return f"deal_{count + 1:06d}"

    def _append_deal_rumor_if_needed(self, *, deal: dict, idempotency_key: str) -> None:
        participant_crew_ids = {
            deal["proposer_crew_id"],
            deal["recipient_crew_id"],
        }
        bystander_crew_ids = [
            crew_id
            for crew_id in self._crew_service.crew_ids()
            if crew_id not in participant_crew_ids
        ]
        if not bystander_crew_ids:
            return
        self._event_store.append_command(
            event_type="contract.rumor.leaked",
            actor_id="server",
            visibility=EventVisibility.crews(bystander_crew_ids),
            payload={
                "rumor_id": f"rumor_{deal['deal_id']}",
                "source_type": "deal.proposed",
                "source_id": deal["deal_id"],
                "contract_id": deal["contract_id"],
                "suspected_crew_ids": [
                    deal["proposer_crew_id"],
                    deal["recipient_crew_id"],
                ],
                "summary": f"A side arrangement is circulating around {deal['contract_id']}.",
                "pressure": "escrow_terms_detected",
            },
            idempotency_key=f"{idempotency_key}.rumor",
        )

    def _deal_by_id(self, deal_id: str) -> dict:
        for row in deal_rows_from_events(self._event_store.read()):
            if row["deal_id"] == deal_id:
                return row
        raise KeyError(deal_id)

    def _require_crew(self, crew_id: str) -> None:
        if not self._crew_service.has_crew(crew_id):
            raise KeyError("crew not found")

    def _require_member(self, *, crew_id: str, player_id: str) -> None:
        self._require_crew(crew_id)
        if not self._crew_service.is_member(crew_id=crew_id, player_id=player_id):
            raise PermissionError("not a crew member")

    def _require_visible_artifacts(
        self,
        *,
        artifact_ids: list[str] | tuple[str, ...],
        crew_id: str,
    ) -> None:
        member_ids = self._crew_service.member_ids(crew_id)
        if not member_ids:
            raise PermissionError("not a crew member")
        member_id = member_ids[0]
        for artifact_id in artifact_ids:
            self._artifact_service.inspect_artifact(
                artifact_id=artifact_id,
                player_id=member_id,
                crew_ids=[crew_id],
            )

    def _matching_propose_replay(self, *, idempotency_key: str, payload: dict) -> dict | None:
        existing = self._event_by_idempotency_key(idempotency_key)
        if existing is None:
            return None
        if existing.type != "deal.proposed":
            raise ValueError("idempotency key conflict")
        comparable_payload = dict(payload)
        comparable_payload["deal_id"] = existing.payload.get("deal_id")
        if existing.payload != comparable_payload:
            raise ValueError("idempotency key conflict")
        return self._deal_by_id(existing.payload["deal_id"])

    def _matching_accept_replay(
        self,
        *,
        idempotency_key: str,
        deal_id: str,
        actor_player_id: str,
    ) -> dict | None:
        existing = self._event_by_idempotency_key(idempotency_key)
        if existing is None:
            return None
        if existing.type != "deal.accepted":
            raise ValueError("idempotency key conflict")
        if (
            existing.payload.get("deal_id") != deal_id
            or existing.payload.get("accepted_by_player_id") != actor_player_id
        ):
            raise ValueError("idempotency key conflict")
        deal = self._deal_by_id(deal_id)
        if deal["status"] == "fulfilled":
            return deal
        return self._fulfill_accepted_deal(
            deal=deal,
            actor_player_id=actor_player_id,
            idempotency_key=idempotency_key,
        )

    def _matching_lifecycle_replay(
        self,
        *,
        idempotency_key: str,
        expected_type: str,
        expected_payload: dict[str, Any],
        expected_actor_id: str,
    ) -> GameEvent | None:
        existing = self._event_by_idempotency_key(idempotency_key)
        if existing is None:
            return None
        if (
            existing.type != expected_type
            or existing.payload != expected_payload
            or existing.actor_id != expected_actor_id
        ):
            raise ValueError("idempotency key conflict")
        return existing

    def _append_simple_lifecycle_event(
        self,
        *,
        event_type: str,
        actor_id: str,
        deal: dict,
        idempotency_key: str,
    ) -> None:
        self._event_store.append_command(
            event_type=event_type,
            actor_id=actor_id,
            visibility=EventVisibility.crews(
                [deal["proposer_crew_id"], deal["recipient_crew_id"]]
            ),
            payload={"deal_id": deal["deal_id"]},
            idempotency_key=idempotency_key,
        )

    def _event_by_idempotency_key(self, idempotency_key: str) -> GameEvent | None:
        for event in self._event_store.read():
            if event.idempotency_key == idempotency_key:
                return event
        return None
