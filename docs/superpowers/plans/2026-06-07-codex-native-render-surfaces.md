# Codex-Native Render Surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make The Hollow Lodge visible and playable inside a Codex session by exposing inbox, contract board, and crew board render packets that are readable by both the player and the agent.

**Architecture:** Add a shared render-packet layer that produces `player_markdown` plus structured `agent_context`, then reuse it from the CLI and a Codex-facing MCP server. Add one authoritative crew-board server projection so the local agent does not infer crew state from raw event replay.

**Tech Stack:** Python 3.12, Pydantic 2, Typer, FastAPI, httpx, pytest, MCP Python SDK.

---

## File Structure

- Create `src/hollow_lodge/client/render_packets.py`
  - Owns `RenderPacket`, `RenderAction`, and packet builders for inbox, contract board, and crew board surfaces.
  - Keeps all Codex-facing markdown and agent-context shaping in one place.
- Modify `src/hollow_lodge/client/render.py`
  - Preserve existing string renderer function names by delegating to render packets.
  - Add `render_crew_board`.
- Modify `src/hollow_lodge/server/services.py`
  - Add crew summary accessors to `CrewService`.
- Modify `src/hollow_lodge/server/routes_crews.py`
  - Add `GET /crews/{crew_id}/board`.
- Modify `src/hollow_lodge/client/api.py`
  - Add `crew_board(crew_id: str)`.
- Modify `src/hollow_lodge/client/cli.py`
  - Add `--json` output for `contracts`, `inbox`, and new `crew-board`.
  - Keep existing human text output unchanged.
- Create `src/hollow_lodge/client/codex_session.py`
  - Small orchestration layer that loads config, syncs events, and returns render packets for Codex tools.
- Create `src/hollow_lodge/mcp_server.py`
  - Exposes MCP tools for Codex: render inbox, contract board, and crew board.
- Modify `pyproject.toml`
  - Add MCP SDK dependency.
  - Add a `hollow-lodge-mcp` console script.
- Create `tests/client/test_render_packets.py`
  - Unit tests for packet shape and markdown content.
- Modify `tests/client/test_contract_board.py`
  - Preserve current string render behavior.
- Modify `tests/client/test_cli_commands.py`
  - Cover `--json` and `crew-board`.
- Modify `tests/server/test_crew_routes.py`
  - Cover authoritative crew-board projection and access control.
- Create `tests/client/test_codex_session.py`
  - Cover session orchestration without starting MCP.
- Create `tests/test_mcp_server.py`
  - Cover MCP helper return shape without requiring a live Codex session.
- Create `docs/codex-play.md`
  - Codex player-agent operating policy.
- Modify `AGENTS.md`
  - Link to `docs/codex-play.md` for game-play sessions.

## Task 1: Render Packet Model

**Files:**
- Create: `src/hollow_lodge/client/render_packets.py`
- Modify: `src/hollow_lodge/client/render.py`
- Test: `tests/client/test_render_packets.py`
- Test: `tests/client/test_contract_board.py`

- [ ] **Step 1: Write failing render packet tests**

Create `tests/client/test_render_packets.py`:

```python
from hollow_lodge.client.render_packets import (
    build_contract_board_packet,
    build_inbox_packet,
)


BOARD = {
    "campaign": {"campaign_id": "campaign_saints_ledgers", "title": "Saints & Ledgers"},
    "contracts": [
        {
            "contract_id": "contract_false_finger",
            "title": "The Saint's False Finger",
            "phase": {"name": "Auction Preview", "remaining_hours": 6},
            "crew_heat": 0,
            "proof_dossier_needs": [
                "provenance chain",
                "material authenticity",
                "auction leverage",
            ],
        }
    ],
}


INBOX = {
    "player_id": "player_0001",
    "active_contracts": BOARD["contracts"],
    "incoming_proof_fragments": [],
}


def test_contract_board_packet_has_player_markdown_and_agent_context():
    packet = build_contract_board_packet(BOARD)

    assert packet.surface == "contract_board"
    assert "Saints & Ledgers" in packet.player_markdown
    assert "The Saint's False Finger" in packet.player_markdown
    assert packet.agent_context["contracts"][0]["contract_id"] == "contract_false_finger"
    assert packet.agent_context["contracts"][0]["phase"]["name"] == "Auction Preview"
    assert packet.suggested_prompts == [
        "Open the contested contract",
        "Review crew packet status",
        "Draft a contract action",
    ]


def test_inbox_packet_prioritizes_actionable_items_for_codex():
    packet = build_inbox_packet(INBOX)

    assert packet.surface == "inbox"
    assert "Inbox: player_0001" in packet.player_markdown
    assert "incoming proof fragments: none" in packet.player_markdown
    assert packet.agent_context["player_id"] == "player_0001"
    assert packet.agent_context["urgent_items"] == []
    assert packet.suggested_prompts == [
        "Open the contract board",
        "Review crew board",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/client/test_render_packets.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'hollow_lodge.client.render_packets'`.

- [ ] **Step 3: Implement render packet models and builders**

Create `src/hollow_lodge/client/render_packets.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RenderAction(BaseModel):
    label: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    requires_confirmation: bool = False


class RenderPacket(BaseModel):
    surface: Literal[
        "inbox",
        "contract_board",
        "crew_board",
    ]
    player_markdown: str = Field(min_length=1)
    agent_context: dict[str, Any]
    suggested_prompts: list[str] = Field(default_factory=list)
    actions: list[RenderAction] = Field(default_factory=list)


def build_contract_board_packet(board: dict[str, Any]) -> RenderPacket:
    lines: list[str] = []
    campaign = board.get("campaign") or {}
    if campaign:
        lines.append(str(campaign["title"]))
        lines.append("")
    contracts = board.get("contracts", [])
    if not contracts:
        lines.append("No visible contracts.")
    for contract in contracts:
        phase = contract["phase"]
        lines.append(f"## {contract['title']}")
        lines.append(f"Phase: {phase['name']} ({phase.get('remaining_hours', 0)}h remaining)")
        lines.append(f"Crew Heat: {contract.get('crew_heat', 0)}")
        lines.append("Proof dossier needs:")
        lines.extend(f"- {need}" for need in contract.get("proof_dossier_needs", []))
        if "phase_result" in contract:
            lines.append("Phase result:")
            for standing in contract["phase_result"].get("standings", []):
                lines.append(
                    f"- {standing['crew_id']}: {standing['standing']} ({standing['score']})"
                )
        lines.append("")
    return RenderPacket(
        surface="contract_board",
        player_markdown="\n".join(lines).strip(),
        agent_context={
            "campaign": campaign or None,
            "contracts": contracts,
            "visible_contract_count": len(contracts),
        },
        suggested_prompts=[
            "Open the contested contract",
            "Review crew packet status",
            "Draft a contract action",
        ],
        actions=[
            RenderAction(label="Review crew board", intent="render_crew_board"),
            RenderAction(label="Draft action", intent="draft_action", requires_confirmation=False),
        ],
    )


def build_inbox_packet(inbox: dict[str, Any]) -> RenderPacket:
    lines = [f"Inbox: {inbox['player_id']}"]
    active_contracts = inbox.get("active_contracts", [])
    if active_contracts:
        lines.append("")
        lines.append("Active contracts:")
        for contract in active_contracts:
            lines.append(f"- {contract['title']} ({contract['phase']['name']})")
    fragments = inbox.get("incoming_proof_fragments", [])
    lines.append("")
    if fragments:
        lines.append("incoming proof fragments:")
        lines.extend(f"- {fragment['fragment_id']}: {fragment['summary']}" for fragment in fragments)
    else:
        lines.append("incoming proof fragments: none")
    urgent_items = [
        {"kind": "proof_fragment", "fragment_id": fragment["fragment_id"]}
        for fragment in fragments
    ]
    return RenderPacket(
        surface="inbox",
        player_markdown="\n".join(lines),
        agent_context={
            "player_id": inbox["player_id"],
            "active_contracts": active_contracts,
            "incoming_proof_fragments": fragments,
            "urgent_items": urgent_items,
        },
        suggested_prompts=[
            "Open the contract board",
            "Review crew board",
        ],
    )
```

- [ ] **Step 4: Preserve current string render API**

Modify `src/hollow_lodge/client/render.py`:

```python
from __future__ import annotations

from typing import Any

from hollow_lodge.client.render_packets import (
    build_contract_board_packet,
    build_inbox_packet,
)


def render_contract_board(board: dict[str, Any]) -> str:
    return build_contract_board_packet(board).player_markdown


def render_inbox(inbox: dict[str, Any]) -> str:
    return build_inbox_packet(inbox).player_markdown
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
pytest tests/client/test_render_packets.py tests/client/test_contract_board.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/hollow_lodge/client/render_packets.py src/hollow_lodge/client/render.py tests/client/test_render_packets.py tests/client/test_contract_board.py
git commit -m "feat: add codex render packets"
```

## Task 2: Authoritative Crew Board Projection

**Files:**
- Modify: `src/hollow_lodge/server/services.py`
- Modify: `src/hollow_lodge/server/routes_crews.py`
- Modify: `src/hollow_lodge/client/api.py`
- Modify: `src/hollow_lodge/client/render_packets.py`
- Modify: `src/hollow_lodge/client/render.py`
- Test: `tests/server/test_crew_routes.py`
- Test: `tests/client/test_render_packets.py`

- [ ] **Step 1: Write failing server route test**

Append to `tests/server/test_crew_routes.py`:

```python
def test_crew_board_shows_member_roster_contracts_and_dossier(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()
    client.post(
        f"/crews/{crew['crew_id']}/join",
        headers=command_auth(grace["token"], "crew-join-grace"),
        json={"join_code": crew["join_code"]},
    )

    response = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["crew"]["crew_id"] == crew["crew_id"]
    assert body["crew"]["name"] == "The Gilt Knives"
    assert body["crew"]["member_ids"] == ["player_0001", "player_0002"]
    assert body["dossier"]["packet_lead_player_id"] == "player_0001"
    assert body["active_contracts"][0]["title"] == "The Saint's False Finger"
    assert "join_code" not in body["crew"]


def test_crew_board_is_crew_scoped(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    grace = register(client, "b", "Grace")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create-gilt"),
        json={"name": "The Gilt Knives"},
    ).json()

    denied = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(grace["token"]))

    assert denied.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/server/test_crew_routes.py::test_crew_board_shows_member_roster_contracts_and_dossier tests/server/test_crew_routes.py::test_crew_board_is_crew_scoped -q
```

Expected: fail with `404 Not Found`.

- [ ] **Step 3: Add crew summary accessors**

Modify `CrewService` in `src/hollow_lodge/server/services.py`:

```python
    def summary(self, crew_id: str) -> dict:
        with self._lock:
            crew = self._crews[crew_id]
            return {
                "crew_id": crew.crew_id,
                "name": crew.name,
                "member_ids": list(crew.member_ids),
                "member_count": len(crew.member_ids),
                "ready_for_full_contracts": crew.ready_for_full_contracts,
                "readiness_warning": crew.readiness_warning,
            }
```

- [ ] **Step 4: Add crew board route**

Modify `src/hollow_lodge/server/routes_crews.py`:

```python
@router.get("/{crew_id}/board")
def crew_board(
    crew_id: str,
    request: Request,
    player: Player = Depends(current_player),
):
    crew_service = request.app.state.crew_service
    if not crew_service.has_crew(crew_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="crew not found")
    if not crew_service.is_member(crew_id=crew_id, player_id=player.player_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a crew member")
    contract_service = _contract_service(request)
    proof_service = _proof_service(request)
    return {
        "player_id": player.player_id,
        "crew": crew_service.summary(crew_id),
        "active_contracts": contract_service.board_for_player(player.player_id)["contracts"],
        "dossier": proof_service.dossier_for_crew(
            crew_id=crew_id,
            player_id=player.player_id,
        ),
    }


def _contract_service(request: Request):
    if not hasattr(request.app.state, "contract_service"):
        request.app.state.contract_service = ContractService(
            event_store=request.app.state.event_store,
        )
    return request.app.state.contract_service


def _proof_service(request: Request):
    if not hasattr(request.app.state, "proof_service"):
        request.app.state.proof_service = ProofService(
            event_store=request.app.state.event_store,
            identity_service=request.app.state.identity_service,
            crew_service=request.app.state.crew_service,
        )
    return request.app.state.proof_service
```

Also import `ContractService` and `ProofService` from `hollow_lodge.server.services`.

- [ ] **Step 5: Add client API method**

Modify `src/hollow_lodge/client/api.py`:

```python
    def crew_board(self, *, crew_id: str) -> dict[str, Any]:
        return self._get(f"/crews/{crew_id}/board")
```

- [ ] **Step 6: Add crew board packet builder**

Append to `src/hollow_lodge/client/render_packets.py`:

```python
def build_crew_board_packet(board: dict[str, Any]) -> RenderPacket:
    crew = board["crew"]
    dossier = board["dossier"]
    lines = [
        f"Crew Board: {crew['name']}",
        f"Crew ID: {crew['crew_id']}",
        f"Members: {crew['member_count']}",
        f"Packet Lead: {dossier['packet_lead_player_id']}",
        "",
        "Active contracts:",
    ]
    for contract in board.get("active_contracts", []):
        lines.append(f"- {contract['title']} ({contract['phase']['name']})")
    lines.extend(
        [
            "",
            "Dossier:",
            f"Claim: {dossier.get('claim') or 'unset'}",
            f"Evidence: {len(dossier.get('evidence_ids', []))}",
            f"Contributions: {len(dossier.get('member_contributions', []))}",
        ]
    )
    return RenderPacket(
        surface="crew_board",
        player_markdown="\n".join(lines),
        agent_context={
            "player_id": board["player_id"],
            "crew": crew,
            "active_contracts": board.get("active_contracts", []),
            "dossier": dossier,
            "urgent_items": [],
        },
        suggested_prompts=[
            "Review the proof dossier",
            "Draft a crew action",
            "Vote on packet lead",
        ],
        actions=[
            RenderAction(label="Draft crew action", intent="draft_action"),
            RenderAction(label="Update dossier claim", intent="update_dossier", requires_confirmation=True),
            RenderAction(label="Vote packet lead", intent="vote_packet_lead", requires_confirmation=True),
        ],
    )
```

- [ ] **Step 7: Add string renderer**

Modify `src/hollow_lodge/client/render.py`:

```python
from hollow_lodge.client.render_packets import (
    build_contract_board_packet,
    build_crew_board_packet,
    build_inbox_packet,
)


def render_crew_board(board: dict[str, Any]) -> str:
    return build_crew_board_packet(board).player_markdown
```

- [ ] **Step 8: Add packet test**

Append to `tests/client/test_render_packets.py`:

```python
def test_crew_board_packet_shows_packet_lead_and_dossier_status():
    packet = build_crew_board_packet(
        {
            "player_id": "player_0001",
            "crew": {
                "crew_id": "crew_0001",
                "name": "The Gilt Knives",
                "member_ids": ["player_0001", "player_0002"],
                "member_count": 2,
                "ready_for_full_contracts": False,
                "readiness_warning": "Crews should have 3-5 players for full contracts.",
            },
            "active_contracts": BOARD["contracts"],
            "dossier": {
                "dossier_id": "dossier_crew_0001",
                "crew_id": "crew_0001",
                "packet_lead_player_id": "player_0001",
                "claim": "",
                "evidence_ids": [],
                "member_contributions": [],
            },
        }
    )

    assert packet.surface == "crew_board"
    assert "Crew Board: The Gilt Knives" in packet.player_markdown
    assert "Packet Lead: player_0001" in packet.player_markdown
    assert packet.agent_context["crew"]["crew_id"] == "crew_0001"
```

- [ ] **Step 9: Run focused tests**

Run:

```bash
pytest tests/server/test_crew_routes.py tests/client/test_render_packets.py -q
```

Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
git add src/hollow_lodge/server/services.py src/hollow_lodge/server/routes_crews.py src/hollow_lodge/client/api.py src/hollow_lodge/client/render_packets.py src/hollow_lodge/client/render.py tests/server/test_crew_routes.py tests/client/test_render_packets.py
git commit -m "feat: add crew board projection"
```

## Task 3: CLI JSON and Crew Board Command

**Files:**
- Modify: `src/hollow_lodge/client/cli.py`
- Test: `tests/client/test_cli_commands.py`

- [ ] **Step 1: Write failing CLI tests**

Append to `tests/client/test_cli_commands.py`:

```python
def test_contracts_can_emit_render_packet_json(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )

    result = runner.invoke(cli.app, ["contracts", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    assert '"surface":"contract_board"' in result.output
    assert "The Saint's False Finger" in result.output


def test_inbox_can_emit_render_packet_json(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )

    result = runner.invoke(cli.app, ["inbox", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    assert '"surface":"inbox"' in result.output
    assert '"player_id":"player_0001"' in result.output


def test_crew_board_command_uses_active_crew_and_can_emit_json(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli, "HollowLodgeApi", FakeApi)
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )

    result = runner.invoke(cli.app, ["crew-board", "--json", "--config", str(config_path)])

    assert result.exit_code == 0
    assert '"surface":"crew_board"' in result.output
    assert '"crew_id":"crew_0001"' in result.output
```

Extend the local `FakeApi` in that test file:

```python
    def crew_board(self, *, crew_id: str):
        self.calls.append(("crew_board", {"crew_id": crew_id}))
        return {
            "player_id": "player_0001",
            "crew": {
                "crew_id": crew_id,
                "name": "The Gilt Knives",
                "member_ids": ["player_0001", "player_0002"],
                "member_count": 2,
                "ready_for_full_contracts": False,
                "readiness_warning": "Crews should have 3-5 players for full contracts.",
            },
            "active_contracts": [
                {
                    "title": "The Saint's False Finger",
                    "phase": {"name": "Auction Preview"},
                }
            ],
            "dossier": {
                "dossier_id": "dossier_crew_0001",
                "crew_id": crew_id,
                "packet_lead_player_id": "player_0001",
                "claim": "",
                "evidence_ids": [],
                "member_contributions": [],
            },
        }
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/client/test_cli_commands.py -q
```

Expected: fail because `--json` and `crew-board` do not exist.

- [ ] **Step 3: Add CLI render helper**

Modify `src/hollow_lodge/client/cli.py` imports:

```python
from hollow_lodge.client.render import render_contract_board, render_crew_board, render_inbox
from hollow_lodge.client.render_packets import (
    build_contract_board_packet,
    build_crew_board_packet,
    build_inbox_packet,
)
```

Add helper:

```python
def _echo_packet(packet, *, as_json: bool) -> None:
    if as_json:
        typer.echo(packet.model_dump_json())
    else:
        typer.echo(packet.player_markdown)
```

- [ ] **Step 4: Add `--json` to existing board commands**

Modify `contracts`:

```python
@app.command()
def contracts(
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
    as_json: bool = typer.Option(False, "--json", help="Emit Codex render packet JSON."),
) -> None:
    """Show the contract board."""
    packet = build_contract_board_packet(_api_from_config(load_config(config)).contracts())
    _echo_packet(packet, as_json=as_json)
```

Modify `inbox`:

```python
@app.command()
def inbox(
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
    as_json: bool = typer.Option(False, "--json", help="Emit Codex render packet JSON."),
) -> None:
    """Show the personal inbox."""
    packet = build_inbox_packet(_api_from_config(load_config(config)).inbox())
    _echo_packet(packet, as_json=as_json)
```

- [ ] **Step 5: Add crew-board CLI command**

Append to `src/hollow_lodge/client/cli.py` before `sync`:

```python
@app.command("crew-board")
def crew_board(
    crew_id: str | None = typer.Option(None, "--crew-id", help="Crew id; defaults to active crew."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
    as_json: bool = typer.Option(False, "--json", help="Emit Codex render packet JSON."),
) -> None:
    """Show the active crew board."""
    current = load_config(config)
    target_crew_id = _target_crew_id(current, crew_id)
    packet = build_crew_board_packet(
        _api_from_config(current).crew_board(crew_id=target_crew_id)
    )
    _echo_packet(packet, as_json=as_json)
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
pytest tests/client/test_cli_commands.py tests/client/test_contract_board.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/hollow_lodge/client/cli.py tests/client/test_cli_commands.py
git commit -m "feat: add codex json board commands"
```

## Task 4: Codex Session Adapter

**Files:**
- Create: `src/hollow_lodge/client/codex_session.py`
- Test: `tests/client/test_codex_session.py`

- [ ] **Step 1: Write failing adapter tests**

Create `tests/client/test_codex_session.py`:

```python
from pathlib import Path

from hollow_lodge.client.codex_session import CodexGameSession
from hollow_lodge.client.config import ClientConfig, save_config


class FakeApi:
    def __init__(self):
        self.synced = False

    def visible_events(self):
        self.synced = True
        return [
            {
                "event_id": "evt_1",
                "sequence": 1,
                "type": "chat.message.created",
                "payload": {"sender_player_id": "player_0002", "body": "The bell moved."},
            }
        ]

    def inbox(self):
        return {
            "player_id": "player_0001",
            "active_contracts": [],
            "incoming_proof_fragments": [],
        }

    def contracts(self):
        return {"campaign": {"title": "Saints & Ledgers"}, "contracts": []}

    def crew_board(self, *, crew_id: str):
        return {
            "player_id": "player_0001",
            "crew": {
                "crew_id": crew_id,
                "name": "The Gilt Knives",
                "member_ids": ["player_0001"],
                "member_count": 1,
                "ready_for_full_contracts": False,
                "readiness_warning": "Crews should have 3-5 players for full contracts.",
            },
            "active_contracts": [],
            "dossier": {
                "dossier_id": f"dossier_{crew_id}",
                "crew_id": crew_id,
                "packet_lead_player_id": "player_0001",
                "claim": "",
                "evidence_ids": [],
                "member_contributions": [],
            },
        }


def test_codex_session_syncs_before_rendering_inbox(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    save_config(
        config_path,
        ClientConfig(server_url="http://testserver", player_id="player_0001", token="token"),
    )
    fake_api = FakeApi()
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=fake_api)

    packet = session.render_inbox()

    assert fake_api.synced is True
    assert packet.surface == "inbox"
    assert "Inbox: player_0001" in packet.player_markdown
    assert "chat.message.created" in log_path.read_text()


def test_codex_session_uses_active_crew_for_crew_board(tmp_path):
    config_path = tmp_path / "config.json"
    log_path = tmp_path / "local.jsonl"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id="player_0001",
            token="token",
            active_crew_id="crew_0001",
        ),
    )
    session = CodexGameSession(config_path=config_path, local_log_path=log_path, api=FakeApi())

    packet = session.render_crew_board()

    assert packet.surface == "crew_board"
    assert packet.agent_context["crew"]["crew_id"] == "crew_0001"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/client/test_codex_session.py -q
```

Expected: fail with `ModuleNotFoundError`.

- [ ] **Step 3: Implement session adapter**

Create `src/hollow_lodge/client/codex_session.py`:

```python
from __future__ import annotations

from pathlib import Path

from hollow_lodge.client.api import HollowLodgeApi
from hollow_lodge.client.cli import DEFAULT_CONFIG_PATH, DEFAULT_LOCAL_LOG_PATH
from hollow_lodge.client.config import ClientConfig, load_config
from hollow_lodge.client.local_log import LocalEventLog
from hollow_lodge.client.render_packets import (
    RenderPacket,
    build_contract_board_packet,
    build_crew_board_packet,
    build_inbox_packet,
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
        self.local_log = LocalEventLog(local_log_path)

    def sync(self) -> int:
        return self.local_log.sync_visible_server_events(self.api.visible_events())

    def render_inbox(self) -> RenderPacket:
        self.sync()
        return build_inbox_packet(self.api.inbox())

    def render_contract_board(self) -> RenderPacket:
        self.sync()
        return build_contract_board_packet(self.api.contracts())

    def render_crew_board(self, crew_id: str | None = None) -> RenderPacket:
        self.sync()
        target_crew_id = crew_id or self.config.active_crew_id
        if target_crew_id is None:
            raise ValueError("crew id required when no active crew is configured")
        return build_crew_board_packet(self.api.crew_board(crew_id=target_crew_id))
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/client/test_codex_session.py tests/client/test_local_log.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/hollow_lodge/client/codex_session.py tests/client/test_codex_session.py
git commit -m "feat: add codex session adapter"
```

## Task 5: MCP Server for Codex Rendering

**Files:**
- Modify: `pyproject.toml`
- Create: `src/hollow_lodge/mcp_server.py`
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Add MCP dependency**

Modify `pyproject.toml`:

```toml
dependencies = [
  "fastapi>=0.115",
  "httpx>=0.27",
  "mcp>=1.0",
  "pydantic>=2.8",
  "typer>=0.12",
  "uvicorn>=0.30",
]

[project.scripts]
hollow-lodge = "hollow_lodge.client.cli:main"
hollow-lodge-mcp = "hollow_lodge.mcp_server:main"
```

- [ ] **Step 2: Write failing MCP tests**

Create `tests/test_mcp_server.py`:

```python
from hollow_lodge.mcp_server import packet_response
from hollow_lodge.client.render_packets import RenderPacket


def test_packet_response_returns_markdown_and_structured_content():
    packet = RenderPacket(
        surface="inbox",
        player_markdown="Inbox: player_0001",
        agent_context={"player_id": "player_0001"},
        suggested_prompts=["Open the contract board"],
    )

    response = packet_response(packet)

    assert response["content"][0]["type"] == "text"
    assert response["content"][0]["text"] == "Inbox: player_0001"
    assert response["structuredContent"]["surface"] == "inbox"
    assert response["structuredContent"]["agent_context"]["player_id"] == "player_0001"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
pytest tests/test_mcp_server.py -q
```

Expected: fail with `ModuleNotFoundError`.

- [ ] **Step 4: Implement MCP server module**

Create `src/hollow_lodge/mcp_server.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from hollow_lodge.client.cli import DEFAULT_CONFIG_PATH, DEFAULT_LOCAL_LOG_PATH
from hollow_lodge.client.codex_session import CodexGameSession
from hollow_lodge.client.render_packets import RenderPacket


mcp = FastMCP(
    "the-hollow-lodge",
    instructions=(
        "Render The Hollow Lodge game state for Codex. Show player_markdown to the "
        "player. Use agent_context for reasoning. Clarify consequences and translate "
        "intent; do not choose player strategy by default."
    ),
)


def packet_response(packet: RenderPacket) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": packet.player_markdown}],
        "structuredContent": packet.model_dump(mode="json"),
    }


def _session(
    *,
    config_path: str | None = None,
    local_log_path: str | None = None,
) -> CodexGameSession:
    return CodexGameSession(
        config_path=Path(config_path) if config_path else DEFAULT_CONFIG_PATH,
        local_log_path=Path(local_log_path) if local_log_path else DEFAULT_LOCAL_LOG_PATH,
    )


@mcp.tool()
def render_inbox(config_path: str | None = None, local_log_path: str | None = None) -> dict[str, Any]:
    return packet_response(
        _session(config_path=config_path, local_log_path=local_log_path).render_inbox()
    )


@mcp.tool()
def render_contract_board(
    config_path: str | None = None,
    local_log_path: str | None = None,
) -> dict[str, Any]:
    return packet_response(
        _session(config_path=config_path, local_log_path=local_log_path).render_contract_board()
    )


@mcp.tool()
def render_crew_board(
    crew_id: str | None = None,
    config_path: str | None = None,
    local_log_path: str | None = None,
) -> dict[str, Any]:
    return packet_response(
        _session(config_path=config_path, local_log_path=local_log_path).render_crew_board(
            crew_id=crew_id
        )
    )


def main() -> None:
    mcp.run()
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
pytest tests/test_mcp_server.py tests/client/test_codex_session.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Smoke test MCP entry point imports**

Run:

```bash
python - <<'PY'
from hollow_lodge.mcp_server import mcp, packet_response
print(mcp.name)
print(callable(packet_response))
PY
```

Expected output includes:

```text
the-hollow-lodge
True
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/hollow_lodge/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: expose codex render mcp tools"
```

## Task 6: Codex Play Guide

**Files:**
- Create: `docs/codex-play.md`
- Modify: `AGENTS.md`
- Test: manual doc review

- [ ] **Step 1: Create player-agent play guide**

Create `docs/codex-play.md`:

```markdown
# Codex Play Guide

The Hollow Lodge is played inside Codex through game render tools, not by asking
the player to manage raw shell commands.

## Session Loop

1. Sync visible events before advising.
2. Render the inbox first.
3. Render the contract board when the player asks what is available or contested.
4. Render the crew board before advising on crew actions, proof packets, heat,
   packet-lead votes, or dossier strategy.
5. Show the player the relevant `player_markdown`.
6. Use `agent_context` for reasoning, but do not hide material consequences from
   the player.
7. Clarify consequences and translate intent. Do not choose player strategy by default.
8. Ask for confirmation before submitting irreversible actions, votes, dossier
   changes, proof transfers, or messages.

## Default Landing

When a player says "what's happening" or starts a play session:

1. Call `render_inbox`.
2. If there are active contracts, call `render_contract_board`.
3. If an active crew is configured, call `render_crew_board`.
4. Summarize the most important visible changes and offer 2-4 concrete next
   actions.

## Visibility

Treat private conversations and crew boards as visibility-scoped game state.
Do not reveal server-only truth. Do not claim certainty about leaked or copied
information unless the game state exposes that certainty.
```

- [ ] **Step 2: Link guide from AGENTS.md**

Append to `AGENTS.md`:

```markdown
## The Hollow Lodge Codex Play

For game-play sessions, follow `docs/codex-play.md`. The player should see
rendered game state inside Codex, and the agent should use structured render
packet context when advising.
```

- [ ] **Step 3: Commit**

```bash
git add docs/codex-play.md AGENTS.md
git commit -m "docs: add codex play guide"
```

## Task 7: End-to-End Vertical Slice

**Files:**
- Create: `tests/e2e/test_codex_render_surfaces.py`

- [ ] **Step 1: Write e2e test**

Create `tests/e2e/test_codex_render_surfaces.py`:

```python
from fastapi.testclient import TestClient

from hollow_lodge.client.api import HollowLodgeApi
from hollow_lodge.client.codex_session import CodexGameSession
from hollow_lodge.client.config import ClientConfig, save_config
from hollow_lodge.server.app import create_app


def test_codex_render_surfaces_show_player_and_agent_state(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path / "server", invite_codes=["a"])
    client = TestClient(app)
    registered = client.post(
        "/identity/register",
        json={"invite_code": "a", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-a"},
    ).json()
    crew = client.post(
        "/crews",
        json={"name": "The Gilt Knives"},
        headers={
            "Authorization": f"Bearer {registered['token']}",
            "Idempotency-Key": "crew-create-gilt",
        },
    ).json()
    config_path = tmp_path / "config.json"
    save_config(
        config_path,
        ClientConfig(
            server_url="http://testserver",
            player_id=registered["player_id"],
            token=registered["token"],
            active_crew_id=crew["crew_id"],
        ),
    )

    def fake_get(url, headers=None, params=None, timeout=None):
        path = url.removeprefix("http://testserver")
        return client.get(path, headers=headers, params=params)

    monkeypatch.setattr("httpx.get", fake_get)
    session = CodexGameSession(
        config_path=config_path,
        local_log_path=tmp_path / "local.jsonl",
        api=HollowLodgeApi(server_url="http://testserver", token=registered["token"]),
    )

    inbox = session.render_inbox()
    contracts = session.render_contract_board()
    crew_board = session.render_crew_board()

    assert inbox.surface == "inbox"
    assert contracts.surface == "contract_board"
    assert crew_board.surface == "crew_board"
    assert "The Saint's False Finger" in contracts.player_markdown
    assert crew_board.agent_context["crew"]["crew_id"] == crew["crew_id"]
```

- [ ] **Step 2: Run e2e test**

Run:

```bash
pytest tests/e2e/test_codex_render_surfaces.py -q
```

Expected: pass.

- [ ] **Step 3: Run full suite**

Run:

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_codex_render_surfaces.py
git commit -m "test: prove codex render vertical slice"
```

## Final Verification

- [ ] Run formatting/whitespace check:

```bash
git diff --check
```

Expected: no output.

- [ ] Run all tests:

```bash
pytest -q
```

Expected: all tests pass.

- [ ] Verify CLI help includes the new command:

```bash
python -m hollow_lodge.client.cli --help
```

Expected: output includes `crew-board`.

- [ ] Verify MCP module import:

```bash
python - <<'PY'
from hollow_lodge.mcp_server import mcp
print(mcp.name)
PY
```

Expected:

```text
the-hollow-lodge
```

## Self-Review

- Spec coverage: This plan covers Codex-visible inbox, contract board, crew board, structured agent context, player markdown, CLI parity, MCP exposure, and play-session guidance.
- Placeholder scan: No deferred implementation placeholders are intentionally left in the task steps.
- Type consistency: `RenderPacket.surface`, `player_markdown`, `agent_context`, `suggested_prompts`, and `actions` are used consistently across CLI, Codex session adapter, and MCP server.
- Scope control: This plan does not add full brokered chat rendering, action submission MCP tools, voice, browser UI, or campaign generation. Those should be separate follow-up plans after the render surfaces prove the in-session loop.
