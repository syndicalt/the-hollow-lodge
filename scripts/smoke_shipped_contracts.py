from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from hollow_lodge.client.artifact_render import build_artifact_graph_packet
from hollow_lodge.client.render_packets import build_contract_board_packet
from hollow_lodge.server.app import create_app


SHIPPED_CONTRACT_SMOKES = (
    {
        "contract_id": "contract_false_finger",
        "title": "The Saint's False Finger",
        "seed": None,
        "hours_elapsed": 6,
        "crew_actions": (
            "Inspect the chapel mark and ask the auction clerk about the catalogue correction.",
            "Compare the red ledger rubric against the chapel omen.",
        ),
        "artifact_citation": {
            "artifact_id": "artifact_ledger_rubric",
            "claim": "The red ledger rubric contradicts the clean provenance chain.",
            "quote": "The last hand is redder and later than the binding.",
        },
        "hidden_terms": (
            "truth_false_finger_forgery",
            "saint-bone forgery",
            "debtor's omen",
        ),
    },
    {
        "contract_id": "contract_ash_window",
        "title": "The Ash Window",
        "seed": "tests/fixtures/ash_window_contract.json",
        "hours_elapsed": 4,
        "crew_actions": (
            "Follow the ash notice into the soot cooling pattern.",
            "Interview the witness about the recovered window frame.",
        ),
        "artifact_citation": {
            "artifact_id": "artifact_ash_notice",
            "claim": "The ash notice puts recovery before the fire chronology.",
            "quote": "timestamped two hours before the fire",
        },
        "hidden_terms": (
            "truth_ash_window_future_burn",
            "cinder oracle",
            "future-burn",
        ),
    },
)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="hollow-lodge-contract-smokes-") as data_dir:
        result = run_smokes(data_dir)
    for line in result["lines"]:
        print(line)


def run_smokes(data_dir: str) -> dict[str, Any]:
    root = Path(data_dir)
    smokes = [
        _run_contract_smoke(root / scenario["contract_id"], scenario)
        for scenario in SHIPPED_CONTRACT_SMOKES
    ]
    return {
        "smokes": smokes,
        "lines": [
            f"{smoke['contract_id']}: resolved "
            f"({len(smoke['resolved_standings'])} standings, "
            f"{smoke['visible_artifact_count']} visible artifacts)"
            for smoke in smokes
        ],
    }


def _run_contract_smoke(data_dir: Path, scenario: dict[str, Any]) -> dict[str, Any]:
    previous_admin_token = os.environ.get("HOLLOW_LODGE_ADMIN_TOKEN")
    os.environ["HOLLOW_LODGE_ADMIN_TOKEN"] = "smoke-admin-secret"
    try:
        client = TestClient(
            create_app(
                data_dir=data_dir,
                invite_codes=[
                    f"{scenario['contract_id']}-ada",
                    f"{scenario['contract_id']}-bela",
                ],
            )
        )
        if scenario["seed"] is not None:
            _post(
                client,
                "/contracts/admin/activate",
                headers={
                    "Idempotency-Key": f"activate-{scenario['contract_id']}",
                    "X-Hollow-Lodge-Admin-Token": "smoke-admin-secret",
                },
                json={"seed": scenario["seed"]},
                expected_status=201,
            )
        return _play_contract(client, scenario)
    finally:
        if previous_admin_token is None:
            os.environ.pop("HOLLOW_LODGE_ADMIN_TOKEN", None)
        else:
            os.environ["HOLLOW_LODGE_ADMIN_TOKEN"] = previous_admin_token


def _play_contract(client: TestClient, scenario: dict[str, Any]) -> dict[str, Any]:
    ada = _register(
        client,
        f"{scenario['contract_id']}-ada",
        f"Ada {scenario['contract_id']}",
    )
    bela = _register(
        client,
        f"{scenario['contract_id']}-bela",
        f"Bela {scenario['contract_id']}",
    )
    gilt = _create_crew(
        client,
        ada,
        "The Gilt Knives",
        f"crew-gilt-{scenario['contract_id']}",
    )
    moth = _create_crew(
        client,
        bela,
        "The Moth Choir",
        f"crew-moth-{scenario['contract_id']}",
    )

    citation = scenario["artifact_citation"]
    _post(
        client,
        f"/proofs/dossiers/{gilt['crew_id']}/artifact-citations",
        headers=_command_auth(ada["token"], f"cite-{scenario['contract_id']}"),
        json=citation,
        expected_status=201,
    )
    for index, (player, crew, intent) in enumerate(
        (
            (ada, gilt, scenario["crew_actions"][0]),
            (bela, moth, scenario["crew_actions"][1]),
        ),
        start=1,
    ):
        _post(
            client,
            "/actions",
            headers=_command_auth(
                player["token"],
                f"action-{scenario['contract_id']}-{index}",
            ),
            json={
                "crew_id": crew["crew_id"],
                "intent": intent,
                "confirmed": True,
            },
            expected_status=201,
        )

    resolved = _post(
        client,
        f"/contracts/{scenario['contract_id']}/phases/auction-preview/lock",
        headers=_command_auth(ada["token"], f"phase-lock-{scenario['contract_id']}"),
        json={"hours_elapsed": scenario["hours_elapsed"]},
        expected_status=200,
    )
    contract_board = _get(client, "/contracts", headers=_auth(ada["token"]))
    artifacts = _get(client, "/artifacts", headers=_auth(ada["token"]))
    contract_packet = build_contract_board_packet(contract_board)
    artifact_packet = build_artifact_graph_packet(artifacts)
    rendered = "\n".join(
        (
            contract_packet.player_markdown,
            artifact_packet.player_markdown,
            str(contract_packet.agent_context),
            str(artifact_packet.agent_context),
        )
    )
    return {
        "contract_id": scenario["contract_id"],
        "resolved_standings": resolved["standings"],
        "contract_board_surface": contract_packet.surface,
        "artifact_surface": artifact_packet.surface,
        "visible_artifact_count": len(artifacts["artifacts"]),
        "hidden_leak_detected": any(
            hidden_term in rendered for hidden_term in scenario["hidden_terms"]
        ),
    }


def _register(client: TestClient, invite: str, name: str) -> dict[str, Any]:
    return _post(
        client,
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
        expected_status=201,
    )


def _create_crew(
    client: TestClient,
    player: dict[str, Any],
    name: str,
    key: str,
) -> dict[str, Any]:
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
    headers: dict[str, str],
    json: dict[str, Any],
    expected_status: int,
) -> dict[str, Any]:
    response = client.post(path, headers=headers, json=json)
    if response.status_code != expected_status:
        raise RuntimeError(
            f"POST {path} returned {response.status_code}: {response.text}"
        )
    return response.json()


if __name__ == "__main__":
    main()
