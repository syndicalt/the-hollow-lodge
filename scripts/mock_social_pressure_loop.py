from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.mock_full_game_loop import (
    _auth,
    _codex_session,
    _create_crew,
    _register,
)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="hollow-lodge-social-pressure-") as data_dir:
        result = run_mock(data_dir)
    for line in result["lines"]:
        print(line)


def run_mock(data_dir: str) -> dict[str, Any]:
    client = TestClient(
        create_app(data_dir=data_dir, invite_codes=["ada", "bela", "caro"])
    )
    ada = _register(client, "ada", "Ada Corelumen")
    bela = _register(client, "bela", "Bela Moth")
    caro = _register(client, "caro", "Caro Ash")
    gilt = _create_crew(client, ada, "The Gilt Knives", "crew-gilt")
    moth = _create_crew(client, bela, "The Moth Lanterns", "crew-moth")
    ash = _create_crew(client, caro, "The Ash Keys", "crew-ash")
    client.app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="social pressure smoke setup",
        idempotency_key="grant-chapel-to-moth",
    )

    ada_session = _codex_session(
        client,
        data_dir=Path(data_dir),
        player=ada,
        active_crew_id=gilt["crew_id"],
    )
    bela_session = _codex_session(
        client,
        data_dir=Path(data_dir),
        player=bela,
        active_crew_id=moth["crew_id"],
    )
    caro_session = _codex_session(
        client,
        data_dir=Path(data_dir),
        player=caro,
        active_crew_id=ash["crew_id"],
    )

    proposed_packet = ada_session.propose_deal(
        recipient_crew_id=moth["crew_id"],
        offered_artifact_ids=["artifact_ledger_rubric"],
        requested_artifact_ids=["artifact_chapel_debt_mark"],
        confirm=True,
        proposer_crew_id=gilt["crew_id"],
        contract_id="contract_false_finger",
        soft_terms=["Do not cite our crew as source until Auction Lock."],
        expires_phase="Auction Preview",
    )
    proposed = proposed_packet.agent_context["result"]
    bystander_activity_packet = caro_session.render_activity()
    bystander_board_packet = caro_session.render_crew_board()
    bystander_inbox_packet = caro_session.render_inbox()
    rumor_decision = next(
        decision
        for decision in bystander_inbox_packet.agent_context["pending_decisions"]
        if decision["kind"] == "rumor_response"
        and decision["rumor_id"] == f"rumor_{proposed['deal_id']}"
    )
    investigation_preview = caro_session.submit_action(
        crew_id=ash["crew_id"],
        intent="Ask a night clerk whether the side arrangement is real.",
        rumor_id=rumor_decision["rumor_id"],
        confirm=False,
    )
    investigation_packet = caro_session.submit_action(
        crew_id=ash["crew_id"],
        intent="Ask a night clerk whether the side arrangement is real.",
        rumor_id=rumor_decision["rumor_id"],
        confirm=True,
    )
    post_investigation_activity_packet = caro_session.render_activity()
    fulfilled_packet = bela_session.accept_deal(
        deal_id=proposed["deal_id"],
        confirm=True,
    )
    fulfilled = fulfilled_packet.agent_context["result"]
    participant_deals_packet = ada_session.render_deals()
    bystander_deals_packet = caro_session.render_deals()
    bystander_final_board_packet = caro_session.render_crew_board()

    return {
        "deal": fulfilled,
        "proposed_deal": proposed,
        "gilt_crew_id": gilt["crew_id"],
        "moth_crew_id": moth["crew_id"],
        "ash_crew_id": ash["crew_id"],
        "bystander_activity": bystander_activity_packet.model_dump(mode="json"),
        "bystander_board": bystander_board_packet.model_dump(mode="json"),
        "bystander_inbox": bystander_inbox_packet.model_dump(mode="json"),
        "investigation_preview": investigation_preview.model_dump(mode="json"),
        "investigation": investigation_packet.model_dump(mode="json"),
        "post_investigation_activity": post_investigation_activity_packet.model_dump(
            mode="json"
        ),
        "participant_deals": participant_deals_packet.model_dump(mode="json"),
        "bystander_deals": bystander_deals_packet.model_dump(mode="json"),
        "bystander_final_board": bystander_final_board_packet.model_dump(mode="json"),
        "lines": [
            f"deal proposed: {proposed['deal_id']} {proposed['status']}",
            "bystander activity:",
            bystander_activity_packet.player_markdown,
            "bystander inbox:",
            bystander_inbox_packet.player_markdown,
            "bystander crew board:",
            bystander_board_packet.player_markdown,
            "bystander investigation:",
            investigation_packet.player_markdown,
            "bystander activity after investigation:",
            post_investigation_activity_packet.player_markdown,
            f"deal accepted: {fulfilled['deal_id']} {fulfilled['status']}",
            "bystander deals:",
            bystander_deals_packet.player_markdown,
            "participant deals:",
            participant_deals_packet.player_markdown,
        ],
    }


if __name__ == "__main__":
    main()
