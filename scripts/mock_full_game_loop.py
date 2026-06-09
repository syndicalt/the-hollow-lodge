from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from hollow_lodge.client.codex_session import CodexGameSession
from hollow_lodge.client.config import ClientConfig, save_config
from hollow_lodge.server.app import create_app


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="hollow-lodge-full-loop-") as data_dir:
        result = run_mock(data_dir)
    for line in result["lines"]:
        print(line)


def run_mock(data_dir: str) -> dict[str, Any]:
    client = TestClient(
        create_app(data_dir=data_dir, invite_codes=["ada", "bela", "grace"])
    )
    ada = _register(client, "ada", "Ada Corelumen")
    bela = _register(client, "bela", "Bela Moth")
    grace = _register(client, "grace", "Grace Ledger")
    gilt = _create_crew(client, ada, "The Gilt Knives", "crew-gilt")
    moth = _create_crew(client, bela, "The Moth Lanterns", "crew-moth")
    _join_crew(client, grace, gilt, "crew-join-grace-gilt")
    ada_headers = _auth(ada["token"])
    bela_headers = _auth(bela["token"])
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

    contract_board = _get(client, "/contracts", headers=ada_headers)
    initial_contract_packet = ada_session.render_contract_board()
    initial_artifact_packet = ada_session.render_artifacts()
    artifact_inspect_preview = ada_session.inspect_artifact(
        artifact_id="artifact_ledger_rubric",
        confirm=False,
    )
    artifact_inspect_packet = ada_session.inspect_artifact(
        artifact_id="artifact_ledger_rubric",
        confirm=True,
    )
    client.app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="mock side action unlock",
        idempotency_key="grant-chapel-to-moth",
    )
    opening_message_preview = ada_session.send_message(
        scope="crew_to_crew",
        sender_crew_id=gilt["crew_id"],
        recipient_crew_id=moth["crew_id"],
        body="We can trade ledger leverage for chapel access before lock.",
        confirm=False,
    )
    opening_message = ada_session.send_message(
        scope="crew_to_crew",
        sender_crew_id=gilt["crew_id"],
        recipient_crew_id=moth["crew_id"],
        body="We can trade ledger leverage for chapel access before lock.",
        confirm=True,
    )
    reply_message_preview = bela_session.send_message(
        scope="crew_to_crew",
        sender_crew_id=moth["crew_id"],
        recipient_crew_id=gilt["crew_id"],
        body="Send the ledger copy first; no public source claims until lock.",
        confirm=False,
    )
    reply_message = bela_session.send_message(
        scope="crew_to_crew",
        sender_crew_id=moth["crew_id"],
        recipient_crew_id=gilt["crew_id"],
        body="Send the ledger copy first; no public source claims until lock.",
        confirm=True,
    )
    conversations_packet = ada_session.render_conversations()

    deal_preview = ada_session.propose_deal(
        recipient_crew_id=moth["crew_id"],
        offered_artifact_ids=["artifact_ledger_rubric"],
        requested_artifact_ids=["artifact_chapel_debt_mark"],
        confirm=False,
        proposer_crew_id=gilt["crew_id"],
        contract_id="contract_false_finger",
        soft_terms=["Do not cite our crew as source until Auction Lock."],
        expires_phase="Auction Preview",
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
    deals_packet = ada_session.render_deals()
    deal_preview_packet = ada_session.preview_deal_acceptance(proposed["deal_id"])
    moth_inbox_packet = bela_session.render_inbox()
    deal_accept_preview = bela_session.accept_deal(
        deal_id=proposed["deal_id"],
        confirm=False,
    )
    fulfilled_packet = bela_session.accept_deal(
        deal_id=proposed["deal_id"],
        confirm=True,
    )
    fulfilled = fulfilled_packet.agent_context["result"]
    gilt_received = fulfilled["proposer_received_artifact_ids"][0]
    moth_received = fulfilled["recipient_received_artifact_ids"][0]
    _get(client, f"/artifacts/{gilt_received}", headers=ada_headers)
    _get(client, f"/artifacts/{moth_received}", headers=bela_headers)

    gilt_citation_preview = ada_session.dossier_cite_artifact(
        artifact_id=gilt_received,
        claim="The chapel debt mark exposes leverage against the lot story.",
        quote="Debt mark",
        confirm=False,
        crew_id=gilt["crew_id"],
    )
    gilt_citation_packet = ada_session.dossier_cite_artifact(
        artifact_id=gilt_received,
        claim="The chapel debt mark exposes leverage against the lot story.",
        quote="Debt mark",
        confirm=True,
        crew_id=gilt["crew_id"],
    )
    moth_citation_preview = bela_session.dossier_cite_artifact(
        artifact_id=moth_received,
        claim="The red ledger rubric contradicts the clean provenance chain.",
        quote="redder and later",
        confirm=False,
        crew_id=moth["crew_id"],
    )
    moth_citation_packet = bela_session.dossier_cite_artifact(
        artifact_id=moth_received,
        claim="The red ledger rubric contradicts the clean provenance chain.",
        quote="redder and later",
        confirm=True,
        crew_id=moth["crew_id"],
    )
    gilt_framing_preview = ada_session.dossier_update_framing(
        claim="The finger is a false relic backed by a compromised chain.",
        reasoning="The chapel debt mark gives motive; the ledger undermines clean provenance.",
        weaknesses="Material testing remains incomplete.",
        provenance_concerns="Traded copy, but source chain names the deal provenance.",
        confirm=False,
        crew_id=gilt["crew_id"],
    )
    gilt_framing_packet = ada_session.dossier_update_framing(
        claim="The finger is a false relic backed by a compromised chain.",
        reasoning="The chapel debt mark gives motive; the ledger undermines clean provenance.",
        weaknesses="Material testing remains incomplete.",
        provenance_concerns="Traded copy, but source chain names the deal provenance.",
        confirm=True,
        crew_id=gilt["crew_id"],
    )
    moth_framing_preview = bela_session.dossier_update_framing(
        claim="The reliquary story is unstable and politically leveraged.",
        reasoning="The ledger and chapel mark support pressure around the auction.",
        weaknesses="The Gilt source may have traded selectively.",
        provenance_concerns="Received copy requires independent verification.",
        confirm=False,
        crew_id=moth["crew_id"],
    )
    moth_framing_packet = bela_session.dossier_update_framing(
        claim="The reliquary story is unstable and politically leveraged.",
        reasoning="The ledger and chapel mark support pressure around the auction.",
        weaknesses="The Gilt source may have traded selectively.",
        provenance_concerns="Received copy requires independent verification.",
        confirm=True,
        crew_id=moth["crew_id"],
    )
    grace_session = _codex_session(
        client,
        data_dir=Path(data_dir),
        player=grace,
        active_crew_id=gilt["crew_id"],
    )
    grace_vote_preview = grace_session.vote_packet_lead(
        player_id=grace["player_id"],
        confirm=False,
        crew_id=gilt["crew_id"],
    )
    grace_vote_packet = grace_session.vote_packet_lead(
        player_id=grace["player_id"],
        confirm=True,
        crew_id=gilt["crew_id"],
    )
    ada_vote_preview = ada_session.vote_packet_lead(
        player_id=grace["player_id"],
        confirm=False,
        crew_id=gilt["crew_id"],
    )
    ada_vote_packet = ada_session.vote_packet_lead(
        player_id=grace["player_id"],
        confirm=True,
        crew_id=gilt["crew_id"],
    )

    gilt_action_preview = ada_session.submit_action(
        crew_id=gilt["crew_id"],
        intent="Use the chapel debt mark to pressure the auction clerk for the corrected lot note.",
        confirm=False,
    )
    gilt_action_packet = ada_session.submit_action(
        crew_id=gilt["crew_id"],
        intent="Use the chapel debt mark to pressure the auction clerk for the corrected lot note.",
        confirm=True,
    )
    moth_action_preview = bela_session.submit_action(
        crew_id=moth["crew_id"],
        intent="Compare the red ledger rubric against the moth jar omen without revealing the Gilt source.",
        confirm=False,
    )
    moth_action_packet = bela_session.submit_action(
        crew_id=moth["crew_id"],
        intent="Compare the red ledger rubric against the moth jar omen without revealing the Gilt source.",
        confirm=True,
    )
    gilt_action = gilt_action_packet.agent_context["result"]
    moth_action = moth_action_packet.agent_context["result"]
    gilt_board = _get(client, f"/crews/{gilt['crew_id']}/board", headers=ada_headers)
    moth_board = _get(client, f"/crews/{moth['crew_id']}/board", headers=bela_headers)
    gilt_board_packet = ada_session.render_crew_board()
    final_dossier_packet = ada_session.render_dossier()
    phase_lock_preview = ada_session.phase_lock(
        contract_id="contract_false_finger",
        hours_elapsed=6,
        confirm=False,
    )
    phase_lock_packet = ada_session.phase_lock(
        contract_id="contract_false_finger",
        hours_elapsed=6,
        confirm=True,
    )
    reveal = phase_lock_packet.agent_context["result"]
    final_activity_delta_packet = bela_session.render_activity_delta()
    final_what_now_packet = ada_session.render_what_now()
    final_contract_packet = ada_session.render_contract_board()
    final_crew_activity_packet = ada_session.render_crew_activity()
    final_activity_packet = ada_session.render_activity()
    codex_packets = [
        initial_contract_packet,
        initial_artifact_packet,
        artifact_inspect_preview,
        artifact_inspect_packet,
        opening_message_preview,
        opening_message,
        reply_message_preview,
        reply_message,
        conversations_packet,
        deal_preview,
        proposed_packet,
        deals_packet,
        deal_preview_packet,
        moth_inbox_packet,
        deal_accept_preview,
        fulfilled_packet,
        gilt_citation_preview,
        gilt_citation_packet,
        moth_citation_preview,
        moth_citation_packet,
        gilt_framing_preview,
        gilt_framing_packet,
        moth_framing_preview,
        moth_framing_packet,
        grace_vote_preview,
        grace_vote_packet,
        ada_vote_preview,
        ada_vote_packet,
        gilt_action_preview,
        gilt_action_packet,
        moth_action_preview,
        moth_action_packet,
        gilt_board_packet,
        final_dossier_packet,
        phase_lock_preview,
        phase_lock_packet,
        final_activity_delta_packet,
        final_what_now_packet,
        final_contract_packet,
        final_crew_activity_packet,
        final_activity_packet,
    ]

    timeline = [
        event.type
        for event in client.app.state.event_store.read()
        if event.type.startswith("deal.") or event.type.startswith("artifact.deal_copied")
    ]
    opening_message_result = opening_message.agent_context["result"]
    reply_message_result = reply_message.agent_context["result"]
    codex_mutation_packets = [
        packet
        for packet in codex_packets
        if packet.surface == "mutation"
    ]
    codex_mutations = [
        {
            "operation": packet.agent_context["operation"],
            "confirmed": packet.agent_context["confirmed"],
        }
        for packet in codex_mutation_packets
    ]
    lines = [
        f"contract: {contract_board['contracts'][0]['title']} / {contract_board['contracts'][0]['phase']['name']}",
        "initial contract board:",
        initial_contract_packet.player_markdown,
        "initial artifact graph:",
        initial_artifact_packet.player_markdown,
        (
            "messages exchanged: "
            f"{opening_message_result['conversation_id']} / "
            f"{reply_message_result['conversation_id']}"
        ),
        (
            "codex mutation previews/confirms: "
            + ", ".join(
                f"{mutation['operation']}:{'confirm' if mutation['confirmed'] else 'preview'}"
                for mutation in codex_mutations
            )
        ),
        "visible conversations:",
        conversations_packet.player_markdown,
        f"deal proposed: {proposed['deal_id']} {proposed['status']}",
        "visible deals:",
        deals_packet.player_markdown,
        "deal preview:",
        deal_preview_packet.player_markdown,
        "moth inbox:",
        moth_inbox_packet.player_markdown,
        f"deal accepted: {fulfilled['deal_id']} {fulfilled['status']}",
        f"gilt received: {gilt_received}",
        f"moth received: {moth_received}",
        f"actions submitted: {gilt_action['action_id']} {moth_action['action_id']}",
        f"gilt board deals: {', '.join(deal['status'] for deal in gilt_board['deals'])}",
        f"moth board deals: {', '.join(deal['status'] for deal in moth_board['deals'])}",
        "gilt board excerpt:",
        "\n".join(gilt_board_packet.player_markdown.splitlines()[:18]),
        "gilt dossier excerpt:",
        "\n".join(final_dossier_packet.player_markdown.splitlines()[:12]),
        "phase standings:",
        *[
            f"- {standing['crew_id']}: {standing['standing']} ({standing['score']})"
            for standing in reveal["standings"]
        ],
        "activity delta after phase lock:",
        final_activity_delta_packet.player_markdown,
        "final what now:",
        final_what_now_packet.player_markdown,
        "final contract board:",
        final_contract_packet.player_markdown,
        "final crew activity:",
        final_crew_activity_packet.player_markdown,
        "final activity:",
        final_activity_packet.player_markdown,
        f"escrow timeline: {' -> '.join(timeline)}",
    ]
    return {
        "deal": fulfilled,
        "gilt_board": gilt_board,
        "moth_board": moth_board,
        "reveal": reveal,
        "conversations": conversations_packet.model_dump(mode="json"),
        "timeline": timeline,
        "codex_packets": [packet.surface for packet in codex_packets],
        "codex_mutations": codex_mutations,
        "final_dossier": final_dossier_packet.model_dump(mode="json"),
        "final_activity_delta": final_activity_delta_packet.model_dump(mode="json"),
        "final_what_now": final_what_now_packet.model_dump(mode="json"),
        "final_crew_activity": final_crew_activity_packet.model_dump(mode="json"),
        "final_activity": final_activity_packet.model_dump(mode="json"),
        "lines": lines,
    }


class _TestClientCodexApi:
    def __init__(self, client: TestClient, token: str):
        self.client = client
        self.token = token

    def visible_events(self) -> list[dict[str, Any]]:
        return self._get("/events")["events"]

    def visible_events_since(self, *, since_sequence: int) -> list[dict[str, Any]]:
        return self._get(f"/events?since_sequence={since_sequence}")["events"]

    def visible_chat_events(
        self,
        *,
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        path = "/chat/messages"
        if conversation_id is not None:
            path = f"{path}?conversation_id={conversation_id}"
        return self._get(path)["events"]

    def contracts(self) -> dict[str, Any]:
        return self._get("/contracts")

    def inbox(self) -> dict[str, Any]:
        return self._get("/inbox")

    def me(self) -> dict[str, Any]:
        return self._get("/identity/me")

    def profile(self) -> dict[str, Any]:
        return self._get("/identity/profile")

    def crew_board(self, *, crew_id: str) -> dict[str, Any]:
        return self._get(f"/crews/{crew_id}/board")

    def dossier(self, *, crew_id: str) -> dict[str, Any]:
        return self._get(f"/proofs/dossiers/{crew_id}")

    def artifacts(self) -> dict[str, Any]:
        return self._get("/artifacts")

    def artifact(self, *, artifact_id: str) -> dict[str, Any]:
        return self._get(f"/artifacts/{artifact_id}")

    def inspect_artifact(self, *, artifact_id: str, idempotency_key: str) -> dict[str, Any]:
        return self._post(
            f"/artifacts/{artifact_id}/inspect",
            json={},
            idempotency_key=idempotency_key,
        )

    def deals(self) -> dict[str, Any]:
        return self._get("/deals")

    def send_direct_message(
        self,
        *,
        recipient_player_id: str,
        body: str,
        idempotency_key: str,
        artifact_ids: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        return self._post(
            "/chat/direct",
            json={
                "recipient_player_id": recipient_player_id,
                "body": body,
                "artifact_ids": list(artifact_ids or []),
            },
            idempotency_key=idempotency_key,
        )

    def send_crew_message(
        self,
        *,
        crew_id: str,
        body: str,
        idempotency_key: str,
        artifact_ids: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        return self._post(
            "/chat/crew",
            json={
                "crew_id": crew_id,
                "body": body,
                "artifact_ids": list(artifact_ids or []),
            },
            idempotency_key=idempotency_key,
        )

    def send_crew_to_crew_message(
        self,
        *,
        sender_crew_id: str,
        recipient_crew_id: str,
        body: str,
        idempotency_key: str,
        artifact_ids: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        return self._post(
            "/chat/crew-to-crew",
            json={
                "sender_crew_id": sender_crew_id,
                "recipient_crew_id": recipient_crew_id,
                "body": body,
                "artifact_ids": list(artifact_ids or []),
            },
            idempotency_key=idempotency_key,
        )

    def propose_deal(
        self,
        *,
        contract_id: str,
        proposer_crew_id: str,
        recipient_crew_id: str,
        offered_artifact_ids: list[str] | tuple[str, ...],
        requested_artifact_ids: list[str] | tuple[str, ...],
        soft_terms: list[str] | tuple[str, ...],
        expires_phase: str | None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._post(
            "/deals",
            json={
                "contract_id": contract_id,
                "proposer_crew_id": proposer_crew_id,
                "recipient_crew_id": recipient_crew_id,
                "offered_artifact_ids": list(offered_artifact_ids),
                "requested_artifact_ids": list(requested_artifact_ids),
                "soft_terms": list(soft_terms),
                "expires_phase": expires_phase,
            },
            idempotency_key=idempotency_key,
        )

    def accept_deal(self, *, deal_id: str, idempotency_key: str) -> dict[str, Any]:
        return self._post(
            f"/deals/{deal_id}/accept",
            json={},
            idempotency_key=idempotency_key,
        )

    def submit_action(
        self,
        *,
        crew_id: str,
        intent: str,
        idempotency_key: str,
        rumor_id: str | None = None,
        rumor_response_mode: str | None = None,
        responds_to_rumor_escalation: bool = False,
        rumor_escalation_mode: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "crew_id": crew_id,
            "intent": intent,
            "confirmed": True,
        }
        if rumor_id is not None:
            payload["rumor_id"] = rumor_id
        if rumor_response_mode is not None:
            payload["rumor_response_mode"] = rumor_response_mode
        if responds_to_rumor_escalation:
            payload["responds_to_rumor_escalation"] = True
        if rumor_escalation_mode is not None:
            payload["rumor_escalation_mode"] = rumor_escalation_mode
        return self._post(
            "/actions",
            json=payload,
            idempotency_key=idempotency_key,
        )

    def cite_artifact_in_dossier(
        self,
        *,
        crew_id: str,
        artifact_id: str,
        claim: str,
        quote: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._post(
            f"/proofs/dossiers/{crew_id}/artifact-citations",
            json={
                "artifact_id": artifact_id,
                "claim": claim,
                "quote": quote,
            },
            idempotency_key=idempotency_key,
        )

    def update_dossier_framing(
        self,
        *,
        crew_id: str,
        claim: str | None = None,
        evidence_ids: list[str] | tuple[str, ...] | None = None,
        reasoning: str | None = None,
        weaknesses: str | None = None,
        provenance_concerns: str | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if claim is not None:
            payload["claim"] = claim
        if evidence_ids is not None:
            payload["evidence_ids"] = list(evidence_ids)
        if reasoning is not None:
            payload["reasoning"] = reasoning
        if weaknesses is not None:
            payload["weaknesses"] = weaknesses
        if provenance_concerns is not None:
            payload["provenance_concerns"] = provenance_concerns
        response = self.client.patch(
            f"/proofs/dossiers/{crew_id}/framing",
            json=payload,
            headers=_command_auth(self.token, idempotency_key),
        )
        if response.status_code != 200:
            raise RuntimeError(
                "PATCH "
                f"/proofs/dossiers/{crew_id}/framing returned "
                f"{response.status_code}: {response.text}"
            )
        return response.json()

    def vote_packet_lead(
        self,
        *,
        crew_id: str,
        player_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._post(
            f"/proofs/dossiers/{crew_id}/packet-lead/votes",
            json={"candidate_player_id": player_id},
            idempotency_key=idempotency_key,
        )

    def lock_auction_preview_phase(
        self,
        *,
        contract_id: str,
        hours_elapsed: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._post(
            f"/contracts/{contract_id}/phases/auction-preview/lock",
            json={"hours_elapsed": hours_elapsed},
            idempotency_key=idempotency_key,
        )

    def _post(
        self,
        path: str,
        *,
        json: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        response = self.client.post(
            path,
            json=json,
            headers=_command_auth(self.token, idempotency_key),
        )
        if response.status_code not in {200, 201}:
            raise RuntimeError(
                f"POST {path} returned {response.status_code}: {response.text}"
            )
        return response.json()

    def _get(self, path: str) -> dict[str, Any]:
        return _get(self.client, path, headers=_auth(self.token))


def _codex_session(
    client: TestClient,
    *,
    data_dir: Path,
    player: dict[str, Any],
    active_crew_id: str,
) -> CodexGameSession:
    config_path = data_dir / f"{player['player_id']}.config.json"
    local_log_path = data_dir / f"{player['player_id']}.local.jsonl"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id=player["player_id"],
            token=player["token"],
            display_name=player["display_name"],
            active_crew_id=active_crew_id,
        ),
    )
    return CodexGameSession(
        config_path=config_path,
        local_log_path=local_log_path,
        api=_TestClientCodexApi(client, player["token"]),
    )


def _register(client: TestClient, invite: str, name: str) -> dict[str, Any]:
    return _post(
        client,
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
        expected_status=201,
    )


def _create_crew(client: TestClient, player: dict[str, Any], name: str, key: str) -> dict[str, Any]:
    return _post(
        client,
        "/crews",
        json={"name": name},
        headers=_command_auth(player["token"], key),
        expected_status=201,
    )


def _join_crew(
    client: TestClient,
    player: dict[str, Any],
    crew: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    return _post(
        client,
        f"/crews/{crew['crew_id']}/join",
        json={"join_code": crew["join_code"]},
        headers=_command_auth(player["token"], key),
        expected_status=200,
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _command_auth(token: str, key: str) -> dict[str, str]:
    return {**_auth(token), "Idempotency-Key": key}


def _get(client: TestClient, path: str, *, headers: dict[str, str]) -> dict[str, Any]:
    response = client.get(path, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"GET {path} returned {response.status_code}: {response.text}")
    return response.json()


def _post(
    client: TestClient,
    path: str,
    *,
    json: dict[str, Any],
    headers: dict[str, str],
    expected_status: int,
) -> dict[str, Any]:
    response = client.post(path, json=json, headers=headers)
    if response.status_code != expected_status:
        raise RuntimeError(
            f"POST {path} returned {response.status_code}: {response.text}"
        )
    return response.json()


if __name__ == "__main__":
    main()
