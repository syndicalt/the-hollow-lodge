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
    client = TestClient(create_app(data_dir=data_dir, invite_codes=["ada", "bela"]))
    ada = _register(client, "ada", "Ada Corelumen")
    bela = _register(client, "bela", "Bela Moth")
    gilt = _create_crew(client, ada, "The Gilt Knives", "crew-gilt")
    moth = _create_crew(client, bela, "The Moth Lanterns", "crew-moth")
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
    _post(
        client,
        "/artifacts/artifact_ledger_rubric/inspect",
        headers=_command_auth(ada["token"], "inspect-ledger"),
        json={},
        expected_status=200,
    )
    client.app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="mock side action unlock",
        idempotency_key="grant-chapel-to-moth",
    )

    proposed = _post(
        client,
        "/deals",
        headers=_command_auth(ada["token"], "deal-propose-ledger-for-chapel"),
        json={
            "contract_id": "contract_false_finger",
            "proposer_crew_id": gilt["crew_id"],
            "recipient_crew_id": moth["crew_id"],
            "offered_artifact_ids": ["artifact_ledger_rubric"],
            "requested_artifact_ids": ["artifact_chapel_debt_mark"],
            "soft_terms": ["Do not cite our crew as source until Auction Lock."],
            "expires_phase": "Auction Preview",
        },
        expected_status=201,
    )
    deals_packet = ada_session.render_deals()
    deal_preview_packet = ada_session.preview_deal_acceptance(proposed["deal_id"])
    moth_inbox_packet = bela_session.render_inbox()
    fulfilled = _post(
        client,
        f"/deals/{proposed['deal_id']}/accept",
        headers=_command_auth(bela["token"], "deal-accept-ledger-for-chapel"),
        json={},
        expected_status=200,
    )
    gilt_received = fulfilled["proposer_received_artifact_ids"][0]
    moth_received = fulfilled["recipient_received_artifact_ids"][0]
    _get(client, f"/artifacts/{gilt_received}", headers=ada_headers)
    _get(client, f"/artifacts/{moth_received}", headers=bela_headers)

    _post(
        client,
        f"/proofs/dossiers/{gilt['crew_id']}/artifact-citations",
        headers=_command_auth(ada["token"], "cite-gilt-received-chapel"),
        json={
            "artifact_id": gilt_received,
            "claim": "The chapel debt mark exposes leverage against the lot story.",
            "quote": "Debt mark",
        },
        expected_status=201,
    )
    _post(
        client,
        f"/proofs/dossiers/{moth['crew_id']}/artifact-citations",
        headers=_command_auth(bela["token"], "cite-moth-received-ledger"),
        json={
            "artifact_id": moth_received,
            "claim": "The red ledger rubric contradicts the clean provenance chain.",
            "quote": "redder and later",
        },
        expected_status=201,
    )
    _patch(
        client,
        f"/proofs/dossiers/{gilt['crew_id']}/framing",
        headers=_command_auth(ada["token"], "gilt-framing"),
        json={
            "claim": "The finger is a false relic backed by a compromised chain.",
            "reasoning": "The chapel debt mark gives motive; the ledger undermines clean provenance.",
            "weaknesses": "Material testing remains incomplete.",
            "provenance_concerns": "Traded copy, but source chain names the deal provenance.",
        },
    )
    _patch(
        client,
        f"/proofs/dossiers/{moth['crew_id']}/framing",
        headers=_command_auth(bela["token"], "moth-framing"),
        json={
            "claim": "The reliquary story is unstable and politically leveraged.",
            "reasoning": "The ledger and chapel mark support pressure around the auction.",
            "weaknesses": "The Gilt source may have traded selectively.",
            "provenance_concerns": "Received copy requires independent verification.",
        },
    )

    gilt_action = _post(
        client,
        "/actions",
        headers=_command_auth(ada["token"], "gilt-action-after-trade"),
        json={
            "crew_id": gilt["crew_id"],
            "intent": "Use the chapel debt mark to pressure the auction clerk for the corrected lot note.",
            "confirmed": True,
        },
        expected_status=201,
    )
    moth_action = _post(
        client,
        "/actions",
        headers=_command_auth(bela["token"], "moth-action-after-trade"),
        json={
            "crew_id": moth["crew_id"],
            "intent": "Compare the red ledger rubric against the moth jar omen without revealing the Gilt source.",
            "confirmed": True,
        },
        expected_status=201,
    )
    gilt_board = _get(client, f"/crews/{gilt['crew_id']}/board", headers=ada_headers)
    moth_board = _get(client, f"/crews/{moth['crew_id']}/board", headers=bela_headers)
    gilt_board_packet = ada_session.render_crew_board()
    final_dossier_packet = ada_session.render_dossier()
    reveal = _post(
        client,
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=_command_auth(ada["token"], "phase-lock-after-escrow"),
        json={"hours_elapsed": 6},
        expected_status=200,
    )
    final_what_now_packet = ada_session.render_what_now()
    final_contract_packet = ada_session.render_contract_board()
    final_crew_activity_packet = ada_session.render_crew_activity()
    final_activity_packet = ada_session.render_activity()
    codex_packets = [
        initial_contract_packet,
        initial_artifact_packet,
        deals_packet,
        deal_preview_packet,
        moth_inbox_packet,
        gilt_board_packet,
        final_dossier_packet,
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
    lines = [
        f"contract: {contract_board['contracts'][0]['title']} / {contract_board['contracts'][0]['phase']['name']}",
        "initial contract board:",
        initial_contract_packet.player_markdown,
        "initial artifact graph:",
        initial_artifact_packet.player_markdown,
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
        "timeline": timeline,
        "codex_packets": [packet.surface for packet in codex_packets],
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

    def deals(self) -> dict[str, Any]:
        return self._get("/deals")

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


def _patch(
    client: TestClient,
    path: str,
    *,
    json: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any]:
    response = client.patch(path, json=json, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"PATCH {path} returned {response.status_code}: {response.text}")
    return response.json()


if __name__ == "__main__":
    main()
