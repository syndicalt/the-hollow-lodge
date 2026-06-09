from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from hollow_lodge.client.codex_session import CodexGameSession
from hollow_lodge.client.config import ClientConfig, save_config
from hollow_lodge.server.app import create_app

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.mock_full_game_loop import (
    _TestClientCodexApi,
    _auth,
    _create_crew,
    _get,
    _join_crew,
    _register,
)


class _ProofFragmentCodexApi(_TestClientCodexApi):
    def proof_fragment(self, *, fragment_id: str) -> dict[str, Any]:
        return self._get(f"/proofs/fragments/{fragment_id}")

    def transfer_proof_fragment(
        self,
        *,
        fragment_id: str,
        recipient_player_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._post(
            f"/proofs/fragments/{fragment_id}/transfer",
            json={"recipient_player_id": recipient_player_id},
            idempotency_key=idempotency_key,
        )

    def check_provenance(self, *, fragment_id: str, idempotency_key: str) -> dict[str, Any]:
        return self._post(
            f"/proofs/fragments/{fragment_id}/check/provenance",
            json={},
            idempotency_key=idempotency_key,
        )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="hollow-lodge-proof-fragment-") as data_dir:
        result = run_mock(data_dir)
    for line in result["lines"]:
        print(line)


def run_mock(data_dir: str) -> dict[str, Any]:
    client = TestClient(create_app(data_dir=data_dir, invite_codes=["ada", "grace"]))
    ada = _register(client, "ada", "Ada Corelumen")
    grace = _register(client, "grace", "Grace Ledger")
    crew = _create_crew(client, ada, "The Gilt Knives", "crew-gilt")
    _join_crew(client, grace, crew, "crew-join-grace")
    ada_session = _codex_session(
        client,
        data_dir=Path(data_dir),
        player=ada,
        active_crew_id=crew["crew_id"],
    )
    grace_session = _codex_session(
        client,
        data_dir=Path(data_dir),
        player=grace,
        active_crew_id=crew["crew_id"],
    )

    transfer_preview = ada_session.transfer_proof_fragment(
        fragment_id="fragment_starter_ledger",
        recipient_player_id=grace["player_id"],
        confirm=False,
    )
    transferred = ada_session.transfer_proof_fragment(
        fragment_id="fragment_starter_ledger",
        recipient_player_id=grace["player_id"],
        confirm=True,
    )
    copied_fragment_id = transferred.agent_context["result"]["fragment_id"]
    grace_inbox = grace_session.render_inbox()
    fragment_before_check = grace_session.render_proof_fragment(copied_fragment_id)
    provenance_preview = grace_session.check_provenance(
        fragment_id=copied_fragment_id,
        confirm=False,
    )
    provenance = grace_session.check_provenance(
        fragment_id=copied_fragment_id,
        confirm=True,
    )
    fragment_after_check = grace_session.render_proof_fragment(copied_fragment_id)
    contribution_preview = grace_session.dossier_contribute(
        crew_id=crew["crew_id"],
        note="Ledger provenance flags show the copied hand and later ink.",
        evidence_ids=[copied_fragment_id],
        confirm=False,
    )
    contribution = grace_session.dossier_contribute(
        crew_id=crew["crew_id"],
        note="Ledger provenance flags show the copied hand and later ink.",
        evidence_ids=[copied_fragment_id],
        confirm=True,
    )
    dossier = grace_session.render_dossier(crew_id=crew["crew_id"])
    activity = grace_session.render_activity()
    grace_events = _get(client, "/events", headers=_auth(grace["token"]))

    return {
        "crew_id": crew["crew_id"],
        "recipient_player_id": grace["player_id"],
        "copied_fragment_id": copied_fragment_id,
        "transfer_preview": transfer_preview.model_dump(mode="json"),
        "transferred": transferred.model_dump(mode="json"),
        "grace_inbox": grace_inbox.model_dump(mode="json"),
        "fragment_before_check": fragment_before_check.model_dump(mode="json"),
        "provenance_preview": provenance_preview.model_dump(mode="json"),
        "provenance": provenance.model_dump(mode="json"),
        "fragment_after_check": fragment_after_check.model_dump(mode="json"),
        "contribution_preview": contribution_preview.model_dump(mode="json"),
        "contribution": contribution.model_dump(mode="json"),
        "dossier": dossier.model_dump(mode="json"),
        "activity": activity.model_dump(mode="json"),
        "grace_events": grace_events,
        "lines": [
            "transfer preview:",
            transfer_preview.player_markdown,
            "transfer confirmed:",
            transferred.player_markdown,
            "grace inbox:",
            grace_inbox.player_markdown,
            "fragment before provenance check:",
            fragment_before_check.player_markdown,
            "provenance preview:",
            provenance_preview.player_markdown,
            "provenance confirmed:",
            provenance.player_markdown,
            "fragment after provenance check:",
            fragment_after_check.player_markdown,
            "contribution preview:",
            contribution_preview.player_markdown,
            "contribution confirmed:",
            contribution.player_markdown,
            "dossier:",
            dossier.player_markdown,
            "activity:",
            activity.player_markdown,
        ],
    }


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
        api=_ProofFragmentCodexApi(client, player["token"]),
    )


if __name__ == "__main__":
    main()
