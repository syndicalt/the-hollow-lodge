# Artifact Graph Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make The Hollow Lodge's core gameplay concrete by adding a server-authoritative evidence graph, artifact inspection, asymmetric artifact unlocks, artifact transfer/leak paths, and Codex-native render surfaces.

**Architecture:** The server owns the contract truth graph: hidden truth, artifact nodes, graph edges, unlock rules, visibility, provenance, and authoritative event append. Local clients only receive player-visible artifact projections and use the Handler to help players inspect, compare, cite, transfer, and act on source material. Oracle workflows may select, reveal, summarize, or derive from seeded graph nodes, but they must not invent unconstrained core evidence after a contract opens.

**Tech Stack:** Python 3.12, FastAPI, Typer, Pydantic, pytest, httpx, append-only JSONL Eventloom-compatible event log, MCP render packets, existing OpenAI/deterministic oracle boundary.

---

## Scope Check

This is a second-stage plan on top of the existing playable skeleton. It does not replace identity, crews, chat, actions, proof dossiers, phase resolution, or the resolution oracle. It adds the missing gameplay substrate that lets players receive source material, reason over it with their local agent, coordinate with crews, trade or leak artifacts, and cite artifacts in proof dossiers.

The plan intentionally avoids a visual territory map. The "map" is an evidence graph:

```text
artifact_lot_card
  contradicts -> artifact_ledger_rubric
  mentions    -> place_chapel_archive
artifact_ledger_rubric
  hints       -> artifact_chapel_debt_mark
artifact_chapel_debt_mark
  supports    -> truth_false_finger_forgery
```

Players only see their perspective slice of that graph.

## Player Loop Target

The implementation should support this loop:

1. Player opens Codex and renders inbox.
2. Inbox shows contract pressure plus new/available artifacts.
3. Player inspects an artifact as source material.
4. Local agent helps compare visible artifacts and draft possible conclusions.
5. Player sends crew or cross-crew messages, possibly attaching artifacts or excerpts.
6. Player submits a freeform action targeting a clue path.
7. Server evaluates the action against artifact unlock rules and produces artifact access or fallout.
8. Crew cites artifacts in the dossier.
9. Phase resolution scores proof quality from actions, dossier citations, artifact provenance, and noise.
10. Result reveals standings and may unlock aftermath artifacts.

## Client/Server Boundary

Server-owned:

- contract artifact graph and hidden truth
- artifact node records and edge records
- unlock rule evaluation
- artifact custody and copy provenance
- visibility-scoped artifact projections
- transfer/leak events
- action result artifact awards
- oracle input packets and accepted outputs
- authoritative event log

Client/local-agent-owned:

- rendering inbox, contract board, crew board, artifact views
- local visible graph summaries
- local comparison/contradiction notes
- consequence clarification before transfer/action/dossier changes
- drafting messages and actions
- local perspective log sync/replay

The local agent must never learn server-only graph nodes unless the server has revealed them to that player.

## Proposed File Structure

Create focused artifact modules instead of growing `services.py` further:

```text
src/hollow_lodge/domain/artifacts.py
src/hollow_lodge/domain/artifact_graph.py
src/hollow_lodge/server/artifact_seed.py
src/hollow_lodge/server/artifact_service.py
src/hollow_lodge/server/artifact_unlocks.py
src/hollow_lodge/server/routes_artifacts.py
src/hollow_lodge/client/artifact_render.py
tests/domain/test_artifacts.py
tests/domain/test_artifact_graph.py
tests/server/test_artifact_seed.py
tests/server/test_artifact_routes.py
tests/server/test_artifact_unlocks.py
tests/client/test_artifact_render.py
tests/e2e/test_artifact_game_loop.py
```

Modify existing files:

```text
src/hollow_lodge/server/app.py
src/hollow_lodge/server/services.py
src/hollow_lodge/server/projections.py
src/hollow_lodge/server/routes_actions.py
src/hollow_lodge/server/routes_chat.py
src/hollow_lodge/server/routes_crews.py
src/hollow_lodge/server/routes_proofs.py
src/hollow_lodge/server/seed_data.py
src/hollow_lodge/client/api.py
src/hollow_lodge/client/cli.py
src/hollow_lodge/client/codex_session.py
src/hollow_lodge/client/render_packets.py
src/hollow_lodge/client/local_log.py
src/hollow_lodge/mcp_server.py
src/hollow_lodge/workflows/oracle_boundary.py
src/hollow_lodge/workflows/deterministic_oracle.py
src/hollow_lodge/workflows/openai_oracle.py
```

Responsibilities:

- `domain/artifacts.py`: immutable artifact, excerpt, custody, copy, provenance, and player-safe surface models.
- `domain/artifact_graph.py`: graph nodes, graph edges, hidden unlock rules, and graph validation.
- `server/artifact_seed.py`: deterministic starter evidence graph for The Saint's False Finger.
- `server/artifact_service.py`: authoritative artifact read/inspect/transfer/leak/award behavior.
- `server/artifact_unlocks.py`: pure unlock evaluation functions for action result and phase aftermath.
- `server/routes_artifacts.py`: HTTP API for artifact inspection, transfer, leak, and visible graph reads.
- `client/artifact_render.py`: human-readable artifact markdown plus compact agent context.

## Event Types

Add these authoritative event types:

```text
artifact.graph.seeded
artifact.access.granted
artifact.inspected
artifact.provenance.checked
artifact.transferred
artifact.transferred.internal
artifact.leaked
artifact.action_result.awarded
artifact.phase_reward.awarded
artifact.dossier.cited
```

Visibility defaults:

- `artifact.graph.seeded`: server-only
- `artifact.access.granted`: player or crew scoped
- `artifact.inspected`: player scoped
- `artifact.provenance.checked`: player scoped
- `artifact.transferred`: sender and recipient scoped
- `artifact.transferred.internal`: server-only
- `artifact.leaked`: target scoped plus possible pressure/leak scopes
- `artifact.action_result.awarded`: player or crew scoped
- `artifact.phase_reward.awarded`: crew scoped or public depending on reward
- `artifact.dossier.cited`: crew scoped

## Artifact Model V1

Use four concepts:

- **Truth graph:** server-only seeded graph for the contract.
- **Artifact node:** inspectable source material.
- **Artifact copy:** visible derivative with provenance chain and possible contamination.
- **Perspective graph:** player-visible projection of known artifacts and safe edges.

Minimal artifact fields:

```python
class ArtifactNode(BaseModel):
    artifact_id: str
    contract_id: str
    title: str
    kind: Literal[
        "lot_card",
        "ledger",
        "letter",
        "receipt",
        "witness_note",
        "rubbing",
        "omen",
        "catalogue",
        "other",
    ]
    public_summary: str
    full_text: str
    source_chain: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    proof_lanes: tuple[Literal["provenance", "material", "witness", "occult", "leverage"], ...] = ()
    phase_relevance: tuple[str, ...] = ()
    hidden_flags: tuple[str, ...] = ()
    visible_flags: tuple[str, ...] = ()
    copy_policy: Literal["copyable", "excerpt_only", "sealed"] = "copyable"
```

Minimal edge fields:

```python
class ArtifactEdge(BaseModel):
    source_id: str
    target_id: str
    relation: Literal[
        "supports",
        "contradicts",
        "mentions",
        "copies",
        "unlocks",
        "requires",
        "contaminates",
        "points_to",
    ]
    visibility: Literal["server_only", "when_both_visible", "public"] = "when_both_visible"
    public_summary: str = ""
```

Minimal unlock fields:

```python
class ArtifactUnlockRule(BaseModel):
    rule_id: str
    artifact_id: str
    contract_id: str
    phase: str
    trigger: Literal[
        "action_exposes_asset",
        "action_mentions_tag",
        "provenance_checked",
        "dossier_cites",
        "phase_resolved",
        "manual_award",
    ]
    required_terms: tuple[str, ...] = ()
    required_artifact_ids: tuple[str, ...] = ()
    award_scope: Literal["player", "crew"] = "crew"
    award_reason: str
```

## Task 1: Domain Models For Artifacts And Graphs

**Files:**
- Create: `src/hollow_lodge/domain/artifacts.py`
- Create: `src/hollow_lodge/domain/artifact_graph.py`
- Test: `tests/domain/test_artifacts.py`
- Test: `tests/domain/test_artifact_graph.py`

- [ ] **Step 1: Write failing artifact model tests**

Create `tests/domain/test_artifacts.py`:

```python
from hollow_lodge.domain.artifacts import ArtifactNode, ArtifactCopy


def test_artifact_surface_view_hides_full_text_and_hidden_flags_by_default():
    artifact = ArtifactNode(
        artifact_id="artifact_ledger_rubric",
        contract_id="contract_false_finger",
        title="Red ledger rubric",
        kind="ledger",
        public_summary="A copied rubric marks prior ownership.",
        full_text="Lot 19 passed under chapel seal.",
        hidden_flags=("ink-after-binding",),
        visible_flags=("copied-hand",),
        proof_lanes=("provenance",),
        phase_relevance=("Auction Preview",),
    )

    assert artifact.surface_view() == {
        "artifact_id": "artifact_ledger_rubric",
        "contract_id": "contract_false_finger",
        "title": "Red ledger rubric",
        "kind": "ledger",
        "public_summary": "A copied rubric marks prior ownership.",
        "visible_flags": ["copied-hand"],
        "proof_lanes": ["provenance"],
        "phase_relevance": ["Auction Preview"],
        "copy_policy": "copyable",
    }


def test_artifact_copy_preserves_provenance_chain_and_marks_copy():
    copied = ArtifactCopy.from_source(
        source_artifact_id="artifact_ledger_rubric",
        copy_artifact_id="artifact_ledger_rubric.copy.player_0002.1",
        contract_id="contract_false_finger",
        sender_player_id="player_0001",
        recipient_player_id="player_0002",
        title="Red ledger rubric copy",
        public_summary="A copied rubric marks prior ownership.",
    )

    assert copied.source_artifact_id == "artifact_ledger_rubric"
    assert copied.source_chain == (
        "artifact:artifact_ledger_rubric",
        "transfer:player_0001->player_0002",
    )
    assert copied.surface_view()["is_copy"] is True
```

- [ ] **Step 2: Run model tests and verify failure**

Run:

```bash
pytest -q tests/domain/test_artifacts.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hollow_lodge.domain.artifacts'`.

- [ ] **Step 3: Implement artifact models**

Create `src/hollow_lodge/domain/artifacts.py` with:

```python
from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field


ArtifactKind = Literal[
    "lot_card",
    "ledger",
    "letter",
    "receipt",
    "witness_note",
    "rubbing",
    "omen",
    "catalogue",
    "other",
]
ProofLane = Literal["provenance", "material", "witness", "occult", "leverage"]
CopyPolicy = Literal["copyable", "excerpt_only", "sealed"]


class ArtifactNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    kind: ArtifactKind
    public_summary: str = Field(min_length=1)
    full_text: str = Field(min_length=1)
    source_chain: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    proof_lanes: tuple[ProofLane, ...] = ()
    phase_relevance: tuple[str, ...] = ()
    hidden_flags: tuple[str, ...] = ()
    visible_flags: tuple[str, ...] = ()
    copy_policy: CopyPolicy = "copyable"

    def surface_view(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "contract_id": self.contract_id,
            "title": self.title,
            "kind": self.kind,
            "public_summary": self.public_summary,
            "visible_flags": list(self.visible_flags),
            "proof_lanes": list(self.proof_lanes),
            "phase_relevance": list(self.phase_relevance),
            "copy_policy": self.copy_policy,
        }

    def inspection_view(self) -> dict:
        return {
            **self.surface_view(),
            "full_text": self.full_text,
            "source_chain": list(self.source_chain),
        }


class ArtifactCopy(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(min_length=1)
    source_artifact_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    public_summary: str = Field(min_length=1)
    source_chain: tuple[str, ...]
    visible_flags: tuple[str, ...] = ("copy",)
    contamination_flags: tuple[str, ...] = ()

    @classmethod
    def from_source(
        cls,
        *,
        source_artifact_id: str,
        copy_artifact_id: str,
        contract_id: str,
        sender_player_id: str,
        recipient_player_id: str,
        title: str,
        public_summary: str,
    ) -> Self:
        return cls(
            artifact_id=copy_artifact_id,
            source_artifact_id=source_artifact_id,
            contract_id=contract_id,
            title=title,
            public_summary=public_summary,
            source_chain=(
                f"artifact:{source_artifact_id}",
                f"transfer:{sender_player_id}->{recipient_player_id}",
            ),
        )

    def surface_view(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "source_artifact_id": self.source_artifact_id,
            "contract_id": self.contract_id,
            "title": self.title,
            "public_summary": self.public_summary,
            "source_chain": list(self.source_chain),
            "visible_flags": list(self.visible_flags),
            "contamination_flags": list(self.contamination_flags),
            "is_copy": True,
        }
```

- [ ] **Step 4: Write failing graph validation tests**

Create `tests/domain/test_artifact_graph.py`:

```python
import pytest

from hollow_lodge.domain.artifact_graph import ArtifactEdge, ArtifactGraph, ArtifactUnlockRule
from hollow_lodge.domain.artifacts import ArtifactNode


def artifact(artifact_id: str) -> ArtifactNode:
    return ArtifactNode(
        artifact_id=artifact_id,
        contract_id="contract_false_finger",
        title=artifact_id.replace("_", " ").title(),
        kind="ledger",
        public_summary=f"Summary for {artifact_id}.",
        full_text=f"Full text for {artifact_id}.",
    )


def test_graph_rejects_edges_to_unknown_artifacts():
    with pytest.raises(ValueError, match="unknown edge target"):
        ArtifactGraph(
            contract_id="contract_false_finger",
            artifacts=(artifact("artifact_lot_card"),),
            edges=(
                ArtifactEdge(
                    source_id="artifact_lot_card",
                    target_id="artifact_missing",
                    relation="mentions",
                ),
            ),
            unlock_rules=(),
        )


def test_graph_visible_slice_only_returns_edges_between_visible_artifacts():
    graph = ArtifactGraph(
        contract_id="contract_false_finger",
        artifacts=(artifact("artifact_lot_card"), artifact("artifact_ledger_rubric")),
        edges=(
            ArtifactEdge(
                source_id="artifact_lot_card",
                target_id="artifact_ledger_rubric",
                relation="contradicts",
                public_summary="The dates do not agree.",
            ),
        ),
        unlock_rules=(
            ArtifactUnlockRule(
                rule_id="unlock-ledger",
                artifact_id="artifact_ledger_rubric",
                contract_id="contract_false_finger",
                phase="Auction Preview",
                trigger="action_mentions_tag",
                required_terms=("ledger",),
                award_reason="Followed the ledger trail.",
            ),
        ),
    )

    assert graph.visible_slice({"artifact_lot_card"})["edges"] == []
    assert graph.visible_slice({"artifact_lot_card", "artifact_ledger_rubric"})["edges"] == [
        {
            "source_id": "artifact_lot_card",
            "target_id": "artifact_ledger_rubric",
            "relation": "contradicts",
            "public_summary": "The dates do not agree.",
        }
    ]
```

- [ ] **Step 5: Implement graph models**

Create `src/hollow_lodge/domain/artifact_graph.py` with:

```python
from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hollow_lodge.domain.artifacts import ArtifactNode


ArtifactRelation = Literal[
    "supports",
    "contradicts",
    "mentions",
    "copies",
    "unlocks",
    "requires",
    "contaminates",
    "points_to",
]
ArtifactVisibility = Literal["server_only", "when_both_visible", "public"]
ArtifactUnlockTrigger = Literal[
    "action_exposes_asset",
    "action_mentions_tag",
    "provenance_checked",
    "dossier_cites",
    "phase_resolved",
    "manual_award",
]
ArtifactAwardScope = Literal["player", "crew"]


class ArtifactEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    relation: ArtifactRelation
    visibility: ArtifactVisibility = "when_both_visible"
    public_summary: str = ""

    def surface_view(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "public_summary": self.public_summary,
        }


class ArtifactUnlockRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    trigger: ArtifactUnlockTrigger
    required_terms: tuple[str, ...] = ()
    required_artifact_ids: tuple[str, ...] = ()
    award_scope: ArtifactAwardScope = "crew"
    award_reason: str = Field(min_length=1)


class ArtifactGraph(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_id: str = Field(min_length=1)
    artifacts: tuple[ArtifactNode, ...]
    edges: tuple[ArtifactEdge, ...] = ()
    unlock_rules: tuple[ArtifactUnlockRule, ...] = ()

    @model_validator(mode="after")
    def validate_graph_references(self) -> Self:
        artifact_ids = {artifact.artifact_id for artifact in self.artifacts}
        for edge in self.edges:
            if edge.source_id not in artifact_ids:
                raise ValueError(f"unknown edge source: {edge.source_id}")
            if edge.target_id not in artifact_ids:
                raise ValueError(f"unknown edge target: {edge.target_id}")
        for rule in self.unlock_rules:
            if rule.artifact_id not in artifact_ids:
                raise ValueError(f"unknown unlock artifact: {rule.artifact_id}")
            for required_artifact_id in rule.required_artifact_ids:
                if required_artifact_id not in artifact_ids:
                    raise ValueError(f"unknown required artifact: {required_artifact_id}")
        return self

    def artifact_by_id(self, artifact_id: str) -> ArtifactNode:
        for artifact in self.artifacts:
            if artifact.artifact_id == artifact_id:
                return artifact
        raise KeyError(artifact_id)

    def visible_slice(self, visible_artifact_ids: set[str]) -> dict:
        return {
            "contract_id": self.contract_id,
            "artifacts": [
                artifact.surface_view()
                for artifact in self.artifacts
                if artifact.artifact_id in visible_artifact_ids
            ],
            "edges": [
                edge.surface_view()
                for edge in self.edges
                if edge.visibility != "server_only"
                and edge.source_id in visible_artifact_ids
                and edge.target_id in visible_artifact_ids
            ],
        }
```

- [ ] **Step 6: Run domain tests**

Run:

```bash
pytest -q tests/domain/test_artifacts.py tests/domain/test_artifact_graph.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/hollow_lodge/domain/artifacts.py src/hollow_lodge/domain/artifact_graph.py tests/domain/test_artifacts.py tests/domain/test_artifact_graph.py
git commit -m "feat: add artifact graph domain models"
```

## Task 2: Seed The Saint's False Finger Artifact Graph

**Files:**
- Create: `src/hollow_lodge/server/artifact_seed.py`
- Modify: `src/hollow_lodge/server/seed_data.py`
- Test: `tests/server/test_artifact_seed.py`

- [ ] **Step 1: Write failing seed tests**

Create `tests/server/test_artifact_seed.py`:

```python
from hollow_lodge.server.artifact_seed import STARTER_ARTIFACT_GRAPH


def test_starter_artifact_graph_has_public_and_hidden_nodes():
    artifact_ids = {artifact.artifact_id for artifact in STARTER_ARTIFACT_GRAPH.artifacts}

    assert "artifact_lot_card" in artifact_ids
    assert "artifact_ledger_rubric" in artifact_ids
    assert "artifact_chapel_debt_mark" in artifact_ids
    assert "artifact_clerk_pencil_note" in artifact_ids


def test_starter_artifact_graph_has_unlock_rules_for_hidden_artifacts():
    rules = {rule.artifact_id: rule for rule in STARTER_ARTIFACT_GRAPH.unlock_rules}

    assert rules["artifact_chapel_debt_mark"].trigger == "action_mentions_tag"
    assert "chapel" in rules["artifact_chapel_debt_mark"].required_terms
    assert rules["artifact_clerk_pencil_note"].trigger == "action_mentions_tag"
    assert "clerk" in rules["artifact_clerk_pencil_note"].required_terms
```

- [ ] **Step 2: Run seed tests and verify failure**

Run:

```bash
pytest -q tests/server/test_artifact_seed.py
```

Expected: FAIL with missing `hollow_lodge.server.artifact_seed`.

- [ ] **Step 3: Implement deterministic starter graph**

Create `src/hollow_lodge/server/artifact_seed.py`:

```python
from __future__ import annotations

from hollow_lodge.domain.artifact_graph import ArtifactEdge, ArtifactGraph, ArtifactUnlockRule
from hollow_lodge.domain.artifacts import ArtifactNode


STARTER_PUBLIC_ARTIFACT_IDS = ("artifact_lot_card", "artifact_ledger_rubric")

STARTER_ARTIFACT_GRAPH = ArtifactGraph(
    contract_id="contract_false_finger",
    artifacts=(
        ArtifactNode(
            artifact_id="artifact_lot_card",
            contract_id="contract_false_finger",
            title="Auction Lot Card",
            kind="lot_card",
            public_summary="A vellum card attributes the reliquary finger to Saint Aint.",
            full_text=(
                "Lot 19. Reliquary finger of Saint Aint. "
                "Held under sealed preview by Venn & Bell, with chapel seal affixed."
            ),
            tags=("auction", "lot", "chapel", "saint-aint"),
            proof_lanes=("provenance", "leverage"),
            phase_relevance=("Auction Preview",),
            visible_flags=("public-lot",),
        ),
        ArtifactNode(
            artifact_id="artifact_ledger_rubric",
            contract_id="contract_false_finger",
            title="Red Ledger Rubric",
            kind="ledger",
            public_summary="A copied rubric marks three prior owners in an unfamiliar hand.",
            full_text=(
                "Rubric copy: Armitage, then Venn, then a chapel debt mark. "
                "The last hand is redder and later than the binding."
            ),
            source_chain=("archive:lot-card",),
            tags=("ledger", "rubric", "ownership", "red-hand"),
            proof_lanes=("provenance", "material"),
            phase_relevance=("Auction Preview",),
            hidden_flags=("ink-after-binding",),
            visible_flags=("copied-hand",),
        ),
        ArtifactNode(
            artifact_id="artifact_chapel_debt_mark",
            contract_id="contract_false_finger",
            title="Chapel Debt Mark Rubbing",
            kind="rubbing",
            public_summary="A charcoal rubbing of a chapel debt mark tied to the reliquary case.",
            full_text=(
                "The rubbing shows the same chapel mark named in the ledger, "
                "but it is a debt sign rather than a saintly custody seal."
            ),
            tags=("chapel", "debt", "mark", "omen"),
            proof_lanes=("occult", "provenance"),
            phase_relevance=("Auction Preview", "Access"),
            hidden_flags=("debtor-omen"),
        ),
        ArtifactNode(
            artifact_id="artifact_clerk_pencil_note",
            contract_id="contract_false_finger",
            title="Clerk's Pencil Correction",
            kind="witness_note",
            public_summary="A clerk's correction questions the lot's ownership date.",
            full_text=(
                "Pencil note: 'Do not read the chapel mark as custody. "
                "Date was corrected after the preview catalogue was copied.'"
            ),
            tags=("clerk", "pencil", "catalogue", "date"),
            proof_lanes=("witness", "provenance", "leverage"),
            phase_relevance=("Auction Preview",),
        ),
    ),
    edges=(
        ArtifactEdge(
            source_id="artifact_lot_card",
            target_id="artifact_ledger_rubric",
            relation="contradicts",
            public_summary="The public lot card and copied ledger disagree on custody.",
        ),
        ArtifactEdge(
            source_id="artifact_ledger_rubric",
            target_id="artifact_chapel_debt_mark",
            relation="points_to",
            public_summary="The ledger's chapel mark points toward a debt record.",
        ),
        ArtifactEdge(
            source_id="artifact_clerk_pencil_note",
            target_id="artifact_lot_card",
            relation="contradicts",
            public_summary="The clerk questions the lot card's copied date.",
        ),
    ),
    unlock_rules=(
        ArtifactUnlockRule(
            rule_id="unlock-chapel-debt-mark",
            artifact_id="artifact_chapel_debt_mark",
            contract_id="contract_false_finger",
            phase="Auction Preview",
            trigger="action_mentions_tag",
            required_terms=("chapel",),
            award_scope="crew",
            award_reason="Followed the chapel mark from the ledger.",
        ),
        ArtifactUnlockRule(
            rule_id="unlock-clerk-pencil-note",
            artifact_id="artifact_clerk_pencil_note",
            contract_id="contract_false_finger",
            phase="Auction Preview",
            trigger="action_mentions_tag",
            required_terms=("clerk", "catalogue"),
            award_scope="crew",
            award_reason="Pressed the auction clerk on the catalogue correction.",
        ),
    ),
)
```

- [ ] **Step 4: Run seed tests**

Run:

```bash
pytest -q tests/server/test_artifact_seed.py tests/domain/test_artifact_graph.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hollow_lodge/server/artifact_seed.py tests/server/test_artifact_seed.py
git commit -m "feat: seed starter artifact graph"
```

## Task 3: Server Artifact Service And Public Starting Access

**Files:**
- Create: `src/hollow_lodge/server/artifact_service.py`
- Create: `src/hollow_lodge/server/routes_artifacts.py`
- Modify: `src/hollow_lodge/server/app.py`
- Test: `tests/server/test_artifact_routes.py`

- [ ] **Step 1: Write failing route tests**

Create `tests/server/test_artifact_routes.py`:

```python
from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def command_auth(token: str, key: str) -> dict[str, str]:
    return {**auth(token), "Idempotency-Key": key}


def register(client: TestClient, invite: str, name: str) -> dict:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def test_player_sees_public_starter_artifacts(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    response = client.get("/artifacts", headers=auth(ada["token"]))

    assert response.status_code == 200
    artifact_ids = {artifact["artifact_id"] for artifact in response.json()["artifacts"]}
    assert "artifact_lot_card" in artifact_ids
    assert "artifact_ledger_rubric" in artifact_ids
    assert "artifact_chapel_debt_mark" not in artifact_ids


def test_player_can_inspect_visible_artifact_without_hidden_flags(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    response = client.get("/artifacts/artifact_ledger_rubric", headers=auth(ada["token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["artifact_id"] == "artifact_ledger_rubric"
    assert "full_text" in body
    assert "ink-after-binding" not in str(body)


def test_hidden_artifact_is_not_visible_until_unlocked(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")

    response = client.get("/artifacts/artifact_chapel_debt_mark", headers=auth(ada["token"]))

    assert response.status_code == 404
```

- [ ] **Step 2: Run route tests and verify failure**

Run:

```bash
pytest -q tests/server/test_artifact_routes.py
```

Expected: FAIL with 404 for missing `/artifacts` routes.

- [ ] **Step 3: Implement artifact service**

Create `src/hollow_lodge/server/artifact_service.py`:

```python
from __future__ import annotations

import threading

from hollow_lodge.domain.events import EventVisibility
from hollow_lodge.eventlog.jsonl_store import JsonlEventStore
from hollow_lodge.eventlog.visibility import Principal
from hollow_lodge.server.artifact_seed import STARTER_ARTIFACT_GRAPH, STARTER_PUBLIC_ARTIFACT_IDS


class ArtifactService:
    def __init__(self, *, event_store: JsonlEventStore):
        self._event_store = event_store
        self._lock = threading.RLock()
        self._seed_graph()

    def visible_artifacts_for_player(self, *, player_id: str) -> dict:
        visible_ids = self._visible_artifact_ids(player_id=player_id)
        return STARTER_ARTIFACT_GRAPH.visible_slice(visible_ids)

    def inspect_artifact(self, *, artifact_id: str, player_id: str, idempotency_key: str | None = None) -> dict:
        visible_ids = self._visible_artifact_ids(player_id=player_id)
        if artifact_id not in visible_ids:
            raise KeyError(artifact_id)
        artifact = STARTER_ARTIFACT_GRAPH.artifact_by_id(artifact_id)
        view = artifact.inspection_view()
        if idempotency_key:
            with self._lock:
                self._event_store.append_command(
                    event_type="artifact.inspected",
                    actor_id=player_id,
                    visibility=EventVisibility.players([player_id]),
                    payload={"artifact_id": artifact_id, "surface": artifact.surface_view()},
                    idempotency_key=idempotency_key,
                )
        return view

    def grant_artifact_access(
        self,
        *,
        artifact_id: str,
        actor_id: str,
        player_ids: list[str],
        reason: str,
        idempotency_key: str,
    ) -> dict:
        artifact = STARTER_ARTIFACT_GRAPH.artifact_by_id(artifact_id)
        self._event_store.append_command(
            event_type="artifact.access.granted",
            actor_id=actor_id,
            visibility=EventVisibility.players(player_ids),
            payload={
                "artifact_id": artifact_id,
                "contract_id": artifact.contract_id,
                "player_ids": player_ids,
                "reason": reason,
                "surface": artifact.surface_view(),
            },
            idempotency_key=idempotency_key,
        )
        return artifact.surface_view()

    def _seed_graph(self) -> None:
        self._event_store.append_command(
            event_type="artifact.graph.seeded",
            actor_id="server",
            visibility=EventVisibility.server_only(),
            payload=STARTER_ARTIFACT_GRAPH.model_dump(mode="json"),
            idempotency_key="seed.artifact-graph.contract_false_finger",
        )

    def _visible_artifact_ids(self, *, player_id: str) -> set[str]:
        visible_ids = set(STARTER_PUBLIC_ARTIFACT_IDS)
        for event in self._event_store.read_for_principal(Principal.player(player_id)):
            if event.type == "artifact.access.granted":
                visible_ids.add(event.payload["artifact_id"])
        return visible_ids
```

- [ ] **Step 4: Implement routes and register service**

Create `src/hollow_lodge/server/routes_artifacts.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from hollow_lodge.domain.identity import Player
from hollow_lodge.server.artifact_service import ArtifactService
from hollow_lodge.server.auth import current_player


router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("")
def visible_artifacts(
    request: Request,
    player: Player = Depends(current_player),
):
    return _artifact_service(request).visible_artifacts_for_player(player_id=player.player_id)


@router.get("/{artifact_id}")
def inspect_artifact(
    artifact_id: str,
    request: Request,
    player: Player = Depends(current_player),
):
    try:
        return _artifact_service(request).inspect_artifact(
            artifact_id=artifact_id,
            player_id=player.player_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found") from exc


@router.post("/{artifact_id}/inspect")
def record_artifact_inspection(
    artifact_id: str,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    try:
        return _artifact_service(request).inspect_artifact(
            artifact_id=artifact_id,
            player_id=player.player_id,
            idempotency_key=idempotency_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found") from exc


def _artifact_service(request: Request) -> ArtifactService:
    if not hasattr(request.app.state, "artifact_service"):
        request.app.state.artifact_service = ArtifactService(
            event_store=request.app.state.event_store,
        )
    return request.app.state.artifact_service
```

Modify `src/hollow_lodge/server/app.py`:

```python
from hollow_lodge.server.routes_artifacts import router as artifacts_router
from hollow_lodge.server.artifact_service import ArtifactService

# inside create_app after event_store:
app.state.artifact_service = ArtifactService(event_store=event_store)

# router registration:
app.include_router(artifacts_router)
```

- [ ] **Step 5: Run route tests**

Run:

```bash
pytest -q tests/server/test_artifact_routes.py tests/server/test_contract_seed.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/hollow_lodge/server/app.py src/hollow_lodge/server/artifact_service.py src/hollow_lodge/server/routes_artifacts.py tests/server/test_artifact_routes.py
git commit -m "feat: add artifact inspection routes"
```

## Task 4: Client API, CLI, And MCP Artifact Render

**Files:**
- Create: `src/hollow_lodge/client/artifact_render.py`
- Modify: `src/hollow_lodge/client/api.py`
- Modify: `src/hollow_lodge/client/cli.py`
- Modify: `src/hollow_lodge/client/codex_session.py`
- Modify: `src/hollow_lodge/client/render_packets.py`
- Modify: `src/hollow_lodge/mcp_server.py`
- Test: `tests/client/test_artifact_render.py`
- Test: `tests/client/test_cli_commands.py`
- Test: `tests/client/test_codex_session.py`

- [ ] **Step 1: Write failing render tests**

Create `tests/client/test_artifact_render.py`:

```python
from hollow_lodge.client.artifact_render import build_artifact_packet, build_artifact_graph_packet


def test_artifact_packet_renders_source_material_and_agent_context():
    packet = build_artifact_packet(
        {
            "artifact_id": "artifact_ledger_rubric",
            "title": "Red Ledger Rubric",
            "kind": "ledger",
            "public_summary": "A copied rubric marks prior ownership.",
            "full_text": "Lot 19 passed under chapel seal.",
            "source_chain": ["archive:lot-card"],
            "visible_flags": ["copied-hand"],
            "proof_lanes": ["provenance"],
        }
    )

    assert packet.surface == "artifact"
    assert "Red Ledger Rubric" in packet.player_markdown
    assert "Lot 19 passed under chapel seal." in packet.player_markdown
    assert packet.agent_context["artifact"]["artifact_id"] == "artifact_ledger_rubric"


def test_artifact_graph_packet_renders_known_artifacts_and_edges():
    packet = build_artifact_graph_packet(
        {
            "contract_id": "contract_false_finger",
            "artifacts": [
                {"artifact_id": "artifact_lot_card", "title": "Auction Lot Card", "kind": "lot_card", "public_summary": "Public lot card."},
                {"artifact_id": "artifact_ledger_rubric", "title": "Red Ledger Rubric", "kind": "ledger", "public_summary": "Copied rubric."},
            ],
            "edges": [
                {
                    "source_id": "artifact_lot_card",
                    "target_id": "artifact_ledger_rubric",
                    "relation": "contradicts",
                    "public_summary": "The dates do not agree.",
                }
            ],
        }
    )

    assert packet.surface == "artifact_graph"
    assert "Auction Lot Card" in packet.player_markdown
    assert "contradicts" in packet.player_markdown
```

- [ ] **Step 2: Extend render packet surface type**

Modify `src/hollow_lodge/client/render_packets.py`:

```python
class RenderPacket(BaseModel):
    surface: Literal[
        "inbox",
        "contract_board",
        "crew_board",
        "artifact",
        "artifact_graph",
    ]
```

- [ ] **Step 3: Implement artifact render helpers**

Create `src/hollow_lodge/client/artifact_render.py`:

```python
from __future__ import annotations

from typing import Any

from hollow_lodge.client.render_packets import RenderAction, RenderPacket


def build_artifact_packet(artifact: dict[str, Any]) -> RenderPacket:
    lines = [
        f"Artifact: {artifact['title']}",
        f"ID: {artifact['artifact_id']}",
        f"Type: {artifact.get('kind', 'unknown')}",
        "",
        artifact["public_summary"],
    ]
    if artifact.get("full_text"):
        lines.extend(["", "Source:", artifact["full_text"]])
    if artifact.get("source_chain"):
        lines.extend(["", "Provenance:"])
        lines.extend(f"- {item}" for item in artifact["source_chain"])
    if artifact.get("visible_flags"):
        lines.extend(["", "Visible flags:"])
        lines.extend(f"- {flag}" for flag in artifact["visible_flags"])
    return RenderPacket(
        surface="artifact",
        player_markdown="\n".join(lines),
        agent_context={"artifact": artifact},
        suggested_prompts=[
            "Compare this artifact with another source",
            "Check whether this is safe to cite",
            "Draft a dossier citation",
        ],
        actions=[
            RenderAction(label="Check provenance", intent="check_artifact_provenance", requires_confirmation=True),
            RenderAction(label="Cite in dossier", intent="cite_artifact", requires_confirmation=True),
            RenderAction(label="Transfer artifact", intent="transfer_artifact", requires_confirmation=True),
        ],
    )


def build_artifact_graph_packet(graph: dict[str, Any]) -> RenderPacket:
    lines = [f"Known Artifacts: {graph['contract_id']}", ""]
    artifacts = graph.get("artifacts", [])
    if artifacts:
        for artifact in artifacts:
            lines.append(f"- {artifact['artifact_id']}: {artifact['title']} ({artifact.get('kind', 'unknown')})")
    else:
        lines.append("- none")
    edges = graph.get("edges", [])
    if edges:
        lines.extend(["", "Known connections:"])
        for edge in edges:
            lines.append(
                f"- {edge['source_id']} {edge['relation']} {edge['target_id']}: {edge.get('public_summary', '')}"
            )
    return RenderPacket(
        surface="artifact_graph",
        player_markdown="\n".join(lines),
        agent_context={"artifact_graph": graph},
        suggested_prompts=[
            "Inspect an artifact",
            "Find contradictions",
            "Draft a crew action from the known graph",
        ],
    )
```

- [ ] **Step 4: Add client API methods**

Modify `src/hollow_lodge/client/api.py`:

```python
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
```

- [ ] **Step 5: Add Codex session methods and MCP tools**

Modify `src/hollow_lodge/client/codex_session.py`:

```python
from hollow_lodge.client.artifact_render import build_artifact_graph_packet, build_artifact_packet

    def render_artifacts(self) -> RenderPacket:
        config = load_config(self.config_path)
        return build_artifact_graph_packet(self._api(config).artifacts())

    def render_artifact(self, *, artifact_id: str) -> RenderPacket:
        config = load_config(self.config_path)
        return build_artifact_packet(self._api(config).artifact(artifact_id=artifact_id))
```

Modify `src/hollow_lodge/mcp_server.py`:

```python
@mcp.tool()
def render_artifacts() -> CallToolResult:
    return packet_response(_session().render_artifacts())


@mcp.tool()
def render_artifact(artifact_id: str) -> CallToolResult:
    return packet_response(_session().render_artifact(artifact_id=artifact_id))
```

- [ ] **Step 6: Add CLI commands**

Modify `src/hollow_lodge/client/cli.py`:

```python
@app.command("artifacts")
def artifacts(
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Show visible artifacts and known evidence connections."""
    from hollow_lodge.client.artifact_render import build_artifact_graph_packet

    packet = build_artifact_graph_packet(_api_from_config(load_config(config)).artifacts())
    typer.echo(packet.player_markdown)


@app.command("artifact")
def artifact(
    artifact_id: str = typer.Argument(..., help="Artifact id."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Inspect a visible artifact."""
    from hollow_lodge.client.artifact_render import build_artifact_packet

    packet = build_artifact_packet(_api_from_config(load_config(config)).artifact(artifact_id=artifact_id))
    typer.echo(packet.player_markdown)
```

- [ ] **Step 7: Run client tests**

Run:

```bash
pytest -q tests/client/test_artifact_render.py tests/client/test_codex_session.py tests/client/test_cli_commands.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/hollow_lodge/client/api.py src/hollow_lodge/client/artifact_render.py src/hollow_lodge/client/cli.py src/hollow_lodge/client/codex_session.py src/hollow_lodge/client/render_packets.py src/hollow_lodge/mcp_server.py tests/client/test_artifact_render.py tests/client/test_codex_session.py tests/client/test_cli_commands.py
git commit -m "feat: render artifacts in client"
```

## Task 5: Unlock Artifacts From Freeform Actions

**Files:**
- Create: `src/hollow_lodge/server/artifact_unlocks.py`
- Modify: `src/hollow_lodge/server/services.py`
- Modify: `src/hollow_lodge/server/routes_actions.py`
- Test: `tests/server/test_artifact_unlocks.py`
- Test: `tests/server/test_action_artifact_awards.py`

- [ ] **Step 1: Write pure unlock tests**

Create `tests/server/test_artifact_unlocks.py`:

```python
from hollow_lodge.server.artifact_seed import STARTER_ARTIFACT_GRAPH
from hollow_lodge.server.artifact_unlocks import action_unlock_candidates


def test_action_mentions_tag_unlocks_matching_artifact_rule():
    candidates = action_unlock_candidates(
        graph=STARTER_ARTIFACT_GRAPH,
        contract_id="contract_false_finger",
        phase="Auction Preview",
        intent="Question the chapel keeper about the debt mark.",
        exposed_assets=(),
        already_visible_artifact_ids={"artifact_lot_card", "artifact_ledger_rubric"},
    )

    assert [candidate.artifact_id for candidate in candidates] == ["artifact_chapel_debt_mark"]


def test_unlock_candidates_skip_already_visible_artifacts():
    candidates = action_unlock_candidates(
        graph=STARTER_ARTIFACT_GRAPH,
        contract_id="contract_false_finger",
        phase="Auction Preview",
        intent="Question the chapel keeper about the debt mark.",
        exposed_assets=(),
        already_visible_artifact_ids={
            "artifact_lot_card",
            "artifact_ledger_rubric",
            "artifact_chapel_debt_mark",
        },
    )

    assert candidates == []
```

- [ ] **Step 2: Implement unlock evaluator**

Create `src/hollow_lodge/server/artifact_unlocks.py`:

```python
from __future__ import annotations

from hollow_lodge.domain.artifact_graph import ArtifactGraph, ArtifactUnlockRule


def action_unlock_candidates(
    *,
    graph: ArtifactGraph,
    contract_id: str,
    phase: str,
    intent: str,
    exposed_assets: tuple[str, ...],
    already_visible_artifact_ids: set[str],
) -> list[ArtifactUnlockRule]:
    normalized_intent = intent.casefold()
    exposed = set(exposed_assets)
    candidates: list[ArtifactUnlockRule] = []
    for rule in graph.unlock_rules:
        if rule.contract_id != contract_id or rule.phase != phase:
            continue
        if rule.artifact_id in already_visible_artifact_ids:
            continue
        if rule.trigger == "action_mentions_tag":
            if all(term.casefold() in normalized_intent for term in rule.required_terms):
                candidates.append(rule)
        elif rule.trigger == "action_exposes_asset":
            if set(rule.required_artifact_ids).issubset(exposed):
                candidates.append(rule)
    return candidates
```

- [ ] **Step 3: Write route/service award test**

Create `tests/server/test_action_artifact_awards.py`:

```python
from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def command_auth(token: str, key: str) -> dict[str, str]:
    return {**auth(token), "Idempotency-Key": key}


def register(client: TestClient, invite: str, name: str) -> dict:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def test_action_can_award_artifact_to_players_crew(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create"),
        json={"name": "The Gilt Knives"},
    ).json()

    action = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-chapel"),
        json={
            "crew_id": crew["crew_id"],
            "intent": "Question the chapel keeper about the debt mark.",
            "confirmed": True,
        },
    )
    artifacts = client.get("/artifacts", headers=auth(ada["token"]))

    assert action.status_code == 201
    assert artifacts.status_code == 200
    artifact_ids = {artifact["artifact_id"] for artifact in artifacts.json()["artifacts"]}
    assert "artifact_chapel_debt_mark" in artifact_ids
```

- [ ] **Step 4: Integrate awards into action submission**

Modify `src/hollow_lodge/server/services.py` carefully in `ActionService.submit_action` after the action event append succeeds:

```python
from hollow_lodge.server.artifact_seed import STARTER_ARTIFACT_GRAPH
from hollow_lodge.server.artifact_unlocks import action_unlock_candidates

# after appending action.submitted:
artifact_service = ArtifactService(event_store=self._event_store)
visible_ids = artifact_service.visible_artifact_ids_for_crew_or_player(
    crew_id=crew_id,
    player_id=player_id,
)
for candidate in action_unlock_candidates(
    graph=STARTER_ARTIFACT_GRAPH,
    contract_id="contract_false_finger",
    phase="Auction Preview",
    intent=normalized.intent,
    exposed_assets=tuple(normalized.exposed_assets),
    already_visible_artifact_ids=visible_ids,
):
    player_ids = self._crew_service.member_ids(crew_id)
    artifact_service.grant_artifact_access(
        artifact_id=candidate.artifact_id,
        actor_id="server",
        player_ids=player_ids,
        reason=candidate.award_reason,
        idempotency_key=f"artifact.award.{action_id}.{candidate.artifact_id}",
    )
```

If `CrewService` does not expose `member_ids`, add:

```python
def member_ids(self, crew_id: str) -> list[str]:
    return list(self._crews[crew_id].member_ids)
```

Add `ArtifactService.visible_artifact_ids_for_crew_or_player` as a small helper returning the union of the player's visible ids and any crew-scoped awards visible to them.

- [ ] **Step 5: Run action unlock tests**

Run:

```bash
pytest -q tests/server/test_artifact_unlocks.py tests/server/test_action_artifact_awards.py tests/server/test_action_routes.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/hollow_lodge/server/artifact_unlocks.py src/hollow_lodge/server/artifact_service.py src/hollow_lodge/server/services.py tests/server/test_artifact_unlocks.py tests/server/test_action_artifact_awards.py
git commit -m "feat: unlock artifacts from actions"
```

## Task 6: Artifact Transfer And Leaky Cross-Crew Communication

**Files:**
- Modify: `src/hollow_lodge/server/artifact_service.py`
- Modify: `src/hollow_lodge/server/routes_artifacts.py`
- Modify: `src/hollow_lodge/server/routes_chat.py`
- Modify: `src/hollow_lodge/client/api.py`
- Modify: `src/hollow_lodge/client/cli.py`
- Test: `tests/server/test_artifact_transfer.py`
- Test: `tests/server/test_chat_routes.py`

- [ ] **Step 1: Write failing transfer tests**

Create `tests/server/test_artifact_transfer.py`:

```python
from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def command_auth(token: str, key: str) -> dict[str, str]:
    return {**auth(token), "Idempotency-Key": key}


def register(client: TestClient, invite: str, name: str) -> dict:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def test_transfer_creates_copy_visible_to_recipient(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    sender = register(client, "a", "Ada")
    recipient = register(client, "b", "Bela")

    transfer = client.post(
        "/artifacts/artifact_ledger_rubric/transfer",
        headers=command_auth(sender["token"], "transfer-ledger"),
        json={"recipient_player_id": recipient["player_id"]},
    )
    copied_id = transfer.json()["artifact_id"]
    recipient_view = client.get(f"/artifacts/{copied_id}", headers=auth(recipient["token"]))

    assert transfer.status_code == 201
    assert copied_id.startswith("artifact_ledger_rubric.copy.")
    assert recipient_view.status_code == 200
    assert "transfer:" in str(recipient_view.json()["source_chain"])
```

- [ ] **Step 2: Implement transfer route**

Add request model and route in `src/hollow_lodge/server/routes_artifacts.py`:

```python
class TransferArtifactRequest(BaseModel):
    recipient_player_id: str = Field(min_length=1)


@router.post("/{artifact_id}/transfer", status_code=status.HTTP_201_CREATED)
def transfer_artifact(
    artifact_id: str,
    payload: TransferArtifactRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    player: Player = Depends(current_player),
):
    try:
        return _artifact_service(request).transfer_artifact(
            artifact_id=artifact_id,
            sender_player_id=player.player_id,
            recipient_player_id=payload.recipient_player_id,
            idempotency_key=idempotency_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
```

Implement `ArtifactService.transfer_artifact` by creating an `ArtifactCopy`, appending `artifact.transferred` for sender/recipient visibility, appending `artifact.transferred.internal` with server-only copy details, and returning the copy surface view.

- [ ] **Step 3: Add optional artifact attachments to chat**

Modify chat request models to accept:

```python
artifact_ids: list[str] = Field(default_factory=list)
```

On chat submit, validate each artifact id is visible to sender. Do not automatically grant access unless the route explicitly says transfer. Store attachments as references in the message payload.

- [ ] **Step 4: Add CLI transfer command**

Modify `src/hollow_lodge/client/api.py`:

```python
    def transfer_artifact(
        self,
        *,
        artifact_id: str,
        recipient_player_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return self._post(
            f"/artifacts/{artifact_id}/transfer",
            json={"recipient_player_id": recipient_player_id},
            idempotency_key=idempotency_key,
        )
```

Modify `src/hollow_lodge/client/cli.py`:

```python
@app.command("artifact-transfer")
def artifact_transfer(
    artifact_id: str = typer.Argument(..., help="Artifact id."),
    recipient: str = typer.Argument(..., help="Recipient player id."),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config", help="Local config path."),
) -> None:
    """Transfer a copy of a visible artifact to another player."""
    response = _api_from_config(load_config(config)).transfer_artifact(
        artifact_id=artifact_id,
        recipient_player_id=recipient,
        idempotency_key=new_command_key("artifact-transfer"),
    )
    typer.echo(f"{response['artifact_id']} transferred")
```

- [ ] **Step 5: Run transfer/chat tests**

Run:

```bash
pytest -q tests/server/test_artifact_transfer.py tests/server/test_chat_routes.py tests/client/test_cli_commands.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/hollow_lodge/server/artifact_service.py src/hollow_lodge/server/routes_artifacts.py src/hollow_lodge/server/routes_chat.py src/hollow_lodge/client/api.py src/hollow_lodge/client/cli.py tests/server/test_artifact_transfer.py tests/server/test_chat_routes.py tests/client/test_cli_commands.py
git commit -m "feat: transfer artifacts between players"
```

## Task 7: Dossier Citations Use Artifacts Instead Of Bare Evidence IDs

**Files:**
- Modify: `src/hollow_lodge/domain/proofs.py`
- Modify: `src/hollow_lodge/server/routes_proofs.py`
- Modify: `src/hollow_lodge/server/services.py`
- Modify: `src/hollow_lodge/client/render_packets.py`
- Test: `tests/domain/test_dossiers.py`
- Test: `tests/server/test_proof_routes.py`
- Test: `tests/client/test_phase_render.py`

- [ ] **Step 1: Write failing citation tests**

Add to `tests/domain/test_dossiers.py`:

```python
from hollow_lodge.domain.proofs import ProofDossier


def test_dossier_tracks_artifact_citations_separately_from_notes():
    dossier = ProofDossier.empty(
        dossier_id="dossier_crew_0001",
        crew_id="crew_0001",
        packet_lead_player_id="player_0001",
    ).with_artifact_citation(
        player_id="player_0001",
        artifact_id="artifact_ledger_rubric",
        claim="The ledger contradicts the public lot card.",
        quote="The last hand is redder and later than the binding.",
    )

    assert dossier.artifact_citations == (
        {
            "player_id": "player_0001",
            "artifact_id": "artifact_ledger_rubric",
            "claim": "The ledger contradicts the public lot card.",
            "quote": "The last hand is redder and later than the binding.",
        },
    )
```

- [ ] **Step 2: Implement dossier citation model method**

Modify `src/hollow_lodge/domain/proofs.py`:

```python
class ProofDossier(BaseModel):
    # existing fields
    artifact_citations: tuple[dict, ...] = ()

    def with_artifact_citation(
        self,
        *,
        player_id: str,
        artifact_id: str,
        claim: str,
        quote: str,
    ) -> ProofDossier:
        return self.model_copy(
            update={
                "artifact_citations": (
                    *self.artifact_citations,
                    {
                        "player_id": player_id,
                        "artifact_id": artifact_id,
                        "claim": claim,
                        "quote": quote,
                    },
                )
            }
        )
```

- [ ] **Step 3: Add proof route to cite artifact**

Add route:

```text
POST /proofs/dossiers/{crew_id}/artifact-citations
```

Request body:

```python
class ArtifactCitationRequest(BaseModel):
    artifact_id: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    quote: str = Field(min_length=1)
```

Server validation:

- player must be crew member
- artifact must be visible to player
- idempotency key replay must match existing event
- append `artifact.dossier.cited` with crew visibility

- [ ] **Step 4: Update scoring packet builder**

Modify `ContractService._current_dossier_for_scoring` and `_auction_preview_score_inputs` so artifact citations contribute to `evidence_ids` and `reasoning`/`provenance_concerns`. For v1, preserve backward compatibility by keeping `evidence_ids` as a tuple of artifact ids and adding citation claims into reasoning text.

- [ ] **Step 5: Update crew board renderer**

Modify `_shape_dossier` and `build_crew_board_packet` in `src/hollow_lodge/client/render_packets.py` to include:

```python
"artifact_citations"
```

Render:

```text
Artifact citations:
- artifact_ledger_rubric: The ledger contradicts the public lot card.
```

- [ ] **Step 6: Run proof and render tests**

Run:

```bash
pytest -q tests/domain/test_dossiers.py tests/server/test_proof_routes.py tests/client/test_phase_render.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/hollow_lodge/domain/proofs.py src/hollow_lodge/server/routes_proofs.py src/hollow_lodge/server/services.py src/hollow_lodge/client/render_packets.py tests/domain/test_dossiers.py tests/server/test_proof_routes.py tests/client/test_phase_render.py
git commit -m "feat: cite artifacts in proof dossiers"
```

## Task 8: Oracle Resolution Reads Artifact Citations And Visible Graph Context

**Files:**
- Modify: `src/hollow_lodge/workflows/oracle_boundary.py`
- Modify: `src/hollow_lodge/workflows/deterministic_oracle.py`
- Modify: `src/hollow_lodge/workflows/openai_oracle.py`
- Modify: `src/hollow_lodge/server/services.py`
- Test: `tests/workflows/test_oracle_boundary.py`
- Test: `tests/workflows/test_deterministic_oracle.py`
- Test: `tests/workflows/test_openai_oracle.py`
- Test: `tests/server/test_phase_resolution.py`

- [ ] **Step 1: Extend oracle packet tests**

Add to `tests/workflows/test_oracle_boundary.py`:

```python
def test_oracle_packet_accepts_artifact_citations_and_known_edges():
    packet = AuctionPreviewOraclePacket(
        contract_id="contract_false_finger",
        phase="Auction Preview",
        hidden_truth_summary="server hidden truth",
        crews=(
            AuctionPreviewCrewPacket(
                crew_id="crew_0001",
                claim="The ledger contradicts the lot card.",
                evidence_ids=("artifact_ledger_rubric",),
                artifact_citations=(
                    {
                        "artifact_id": "artifact_ledger_rubric",
                        "claim": "The ledger contradicts the lot card.",
                        "quote": "The last hand is redder and later than the binding.",
                    },
                ),
                known_edges=(
                    {
                        "source_id": "artifact_lot_card",
                        "relation": "contradicts",
                        "target_id": "artifact_ledger_rubric",
                    },
                ),
            ),
        ),
        allowed_evidence_ids=("artifact_ledger_rubric",),
    )

    assert packet.crews[0].artifact_citations[0]["artifact_id"] == "artifact_ledger_rubric"
```

- [ ] **Step 2: Add packet fields**

Modify `AuctionPreviewCrewPacket`:

```python
artifact_citations: tuple[dict, ...] = ()
known_edges: tuple[dict, ...] = ()
```

Keep `evidence_ids` for compatibility, but prefer artifact ids in new tests.

- [ ] **Step 3: Update deterministic oracle scoring inputs**

Modify `DeterministicResolutionOracle.resolve_auction_preview` so citations add small deterministic strength:

```python
if crew.artifact_citations:
    strengths.append("cited artifact source material")
    score += min(12, 4 * len(crew.artifact_citations))
if crew.known_edges:
    strengths.append("mapped evidence contradiction")
    score += min(8, 4 * len(crew.known_edges))
```

Keep scores clamped through existing validation.

- [ ] **Step 4: Update OpenAI oracle schema/prompt**

Modify `src/hollow_lodge/workflows/openai_oracle.py` prompt text to include:

```text
Reward cited artifacts, direct quotes, and graph contradictions.
Penalize claims that lack artifact citations or rely only on broad action prose.
Do not reveal hidden graph nodes unless they are in allowed reveal strings.
```

No schema output change is needed unless tests require it; artifact citations are input context.

- [ ] **Step 5: Update packet builder**

Modify `ContractService._build_auction_preview_packet` to include per-crew:

- `artifact_citations` from current dossier
- known visible graph edges among cited artifact ids
- `allowed_evidence_ids` from visible/seeded artifact ids plus legacy proof fragment ids

- [ ] **Step 6: Run oracle tests**

Run:

```bash
pytest -q tests/workflows/test_oracle_boundary.py tests/workflows/test_deterministic_oracle.py tests/workflows/test_openai_oracle.py tests/server/test_phase_resolution.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/hollow_lodge/workflows/oracle_boundary.py src/hollow_lodge/workflows/deterministic_oracle.py src/hollow_lodge/workflows/openai_oracle.py src/hollow_lodge/server/services.py tests/workflows/test_oracle_boundary.py tests/workflows/test_deterministic_oracle.py tests/workflows/test_openai_oracle.py tests/server/test_phase_resolution.py
git commit -m "feat: score artifact graph evidence"
```

## Task 9: Phase Aftermath Artifact Awards

**Files:**
- Modify: `src/hollow_lodge/server/artifact_unlocks.py`
- Modify: `src/hollow_lodge/server/services.py`
- Test: `tests/server/test_phase_artifact_rewards.py`

- [ ] **Step 1: Write failing phase reward test**

Create `tests/server/test_phase_artifact_rewards.py`:

```python
from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def command_auth(token: str, key: str) -> dict[str, str]:
    return {**auth(token), "Idempotency-Key": key}


def register(client: TestClient, invite: str, name: str) -> dict:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def test_phase_resolution_awards_leader_followup_artifact(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = client.post("/crews", headers=command_auth(ada["token"], "crew-a"), json={"name": "Gilt"}).json()
    moth = client.post("/crews", headers=command_auth(bela["token"], "crew-b"), json={"name": "Moth"}).json()
    client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-a"),
        json={"crew_id": gilt["crew_id"], "intent": "Inspect the ledger and clerk catalogue correction.", "confirmed": True},
    )
    client.post(
        "/actions",
        headers=command_auth(bela["token"], "action-b"),
        json={"crew_id": moth["crew_id"], "intent": "Read the chapel omen.", "confirmed": True},
    )

    resolved = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock"),
        json={"hours_elapsed": 6},
    )
    artifacts = client.get("/artifacts", headers=auth(ada["token"]))

    assert resolved.status_code == 200
    assert any(
        artifact["artifact_id"] == "artifact_clerk_pencil_note"
        for artifact in artifacts.json()["artifacts"]
    )
```

- [ ] **Step 2: Implement deterministic aftermath awards**

For v1, keep aftermath simple:

- if the leader has unlocked or cited `artifact_clerk_pencil_note`, award no duplicate
- otherwise award `artifact_clerk_pencil_note` to leader crew when leader score is highest
- losing crews keep any artifacts they already unlocked

Append `artifact.phase_reward.awarded` with crew visibility and call `artifact.access.granted` with idempotent key:

```python
f"artifact.phase-reward.{contract_id}.auction-preview.{crew_id}.artifact_clerk_pencil_note"
```

- [ ] **Step 3: Run phase reward tests**

Run:

```bash
pytest -q tests/server/test_phase_artifact_rewards.py tests/server/test_phase_resolution.py
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/hollow_lodge/server/artifact_unlocks.py src/hollow_lodge/server/services.py tests/server/test_phase_artifact_rewards.py
git commit -m "feat: award artifacts after phase resolution"
```

## Task 10: Inbox, Contract Board, And Crew Board Artifact Projections

**Files:**
- Modify: `src/hollow_lodge/server/projections.py`
- Modify: `src/hollow_lodge/server/routes_contracts.py`
- Modify: `src/hollow_lodge/server/routes_crews.py`
- Modify: `src/hollow_lodge/client/render_packets.py`
- Test: `tests/server/test_artifact_projections.py`
- Test: `tests/client/test_contract_board.py`
- Test: `tests/client/test_codex_session.py`

- [ ] **Step 1: Write projection tests**

Create `tests/server/test_artifact_projections.py`:

```python
from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def command_auth(token: str, key: str) -> dict[str, str]:
    return {**auth(token), "Idempotency-Key": key}


def register(client: TestClient, invite: str, name: str) -> dict:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def test_inbox_and_crew_board_include_visible_artifacts(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a"]))
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create"),
        json={"name": "Gilt"},
    ).json()

    inbox = client.get("/inbox", headers=auth(ada["token"]))
    board = client.get(f"/crews/{crew['crew_id']}/board", headers=auth(ada["token"]))

    assert "visible_artifacts" in inbox.json()
    assert "visible_artifacts" in board.json()
    assert any(
        artifact["artifact_id"] == "artifact_lot_card"
        for artifact in board.json()["visible_artifacts"]
    )
```

- [ ] **Step 2: Add visible artifacts to route payloads**

In `/inbox`, add:

```python
payload["visible_artifacts"] = artifact_service.visible_artifacts_for_player(player_id=player.player_id)["artifacts"]
```

In crew board, add:

```python
"visible_artifacts": artifact_service.visible_artifacts_for_player(player_id=player.player_id)["artifacts"]
```

- [ ] **Step 3: Render artifacts in inbox and crew board**

Modify `build_inbox_packet`:

```python
artifacts = inbox.get("visible_artifacts", [])
if artifacts:
    lines.append("")
    lines.append("visible artifacts:")
    lines.extend(f"- {artifact['artifact_id']}: {artifact['title']}" for artifact in artifacts[:5])
```

Modify `build_crew_board_packet`:

```python
visible_artifacts = board.get("visible_artifacts", [])
lines.extend(["", "Artifacts:"])
if visible_artifacts:
    lines.extend(f"- {artifact['artifact_id']}: {artifact['title']}" for artifact in visible_artifacts)
else:
    lines.append("- none")
```

Add `visible_artifacts` to `agent_context`.

- [ ] **Step 4: Run projection/render tests**

Run:

```bash
pytest -q tests/server/test_artifact_projections.py tests/client/test_contract_board.py tests/client/test_codex_session.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hollow_lodge/server/projections.py src/hollow_lodge/server/routes_contracts.py src/hollow_lodge/server/routes_crews.py src/hollow_lodge/client/render_packets.py tests/server/test_artifact_projections.py tests/client/test_contract_board.py tests/client/test_codex_session.py
git commit -m "feat: show artifacts on game boards"
```

## Task 11: End-To-End Artifact Gameplay UAT Test

**Files:**
- Create: `tests/e2e/test_artifact_game_loop.py`
- Modify: `README.md`
- Modify: `docs/codex-play.md`

- [ ] **Step 1: Write E2E test for the concrete game loop**

Create `tests/e2e/test_artifact_game_loop.py`:

```python
from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def command_auth(token: str, key: str) -> dict[str, str]:
    return {**auth(token), "Idempotency-Key": key}


def register(client: TestClient, invite: str, name: str) -> dict:
    response = client.post(
        "/identity/register",
        json={"invite_code": invite, "display_name": name},
        headers={"Idempotency-Key": f"register-{invite}"},
    )
    assert response.status_code == 201
    return response.json()


def test_player_gets_artifacts_inspects_transfers_cites_and_resolves(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path, invite_codes=["a", "b"]))
    ada = register(client, "a", "Ada")
    bela = register(client, "b", "Bela")
    gilt = client.post("/crews", headers=command_auth(ada["token"], "crew-a"), json={"name": "Gilt"}).json()
    moth = client.post("/crews", headers=command_auth(bela["token"], "crew-b"), json={"name": "Moth"}).json()

    starter_artifacts = client.get("/artifacts", headers=auth(ada["token"])).json()
    assert "artifact_ledger_rubric" in {artifact["artifact_id"] for artifact in starter_artifacts["artifacts"]}

    inspected = client.post(
        "/artifacts/artifact_ledger_rubric/inspect",
        headers=command_auth(ada["token"], "inspect-ledger"),
    )
    assert inspected.status_code == 200

    transferred = client.post(
        "/artifacts/artifact_ledger_rubric/transfer",
        headers=command_auth(ada["token"], "transfer-ledger"),
        json={"recipient_player_id": bela["player_id"]},
    )
    assert transferred.status_code == 201

    citation = client.post(
        f"/proofs/dossiers/{gilt['crew_id']}/artifact-citations",
        headers=command_auth(ada["token"], "cite-ledger"),
        json={
            "artifact_id": "artifact_ledger_rubric",
            "claim": "The ledger contradicts the public lot card.",
            "quote": "The last hand is redder and later than the binding.",
        },
    )
    assert citation.status_code in {200, 201}

    client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-clerk"),
        json={"crew_id": gilt["crew_id"], "intent": "Question the clerk about the catalogue correction.", "confirmed": True},
    )
    client.post(
        "/actions",
        headers=command_auth(bela["token"], "action-chapel"),
        json={"crew_id": moth["crew_id"], "intent": "Follow the chapel omen and debt mark.", "confirmed": True},
    )
    resolved = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock"),
        json={"hours_elapsed": 6},
    )

    assert resolved.status_code == 200
    assert resolved.json()["standings"]
```

- [ ] **Step 2: Add README loop docs**

Add a short section to `README.md`:

```markdown
## Artifact Gameplay Loop

Contracts seed a server-only evidence graph before play. Players see a
visibility-scoped slice of that graph as artifacts. They can inspect artifacts,
transfer copies, cite artifacts in crew dossiers, and submit freeform actions
that unlock additional artifacts. Phase resolution scores dossiers and actions
against the server-owned graph.
```

- [ ] **Step 3: Add Codex play docs**

Add to `docs/codex-play.md`:

```markdown
Before advising on proof, render artifacts or a specific artifact when the
player references evidence. Treat visible artifact content as source material.
Do not infer hidden graph nodes as facts; frame them as hypotheses unless the
server has revealed them.
```

- [ ] **Step 4: Run E2E and full tests**

Run:

```bash
pytest -q tests/e2e/test_artifact_game_loop.py
pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_artifact_game_loop.py README.md docs/codex-play.md
git commit -m "test: cover artifact gameplay loop"
```

## Task 12: Production Smoke Script For Artifact Loop

**Files:**
- Create: `scripts/smoke_artifact_loop.py`
- Test: manual command only; do not run automatically in pytest because it mutates the configured server.

- [ ] **Step 1: Create smoke script**

Create `scripts/smoke_artifact_loop.py`:

```python
from __future__ import annotations

import argparse
import os
import uuid

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="https://server.thehollowlodge.com")
    parser.add_argument("--admin-token", default=os.environ.get("HOLLOW_LODGE_ADMIN_TOKEN"))
    args = parser.parse_args()
    if not args.admin_token:
        raise SystemExit("HOLLOW_LODGE_ADMIN_TOKEN is required")

    run = uuid.uuid4().hex[:8]
    server = args.server.rstrip("/")

    def post(path: str, *, headers=None, json=None, timeout=30):
        response = httpx.post(f"{server}{path}", headers=headers or {}, json=json or {}, timeout=timeout)
        response.raise_for_status()
        return response.json()

    def get(path: str, *, token: str):
        response = httpx.get(f"{server}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=30)
        response.raise_for_status()
        return response.json()

    def invite(label: str) -> str:
        return post(
            "/identity/admin/invites",
            headers={
                "X-Hollow-Lodge-Admin-Token": args.admin_token,
                "Idempotency-Key": f"artifact-smoke-{run}-invite-{label}",
            },
        )["invite_code"]

    def register(label: str) -> dict:
        return post(
            "/identity/register",
            headers={"Idempotency-Key": f"artifact-smoke-{run}-register-{label}"},
            json={"invite_code": invite(label), "display_name": f"Artifact Smoke {label} {run}"},
        )

    first = register("one")
    second = register("two")
    h1 = {"Authorization": f"Bearer {first['token']}", "Idempotency-Key": f"artifact-smoke-{run}-crew-one"}
    h2 = {"Authorization": f"Bearer {second['token']}", "Idempotency-Key": f"artifact-smoke-{run}-crew-two"}
    crew_one = post("/crews", headers=h1, json={"name": f"Smoke Gilt {run}"})
    crew_two = post("/crews", headers=h2, json={"name": f"Smoke Moth {run}"})

    artifacts = get("/artifacts", token=first["token"])
    post("/artifacts/artifact_ledger_rubric/inspect", headers={"Authorization": f"Bearer {first['token']}", "Idempotency-Key": f"artifact-smoke-{run}-inspect"})
    transfer = post(
        "/artifacts/artifact_ledger_rubric/transfer",
        headers={"Authorization": f"Bearer {first['token']}", "Idempotency-Key": f"artifact-smoke-{run}-transfer"},
        json={"recipient_player_id": second["player_id"]},
    )

    print(
        {
            "run": run,
            "players": [first["player_id"], second["player_id"]],
            "crews": [crew_one["crew_id"], crew_two["crew_id"]],
            "visible_artifact_count": len(artifacts["artifacts"]),
            "transferred_artifact_id": transfer["artifact_id"],
        }
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run smoke script locally against a local server**

Run:

```bash
HOLLOW_LODGE_ADMIN_TOKEN=test-admin python scripts/smoke_artifact_loop.py --server http://127.0.0.1:8000 --admin-token test-admin
```

Expected: prints player ids, crew ids, visible artifact count, and transferred artifact id.

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_artifact_loop.py
git commit -m "chore: add artifact loop smoke script"
```

## Final Verification

Run:

```bash
pytest -q
HOLLOW_LODGE_ORACLE_PROVIDER=openai HOLLOW_LODGE_OPENAI_API_KEY=test-key pytest -q tests/server/test_phase_resolution.py tests/server/test_resolution_oracle.py tests/server/test_artifact_routes.py
git status --short --branch
```

Expected:

- all tests pass
- OpenAI-env test suite does not call the real API unless explicitly using injected/mocked clients
- worktree clean
- branch ready to push

## Production Rollout Notes

Do not run the production smoke until a resettable test campaign or contract-instance system exists. The current production UAT already resolved the shared starter contract, which shows why artifact work should introduce contract instances or admin-reset tooling soon after this plan.

For first deployment:

1. Deploy code.
2. Create a fresh test contract instance or reset production volume intentionally.
3. Register two throwaway players.
4. Confirm `render_artifacts`, `render_artifact`, inbox, contract board, and crew board work inside Codex.
5. Run one transfer and one dossier citation.
6. Resolve phase and confirm artifact-citation strengths are reflected in the result.

## Self-Review

Spec coverage:

- Seeded truth graph: Tasks 1-3.
- Artifact unlocking over gameplay: Tasks 5 and 9.
- Asymmetric crew access: Tasks 3, 5, 6, 9, 10.
- Source material review inside Codex: Task 4.
- Crew/cross-crew communication with artifacts: Task 6.
- Dossier citations and scoring: Tasks 7 and 8.
- End-to-end game loop: Task 11.

Known follow-up not included:

- Contract instances/admin reset tooling.
- Rich generated media assets.
- Admin-only oracle audit browser.
- Full artifact-generation Oracle for new campaigns.
- Leak pressure mechanics that automatically expose private deals.

Those are deliberately excluded so this plan can ship the concrete artifact loop first.
