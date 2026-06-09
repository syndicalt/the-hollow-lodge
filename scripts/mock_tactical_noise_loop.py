from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app

from scripts.mock_full_game_loop import _codex_session, _create_crew, _register


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="hollow-lodge-tactical-noise-") as data_dir:
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

    first_action = session.submit_action(
        crew_id=crew["crew_id"],
        intent="Quietly inspect the ledger provenance date against the chapel timestamp.",
        confirm=True,
    )
    second_action = session.submit_action(
        crew_id=crew["crew_id"],
        intent="Pressure the auction clerk about the forged provenance correction.",
        confirm=True,
    )
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
        "resolution": resolved.model_dump(mode="json"),
        "contract_board": contract_board.model_dump(mode="json"),
        "activity": activity.model_dump(mode="json"),
        "lines": [
            "first action:",
            first_action.player_markdown,
            "second action:",
            second_action.player_markdown,
            "resolution:",
            resolved.player_markdown,
            "contract board:",
            contract_board.player_markdown,
            "activity:",
            activity.player_markdown,
        ],
    }


if __name__ == "__main__":
    main()
