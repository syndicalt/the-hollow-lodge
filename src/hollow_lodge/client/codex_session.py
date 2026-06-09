from __future__ import annotations

from pathlib import Path
from typing import Any

from hollow_lodge.client.api import HollowLodgeApi, new_command_key
from hollow_lodge.client.artifact_render import (
    build_artifact_graph_packet,
    build_artifact_packet,
)
from hollow_lodge.client.config import ClientConfig, load_config, save_config
from hollow_lodge.client.local_log import LocalEventLog
from hollow_lodge.client.paths import DEFAULT_CONFIG_PATH, DEFAULT_LOCAL_LOG_PATH
from hollow_lodge.client.render_packets import (
    RenderPacket,
    build_activity_delta_packet,
    build_activity_summary_packet,
    build_conversations_packet,
    build_deal_acceptance_preview_packet,
    build_deals_packet,
    build_contract_board_packet,
    build_crew_activity_packet,
    build_crew_board_packet,
    build_dossier_packet,
    build_inbox_packet,
    build_mutation_result_packet,
    build_profile_packet,
    build_thread_packet,
    build_what_now_packet,
)


class CodexGameSession:
    def __init__(
        self,
        *,
        config_path: Path = DEFAULT_CONFIG_PATH,
        local_log_path: Path = DEFAULT_LOCAL_LOG_PATH,
        api: HollowLodgeApi | None = None,
    ):
        self.config_path = config_path
        self.local_log_path = local_log_path
        self.config: ClientConfig = load_config(config_path)
        self.api = api or HollowLodgeApi(
            server_url=self.config.server_url,
            token=self.config.token,
        )
        self._refresh_display_name()
        self.local_log = LocalEventLog(local_log_path)

    def sync(self) -> int:
        return self.local_log.sync_visible_server_events(self.api.visible_events())

    def render_inbox(self) -> RenderPacket:
        self.sync()
        inbox = self.api.inbox()
        if self.config.display_name:
            inbox.setdefault("display_name", self.config.display_name)
        return build_inbox_packet(inbox)

    def render_what_now(self) -> RenderPacket:
        self.sync()
        profile = self.api.profile()
        inbox = self.api.inbox()
        if self.config.display_name:
            inbox.setdefault("display_name", self.config.display_name)
        deals = self.api.deals()
        return build_what_now_packet(
            {
                "profile": profile,
                "inbox": inbox,
                "deals": deals,
                "events": self._visible_server_events(),
                "active_crew_id": self.config.active_crew_id,
            }
        )

    def render_profile(self) -> RenderPacket:
        self.sync()
        return build_profile_packet(self.api.profile())

    def render_contract_board(self) -> RenderPacket:
        self.sync()
        return build_contract_board_packet(self.api.contracts())

    def render_crew_board(self, crew_id: str | None = None) -> RenderPacket:
        self.sync()
        target_crew_id = self._target_crew_id(crew_id)
        return build_crew_board_packet(self.api.crew_board(crew_id=target_crew_id))

    def render_dossier(self, crew_id: str | None = None) -> RenderPacket:
        self.sync()
        target_crew_id = self._target_crew_id(crew_id)
        return build_dossier_packet(self.api.dossier(crew_id=target_crew_id))

    def render_artifacts(self) -> RenderPacket:
        self.sync()
        return build_artifact_graph_packet(self.api.artifacts())

    def render_artifact(self, artifact_id: str) -> RenderPacket:
        self.sync()
        return build_artifact_packet(self.api.artifact(artifact_id=artifact_id))

    def render_deals(self) -> RenderPacket:
        self.sync()
        return build_deals_packet(self.api.deals())

    def render_activity(self) -> RenderPacket:
        self.sync()
        return build_activity_summary_packet(self._visible_server_events())

    def render_activity_delta(self) -> RenderPacket:
        checkpoint = self.local_log.max_server_sequence()
        events = self.api.visible_events_since(since_sequence=checkpoint)
        self.local_log.sync_visible_server_events(events)
        return build_activity_delta_packet(
            events,
            checkpoint_sequence=checkpoint,
        )

    def render_crew_activity(self, crew_id: str | None = None) -> RenderPacket:
        self.sync()
        target_crew_id = self._target_crew_id(crew_id)
        return build_crew_activity_packet(
            self._visible_server_events(),
            crew_id=target_crew_id,
        )

    def render_crew_activity_delta(self, crew_id: str | None = None) -> RenderPacket:
        target_crew_id = self._target_crew_id(crew_id)
        checkpoint = self.local_log.max_server_sequence()
        events = self.api.visible_events_since(since_sequence=checkpoint)
        self.local_log.sync_visible_server_events(events)
        return build_activity_delta_packet(
            events,
            checkpoint_sequence=checkpoint,
            crew_id=target_crew_id,
        )

    def render_thread(self, conversation_id: str) -> RenderPacket:
        self.sync()
        return build_thread_packet(
            self.api.visible_chat_events(conversation_id=conversation_id),
            conversation_id=conversation_id,
        )

    def render_conversations(self) -> RenderPacket:
        self.sync()
        return build_conversations_packet(self.api.visible_chat_events())

    def preview_deal_acceptance(self, deal_id: str) -> RenderPacket:
        self.sync()
        deals = self.api.deals()["deals"]
        for deal in deals:
            if deal["deal_id"] == deal_id:
                viewer_crew_ids = [self.config.active_crew_id] if self.config.active_crew_id else []
                return build_deal_acceptance_preview_packet(
                    {
                        "deal": deal,
                        "viewer_crew_ids": viewer_crew_ids,
                    }
                )
        raise ValueError("deal not found")

    def submit_action(
        self,
        *,
        intent: str,
        confirm: bool,
        crew_id: str | None = None,
        rumor_id: str | None = None,
        rumor_response_mode: str | None = None,
        responds_to_rumor_escalation: bool = False,
        rumor_escalation_mode: str | None = None,
    ) -> RenderPacket:
        target_crew_id = self._target_crew_id(crew_id)
        if not confirm:
            preview_fields = {"crew_id": target_crew_id, "intent": intent}
            if rumor_id is not None:
                preview_fields["rumor_id"] = rumor_id
            if rumor_response_mode is not None:
                preview_fields["rumor_response_mode"] = rumor_response_mode
            if responds_to_rumor_escalation:
                preview_fields["responds_to_rumor_escalation"] = True
            if rumor_escalation_mode is not None:
                preview_fields["rumor_escalation_mode"] = rumor_escalation_mode
            return build_mutation_result_packet(
                operation="submit_action",
                confirmed=False,
                preview_fields=preview_fields,
            )
        result = self.api.submit_action(
            crew_id=target_crew_id,
            intent=intent,
            rumor_id=rumor_id,
            rumor_response_mode=rumor_response_mode,
            responds_to_rumor_escalation=responds_to_rumor_escalation,
            rumor_escalation_mode=rumor_escalation_mode,
            idempotency_key=new_command_key("action-submit"),
        )
        self.sync()
        return build_mutation_result_packet(
            operation="submit_action",
            confirmed=True,
            result=result,
        )

    def dossier_contribute(
        self,
        *,
        note: str,
        evidence_ids: list[str] | tuple[str, ...],
        confirm: bool,
        crew_id: str | None = None,
    ) -> RenderPacket:
        target_crew_id = self._target_crew_id(crew_id)
        preview = {
            "crew_id": target_crew_id,
            "note": note,
            "evidence_ids": list(evidence_ids),
        }
        if not confirm:
            return build_mutation_result_packet(
                operation="dossier_contribute",
                confirmed=False,
                preview_fields=preview,
            )
        result = self.api.add_dossier_contribution(
            crew_id=target_crew_id,
            note=note,
            evidence_ids=evidence_ids,
            idempotency_key=new_command_key("dossier-contribute"),
        )
        self.sync()
        return build_mutation_result_packet(
            operation="dossier_contribute",
            confirmed=True,
            result=result,
        )

    def dossier_cite_artifact(
        self,
        *,
        artifact_id: str,
        claim: str,
        quote: str,
        confirm: bool,
        crew_id: str | None = None,
    ) -> RenderPacket:
        target_crew_id = self._target_crew_id(crew_id)
        preview = {
            "crew_id": target_crew_id,
            "artifact_id": artifact_id,
            "claim": claim,
            "quote": quote,
        }
        if not confirm:
            return build_mutation_result_packet(
                operation="dossier_cite_artifact",
                confirmed=False,
                preview_fields=preview,
            )
        result = self.api.cite_artifact_in_dossier(
            crew_id=target_crew_id,
            artifact_id=artifact_id,
            claim=claim,
            quote=quote,
            idempotency_key=new_command_key("dossier-cite-artifact"),
        )
        self.sync()
        return build_mutation_result_packet(
            operation="dossier_cite_artifact",
            confirmed=True,
            result=result,
        )

    def propose_deal(
        self,
        *,
        recipient_crew_id: str,
        offered_artifact_ids: list[str] | tuple[str, ...],
        requested_artifact_ids: list[str] | tuple[str, ...],
        confirm: bool,
        proposer_crew_id: str | None = None,
        contract_id: str = "contract_false_finger",
        soft_terms: list[str] | tuple[str, ...] | None = None,
        expires_phase: str | None = None,
    ) -> RenderPacket:
        target_proposer_crew_id = self._target_crew_id(proposer_crew_id)
        preview = {
            "contract_id": contract_id,
            "proposer_crew_id": target_proposer_crew_id,
            "recipient_crew_id": recipient_crew_id,
            "offered_artifact_ids": list(offered_artifact_ids),
            "requested_artifact_ids": list(requested_artifact_ids),
            "soft_terms": list(soft_terms or []),
            "expires_phase": expires_phase,
        }
        if not confirm:
            return build_mutation_result_packet(
                operation="propose_deal",
                confirmed=False,
                preview_fields=preview,
            )
        result = self.api.propose_deal(
            contract_id=contract_id,
            proposer_crew_id=target_proposer_crew_id,
            recipient_crew_id=recipient_crew_id,
            offered_artifact_ids=offered_artifact_ids,
            requested_artifact_ids=requested_artifact_ids,
            soft_terms=soft_terms or [],
            expires_phase=expires_phase,
            idempotency_key=new_command_key("deal-propose"),
        )
        self.sync()
        return build_mutation_result_packet(
            operation="propose_deal",
            confirmed=True,
            result=result,
        )

    def accept_deal(self, *, deal_id: str, confirm: bool) -> RenderPacket:
        if not confirm:
            return self.preview_deal_acceptance(deal_id)
        result = self.api.accept_deal(
            deal_id=deal_id,
            idempotency_key=new_command_key("deal-accept"),
        )
        self.sync()
        return build_mutation_result_packet(
            operation="accept_deal",
            confirmed=True,
            result=result,
        )

    def transfer_artifact(
        self,
        *,
        artifact_id: str,
        recipient_player_id: str,
        confirm: bool,
    ) -> RenderPacket:
        preview = {
            "artifact_id": artifact_id,
            "recipient_player_id": recipient_player_id,
        }
        if not confirm:
            return build_mutation_result_packet(
                operation="transfer_artifact",
                confirmed=False,
                preview_fields=preview,
            )
        result = self.api.transfer_artifact(
            artifact_id=artifact_id,
            recipient_player_id=recipient_player_id,
            idempotency_key=new_command_key("artifact-transfer"),
        )
        self.sync()
        return build_mutation_result_packet(
            operation="transfer_artifact",
            confirmed=True,
            result=result,
        )

    def vote_packet_lead(
        self,
        *,
        player_id: str,
        confirm: bool,
        crew_id: str | None = None,
    ) -> RenderPacket:
        target_crew_id = self._target_crew_id(crew_id)
        if not confirm:
            return build_mutation_result_packet(
                operation="vote_packet_lead",
                confirmed=False,
                preview_fields={"crew_id": target_crew_id, "player_id": player_id},
            )
        result = self.api.vote_packet_lead(
            crew_id=target_crew_id,
            player_id=player_id,
            idempotency_key=new_command_key("packet-lead-vote"),
        )
        self.sync()
        return build_mutation_result_packet(
            operation="vote_packet_lead",
            confirmed=True,
            result=result,
        )

    def phase_lock(
        self,
        *,
        contract_id: str = "contract_false_finger",
        hours_elapsed: int = 6,
        confirm: bool,
    ) -> RenderPacket:
        if not confirm:
            contract = _contract_for_preview(self.api.contracts(), contract_id)
            phase = contract.get("phase", {})
            return build_mutation_result_packet(
                operation="phase_lock",
                confirmed=False,
                preview_fields={
                    "contract_id": contract.get("contract_id", contract_id),
                    "title": contract.get("title"),
                    "phase": phase.get("name", "Auction Preview"),
                    "remaining_hours": phase.get("remaining_hours"),
                    "hours_elapsed": hours_elapsed,
                },
            )
        result = self.api.lock_auction_preview_phase(
            contract_id=contract_id,
            hours_elapsed=hours_elapsed,
            idempotency_key=new_command_key("phase-lock"),
        )
        self.sync()
        return build_mutation_result_packet(
            operation="phase_lock",
            confirmed=True,
            result={
                **result,
                "contract_id": contract_id,
                "phase": result.get("phase", "auction-preview"),
            },
        )

    def _refresh_display_name(self) -> None:
        if self.config.display_name or not hasattr(self.api, "me"):
            return
        identity = self.api.me()
        if identity.get("player_id") != self.config.player_id:
            return
        display_name = identity.get("display_name")
        if not display_name:
            return
        self.config = self.config.model_copy(update={"display_name": display_name})
        save_config(self.config_path, self.config)

    def _target_crew_id(self, crew_id: str | None) -> str:
        target_crew_id = crew_id or self.config.active_crew_id
        if target_crew_id is None:
            raise ValueError("crew id required when no active crew is configured")
        return target_crew_id

    def _visible_server_events(self) -> list[dict[str, Any]]:
        return [
            event
            for event in self.local_log.read()
            if event.get("origin") == "server"
        ]


def _contract_for_preview(board: dict[str, Any], contract_id: str) -> dict[str, Any]:
    contracts = board.get("contracts", [])
    for contract in contracts:
        if contract.get("contract_id") == contract_id:
            return contract
    if len(contracts) == 1:
        return contracts[0]
    raise ValueError("contract not found")
