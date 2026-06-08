# Resolution Oracle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded server-side Resolution Oracle for Auction Preview that can use deterministic scoring now and OpenAI Structured Outputs later, with audit events and safe fallback.

**Architecture:** Introduce typed Oracle packet/result models in `workflows/oracle_boundary.py`, wrap the existing deterministic scorer as `DeterministicResolutionOracle`, and route `ContractService` phase resolution through a configurable `ResolutionOracle`. The OpenAI adapter is behind env flags and never owns authority directly: server validation accepts or rejects candidate output before committing phase resolution.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, httpx, OpenAI Responses API Structured Outputs, append-only JSONL Eventloom-compatible events.

---

## File Structure

- Create `src/hollow_lodge/workflows/oracle_boundary.py`
  - Pydantic models for `AuctionPreviewOraclePacket`, `AuctionPreviewCrewPacket`, `AuctionPreviewOracleResult`, `AuctionPreviewCrewResult`, and provider metadata.
  - Protocol `ResolutionOracle`.
  - Validation helpers for accepted crew ids, bounded scores, allowed evidence ids, and hidden-truth leak checks.
- Create `src/hollow_lodge/workflows/deterministic_oracle.py`
  - Adapter around `score_auction_preview`.
  - Converts packets into the same reveal shape currently produced by `ContractService`.
- Create `src/hollow_lodge/workflows/oracle_factory.py`
  - Reads `HOLLOW_LODGE_ORACLE_PROVIDER`, `HOLLOW_LODGE_ORACLE_MODEL`, `HOLLOW_LODGE_ORACLE_TIMEOUT_SECONDS`, and `HOLLOW_LODGE_OPENAI_API_KEY`.
  - Defaults to deterministic provider.
- Create `src/hollow_lodge/workflows/openai_oracle.py`
  - OpenAI provider behind env/config.
  - Uses Structured Outputs strict JSON schema.
  - Accepts injected HTTP/client callable in tests so tests never call real API.
- Modify `src/hollow_lodge/server/app.py`
  - Create and attach `app.state.resolution_oracle`.
  - Pass it into `ContractService`.
- Modify `src/hollow_lodge/server/services.py`
  - Accept optional `resolution_oracle`.
  - Build `AuctionPreviewOraclePacket` from current scoring inputs and hidden truth hooks.
  - Route phase resolution through provider.
  - Append server-only Oracle audit events.
  - Fall back to deterministic provider on provider/validation failure.
- Modify `pyproject.toml`
  - Add `openai>=1.0` only when the real provider task is implemented.
- Test files:
  - `tests/workflows/test_oracle_boundary.py`
  - `tests/workflows/test_deterministic_oracle.py`
  - `tests/workflows/test_oracle_factory.py`
  - `tests/workflows/test_openai_oracle.py`
  - `tests/server/test_resolution_oracle.py`
  - update `tests/server/test_phase_resolution.py`

---

## Task 1: Boundary Models And Validation

**Files:**
- Create: `src/hollow_lodge/workflows/oracle_boundary.py`
- Test: `tests/workflows/test_oracle_boundary.py`

- [ ] **Step 1: Write failing tests for packet/result schema and validation**

Add `tests/workflows/test_oracle_boundary.py`:

```python
import pytest

from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewPacket,
    AuctionPreviewCrewResult,
    AuctionPreviewOraclePacket,
    AuctionPreviewOracleResult,
    OracleProviderMetadata,
    validate_auction_preview_result,
)


def valid_packet() -> AuctionPreviewOraclePacket:
    return AuctionPreviewOraclePacket(
        contract_id="contract_false_finger",
        phase="Auction Preview",
        hidden_truth_summary="The finger is a saint-bone forgery.",
        allowed_reveal_strings=(
            "Auction house provenance is now suspect.",
            "Rival alternate clue paths remain open.",
        ),
        rubric_hooks=("provenance quality", "corroboration", "heat/noise penalties"),
        crews=(
            AuctionPreviewCrewPacket(
                crew_id="crew_gilt",
                claim="The relic is likely false.",
                evidence_ids=("fragment_starter_ledger",),
                exposed_assets=("fragment_starter_ledger",),
                reasoning="The ledger date contradicts the chapel timestamp.",
                weaknesses="No material confirmation.",
                provenance_concerns="Copied hand.",
                action_intents=("Inspect the ledger for forged provenance.",),
                crew_noise=1,
            ),
        ),
        allowed_evidence_ids=("fragment_starter_ledger", "asset_door_omen"),
        score_min=0,
        score_max=100,
    )


def valid_result() -> AuctionPreviewOracleResult:
    return AuctionPreviewOracleResult(
        provider=OracleProviderMetadata(provider="deterministic", model=None, prompt_version="deterministic-v1"),
        standings=(
            AuctionPreviewCrewResult(
                crew_id="crew_gilt",
                score=76,
                standing="Strong lead",
                strengths=("clean provenance contradiction",),
                weaknesses=("no material confirmation",),
                penalties=("minor heat trace",),
                revealed_clues=("Auction house provenance is now suspect.",),
            ),
        ),
        contract_state=("Auction house provenance is now suspect.",),
        narration="The Gilt packet leads on provenance without settling material truth.",
        validation_warnings=(),
    )


def test_validate_accepts_known_crews_and_safe_reveal_strings():
    accepted = validate_auction_preview_result(packet=valid_packet(), result=valid_result())

    assert accepted.standings[0].crew_id == "crew_gilt"
    assert accepted.standings[0].score == 76
    assert accepted.contract_state == ("Auction house provenance is now suspect.",)


def test_validate_rejects_unknown_crew_id():
    result = valid_result().model_copy(
        update={
            "standings": (
                valid_result().standings[0].model_copy(update={"crew_id": "crew_unknown"}),
            )
        }
    )

    with pytest.raises(ValueError, match="unknown crew id"):
        validate_auction_preview_result(packet=valid_packet(), result=result)


def test_validate_clamps_scores_to_packet_bounds():
    result = valid_result().model_copy(
        update={
            "standings": (
                valid_result().standings[0].model_copy(update={"score": 500}),
            )
        }
    )

    accepted = validate_auction_preview_result(packet=valid_packet(), result=result)

    assert accepted.standings[0].score == 100


def test_validate_rejects_hidden_truth_leakage():
    result = valid_result().model_copy(
        update={"narration": "The finger is a saint-bone forgery."}
    )

    with pytest.raises(ValueError, match="hidden truth leak"):
        validate_auction_preview_result(packet=valid_packet(), result=result)


def test_validate_rejects_unknown_revealed_clue():
    result = valid_result().model_copy(
        update={
            "standings": (
                valid_result().standings[0].model_copy(update={"revealed_clues": ("The debtor omen is real.",)}),
            )
        }
    )

    with pytest.raises(ValueError, match="unsafe reveal"):
        validate_auction_preview_result(packet=valid_packet(), result=result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/workflows/test_oracle_boundary.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hollow_lodge.workflows.oracle_boundary'`.

- [ ] **Step 3: Implement boundary models and validator**

Create `src/hollow_lodge/workflows/oracle_boundary.py`:

```python
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AuctionPreviewCrewPacket(BaseModel):
    model_config = ConfigDict(frozen=True)

    crew_id: str = Field(min_length=1)
    claim: str = ""
    evidence_ids: tuple[str, ...] = ()
    exposed_assets: tuple[str, ...] = ()
    reasoning: str = ""
    weaknesses: str = ""
    provenance_concerns: str = ""
    action_intents: tuple[str, ...] = ()
    crew_noise: int = Field(ge=0)


class AuctionPreviewOraclePacket(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    hidden_truth_summary: str = ""
    allowed_reveal_strings: tuple[str, ...] = ()
    rubric_hooks: tuple[str, ...] = ()
    crews: tuple[AuctionPreviewCrewPacket, ...]
    allowed_evidence_ids: tuple[str, ...] = ()
    score_min: int = Field(default=0, ge=0)
    score_max: int = Field(default=100, ge=1)

    @model_validator(mode="after")
    def validate_score_bounds(self) -> AuctionPreviewOraclePacket:
        if self.score_max < self.score_min:
            raise ValueError("score_max must be greater than or equal to score_min")
        return self


class OracleProviderMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = Field(min_length=1)
    model: str | None = None
    prompt_version: str = Field(min_length=1)


class AuctionPreviewCrewResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    crew_id: str = Field(min_length=1)
    score: int = Field(ge=0)
    standing: str = Field(min_length=1)
    strengths: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    penalties: tuple[str, ...] = ()
    revealed_clues: tuple[str, ...] = ()


class AuctionPreviewOracleResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: OracleProviderMetadata
    standings: tuple[AuctionPreviewCrewResult, ...]
    contract_state: tuple[str, ...] = ()
    narration: str = ""
    validation_warnings: tuple[str, ...] = ()


class ResolutionOracle(Protocol):
    def resolve_auction_preview(
        self,
        packet: AuctionPreviewOraclePacket,
    ) -> AuctionPreviewOracleResult:
        """Return a candidate Auction Preview resolution."""


def validate_auction_preview_result(
    *,
    packet: AuctionPreviewOraclePacket,
    result: AuctionPreviewOracleResult,
) -> AuctionPreviewOracleResult:
    crew_ids = {crew.crew_id for crew in packet.crews}
    seen_crew_ids: set[str] = set()
    allowed_reveals = set(packet.allowed_reveal_strings)
    hidden_phrases = _hidden_phrases(packet.hidden_truth_summary)
    accepted: list[AuctionPreviewCrewResult] = []

    for standing in result.standings:
        if standing.crew_id not in crew_ids:
            raise ValueError(f"unknown crew id: {standing.crew_id}")
        if standing.crew_id in seen_crew_ids:
            raise ValueError(f"duplicate crew id: {standing.crew_id}")
        seen_crew_ids.add(standing.crew_id)
        for clue in standing.revealed_clues:
            if clue not in allowed_reveals:
                raise ValueError(f"unsafe reveal: {clue}")
        _reject_hidden_truth_leaks(
            hidden_phrases=hidden_phrases,
            text=" ".join(
                (
                    standing.standing,
                    " ".join(standing.strengths),
                    " ".join(standing.weaknesses),
                    " ".join(standing.penalties),
                    " ".join(standing.revealed_clues),
                )
            ),
        )
        accepted.append(
            standing.model_copy(
                update={"score": max(packet.score_min, min(packet.score_max, standing.score))}
            )
        )

    for line in result.contract_state:
        if line not in allowed_reveals:
            raise ValueError(f"unsafe reveal: {line}")
    _reject_hidden_truth_leaks(hidden_phrases=hidden_phrases, text=result.narration)

    ordered = tuple(sorted(accepted, key=lambda item: (-item.score, item.crew_id)))
    return result.model_copy(update={"standings": ordered})


def _hidden_phrases(hidden_truth_summary: str) -> tuple[str, ...]:
    phrases = []
    lowered = hidden_truth_summary.lower()
    for phrase in ("saint-bone forgery", "real debtor's omen", "truth_false_finger_forgery"):
        if phrase in lowered:
            phrases.append(phrase)
    return tuple(phrases)


def _reject_hidden_truth_leaks(*, hidden_phrases: tuple[str, ...], text: str) -> None:
    lowered = text.lower()
    for phrase in hidden_phrases:
        if phrase and phrase in lowered:
            raise ValueError(f"hidden truth leak: {phrase}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest -q tests/workflows/test_oracle_boundary.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hollow_lodge/workflows/oracle_boundary.py tests/workflows/test_oracle_boundary.py
git commit -m "feat: add resolution oracle boundary"
```

---

## Task 2: Deterministic Resolution Oracle

**Files:**
- Create: `src/hollow_lodge/workflows/deterministic_oracle.py`
- Test: `tests/workflows/test_deterministic_oracle.py`

- [ ] **Step 1: Write failing deterministic adapter tests**

Add `tests/workflows/test_deterministic_oracle.py`:

```python
from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewPacket,
    AuctionPreviewOraclePacket,
)


def test_deterministic_oracle_preserves_current_scoring_shape():
    packet = AuctionPreviewOraclePacket(
        contract_id="contract_false_finger",
        phase="Auction Preview",
        hidden_truth_summary="The finger is a saint-bone forgery.",
        allowed_reveal_strings=(
            "Auction house provenance is now suspect.",
            "Rival alternate clue paths remain open.",
        ),
        rubric_hooks=("provenance quality",),
        crews=(
            AuctionPreviewCrewPacket(
                crew_id="crew_gilt",
                claim="The relic is likely false.",
                evidence_ids=("fragment_starter_ledger",),
                exposed_assets=("fragment_starter_ledger",),
                reasoning="The ledger date contradicts the chapel timestamp.",
                weaknesses="No material confirmation.",
                provenance_concerns="Copied hand.",
                action_intents=("Inspect the ledger for forged provenance.",),
                crew_noise=1,
            ),
            AuctionPreviewCrewPacket(
                crew_id="crew_moth",
                claim="The reliquary is occult but unstable.",
                evidence_ids=(),
                exposed_assets=("asset_door_omen",),
                reasoning="A moth jar door omen appears near the auction room.",
                weaknesses="Omen has no corroboration.",
                provenance_concerns="",
                action_intents=("Observe the sealed door omen for occult resonance.",),
                crew_noise=0,
            ),
        ),
        allowed_evidence_ids=("fragment_starter_ledger", "asset_door_omen"),
        score_min=0,
        score_max=100,
    )

    result = DeterministicResolutionOracle().resolve_auction_preview(packet)

    assert result.provider.provider == "deterministic"
    assert result.provider.prompt_version == "deterministic-v1"
    assert result.standings[0].crew_id == "crew_gilt"
    assert result.standings[0].standing == "Strong lead"
    assert "clean provenance contradiction" in result.standings[0].strengths
    assert result.standings[1].crew_id == "crew_moth"
    assert result.standings[1].standing == "Viable but unstable"
    assert result.contract_state == (
        "Auction house provenance is now suspect.",
        "Rival alternate clue paths remain open.",
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/workflows/test_deterministic_oracle.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hollow_lodge.workflows.deterministic_oracle'`.

- [ ] **Step 3: Implement deterministic provider**

Create `src/hollow_lodge/workflows/deterministic_oracle.py`:

```python
from __future__ import annotations

from hollow_lodge.domain.scoring import AuctionPreviewScoreInput, score_auction_preview
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewResult,
    AuctionPreviewOraclePacket,
    AuctionPreviewOracleResult,
    OracleProviderMetadata,
    validate_auction_preview_result,
)


class DeterministicResolutionOracle:
    def resolve_auction_preview(
        self,
        packet: AuctionPreviewOraclePacket,
    ) -> AuctionPreviewOracleResult:
        scores = [
            score_auction_preview(
                AuctionPreviewScoreInput(
                    crew_id=crew.crew_id,
                    claim=crew.claim,
                    evidence_ids=crew.evidence_ids,
                    exposed_assets=crew.exposed_assets,
                    reasoning=crew.reasoning,
                    weaknesses=crew.weaknesses,
                    provenance_concerns=crew.provenance_concerns,
                    action_intents=crew.action_intents,
                    crew_noise=crew.crew_noise,
                )
            )
            for crew in packet.crews
        ]
        result = AuctionPreviewOracleResult(
            provider=OracleProviderMetadata(
                provider="deterministic",
                model=None,
                prompt_version="deterministic-v1",
            ),
            standings=tuple(
                AuctionPreviewCrewResult(
                    crew_id=score.crew_id,
                    score=score.total,
                    standing=score.standing,
                    strengths=score.strengths,
                    weaknesses=score.weaknesses,
                    penalties=score.penalties,
                    revealed_clues=score.revealed_clues,
                )
                for score in scores
            ),
            contract_state=(
                "Auction house provenance is now suspect.",
                "Rival alternate clue paths remain open.",
            ),
            narration="The auction preview resolves from submitted proof packets.",
            validation_warnings=(),
        )
        return validate_auction_preview_result(packet=packet, result=result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest -q tests/workflows/test_deterministic_oracle.py tests/workflows/test_oracle_boundary.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hollow_lodge/workflows/deterministic_oracle.py tests/workflows/test_deterministic_oracle.py
git commit -m "feat: add deterministic resolution oracle"
```

---

## Task 3: Refactor Contract Resolution Through Oracle Boundary

**Files:**
- Modify: `src/hollow_lodge/server/services.py`
- Test: `tests/server/test_phase_resolution.py`

- [ ] **Step 1: Add failing service test for oracle audit events**

Append to `tests/server/test_phase_resolution.py`:

```python
def test_phase_resolution_records_server_only_oracle_audit_events(tmp_path):
    client, ada, _, gilt, _ = setup_two_crews(tmp_path)
    submit_action(client, ada, gilt, "action-gilt", "Inspect the ledger for forged provenance.")

    response = lock_preview(client, ada, "phase-lock-oracle-audit")

    assert response.status_code == 200
    all_events = client.app.state.event_store.read()
    event_types = [event.type for event in all_events]
    assert "oracle.resolution.requested" in event_types
    assert "oracle.resolution.completed" in event_types
    requested = next(event for event in all_events if event.type == "oracle.resolution.requested")
    completed = next(event for event in all_events if event.type == "oracle.resolution.completed")
    assert requested.visibility.entries[0].kind == "server"
    assert completed.visibility.entries[0].kind == "server"
    assert completed.payload["provider"] == "deterministic"
    assert completed.payload["fallback"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest -q tests/server/test_phase_resolution.py::test_phase_resolution_records_server_only_oracle_audit_events
```

Expected: FAIL because no `oracle.resolution.*` events are appended.

- [ ] **Step 3: Modify `ContractService` constructor and imports**

In `src/hollow_lodge/server/services.py`, add imports:

```python
import hashlib
import json
```

Add workflow imports:

```python
from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewPacket,
    AuctionPreviewOraclePacket,
    AuctionPreviewOracleResult,
    ResolutionOracle,
    validate_auction_preview_result,
)
```

Change `ContractService.__init__` to accept an oracle:

```python
class ContractService:
    def __init__(
        self,
        *,
        event_store: JsonlEventStore,
        resolution_oracle: ResolutionOracle | None = None,
    ):
        self._event_store = event_store
        self._resolution_oracle = resolution_oracle or DeterministicResolutionOracle()
        self._lock = RLock()
        self._seed_starter_contract()
```

- [ ] **Step 4: Add packet builder and reveal conversion helpers**

In `ContractService`, add:

```python
    def _build_auction_preview_packet(self, *, contract_id: str) -> AuctionPreviewOraclePacket:
        score_inputs = self._auction_preview_score_inputs()
        return AuctionPreviewOraclePacket(
            contract_id=contract_id,
            phase="Auction Preview",
            hidden_truth_summary="The finger is a saint-bone forgery.",
            allowed_reveal_strings=(
                "Auction house provenance is now suspect.",
                "Rival alternate clue paths remain open.",
            ),
            rubric_hooks=(
                "evidence credibility",
                "corroboration",
                "source independence",
                "provenance quality",
                "contradictions",
                "reasoning quality",
                "heat/noise penalties",
                "occult resonance",
            ),
            crews=tuple(
                AuctionPreviewCrewPacket(
                    crew_id=score_input.crew_id,
                    claim=score_input.claim,
                    evidence_ids=tuple(score_input.evidence_ids),
                    exposed_assets=tuple(score_input.exposed_assets),
                    reasoning=score_input.reasoning,
                    weaknesses=score_input.weaknesses,
                    provenance_concerns=score_input.provenance_concerns,
                    action_intents=tuple(score_input.action_intents),
                    crew_noise=score_input.crew_noise,
                )
                for score_input in score_inputs
            ),
            allowed_evidence_ids=("fragment_starter_ledger", "asset_door_omen"),
            score_min=0,
            score_max=100,
        )

    def _auction_preview_reveal_from_oracle_result(
        self,
        *,
        contract_id: str,
        result: AuctionPreviewOracleResult,
    ) -> dict:
        return {
            "contract_id": contract_id,
            "phase": "Auction Preview",
            "status": "resolved",
            "standings": [
                {
                    "crew_id": standing.crew_id,
                    "score": standing.score,
                    "standing": standing.standing,
                    "strengths": list(standing.strengths),
                    "weaknesses": list(standing.weaknesses),
                    "penalties": list(standing.penalties),
                    "revealed_clues": list(standing.revealed_clues),
                }
                for standing in result.standings
            ],
            "contract_state": list(result.contract_state),
            "narration": result.narration,
        }

    def _oracle_packet_hash(self, packet: AuctionPreviewOraclePacket) -> str:
        encoded = packet.model_dump_json().encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
```

- [ ] **Step 5: Route `_build_auction_preview_reveal` through provider and audit events**

Replace `_build_auction_preview_reveal` with:

```python
    def _build_auction_preview_reveal(self, *, contract_id: str) -> dict:
        packet = self._build_auction_preview_packet(contract_id=contract_id)
        packet_hash = self._oracle_packet_hash(packet)
        self._event_store.append_command(
            event_type="oracle.resolution.requested",
            actor_id="server",
            visibility=EventVisibility.server_only(),
            payload={
                "contract_id": contract_id,
                "phase": "Auction Preview",
                "input_packet_hash": packet_hash,
                "provider": self._resolution_oracle.__class__.__name__,
            },
            idempotency_key=f"oracle.resolution.{contract_id}.auction-preview.requested",
        )
        fallback = False
        fallback_reason = None
        try:
            candidate = self._resolution_oracle.resolve_auction_preview(packet)
            accepted = validate_auction_preview_result(packet=packet, result=candidate)
        except Exception as exc:
            fallback = True
            fallback_reason = exc.__class__.__name__
            accepted = DeterministicResolutionOracle().resolve_auction_preview(packet)
            self._event_store.append_command(
                event_type="oracle.resolution.failed",
                actor_id="server",
                visibility=EventVisibility.server_only(),
                payload={
                    "contract_id": contract_id,
                    "phase": "Auction Preview",
                    "input_packet_hash": packet_hash,
                    "fallback_reason": fallback_reason,
                },
                idempotency_key=f"oracle.resolution.{contract_id}.auction-preview.failed",
            )
        self._event_store.append_command(
            event_type="oracle.resolution.completed",
            actor_id="server",
            visibility=EventVisibility.server_only(),
            payload={
                "contract_id": contract_id,
                "phase": "Auction Preview",
                "input_packet_hash": packet_hash,
                "provider": accepted.provider.provider,
                "model": accepted.provider.model,
                "prompt_version": accepted.provider.prompt_version,
                "fallback": fallback,
                "fallback_reason": fallback_reason,
                "accepted_output": accepted.model_dump(mode="json"),
            },
            idempotency_key=f"oracle.resolution.{contract_id}.auction-preview.completed",
        )
        return self._auction_preview_reveal_from_oracle_result(
            contract_id=contract_id,
            result=accepted,
        )
```

- [ ] **Step 6: Run focused phase tests**

Run:

```bash
pytest -q tests/server/test_phase_resolution.py tests/workflows/test_deterministic_oracle.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/hollow_lodge/server/services.py tests/server/test_phase_resolution.py
git commit -m "feat: route phase resolution through oracle"
```

---

## Task 4: Fallback On Invalid Provider Output

**Files:**
- Test: `tests/server/test_resolution_oracle.py`
- Modify: `src/hollow_lodge/server/app.py`
- Modify: `src/hollow_lodge/server/services.py`

- [ ] **Step 1: Write failing tests with injected bad oracle**

Create `tests/server/test_resolution_oracle.py`:

```python
from fastapi.testclient import TestClient

from hollow_lodge.server.app import create_app
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewResult,
    AuctionPreviewOracleResult,
    OracleProviderMetadata,
)


class UnknownCrewOracle:
    calls = 0

    def resolve_auction_preview(self, packet):
        self.calls += 1
        return AuctionPreviewOracleResult(
            provider=OracleProviderMetadata(provider="test", model="bad", prompt_version="test-v1"),
            standings=(
                AuctionPreviewCrewResult(
                    crew_id="crew_unknown",
                    score=99,
                    standing="Strong lead",
                    strengths=("invalid",),
                    weaknesses=(),
                    penalties=(),
                    revealed_clues=(),
                ),
            ),
            contract_state=(),
            narration="Invalid crew wins.",
            validation_warnings=(),
        )


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


def test_invalid_oracle_result_falls_back_and_is_audited(tmp_path):
    oracle = UnknownCrewOracle()
    client = TestClient(
        create_app(data_dir=tmp_path, invite_codes=["a"], resolution_oracle=oracle)
    )
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create"),
        json={"name": "The Gilt Knives"},
    ).json()
    action = client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-gilt"),
        json={
            "crew_id": crew["crew_id"],
            "intent": "Inspect the ledger for forged provenance.",
            "confirmed": True,
        },
    )
    assert action.status_code == 201

    response = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock"),
        json={"hours_elapsed": 6},
    )

    assert response.status_code == 200
    assert oracle.calls == 1
    reveal = response.json()
    assert reveal["standings"][0]["crew_id"] == crew["crew_id"]
    events = client.app.state.event_store.read()
    failed = next(event for event in events if event.type == "oracle.resolution.failed")
    completed = next(event for event in events if event.type == "oracle.resolution.completed")
    assert failed.payload["fallback_reason"] == "ValueError"
    assert completed.payload["fallback"] is True
    assert completed.payload["provider"] == "deterministic"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest -q tests/server/test_resolution_oracle.py
```

Expected: FAIL because `create_app` does not accept `resolution_oracle`.

- [ ] **Step 3: Update app factory and lazy route constructors**

Modify `src/hollow_lodge/server/app.py`:

```python
from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_boundary import ResolutionOracle
from hollow_lodge.workflows.oracle_factory import resolution_oracle_from_env
```

Change signature:

```python
def create_app(
    *,
    data_dir: str | Path | None = None,
    invite_codes: list[str] | None = None,
    resolution_oracle: ResolutionOracle | None = None,
) -> FastAPI:
```

Before services:

```python
    app.state.resolution_oracle = resolution_oracle or resolution_oracle_from_env()
```

When creating `ContractService`:

```python
        app.state.contract_service = ContractService(
            event_store=event_store,
            resolution_oracle=app.state.resolution_oracle,
        )
```

Modify `src/hollow_lodge/server/routes_contracts.py` and any lazy `ContractService` constructor in route helpers to pass `request.app.state.resolution_oracle`.

- [ ] **Step 4: Add temporary factory returning deterministic provider**

Create `src/hollow_lodge/workflows/oracle_factory.py`:

```python
from __future__ import annotations

import os

from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_boundary import ResolutionOracle


def resolution_oracle_from_env() -> ResolutionOracle:
    provider = os.environ.get("HOLLOW_LODGE_ORACLE_PROVIDER", "deterministic").strip().lower()
    if provider in {"", "deterministic"}:
        return DeterministicResolutionOracle()
    if provider == "openai":
        return DeterministicResolutionOracle()
    raise ValueError(f"unsupported oracle provider: {provider}")
```

This is intentionally deterministic until Task 6 adds the OpenAI provider.

- [ ] **Step 5: Run tests**

Run:

```bash
pytest -q tests/server/test_resolution_oracle.py tests/server/test_phase_resolution.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/hollow_lodge/server/app.py src/hollow_lodge/server/routes_contracts.py src/hollow_lodge/workflows/oracle_factory.py tests/server/test_resolution_oracle.py
git commit -m "feat: add oracle fallback audit path"
```

---

## Task 5: Provider Factory Configuration

**Files:**
- Modify: `src/hollow_lodge/workflows/oracle_factory.py`
- Test: `tests/workflows/test_oracle_factory.py`

- [ ] **Step 1: Write failing factory tests**

Create `tests/workflows/test_oracle_factory.py`:

```python
import pytest

from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle
from hollow_lodge.workflows.oracle_factory import resolution_oracle_from_env


def test_factory_defaults_to_deterministic(monkeypatch):
    monkeypatch.delenv("HOLLOW_LODGE_ORACLE_PROVIDER", raising=False)

    oracle = resolution_oracle_from_env()

    assert isinstance(oracle, DeterministicResolutionOracle)


def test_factory_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ORACLE_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="unsupported oracle provider"):
        resolution_oracle_from_env()


def test_factory_openai_without_api_key_uses_deterministic(monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ORACLE_PROVIDER", "openai")
    monkeypatch.delenv("HOLLOW_LODGE_OPENAI_API_KEY", raising=False)

    oracle = resolution_oracle_from_env()

    assert isinstance(oracle, DeterministicResolutionOracle)
```

- [ ] **Step 2: Run tests**

Run:

```bash
pytest -q tests/workflows/test_oracle_factory.py
```

Expected: PASS with the temporary factory from Task 4.

- [ ] **Step 3: Add explicit timeout parsing test**

Append:

```python
def test_factory_rejects_invalid_timeout(monkeypatch):
    monkeypatch.setenv("HOLLOW_LODGE_ORACLE_PROVIDER", "deterministic")
    monkeypatch.setenv("HOLLOW_LODGE_ORACLE_TIMEOUT_SECONDS", "0")

    with pytest.raises(ValueError, match="timeout"):
        resolution_oracle_from_env()
```

- [ ] **Step 4: Run test to verify it fails**

Run:

```bash
pytest -q tests/workflows/test_oracle_factory.py::test_factory_rejects_invalid_timeout
```

Expected: FAIL because timeout is not parsed.

- [ ] **Step 5: Implement timeout parsing**

Modify `src/hollow_lodge/workflows/oracle_factory.py`:

```python
def _timeout_seconds_from_env() -> float:
    raw = os.environ.get("HOLLOW_LODGE_ORACLE_TIMEOUT_SECONDS", "20")
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise ValueError("oracle timeout must be a number") from exc
    if timeout <= 0:
        raise ValueError("oracle timeout must be greater than zero")
    return timeout


def resolution_oracle_from_env() -> ResolutionOracle:
    _ = _timeout_seconds_from_env()
    provider = os.environ.get("HOLLOW_LODGE_ORACLE_PROVIDER", "deterministic").strip().lower()
    if provider in {"", "deterministic"}:
        return DeterministicResolutionOracle()
    if provider == "openai":
        if not os.environ.get("HOLLOW_LODGE_OPENAI_API_KEY"):
            return DeterministicResolutionOracle()
        return DeterministicResolutionOracle()
    raise ValueError(f"unsupported oracle provider: {provider}")
```

- [ ] **Step 6: Run tests**

Run:

```bash
pytest -q tests/workflows/test_oracle_factory.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/hollow_lodge/workflows/oracle_factory.py tests/workflows/test_oracle_factory.py
git commit -m "feat: configure oracle provider defaults"
```

---

## Task 6: OpenAI Provider With Mocked Structured Outputs

**Files:**
- Create: `src/hollow_lodge/workflows/openai_oracle.py`
- Modify: `src/hollow_lodge/workflows/oracle_factory.py`
- Modify: `pyproject.toml`
- Test: `tests/workflows/test_openai_oracle.py`
- Test: `tests/workflows/test_oracle_factory.py`

- [ ] **Step 1: Write mocked OpenAI provider tests**

Create `tests/workflows/test_openai_oracle.py`:

```python
from hollow_lodge.workflows.openai_oracle import OpenAIResolutionOracle
from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewPacket,
    AuctionPreviewOraclePacket,
)


class FakeResponses:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.output


class FakeClient:
    def __init__(self, output):
        self.responses = FakeResponses(output)


class FakeParsed:
    def __init__(self, parsed):
        self.output_parsed = parsed


def packet() -> AuctionPreviewOraclePacket:
    return AuctionPreviewOraclePacket(
        contract_id="contract_false_finger",
        phase="Auction Preview",
        hidden_truth_summary="The finger is a saint-bone forgery.",
        allowed_reveal_strings=("Auction house provenance is now suspect.",),
        rubric_hooks=("provenance quality",),
        crews=(
            AuctionPreviewCrewPacket(
                crew_id="crew_gilt",
                claim="The relic is false.",
                evidence_ids=("fragment_starter_ledger",),
                exposed_assets=("fragment_starter_ledger",),
                reasoning="The ledger contradicts the timestamp.",
                weaknesses="No material proof.",
                provenance_concerns="Copied hand.",
                action_intents=("Inspect the ledger.",),
                crew_noise=0,
            ),
        ),
        allowed_evidence_ids=("fragment_starter_ledger",),
        score_min=0,
        score_max=100,
    )


def test_openai_oracle_uses_structured_outputs_parse_contract():
    parsed = {
        "standings": [
            {
                "crew_id": "crew_gilt",
                "score": 88,
                "standing": "Strong lead",
                "strengths": ["clean provenance contradiction"],
                "weaknesses": ["no material confirmation"],
                "penalties": [],
                "revealed_clues": ["Auction house provenance is now suspect."],
            }
        ],
        "contract_state": ["Auction house provenance is now suspect."],
        "narration": "The Gilt packet leads through provenance.",
        "validation_warnings": [],
    }
    client = FakeClient(FakeParsed(parsed))
    oracle = OpenAIResolutionOracle(client=client, model="gpt-test", timeout_seconds=7)

    result = oracle.resolve_auction_preview(packet())

    assert result.provider.provider == "openai"
    assert result.provider.model == "gpt-test"
    assert result.standings[0].score == 88
    call = client.responses.calls[0]
    assert call["model"] == "gpt-test"
    assert call["text"]["format"]["type"] == "json_schema"
    assert call["text"]["format"]["strict"] is True
    assert call["timeout"] == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest -q tests/workflows/test_openai_oracle.py
```

Expected: FAIL with missing `openai_oracle`.

- [ ] **Step 3: Add OpenAI dependency**

Modify `pyproject.toml` dependencies:

```toml
  "openai>=1.0",
```

- [ ] **Step 4: Implement provider**

Create `src/hollow_lodge/workflows/openai_oracle.py`:

```python
from __future__ import annotations

from typing import Any

from openai import OpenAI

from hollow_lodge.workflows.oracle_boundary import (
    AuctionPreviewCrewResult,
    AuctionPreviewOraclePacket,
    AuctionPreviewOracleResult,
    OracleProviderMetadata,
)


PROMPT_VERSION = "auction-preview-resolution-v1"


class OpenAIResolutionOracle:
    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str,
        timeout_seconds: float,
    ):
        self._client = client or OpenAI()
        self._model = model
        self._timeout_seconds = timeout_seconds

    def resolve_auction_preview(
        self,
        packet: AuctionPreviewOraclePacket,
    ) -> AuctionPreviewOracleResult:
        response = self._client.responses.parse(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are The Hollow Lodge Resolution Oracle. "
                        "Return only structured JSON. Evaluate proof quality, "
                        "preserve hidden truth, and use only allowed reveal strings."
                    ),
                },
                {
                    "role": "user",
                    "content": packet.model_dump_json(),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "auction_preview_resolution",
                    "strict": True,
                    "schema": _schema(),
                }
            },
            timeout=self._timeout_seconds,
        )
        parsed = response.output_parsed
        return AuctionPreviewOracleResult(
            provider=OracleProviderMetadata(
                provider="openai",
                model=self._model,
                prompt_version=PROMPT_VERSION,
            ),
            standings=tuple(
                AuctionPreviewCrewResult(
                    crew_id=item["crew_id"],
                    score=item["score"],
                    standing=item["standing"],
                    strengths=tuple(item.get("strengths", ())),
                    weaknesses=tuple(item.get("weaknesses", ())),
                    penalties=tuple(item.get("penalties", ())),
                    revealed_clues=tuple(item.get("revealed_clues", ())),
                )
                for item in parsed["standings"]
            ),
            contract_state=tuple(parsed.get("contract_state", ())),
            narration=parsed.get("narration", ""),
            validation_warnings=tuple(parsed.get("validation_warnings", ())),
        )


def _schema() -> dict[str, Any]:
    crew_result = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "crew_id",
            "score",
            "standing",
            "strengths",
            "weaknesses",
            "penalties",
            "revealed_clues",
        ],
        "properties": {
            "crew_id": {"type": "string", "minLength": 1},
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "standing": {"type": "string", "minLength": 1},
            "strengths": {"type": "array", "items": {"type": "string"}},
            "weaknesses": {"type": "array", "items": {"type": "string"}},
            "penalties": {"type": "array", "items": {"type": "string"}},
            "revealed_clues": {"type": "array", "items": {"type": "string"}},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["standings", "contract_state", "narration", "validation_warnings"],
        "properties": {
            "standings": {"type": "array", "items": crew_result},
            "contract_state": {"type": "array", "items": {"type": "string"}},
            "narration": {"type": "string"},
            "validation_warnings": {"type": "array", "items": {"type": "string"}},
        },
    }
```

- [ ] **Step 5: Update factory for real provider**

Modify `src/hollow_lodge/workflows/oracle_factory.py`:

```python
from hollow_lodge.workflows.openai_oracle import OpenAIResolutionOracle
```

In the `provider == "openai"` branch:

```python
        if not os.environ.get("HOLLOW_LODGE_OPENAI_API_KEY"):
            return DeterministicResolutionOracle()
        return OpenAIResolutionOracle(
            model=os.environ.get("HOLLOW_LODGE_ORACLE_MODEL", "gpt-4.1-mini"),
            timeout_seconds=_timeout_seconds_from_env(),
        )
```

Update `tests/workflows/test_oracle_factory.py` with:

```python
def test_factory_openai_with_api_key_returns_openai_provider(monkeypatch):
    from hollow_lodge.workflows.openai_oracle import OpenAIResolutionOracle

    monkeypatch.setenv("HOLLOW_LODGE_ORACLE_PROVIDER", "openai")
    monkeypatch.setenv("HOLLOW_LODGE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("HOLLOW_LODGE_ORACLE_MODEL", "gpt-test")

    oracle = resolution_oracle_from_env()

    assert isinstance(oracle, OpenAIResolutionOracle)
```

- [ ] **Step 6: Run workflow tests**

Run:

```bash
pytest -q tests/workflows/test_openai_oracle.py tests/workflows/test_oracle_factory.py tests/workflows/test_oracle_boundary.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/hollow_lodge/workflows/openai_oracle.py src/hollow_lodge/workflows/oracle_factory.py tests/workflows/test_openai_oracle.py tests/workflows/test_oracle_factory.py
git commit -m "feat: add openai resolution oracle provider"
```

---

## Task 7: Idempotency And No Duplicate Provider Calls

**Files:**
- Test: `tests/server/test_resolution_oracle.py`
- Modify: `src/hollow_lodge/server/services.py` only if the test fails.

- [ ] **Step 1: Add idempotency regression test**

Append to `tests/server/test_resolution_oracle.py`:

```python
class CountingOracle:
    def __init__(self):
        self.calls = 0

    def resolve_auction_preview(self, packet):
        from hollow_lodge.workflows.deterministic_oracle import DeterministicResolutionOracle

        self.calls += 1
        return DeterministicResolutionOracle().resolve_auction_preview(packet)


def test_duplicate_phase_lock_does_not_call_oracle_twice(tmp_path):
    oracle = CountingOracle()
    client = TestClient(
        create_app(data_dir=tmp_path, invite_codes=["a"], resolution_oracle=oracle)
    )
    ada = register(client, "a", "Ada")
    crew = client.post(
        "/crews",
        headers=command_auth(ada["token"], "crew-create"),
        json={"name": "The Gilt Knives"},
    ).json()
    client.post(
        "/actions",
        headers=command_auth(ada["token"], "action-gilt"),
        json={
            "crew_id": crew["crew_id"],
            "intent": "Inspect the ledger for forged provenance.",
            "confirmed": True,
        },
    )

    first = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock"),
        json={"hours_elapsed": 6},
    )
    replay = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock"),
        json={"hours_elapsed": 6},
    )
    duplicate = client.post(
        "/contracts/contract_false_finger/phases/auction-preview/lock",
        headers=command_auth(ada["token"], "phase-lock-other"),
        json={"hours_elapsed": 7},
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert duplicate.status_code == 200
    assert replay.json() == first.json()
    assert duplicate.json() == first.json()
    assert oracle.calls == 1
```

- [ ] **Step 2: Run the test**

Run:

```bash
pytest -q tests/server/test_resolution_oracle.py::test_duplicate_phase_lock_does_not_call_oracle_twice
```

Expected: PASS if existing resolved-phase short-circuit remains ahead of `_build_auction_preview_reveal`; FAIL if provider is called more than once.

- [ ] **Step 3: If it fails, fix resolved short-circuit**

Ensure `ContractService.lock_auction_preview` checks `_resolved_auction_preview()` and returns it before building packet or calling `_build_auction_preview_reveal`.

The relevant shape should be:

```python
            resolved = self._resolved_auction_preview()
            if resolved is not None:
                return resolved
            locked = self._locked_auction_preview()
            if locked is None:
                append lock event
            reveal = self._build_auction_preview_reveal(contract_id=contract_id)
```

- [ ] **Step 4: Run tests**

Run:

```bash
pytest -q tests/server/test_resolution_oracle.py tests/server/test_phase_resolution.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hollow_lodge/server/services.py tests/server/test_resolution_oracle.py
git commit -m "test: guard oracle phase idempotency"
```

---

## Task 8: Full Verification And Deployment Defaults

**Files:**
- Modify: `README.md` only if needed to document env vars.
- No production provider enablement in this task.

- [ ] **Step 1: Run full suite**

Run:

```bash
pytest -q
```

Expected: all tests pass. No test calls a real external LLM API.

- [ ] **Step 2: Verify env-default behavior locally**

Run:

```bash
HOLLOW_LODGE_ORACLE_PROVIDER=deterministic pytest -q tests/server/test_phase_resolution.py tests/server/test_resolution_oracle.py
```

Expected: PASS.

- [ ] **Step 3: Verify OpenAI provider without key falls back at factory level**

Run:

```bash
HOLLOW_LODGE_ORACLE_PROVIDER=openai env -u HOLLOW_LODGE_OPENAI_API_KEY pytest -q tests/workflows/test_oracle_factory.py::test_factory_openai_without_api_key_uses_deterministic
```

Expected: PASS.

- [ ] **Step 4: Document env vars**

If `README.md` does not mention server oracle env vars, add:

```markdown
## Server Oracle

The server defaults to deterministic resolution:

```sh
HOLLOW_LODGE_ORACLE_PROVIDER=deterministic
```

OpenAI-backed resolution is available behind explicit server env vars:

```sh
HOLLOW_LODGE_ORACLE_PROVIDER=openai
HOLLOW_LODGE_ORACLE_MODEL=gpt-4.1-mini
HOLLOW_LODGE_ORACLE_TIMEOUT_SECONDS=20
HOLLOW_LODGE_OPENAI_API_KEY=...
```

The model output is validated by the server before it is committed. Missing API
keys or invalid model output fall back to deterministic resolution.
```

- [ ] **Step 5: Run README/docs grep**

Run:

```bash
rg -n "HOLLOW_LODGE_ORACLE_PROVIDER|HOLLOW_LODGE_OPENAI_API_KEY" README.md docs src tests
```

Expected: env vars appear in README, factory, and tests.

- [ ] **Step 6: Commit docs if changed**

```bash
git add README.md
git commit -m "docs: document server oracle configuration"
```

- [ ] **Step 7: Final status**

Run:

```bash
git status --short
git log --oneline -5
```

Expected: clean worktree after all commits.

---

## Self-Review

Spec coverage:

- Bounded Auction Preview Resolution Oracle: Tasks 1-3.
- Server authority and validation: Tasks 1, 3, 4.
- Deterministic fallback: Tasks 2, 4, 5, 8.
- Provider env strategy: Tasks 5, 6, 8.
- Audit events: Tasks 3 and 4.
- OpenAI Structured Outputs: Task 6.
- No real external LLM calls in tests: Task 6 uses injected fake client; Task 8 verifies factory fallback.
- Idempotent phase resolution: Task 7.

Placeholder scan: no placeholder-marker steps remain.

Type consistency: `AuctionPreviewOraclePacket`, `AuctionPreviewCrewPacket`,
`AuctionPreviewOracleResult`, `AuctionPreviewCrewResult`,
`OracleProviderMetadata`, `ResolutionOracle`, and
`validate_auction_preview_result` are defined in Task 1 and used consistently.
