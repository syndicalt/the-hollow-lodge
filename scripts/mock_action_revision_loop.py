from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from hollow_lodge.client.codex_session import CodexGameSession
from hollow_lodge.client.config import ClientConfig, save_config
from hollow_lodge.server.app import create_app

from scripts.mock_full_game_loop import (
    _TestClientCodexApi,
    _command_auth,
    _create_crew,
    _register,
)


class _ActionRevisionCodexApi(_TestClientCodexApi):
    def edit_action(
        self,
        *,
        action_id: str,
        intent: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        response = self.client.patch(
            f"/actions/{action_id}",
            json={"intent": intent},
            headers=_command_auth(self.token, idempotency_key),
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"PATCH /actions/{action_id} returned "
                f"{response.status_code}: {response.text}"
            )
        return response.json()

    def cancel_action(self, *, action_id: str, idempotency_key: str) -> dict[str, Any]:
        response = self.client.delete(
            f"/actions/{action_id}",
            headers=_command_auth(self.token, idempotency_key),
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"DELETE /actions/{action_id} returned "
                f"{response.status_code}: {response.text}"
            )
        return response.json()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="hollow-lodge-action-revision-") as data_dir:
        result = run_mock(data_dir)
    for line in result["lines"]:
        print(line)


def run_mock(data_dir: str) -> dict[str, Any]:
    client = TestClient(create_app(data_dir=data_dir, invite_codes=["ada"]))
    ada = _register(client, "ada", "Ada Corelumen")
    crew = _create_crew(client, ada, "The Gilt Knives", "crew-gilt")
    session = _codex_session(
        client,
        data_dir=Path(data_dir),
        player=ada,
        active_crew_id=crew["crew_id"],
    )
    observer = _codex_session(
        client,
        data_dir=Path(data_dir) / "observer",
        player=ada,
        active_crew_id=crew["crew_id"],
    )

    first_action = session.submit_action(
        crew_id=crew["crew_id"],
        intent="Inspect the ledger entry under candlelight without drawing a source conclusion.",
        confirm=True,
    )
    second_action = session.submit_action(
        crew_id=crew["crew_id"],
        intent="Pressure the auction clerk loudly about the debt mark.",
        confirm=True,
    )
    pre_revision_board = observer.render_crew_board(crew_id=crew["crew_id"])
    edited_preview = session.edit_action(
        action_id="action_000001",
        intent="Inspect the ledger for forged provenance before the chapel timestamp.",
        confirm=False,
    )
    edited = session.edit_action(
        action_id="action_000001",
        intent="Inspect the ledger for forged provenance before the chapel timestamp.",
        confirm=True,
    )
    canceled_preview = session.cancel_action(
        action_id="action_000002",
        confirm=False,
    )
    canceled = session.cancel_action(
        action_id="action_000002",
        confirm=True,
    )
    revision_delta = observer.render_activity_delta()
    post_revision_board = session.render_crew_board(crew_id=crew["crew_id"])
    resolved = session.phase_lock(
        contract_id="contract_false_finger",
        hours_elapsed=6,
        confirm=True,
    )
    contract_board = session.render_contract_board()
    activity = session.render_activity()

    return {
        "crew_id": crew["crew_id"],
        "first_action": first_action.model_dump(mode="json"),
        "second_action": second_action.model_dump(mode="json"),
        "pre_revision_board": pre_revision_board.model_dump(mode="json"),
        "edited_preview": edited_preview.model_dump(mode="json"),
        "edited": edited.model_dump(mode="json"),
        "canceled_preview": canceled_preview.model_dump(mode="json"),
        "canceled": canceled.model_dump(mode="json"),
        "revision_delta": revision_delta.model_dump(mode="json"),
        "post_revision_board": post_revision_board.model_dump(mode="json"),
        "resolution": resolved.model_dump(mode="json"),
        "contract_board": contract_board.model_dump(mode="json"),
        "activity": activity.model_dump(mode="json"),
        "lines": [
            "pre-revision crew board:",
            pre_revision_board.player_markdown,
            "edit preview:",
            edited_preview.player_markdown,
            "edit confirmed:",
            edited.player_markdown,
            "cancel preview:",
            canceled_preview.player_markdown,
            "cancel confirmed:",
            canceled.player_markdown,
            "revision delta:",
            revision_delta.player_markdown,
            "post-revision crew board:",
            post_revision_board.player_markdown,
            "resolution:",
            resolved.player_markdown,
            "contract board:",
            contract_board.player_markdown,
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
    data_dir.mkdir(parents=True, exist_ok=True)
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
        api=_ActionRevisionCodexApi(client, player["token"]),
    )


if __name__ == "__main__":
    main()
