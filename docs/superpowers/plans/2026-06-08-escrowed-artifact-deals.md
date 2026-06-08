# Escrowed Artifact Deals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add server-enforced, visibility-scoped, atomic artifact-for-artifact swaps between crews.

**Architecture:** Deals are authoritative event-log projections backed by a focused `DealService`. The service validates crew membership and artifact visibility, appends deal lifecycle events, and fulfills accepted swaps by creating crew-scoped artifact copy events through `ArtifactService`. Clients and MCP do not choose strategy; they render pending/fulfilled deals and submit player-confirmed commands.

**Tech Stack:** Python 3.12, FastAPI, Typer, Pydantic, pytest, httpx, append-only JSONL Eventloom-compatible event log, existing MCP render packets.

---

## Scope Check

This plan implements the approved v1 scope from `docs/superpowers/specs/2026-06-08-escrowed-artifact-deals-design.md`.

Included:

- proposed, accepted, fulfilled, declined, and canceled deal states
- concrete artifact swap enforcement
- soft terms recorded and rendered
- crew-scoped deal copy access
- idempotent propose and accept commands
- inbox and crew board deal visibility
- CLI commands for list, propose, accept, decline, and cancel

Excluded:

- marketplace search
- currency
- automatic expiry
- broken soft-term enforcement
- public deal feeds
- anonymous or multi-party deals
- local-agent autonomous acceptance

## File Structure

Create:

```text
src/hollow_lodge/domain/deals.py
src/hollow_lodge/server/deal_service.py
src/hollow_lodge/server/routes_deals.py
tests/domain/test_deals.py
tests/server/test_deal_service.py
tests/server/test_deal_routes.py
tests/client/test_deal_cli.py
tests/e2e/test_escrowed_artifact_deals.py
scripts/smoke_deal_loop.py
```

Modify:

```text
src/hollow_lodge/domain/artifacts.py
src/hollow_lodge/server/artifact_service.py
src/hollow_lodge/server/app.py
src/hollow_lodge/server/routes_crews.py
src/hollow_lodge/server/routes_contracts.py
src/hollow_lodge/client/api.py
src/hollow_lodge/client/cli.py
src/hollow_lodge/client/render_packets.py
src/hollow_lodge/client/render.py
```

Responsibilities:

- `domain/deals.py`: Deal model, lifecycle status literals, and event projection helpers.
- `server/deal_service.py`: Validates membership, visibility, idempotency, and atomic fulfillment ordering.
- `server/routes_deals.py`: HTTP API for deal list/propose/accept/decline/cancel.
- `artifact_service.py`: Adds crew-scoped artifact copy creation without changing existing player transfer behavior.
- `render_packets.py`: Adds deal summaries to inbox and crew-board render packets.

## Event Types

Implement these v1 event types:

```text
deal.proposed
deal.accepted
deal.fulfilled
deal.declined
deal.canceled
artifact.deal_copied
artifact.deal_copied.internal
```

Visibility:

- `deal.*`: `EventVisibility.crews([proposer_crew_id, recipient_crew_id])`
- `artifact.deal_copied`: `EventVisibility.crews([source_crew_id, recipient_crew_id])`
- `artifact.deal_copied.internal`: `EventVisibility.server_only()`

Do not implement `deal.expired` or `deal.broken` in this plan.

## Task 1: Deal Domain Projection

**Files:**

- Create: `src/hollow_lodge/domain/deals.py`
- Create: `tests/domain/test_deals.py`

- [ ] **Step 1: Write failing projection tests**

Create `tests/domain/test_deals.py`:

```python
from hollow_lodge.domain.deals import Deal, deal_rows_from_events
from hollow_lodge.domain.events import EventVisibility, GameEvent


def event(sequence: int, event_type: str, payload: dict) -> GameEvent:
    return GameEvent(
        event_id=f"evt_{sequence:06d}",
        sequence=sequence,
        type=event_type,
        actor_id=payload.get("actor_id", "player_0001"),
        visibility=EventVisibility.crews(
            [payload["proposer_crew_id"], payload["recipient_crew_id"]]
        ),
        payload=payload,
        idempotency_key=f"key-{sequence}",
    )


def test_deal_projection_tracks_fulfilled_swap():
    rows = deal_rows_from_events(
        [
            event(
                1,
                "deal.proposed",
                {
                    "deal_id": "deal_000001",
                    "contract_id": "contract_false_finger",
                    "proposer_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "offered_artifact_ids": ["artifact_ledger_rubric"],
                    "requested_artifact_ids": ["artifact_chapel_debt_mark"],
                    "soft_terms": ["Do not cite us."],
                    "expires_phase": "Auction Preview",
                    "proposer_player_id": "player_0001",
                    "accepted_by_player_id": None,
                    "status": "proposed",
                },
            ),
            event(
                2,
                "deal.accepted",
                {
                    "deal_id": "deal_000001",
                    "contract_id": "contract_false_finger",
                    "proposer_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "accepted_by_player_id": "player_0002",
                },
            ),
            event(
                3,
                "deal.fulfilled",
                {
                    "deal_id": "deal_000001",
                    "contract_id": "contract_false_finger",
                    "proposer_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "proposer_received_artifact_ids": [
                        "artifact_chapel_debt_mark.dealcopy.deal_000001.crew_0001.1"
                    ],
                    "recipient_received_artifact_ids": [
                        "artifact_ledger_rubric.dealcopy.deal_000001.crew_0002.1"
                    ],
                    "status": "fulfilled",
                },
            ),
        ]
    )

    assert rows == [
        {
            "deal_id": "deal_000001",
            "contract_id": "contract_false_finger",
            "proposer_crew_id": "crew_0001",
            "recipient_crew_id": "crew_0002",
            "status": "fulfilled",
            "offered_artifact_ids": ["artifact_ledger_rubric"],
            "requested_artifact_ids": ["artifact_chapel_debt_mark"],
            "soft_terms": ["Do not cite us."],
            "expires_phase": "Auction Preview",
            "proposer_player_id": "player_0001",
            "accepted_by_player_id": "player_0002",
            "proposer_received_artifact_ids": [
                "artifact_chapel_debt_mark.dealcopy.deal_000001.crew_0001.1"
            ],
            "recipient_received_artifact_ids": [
                "artifact_ledger_rubric.dealcopy.deal_000001.crew_0002.1"
            ],
        }
    ]


def test_deal_projection_tracks_canceled_state():
    rows = deal_rows_from_events(
        [
            event(
                1,
                "deal.proposed",
                {
                    "deal_id": "deal_000001",
                    "contract_id": "contract_false_finger",
                    "proposer_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "offered_artifact_ids": ["artifact_ledger_rubric"],
                    "requested_artifact_ids": ["artifact_chapel_debt_mark"],
                    "soft_terms": [],
                    "expires_phase": None,
                    "proposer_player_id": "player_0001",
                    "accepted_by_player_id": None,
                    "status": "proposed",
                },
            ),
            event(
                2,
                "deal.canceled",
                {
                    "deal_id": "deal_000001",
                    "contract_id": "contract_false_finger",
                    "proposer_crew_id": "crew_0001",
                    "recipient_crew_id": "crew_0002",
                    "status": "canceled",
                },
            ),
        ]
    )

    assert rows[0]["status"] == "canceled"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/domain/test_deals.py -q
```

Expected: import failure for `hollow_lodge.domain.deals`.

- [ ] **Step 3: Implement deal domain model**

Create `src/hollow_lodge/domain/deals.py` with:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from hollow_lodge.domain.events import GameEvent


DealStatus = Literal["proposed", "accepted", "fulfilled", "declined", "canceled"]


class Deal(BaseModel):
    model_config = ConfigDict(frozen=True)

    deal_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    proposer_crew_id: str = Field(min_length=1)
    recipient_crew_id: str = Field(min_length=1)
    status: DealStatus
    offered_artifact_ids: tuple[str, ...]
    requested_artifact_ids: tuple[str, ...]
    soft_terms: tuple[str, ...] = ()
    expires_phase: str | None = None
    proposer_player_id: str = Field(min_length=1)
    accepted_by_player_id: str | None = None
    proposer_received_artifact_ids: tuple[str, ...] = ()
    recipient_received_artifact_ids: tuple[str, ...] = ()

    def visible_to_crew(self, crew_id: str) -> bool:
        return crew_id in {self.proposer_crew_id, self.recipient_crew_id}


def deal_rows_from_events(events: list[GameEvent] | tuple[GameEvent, ...]) -> list[dict]:
    deals: dict[str, Deal] = {}
    for item in events:
        if item.type == "deal.proposed":
            deals[item.payload["deal_id"]] = Deal(
                deal_id=item.payload["deal_id"],
                contract_id=item.payload["contract_id"],
                proposer_crew_id=item.payload["proposer_crew_id"],
                recipient_crew_id=item.payload["recipient_crew_id"],
                status="proposed",
                offered_artifact_ids=tuple(item.payload["offered_artifact_ids"]),
                requested_artifact_ids=tuple(item.payload["requested_artifact_ids"]),
                soft_terms=tuple(item.payload.get("soft_terms", [])),
                expires_phase=item.payload.get("expires_phase"),
                proposer_player_id=item.payload["proposer_player_id"],
                accepted_by_player_id=item.payload.get("accepted_by_player_id"),
            )
        elif item.type in {"deal.accepted", "deal.fulfilled", "deal.declined", "deal.canceled"}:
            deal_id = item.payload["deal_id"]
            if deal_id not in deals:
                continue
            deals[deal_id] = _apply_lifecycle_event(deals[deal_id], item)
    return [
        deal.model_dump(mode="json")
        for deal in sorted(deals.values(), key=lambda candidate: candidate.deal_id)
    ]


def _apply_lifecycle_event(deal: Deal, event: GameEvent) -> Deal:
    if event.type == "deal.accepted":
        return deal.model_copy(
            update={
                "status": "accepted",
                "accepted_by_player_id": event.payload["accepted_by_player_id"],
            }
        )
    if event.type == "deal.fulfilled":
        return deal.model_copy(
            update={
                "status": "fulfilled",
                "proposer_received_artifact_ids": tuple(
                    event.payload.get("proposer_received_artifact_ids", [])
                ),
                "recipient_received_artifact_ids": tuple(
                    event.payload.get("recipient_received_artifact_ids", [])
                ),
            }
        )
    if event.type == "deal.declined":
        return deal.model_copy(update={"status": "declined"})
    if event.type == "deal.canceled":
        return deal.model_copy(update={"status": "canceled"})
    return deal
```

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/domain/test_deals.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/hollow_lodge/domain/deals.py tests/domain/test_deals.py
git commit -m "feat: add deal domain projection"
```

## Task 2: Crew-Scoped Artifact Deal Copies

**Files:**

- Modify: `src/hollow_lodge/domain/artifacts.py`
- Modify: `src/hollow_lodge/server/artifact_service.py`
- Create: `tests/server/test_artifact_deal_copies.py`

- [ ] **Step 1: Write failing crew-copy tests**

Create `tests/server/test_artifact_deal_copies.py`:

```python
from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def register(client: TestClient, invite: str, name: str) -> dict[str, str]:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def command_auth(token: str, key: str) -> dict[str, str]:
    return {**auth(token), "Idempotency-Key": key}


def test_deal_copy_is_visible_to_recipient_crew_members(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    crew = client.post(
        "/crews",
        json={"name": "Moth"},
        headers=command_auth(bela["token"], "crew-moth"),
    ).json()
    client.post(
        f"/crews/{crew['crew_id']}/join",
        json={"join_code": crew["join_code"]},
        headers=command_auth(caro["token"], "join-caro"),
    )

    copied = app.state.artifact_service.copy_artifact_for_deal(
        source_artifact_id="artifact_ledger_rubric",
        source_crew_id="crew_source",
        recipient_crew_id=crew["crew_id"],
        actor_id=ada["player_id"],
        deal_id="deal_000001",
        idempotency_key="deal-copy-ledger",
    )

    bela_view = client.get(f"/artifacts/{copied['artifact_id']}", headers=auth(bela["token"]))
    caro_view = client.get(f"/artifacts/{copied['artifact_id']}", headers=auth(caro["token"]))
    assert bela_view.status_code == 200
    assert caro_view.status_code == 200
    assert "deal:deal_000001" in bela_view.json()["source_chain"]


def test_deal_copy_replay_returns_same_copy(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    first = app.state.artifact_service.copy_artifact_for_deal(
        source_artifact_id="artifact_ledger_rubric",
        source_crew_id="crew_0001",
        recipient_crew_id="crew_0002",
        actor_id=ada["player_id"],
        deal_id="deal_000001",
        idempotency_key="deal-copy-ledger",
    )
    replay = app.state.artifact_service.copy_artifact_for_deal(
        source_artifact_id="artifact_ledger_rubric",
        source_crew_id="crew_0001",
        recipient_crew_id="crew_0002",
        actor_id=ada["player_id"],
        deal_id="deal_000001",
        idempotency_key="deal-copy-ledger",
    )

    assert replay["artifact_id"] == first["artifact_id"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/server/test_artifact_deal_copies.py -q
```

Expected: `AttributeError` for missing `copy_artifact_for_deal`.

- [ ] **Step 3: Add artifact copy constructor**

Modify `ArtifactCopy` in `src/hollow_lodge/domain/artifacts.py`:

```python
    @classmethod
    def from_deal_source(
        cls,
        *,
        source_artifact_id: str,
        copy_artifact_id: str,
        contract_id: str,
        source_crew_id: str,
        recipient_crew_id: str,
        deal_id: str,
        title: str,
        public_summary: str,
    ) -> ArtifactCopy:
        return cls(
            artifact_id=copy_artifact_id,
            source_artifact_id=source_artifact_id,
            contract_id=contract_id,
            title=title,
            public_summary=public_summary,
            source_chain=(
                f"artifact:{source_artifact_id}",
                f"deal:{deal_id}",
                f"crew-transfer:{source_crew_id}->{recipient_crew_id}",
            ),
        )
```

- [ ] **Step 4: Add `ArtifactService.copy_artifact_for_deal`**

Modify `src/hollow_lodge/server/artifact_service.py`:

```python
    def copy_artifact_for_deal(
        self,
        *,
        source_artifact_id: str,
        source_crew_id: str,
        recipient_crew_id: str,
        actor_id: str,
        deal_id: str,
        idempotency_key: str,
    ) -> dict:
        with self._lock:
            replay = self._matching_deal_copy_replay(
                idempotency_key=idempotency_key,
                source_artifact_id=source_artifact_id,
                source_crew_id=source_crew_id,
                recipient_crew_id=recipient_crew_id,
                deal_id=deal_id,
            )
            if replay is not None:
                return replay
            artifact = STARTER_ARTIFACT_GRAPH.artifact_by_id(source_artifact_id)
            if artifact.copy_policy == "sealed":
                raise ValueError("artifact cannot be transferred")
            artifact_copy = ArtifactCopy.from_deal_source(
                source_artifact_id=artifact.artifact_id,
                copy_artifact_id=(
                    f"{artifact.artifact_id}.dealcopy."
                    f"{deal_id}.{recipient_crew_id}.{self._next_transfer_number()}"
                ),
                contract_id=artifact.contract_id,
                source_crew_id=source_crew_id,
                recipient_crew_id=recipient_crew_id,
                deal_id=deal_id,
                title=artifact.title,
                public_summary=artifact.public_summary,
            )
            surface = artifact_copy.surface_view()
            self._event_store.append_command(
                event_type="artifact.deal_copied",
                actor_id=actor_id,
                visibility=EventVisibility.crews([source_crew_id, recipient_crew_id]),
                payload={
                    "deal_id": deal_id,
                    "source_crew_id": source_crew_id,
                    "recipient_crew_id": recipient_crew_id,
                    "source_artifact_id": artifact.artifact_id,
                    "surface": surface,
                },
                idempotency_key=idempotency_key,
            )
            self._event_store.append_command(
                event_type="artifact.deal_copied.internal",
                actor_id="server",
                visibility=EventVisibility.server_only(),
                payload={
                    "copy_idempotency_key": idempotency_key,
                    "artifact_copy": artifact_copy.model_dump(mode="json"),
                },
                idempotency_key=f"{idempotency_key}.internal",
            )
            return surface
```

Also update:

```python
    def _visible_transferred_copy_surfaces(self, player_id: str) -> list[dict]:
```

to include both `artifact.transferred` and `artifact.deal_copied` events visible to the player through their player principal. Then add a new helper that includes crew principals in `visible_artifacts_for_player`; direct player copies remain player-visible, deal copies become visible through `crew_ids`.

Add:

```python
    def _matching_deal_copy_replay(
        self,
        *,
        idempotency_key: str,
        source_artifact_id: str,
        source_crew_id: str,
        recipient_crew_id: str,
        deal_id: str,
    ) -> dict | None:
        for event in self._event_store.read():
            if event.idempotency_key != idempotency_key:
                continue
            if event.type != "artifact.deal_copied":
                raise ValueError("idempotency key conflict")
            if (
                event.payload.get("source_artifact_id") != source_artifact_id
                or event.payload.get("source_crew_id") != source_crew_id
                or event.payload.get("recipient_crew_id") != recipient_crew_id
                or event.payload.get("deal_id") != deal_id
            ):
                raise ValueError("idempotency key conflict")
            return event.payload["surface"]
        return None
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/server/test_artifact_deal_copies.py tests/server/test_artifact_transfer.py -q
```

Expected: all tests pass and existing player transfer behavior remains unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/hollow_lodge/domain/artifacts.py src/hollow_lodge/server/artifact_service.py tests/server/test_artifact_deal_copies.py
git commit -m "feat: add crew-scoped artifact deal copies"
```

## Task 3: Deal Service

**Files:**

- Create: `src/hollow_lodge/server/deal_service.py`
- Create: `tests/server/test_deal_service.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/server/test_deal_service.py`:

```python
from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def register(client: TestClient, invite: str, name: str) -> dict[str, str]:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def command_auth(token: str, key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


def create_crew(client: TestClient, token: str, name: str, key: str) -> dict:
    response = client.post("/crews", json={"name": name}, headers=command_auth(token, key))
    assert response.status_code == 201
    return response.json()


def test_accept_fulfills_artifact_swap_atomically(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "Gilt Knives", "crew-gilt")
    moth = create_crew(client, bela["token"], "Moth Lanterns", "crew-moth")
    app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="test setup",
        idempotency_key="grant-chapel",
    )

    deal = app.state.deal_service.propose(
        contract_id="contract_false_finger",
        proposer_crew_id=gilt["crew_id"],
        recipient_crew_id=moth["crew_id"],
        offered_artifact_ids=["artifact_ledger_rubric"],
        requested_artifact_ids=["artifact_chapel_debt_mark"],
        soft_terms=["Do not cite us."],
        expires_phase="Auction Preview",
        proposer_player_id=ada["player_id"],
        idempotency_key="deal-propose",
    )
    fulfilled = app.state.deal_service.accept(
        deal_id=deal["deal_id"],
        actor_player_id=bela["player_id"],
        idempotency_key="deal-accept",
    )

    assert fulfilled["status"] == "fulfilled"
    assert fulfilled["recipient_received_artifact_ids"][0].startswith("artifact_ledger_rubric.dealcopy.")
    assert fulfilled["proposer_received_artifact_ids"][0].startswith("artifact_chapel_debt_mark.dealcopy.")


def test_accept_rejects_when_requested_artifact_not_visible_to_recipient(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "Gilt Knives", "crew-gilt")
    moth = create_crew(client, bela["token"], "Moth Lanterns", "crew-moth")
    deal = app.state.deal_service.propose(
        contract_id="contract_false_finger",
        proposer_crew_id=gilt["crew_id"],
        recipient_crew_id=moth["crew_id"],
        offered_artifact_ids=["artifact_ledger_rubric"],
        requested_artifact_ids=["artifact_chapel_debt_mark"],
        soft_terms=[],
        expires_phase=None,
        proposer_player_id=ada["player_id"],
        idempotency_key="deal-propose",
    )

    try:
        app.state.deal_service.accept(
            deal_id=deal["deal_id"],
            actor_player_id=bela["player_id"],
            idempotency_key="deal-accept",
        )
    except KeyError as exc:
        assert str(exc).strip("'") == "artifact_chapel_debt_mark"
    else:
        raise AssertionError("accept should reject unavailable requested artifact")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/server/test_deal_service.py -q
```

Expected: missing `deal_service` on app state.

- [ ] **Step 3: Implement DealService**

Create `src/hollow_lodge/server/deal_service.py` with these public methods:

```python
class DealService:
    def __init__(
        self,
        *,
        event_store: JsonlEventStore,
        crew_service: CrewService,
        artifact_service: ArtifactService,
    ):
        self._event_store = event_store
        self._crew_service = crew_service
        self._artifact_service = artifact_service
        self._lock = threading.RLock()

    def list_for_player(self, player_id: str) -> list[dict]:
        crew_ids = set(self._crew_service.crew_ids_for_player(player_id))
        return [
            row
            for row in deal_rows_from_events(self._event_store.read())
            if row["proposer_crew_id"] in crew_ids or row["recipient_crew_id"] in crew_ids
        ]
```

Implement `propose`, `accept`, `decline`, and `cancel` with these exact validation outcomes:

```text
PermissionError("not a crew member")
KeyError("crew not found")
KeyError(<artifact_id>)
ValueError("deal not proposed")
ValueError("idempotency key conflict")
```

Use these deal ids:

```python
def _next_deal_id(self) -> str:
    count = sum(1 for event in self._event_store.read() if event.type == "deal.proposed")
    return f"deal_{count + 1:06d}"
```

Acceptance order must be:

1. Resolve deal from projection.
2. Validate actor is recipient crew member.
3. Validate deal status is `proposed`.
4. Validate proposer crew can still view every offered artifact by checking any proposer crew member with proposer crew ids.
5. Validate recipient crew can still view every requested artifact by checking any recipient crew member with recipient crew ids.
6. Append `deal.accepted`.
7. Copy offered artifacts to recipient crew with idempotency keys `f"{idempotency_key}.recipient.{index}"`.
8. Copy requested artifacts to proposer crew with idempotency keys `f"{idempotency_key}.proposer.{index}"`.
9. Append `deal.fulfilled`.
10. Return the fulfilled projected deal.

Use `COMMAND_SERIALIZATION_LOCK` from `services.py` or a local `RLock` to prevent interleaved accept operations in the single-process v1 server.

- [ ] **Step 4: Wire app state**

Modify `src/hollow_lodge/server/app.py`:

```python
from hollow_lodge.server.deal_service import DealService
```

After `artifact_service` creation:

```python
    if artifact_service is not None:
        app.state.deal_service = DealService(
            event_store=event_store,
            crew_service=crew_service,
            artifact_service=artifact_service,
        )
```

- [ ] **Step 5: Run service tests**

Run:

```bash
pytest tests/server/test_deal_service.py tests/server/test_artifact_deal_copies.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/hollow_lodge/server/deal_service.py src/hollow_lodge/server/app.py tests/server/test_deal_service.py
git commit -m "feat: add escrowed deal service"
```

## Task 4: Deal HTTP Routes

**Files:**

- Create: `src/hollow_lodge/server/routes_deals.py`
- Modify: `src/hollow_lodge/server/app.py`
- Create: `tests/server/test_deal_routes.py`

- [ ] **Step 1: Write failing route tests**

Create `tests/server/test_deal_routes.py`:

```python
from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def register(client: TestClient, invite: str, name: str) -> dict[str, str]:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def command_auth(token: str, key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_crew(client: TestClient, token: str, name: str, key: str) -> dict:
    response = client.post("/crews", json={"name": name}, headers=command_auth(token, key))
    assert response.status_code == 201
    return response.json()


def proposed_deal_payload(gilt: dict, moth: dict) -> dict:
    return {
        "contract_id": "contract_false_finger",
        "proposer_crew_id": gilt["crew_id"],
        "recipient_crew_id": moth["crew_id"],
        "offered_artifact_ids": ["artifact_ledger_rubric"],
        "requested_artifact_ids": ["artifact_chapel_debt_mark"],
        "soft_terms": ["Do not cite us."],
        "expires_phase": "Auction Preview",
    }


def test_deal_routes_propose_list_accept(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = create_crew(client, ada["token"], "Gilt Knives", "crew-gilt")
    moth = create_crew(client, bela["token"], "Moth Lanterns", "crew-moth")
    app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="test setup",
        idempotency_key="grant-chapel",
    )

    propose = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )
    visible = client.get("/deals", headers=auth(bela["token"]))
    accept = client.post(
        f"/deals/{propose.json()['deal_id']}/accept",
        headers=command_auth(bela["token"], "deal-accept"),
        json={},
    )

    assert propose.status_code == 201
    assert propose.json()["status"] == "proposed"
    assert visible.status_code == 200
    assert visible.json()["deals"][0]["soft_terms"] == ["Do not cite us."]
    assert accept.status_code == 200
    assert accept.json()["status"] == "fulfilled"


def test_non_member_cannot_accept_deal(tmp_path):
    app = create_app(data_dir=tmp_path, invite_codes=["a", "b", "c"])
    client = TestClient(app)
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    caro = register(client, "c", "Caro")
    gilt = create_crew(client, ada["token"], "Gilt Knives", "crew-gilt")
    moth = create_crew(client, bela["token"], "Moth Lanterns", "crew-moth")
    app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="test setup",
        idempotency_key="grant-chapel",
    )
    propose = client.post(
        "/deals",
        headers=command_auth(ada["token"], "deal-propose"),
        json=proposed_deal_payload(gilt, moth),
    )

    accept = client.post(
        f"/deals/{propose.json()['deal_id']}/accept",
        headers=command_auth(caro["token"], "deal-accept"),
        json={},
    )

    assert accept.status_code == 403
    assert accept.json()["detail"] == "not a crew member"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/server/test_deal_routes.py -q
```

Expected: 404 for `/deals`.

- [ ] **Step 3: Implement routes**

Create `src/hollow_lodge/server/routes_deals.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.auth import current_player


router = APIRouter(prefix="/deals", tags=["deals"])


class ProposeDealRequest(BaseModel):
    contract_id: str = Field(min_length=1)
    proposer_crew_id: str = Field(min_length=1)
    recipient_crew_id: str = Field(min_length=1)
    offered_artifact_ids: list[str] = Field(min_length=1)
    requested_artifact_ids: list[str] = Field(min_length=1)
    soft_terms: list[str] = []
    expires_phase: str | None = None


@router.get("")
def list_deals(request: Request, player: Player = Depends(current_player)):
    return {"deals": request.app.state.deal_service.list_for_player(player.player_id)}
```

Add `POST /deals`, `POST /deals/{deal_id}/accept`, `POST /deals/{deal_id}/decline`, and `POST /deals/{deal_id}/cancel`. Map exceptions to:

```text
PermissionError -> 403
KeyError("crew not found") -> 404 detail "crew not found"
KeyError(other) -> 404 detail "artifact not found"
ValueError("deal not proposed") -> 409 detail "deal not proposed"
ValueError("idempotency key conflict") -> 409 detail "idempotency key conflict"
```

Modify `src/hollow_lodge/server/app.py`:

```python
from hollow_lodge.server.routes_deals import router as deals_router
...
app.include_router(deals_router)
```

- [ ] **Step 4: Run route tests**

Run:

```bash
pytest tests/server/test_deal_routes.py tests/server/test_deal_service.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/hollow_lodge/server/routes_deals.py src/hollow_lodge/server/app.py tests/server/test_deal_routes.py
git commit -m "feat: expose escrowed deal routes"
```

## Task 5: Inbox And Crew Board Deal Projections

**Files:**

- Modify: `src/hollow_lodge/server/routes_crews.py`
- Modify: `src/hollow_lodge/server/routes_contracts.py`
- Modify: `src/hollow_lodge/client/render_packets.py`
- Modify: `src/hollow_lodge/client/render.py`
- Create: `tests/client/test_deal_render.py`

- [ ] **Step 1: Write render tests**

Create `tests/client/test_deal_render.py`:

```python
from hollow_lodge.client.render_packets import build_crew_board_packet, build_inbox_packet


def deal_row(status: str = "proposed") -> dict:
    return {
        "deal_id": "deal_000001",
        "contract_id": "contract_false_finger",
        "proposer_crew_id": "crew_0001",
        "recipient_crew_id": "crew_0002",
        "status": status,
        "offered_artifact_ids": ["artifact_ledger_rubric"],
        "requested_artifact_ids": ["artifact_chapel_debt_mark"],
        "soft_terms": ["Do not cite us."],
        "expires_phase": "Auction Preview",
        "proposer_player_id": "player_0001",
        "accepted_by_player_id": None,
        "proposer_received_artifact_ids": [],
        "recipient_received_artifact_ids": [],
    }


def test_inbox_renders_incoming_deal():
    packet = build_inbox_packet(
        {
            "player_id": "player_0002",
            "active_contracts": [],
            "incoming_proof_fragments": [],
            "visible_artifacts": [],
            "deals": [deal_row()],
        }
    )

    assert "Incoming deals:" in packet.player_markdown
    assert "deal_000001 proposed" in packet.player_markdown
    assert packet.agent_context["deals"][0]["soft_terms"] == ["Do not cite us."]


def test_crew_board_renders_deals():
    packet = build_crew_board_packet(
        {
            "player_id": "player_0001",
            "crew": {
                "crew_id": "crew_0001",
                "name": "Gilt Knives",
                "member_ids": ["player_0001"],
                "member_count": 1,
                "ready_for_full_contracts": False,
                "readiness_warning": "Needs 3-5 players for full contracts.",
            },
            "active_contracts": [],
            "visible_artifacts": [],
            "deals": [deal_row("fulfilled")],
            "dossier": {
                "dossier_id": "dossier_crew_0001",
                "crew_id": "crew_0001",
                "packet_lead_player_id": "player_0001",
                "claim": None,
                "evidence_ids": [],
                "artifact_citations": [],
                "member_contributions": [],
            },
        }
    )

    assert "Deals:" in packet.player_markdown
    assert "deal_000001 fulfilled" in packet.player_markdown
    assert packet.agent_context["deals"][0]["status"] == "fulfilled"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/client/test_deal_render.py -q
```

Expected: missing rendered deal content.

- [ ] **Step 3: Add deal rows to server boards**

Modify `routes_contracts.py` inbox response and `routes_crews.py` crew-board response to include:

```python
"deals": request.app.state.deal_service.list_for_player(player.player_id),
```

Only add this when `deal_service` exists on `app.state`; otherwise return an empty list for tests that build partial app state.

- [ ] **Step 4: Render deals**

Modify `src/hollow_lodge/client/render_packets.py`:

```python
def _shape_deal(deal: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deal[key]
        for key in (
            "deal_id",
            "contract_id",
            "proposer_crew_id",
            "recipient_crew_id",
            "status",
            "offered_artifact_ids",
            "requested_artifact_ids",
            "soft_terms",
            "expires_phase",
            "proposer_received_artifact_ids",
            "recipient_received_artifact_ids",
        )
        if key in deal
    }
```

In inbox markdown, add:

```python
    deals = inbox.get("deals", [])
    lines.append("")
    lines.append("Incoming deals:")
    if deals:
        lines.extend(f"- {deal['deal_id']} {deal['status']}" for deal in deals)
    else:
        lines.append("- none")
```

In crew board markdown, add:

```python
    lines.extend(["", "Deals:"])
    deals = board.get("deals", [])
    if deals:
        lines.extend(f"- {deal['deal_id']} {deal['status']}" for deal in deals)
    else:
        lines.append("- none")
```

Add shaped deals to each packet's `agent_context`.

- [ ] **Step 5: Run render and board tests**

Run:

```bash
pytest tests/client/test_deal_render.py tests/client/test_contract_board.py tests/client/test_artifact_render.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/hollow_lodge/server/routes_crews.py src/hollow_lodge/server/routes_contracts.py src/hollow_lodge/client/render_packets.py src/hollow_lodge/client/render.py tests/client/test_deal_render.py
git commit -m "feat: render escrowed deals on boards"
```

## Task 6: CLI Deal Commands

**Files:**

- Modify: `src/hollow_lodge/client/api.py`
- Modify: `src/hollow_lodge/client/cli.py`
- Create: `tests/client/test_deal_cli.py`

- [ ] **Step 1: Write CLI tests**

Create `tests/client/test_deal_cli.py` with `typer.testing.CliRunner` tests matching the existing CLI test style:

```python
from typer.testing import CliRunner

from hollow_lodge.client.cli import app


runner = CliRunner()


def test_deal_propose_requires_from_crew_when_no_active_crew(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(
        '{"server_url":"http://example.test","player_id":"player_0001","display_name":"Ada","token":"token","active_crew_id":null}\\n'
    )

    result = runner.invoke(
        app,
        [
            "deal",
            "propose",
            "--to-crew",
            "crew_0002",
            "--offer",
            "artifact_ledger_rubric",
            "--request",
            "artifact_chapel_debt_mark",
            "--config",
            str(config),
        ],
    )

    assert result.exit_code != 0
    assert "from crew required" in result.output
```

Add happy-path tests by monkeypatching `HollowLodgeApi.propose_deal`, `accept_deal`, `decline_deal`, `cancel_deal`, and `deals` to assert payloads and returned echo strings.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/client/test_deal_cli.py -q
```

Expected: command group `deal` does not exist.

- [ ] **Step 3: Add API methods**

Modify `src/hollow_lodge/client/api.py`:

```python
    def deals(self) -> dict[str, Any]:
        return self._get("/deals")

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
```

Add `accept_deal`, `decline_deal`, and `cancel_deal` methods that call `/deals/{deal_id}/accept`, `/decline`, and `/cancel`.

- [ ] **Step 4: Add Typer command group**

Modify `src/hollow_lodge/client/cli.py`:

```python
deal_app = typer.Typer(help="Manage escrowed artifact deals.", no_args_is_help=True)
app.add_typer(deal_app, name="deal")
```

Add commands:

```text
hollow-lodge deal list
hollow-lodge deal propose --from-crew crew_0001 --to-crew crew_0002 --offer artifact_ledger_rubric --request artifact_chapel_debt_mark --soft-term "Do not cite us."
hollow-lodge deal accept deal_000001
hollow-lodge deal decline deal_000001
hollow-lodge deal cancel deal_000001
```

Use active crew as `--from-crew` default for propose. If neither is available, raise:

```python
raise typer.BadParameter("from crew required when no active crew is configured")
```

Echo:

```text
deal_000001 proposed
deal_000001 fulfilled
deal_000001 declined
deal_000001 canceled
```

- [ ] **Step 5: Run CLI tests**

Run:

```bash
pytest tests/client/test_deal_cli.py tests/client/test_cli_commands.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/hollow_lodge/client/api.py src/hollow_lodge/client/cli.py tests/client/test_deal_cli.py
git commit -m "feat: add escrowed deal cli commands"
```

## Task 7: End-To-End Deal Loop And Smoke Script

**Files:**

- Create: `tests/e2e/test_escrowed_artifact_deals.py`
- Create: `scripts/smoke_deal_loop.py`

- [ ] **Step 1: Write e2e test**

Create `tests/e2e/test_escrowed_artifact_deals.py`:

```python
from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def test_two_crews_complete_escrowed_artifact_swap(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = client.post(
        "/identity/register",
        json={"invite_code": "a", "display_name": "Ada"},
        headers={"Idempotency-Key": "register-a"},
    ).json()
    bela = client.post(
        "/identity/register",
        json={"invite_code": "b", "display_name": "Bela"},
        headers={"Idempotency-Key": "register-b"},
    ).json()
    ada_headers = {"Authorization": f"Bearer {ada['token']}"}
    bela_headers = {"Authorization": f"Bearer {bela['token']}"}
    gilt = client.post(
        "/crews",
        json={"name": "Gilt Knives"},
        headers={**ada_headers, "Idempotency-Key": "crew-gilt"},
    ).json()
    moth = client.post(
        "/crews",
        json={"name": "Moth Lanterns"},
        headers={**bela_headers, "Idempotency-Key": "crew-moth"},
    ).json()
    client.app.state.artifact_service.grant_artifact_access(
        artifact_id="artifact_chapel_debt_mark",
        actor_id="server",
        player_ids=[],
        crew_ids=[moth["crew_id"]],
        reason="e2e setup",
        idempotency_key="grant-chapel",
    )

    proposed = client.post(
        "/deals",
        json={
            "contract_id": "contract_false_finger",
            "proposer_crew_id": gilt["crew_id"],
            "recipient_crew_id": moth["crew_id"],
            "offered_artifact_ids": ["artifact_ledger_rubric"],
            "requested_artifact_ids": ["artifact_chapel_debt_mark"],
            "soft_terms": ["Do not cite us."],
            "expires_phase": "Auction Preview",
        },
        headers={**ada_headers, "Idempotency-Key": "deal-propose"},
    ).json()
    fulfilled = client.post(
        f"/deals/{proposed['deal_id']}/accept",
        json={},
        headers={**bela_headers, "Idempotency-Key": "deal-accept"},
    ).json()
    gilt_board = client.get(f"/crews/{gilt['crew_id']}/board", headers=ada_headers).json()
    moth_board = client.get(f"/crews/{moth['crew_id']}/board", headers=bela_headers).json()

    assert fulfilled["status"] == "fulfilled"
    assert any(item["status"] == "fulfilled" for item in gilt_board["deals"])
    assert any(item["status"] == "fulfilled" for item in moth_board["deals"])
```

- [ ] **Step 2: Run e2e test**

Run:

```bash
pytest tests/e2e/test_escrowed_artifact_deals.py -q
```

Expected: pass after Tasks 1-6.

- [ ] **Step 3: Add smoke script**

Create `scripts/smoke_deal_loop.py` that:

1. Creates a temporary data dir.
2. Registers Ada and Bela.
3. Creates Gilt Knives and Moth Lanterns.
4. Grants Moth `artifact_chapel_debt_mark`.
5. Proposes and accepts an escrowed deal.
6. Prints each deal and artifact event type in sequence.

Use `TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))` so it runs without a live server.

- [ ] **Step 4: Run smoke script**

Run:

```bash
python scripts/smoke_deal_loop.py
```

Expected output includes:

```text
deal.proposed
deal.accepted
artifact.deal_copied
artifact.deal_copied.internal
artifact.deal_copied
artifact.deal_copied.internal
deal.fulfilled
```

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_escrowed_artifact_deals.py scripts/smoke_deal_loop.py
git commit -m "test: cover escrowed artifact deal loop"
```

## Task 8: Final Verification

**Files:**

- No new files.

- [ ] **Step 1: Run targeted tests**

Run:

```bash
pytest tests/domain/test_deals.py tests/server/test_artifact_deal_copies.py tests/server/test_deal_service.py tests/server/test_deal_routes.py tests/client/test_deal_render.py tests/client/test_deal_cli.py tests/e2e/test_escrowed_artifact_deals.py -q
```

Expected: all targeted tests pass.

- [ ] **Step 2: Run full suite**

Run:

```bash
pytest -q
```

Expected: full suite passes.

- [ ] **Step 3: Run smoke script**

Run:

```bash
python scripts/smoke_deal_loop.py
```

Expected: event timeline includes proposed, accepted, two deal copies, and fulfilled.

- [ ] **Step 4: Inspect git state**

Run:

```bash
git status --short
```

Expected: no uncommitted changes.

## Self-Review

Spec coverage:

- Concrete artifact terms are enforced by `DealService.accept`.
- Soft terms are stored in `deal.proposed`, projected by `deal_rows_from_events`, and rendered in agent context.
- Atomicity is protected by all visibility checks before lifecycle and copy events are appended.
- Crew-scoped access is implemented through `artifact.deal_copied` visibility and crew-principal artifact projection.
- Deal routes, CLI commands, inbox, and crew board surfaces are covered.
- Expiry and broken soft-term mechanics remain outside v1.

Placeholder scan:

- This plan contains no deferred implementation markers.
- Route tests include concrete setup and assertions for success and permission failure.

Type consistency:

- Deal fields use `proposer_crew_id`, `recipient_crew_id`, `offered_artifact_ids`, `requested_artifact_ids`, `soft_terms`, `proposer_received_artifact_ids`, and `recipient_received_artifact_ids` consistently across domain, service, route, CLI, and render tasks.
