from __future__ import annotations

from pathlib import Path
from typing import Any

from hollow_lodge.client.api import HollowLodgeApi
from hollow_lodge.client.artifact_render import (
    build_artifact_graph_packet,
    build_artifact_packet,
)
from hollow_lodge.client.config import ClientConfig, load_config, save_config
from hollow_lodge.client.local_log import LocalEventLog
from hollow_lodge.client.paths import DEFAULT_CONFIG_PATH, DEFAULT_LOCAL_LOG_PATH
from hollow_lodge.client.render_packets import (
    RenderPacket,
    build_activity_summary_packet,
    build_deal_acceptance_preview_packet,
    build_deals_packet,
    build_contract_board_packet,
    build_crew_board_packet,
    build_inbox_packet,
    build_thread_packet,
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

    def render_contract_board(self) -> RenderPacket:
        self.sync()
        return build_contract_board_packet(self.api.contracts())

    def render_crew_board(self, crew_id: str | None = None) -> RenderPacket:
        self.sync()
        target_crew_id = crew_id or self.config.active_crew_id
        if target_crew_id is None:
            raise ValueError("crew id required when no active crew is configured")
        return build_crew_board_packet(self.api.crew_board(crew_id=target_crew_id))

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

    def render_thread(self, conversation_id: str) -> RenderPacket:
        self.sync()
        return build_thread_packet(
            self._visible_server_events(),
            conversation_id=conversation_id,
        )

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

    def _visible_server_events(self) -> list[dict[str, Any]]:
        return [
            event
            for event in self.local_log.read()
            if event.get("origin") == "server"
        ]
