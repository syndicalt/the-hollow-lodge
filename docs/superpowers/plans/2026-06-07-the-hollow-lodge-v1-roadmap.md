# The Hollow Lodge V1 Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first playable vertical slice of The Hollow Lodge: invite-code login, first-party brokered chat, two crews contesting The Saint's False Finger, freeform-first action submission, proof dossiers, phase resolution, and Eventloom-backed authoritative/local logs.

**Architecture:** Use a central authoritative server with an append-only Eventloom-compatible JSONL log and SQLite projections for current state. Use a CLI client with a local perspective log and Handler-facing commands. Keep llmff behind a typed workflow boundary with deterministic/mock implementations first, so core gameplay can be tested before model integration.

**Tech Stack:** Python 3.12, FastAPI, Typer, Pydantic, SQLite, pytest, httpx, append-only JSONL event logs.

---

## Scope Check

The approved design covers multiple subsystems. Implementing it as one plan would create a large, brittle build. V1 should be delivered as a sequence of independently testable slices:

1. Project scaffold and event model
2. Identity, crews, and local CLI configuration
3. First-party brokered chat
4. Contract seed and board/inbox projections
5. Side actions and proof-fragment provenance checks
6. Freeform full action intake and Handler normalization
7. Proof dossiers and Packet Lead office
8. Auction Preview phase resolution and score reveal
9. Local perspective sync and replay
10. End-to-end two-crew vertical slice

Each slice should leave the repo runnable, tested, and committed.

## Proposed File Structure

Create a Python monorepo with explicit server/client/domain boundaries:

```text
pyproject.toml
README.md
src/hollow_lodge/
  __init__.py
  domain/
    __init__.py
    ids.py
    events.py
    identity.py
    crews.py
    contracts.py
    chat.py
    actions.py
    proofs.py
    scoring.py
  eventlog/
    __init__.py
    jsonl_store.py
    visibility.py
  server/
    __init__.py
    app.py
    auth.py
    projections.py
    routes_identity.py
    routes_crews.py
    routes_chat.py
    routes_contracts.py
    routes_actions.py
    routes_proofs.py
    seed_data.py
  client/
    __init__.py
    cli.py
    config.py
    api.py
    render.py
    local_log.py
    handler.py
  workflows/
    __init__.py
    llmff_boundary.py
    deterministic_handler.py
tests/
  domain/
  eventlog/
  server/
  client/
  workflows/
```

Responsibilities:

- `domain/`: pure game objects and transition rules. No HTTP, no filesystem writes.
- `eventlog/`: append-only JSONL event persistence and visibility filtering.
- `server/`: authoritative API, command validation, projections, and seeded starter contract.
- `client/`: Typer CLI, local token/config, local perspective log, and terminal rendering.
- `workflows/`: typed boundaries for Handler/Oracle/llmff tasks. Deterministic implementations are used first.

## Milestone 0: Scaffold

**Purpose:** Establish a testable Python project without gameplay behavior.

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/hollow_lodge/__init__.py`
- Create: package directories listed above
- Create: `tests/test_imports.py`

- [ ] Create the Python package scaffold.
- [ ] Add dependencies: `fastapi`, `uvicorn`, `typer`, `pydantic`, `httpx`, `pytest`.
- [ ] Add scripts or documented commands:
  - `pytest`
  - `python -m hollow_lodge.client.cli --help`
  - `uvicorn hollow_lodge.server.app:app --reload`
- [ ] Write `tests/test_imports.py` to verify server and client packages import.
- [ ] Run `pytest`.
- [ ] Commit with message: `chore: scaffold Hollow Lodge app`.

Exit criteria:

- `pytest` passes.
- CLI help imports without starting a server.
- FastAPI app imports without touching a real event log.

## Milestone 1: Authoritative Event Log

**Purpose:** Build the append-only event foundation before game state.

**Files:**
- Create: `src/hollow_lodge/domain/events.py`
- Create: `src/hollow_lodge/domain/ids.py`
- Create: `src/hollow_lodge/eventlog/jsonl_store.py`
- Create: `src/hollow_lodge/eventlog/visibility.py`
- Test: `tests/eventlog/test_jsonl_store.py`
- Test: `tests/eventlog/test_visibility.py`

- [ ] Define a Pydantic `GameEvent` with event id, sequence, timestamp, type, actor id, visibility, payload, and previous hash.
- [ ] Implement JSONL append with monotonic sequence numbers and hash chaining.
- [ ] Implement read by sequence range.
- [ ] Implement visibility filtering for public, crew-scoped, player-scoped, and server-only events.
- [ ] Test append/read/hash-chain behavior.
- [ ] Test that player-scoped events are only visible to the named player.
- [ ] Test that server-only events never appear in local perspective reads.
- [ ] Run `pytest tests/eventlog -q`.
- [ ] Commit with message: `feat: add authoritative event log`.

Exit criteria:

- Event log append is deterministic and auditable.
- Visibility filtering is test-covered before chat or contracts exist.

## Milestone 2: Identity, Invites, Crews, And CLI Tokens

**Purpose:** Let invited players register, store a local CLI token, and join stable crews.

**Files:**
- Create: `src/hollow_lodge/domain/identity.py`
- Create: `src/hollow_lodge/domain/crews.py`
- Create: `src/hollow_lodge/server/auth.py`
- Create: `src/hollow_lodge/server/routes_identity.py`
- Create: `src/hollow_lodge/server/routes_crews.py`
- Create: `src/hollow_lodge/client/config.py`
- Modify: `src/hollow_lodge/server/app.py`
- Modify: `src/hollow_lodge/client/cli.py`
- Test: `tests/server/test_identity_routes.py`
- Test: `tests/server/test_crew_routes.py`
- Test: `tests/client/test_config.py`

- [ ] Add invite-code registration endpoint that returns a player id and token.
- [ ] Store tokens server-side as hashed token records.
- [ ] Add token auth dependency for server routes.
- [ ] Add CLI command: `hollow lodge register --server <url> --invite <code> --name <name>`.
- [ ] Store local config under an explicit path supplied by tests; default user path can be added after tests.
- [ ] Add crew creation and join commands.
- [ ] Enforce crew size range of 3-5 as a warning for readiness, while allowing 2-player test crews for the starter slice.
- [ ] Test invite registration succeeds once and rejects reused invite codes.
- [ ] Test token auth rejects missing/invalid tokens.
- [ ] Test crew membership is recorded through authoritative events.
- [ ] Run `pytest tests/server/test_identity_routes.py tests/server/test_crew_routes.py tests/client/test_config.py -q`.
- [ ] Commit with message: `feat: add invite identity and crews`.

Exit criteria:

- V1 identity is invite-code plus local token.
- OAuth remains absent.
- Crew membership is Eventloom-recorded.

## Milestone 3: First-Party Brokered Chat

**Purpose:** Build game-native chat before deals and Handler summaries.

**Files:**
- Create: `src/hollow_lodge/domain/chat.py`
- Create: `src/hollow_lodge/server/routes_chat.py`
- Modify: `src/hollow_lodge/client/cli.py`
- Modify: `src/hollow_lodge/client/render.py`
- Test: `tests/server/test_chat_routes.py`
- Test: `tests/client/test_chat_cli.py`

- [ ] Define chat event payloads for direct player message, crew message, and crew-to-crew targeted message.
- [ ] Require every chat message to receive a canonical server message id.
- [ ] Persist chat as visibility-scoped events.
- [ ] Add CLI commands:
  - `hollow lodge msg @player <text>`
  - `hollow lodge crew <text>`
  - `hollow lodge crew-msg <crew-id> <text>`
  - `hollow lodge thread <conversation-id>`
- [ ] Ensure chat itself creates no binding deal state.
- [ ] Test direct messages sync only to sender and recipient.
- [ ] Test crew messages sync only to crew members.
- [ ] Test crew-to-crew messages sync only to both crews.
- [ ] Test message ids can be cited by later commands.
- [ ] Run `pytest tests/server/test_chat_routes.py tests/client/test_chat_cli.py -q`.
- [ ] Commit with message: `feat: add brokered chat`.

Exit criteria:

- Game-critical negotiation has first-party visibility-scoped persistence.
- Local Handler can later cite message ids for deal extraction.

## Milestone 4: Starter Contract Seed And Board

**Purpose:** Commit The Saint's False Finger seed assets and render board/inbox state.

**Files:**
- Create: `src/hollow_lodge/domain/contracts.py`
- Create: `src/hollow_lodge/server/seed_data.py`
- Create: `src/hollow_lodge/server/routes_contracts.py`
- Modify: `src/hollow_lodge/server/projections.py`
- Modify: `src/hollow_lodge/client/cli.py`
- Modify: `src/hollow_lodge/client/render.py`
- Test: `tests/server/test_contract_seed.py`
- Test: `tests/client/test_contract_board.py`

- [ ] Define campaign, contract, phase, evidence asset, and hidden truth models.
- [ ] Add deterministic seed data for Saints & Ledgers and The Saint's False Finger.
- [ ] Store hidden truth as server-only events.
- [ ] Store public contract hooks as crew-visible/public events.
- [ ] Add route: `GET /contracts`.
- [ ] Add route: `GET /inbox`.
- [ ] Add CLI command: `hollow lodge contracts`.
- [ ] Add CLI command: `hollow lodge inbox`.
- [ ] Render Auction Preview timer, crew heat, proof dossier needs, and incoming proof fragment notices.
- [ ] Test hidden truth never appears in player inbox/board.
- [ ] Test board renders The Saint's False Finger with Auction Preview active.
- [ ] Run `pytest tests/server/test_contract_seed.py tests/client/test_contract_board.py -q`.
- [ ] Commit with message: `feat: seed starter contract board`.

Exit criteria:

- Players can see the starter contract and inbox state.
- Server has committed seed assets before play.

## Milestone 5: Proof Fragments, Provenance, And Side Actions

**Purpose:** Let players inspect copied proof fragments with limited side actions.

**Files:**
- Create: `src/hollow_lodge/domain/proofs.py`
- Create: `src/hollow_lodge/server/routes_proofs.py`
- Modify: `src/hollow_lodge/client/cli.py`
- Modify: `src/hollow_lodge/workflows/deterministic_handler.py`
- Test: `tests/domain/test_proof_fragments.py`
- Test: `tests/server/test_proof_routes.py`
- Test: `tests/workflows/test_deterministic_handler.py`

- [ ] Define proof fragment model with fragment id, content summary, source chain, visibility, and provenance flags.
- [ ] Add targeted proof transfer route.
- [ ] Add side-action counter per player per phase.
- [ ] Add CLI command: `hollow lodge check <fragment-id> provenance`.
- [ ] Implement deterministic shallow provenance read for the starter ledger fragment.
- [ ] Enforce side-action consumption.
- [ ] Test copied fragments preserve provenance chain internally.
- [ ] Test recipient sees only surface provenance until a check is spent.
- [ ] Test side-action limit rejects extra checks.
- [ ] Run `pytest tests/domain/test_proof_fragments.py tests/server/test_proof_routes.py tests/workflows/test_deterministic_handler.py -q`.
- [ ] Commit with message: `feat: add proof provenance checks`.

Exit criteria:

- Information is copyable but provenance remains gameplay-relevant.
- Side actions are useful without becoming full contract actions.

## Milestone 6: Freeform Action Intake And Handler Normalization

**Purpose:** Prove the freeform-first hybrid action loop before resolving outcomes.

**Files:**
- Create: `src/hollow_lodge/domain/actions.py`
- Create: `src/hollow_lodge/server/routes_actions.py`
- Create: `src/hollow_lodge/workflows/llmff_boundary.py`
- Modify: `src/hollow_lodge/workflows/deterministic_handler.py`
- Modify: `src/hollow_lodge/client/handler.py`
- Modify: `src/hollow_lodge/client/cli.py`
- Test: `tests/domain/test_actions.py`
- Test: `tests/server/test_action_routes.py`
- Test: `tests/client/test_action_cli.py`

- [ ] Define normalized action frame: intent, scope, approach, risk posture, exposed assets, and crew noise impact.
- [ ] Add Handler normalization workflow interface.
- [ ] Implement deterministic normalizer for the two starter walkthrough actions.
- [ ] Add CLI command: `hollow lodge act`.
- [ ] Add normalize-confirm-submit flow.
- [ ] Store draft normalization in local perspective log before confirmation.
- [ ] Submit confirmed action to server.
- [ ] Allow confirmed actions to be edited or canceled before phase lock.
- [ ] Test prose action normalizes into expected frame.
- [ ] Test unconfirmed action does not reach server.
- [ ] Test confirmed action is private until result.
- [ ] Test second full action in a phase increases crew noise risk.
- [ ] Run `pytest tests/domain/test_actions.py tests/server/test_action_routes.py tests/client/test_action_cli.py -q`.
- [ ] Commit with message: `feat: add freeform action intake`.

Exit criteria:

- Players can type freeform actions.
- Handler translates intent but does not choose strategy or submit without confirmation.

## Milestone 7: Proof Dossiers And Packet Lead

**Purpose:** Add the shared evidence packet that contracts score.

**Files:**
- Modify: `src/hollow_lodge/domain/proofs.py`
- Create: `src/hollow_lodge/server/routes_proofs.py`
- Modify: `src/hollow_lodge/client/cli.py`
- Modify: `src/hollow_lodge/client/render.py`
- Test: `tests/domain/test_dossiers.py`
- Test: `tests/server/test_packet_lead.py`

- [ ] Define proof dossier model with claim, evidence ids, reasoning, weaknesses, and provenance concerns.
- [ ] Add campaign Packet Lead assignment.
- [ ] Add simple-majority Packet Lead replacement vote.
- [ ] Add dossier update endpoint restricted to Packet Lead for framing fields.
- [ ] Allow crew members to contribute notes/evidence without changing final framing.
- [ ] Add CLI commands:
  - `hollow lodge dossier`
  - `hollow lodge dossier add-evidence <fragment-id>`
  - `hollow lodge dossier claim <text>`
  - `hollow lodge packet-lead vote <player-id>`
- [ ] Test Packet Lead can edit claim/reasoning.
- [ ] Test non-lead cannot overwrite framing.
- [ ] Test simple-majority vote replaces Packet Lead.
- [ ] Test server does not label dossier contamination intent.
- [ ] Run `pytest tests/domain/test_dossiers.py tests/server/test_packet_lead.py -q`.
- [ ] Commit with message: `feat: add proof dossiers`.

Exit criteria:

- Crews can build living proof dossiers.
- Packet Lead is the only formal crew office.

## Milestone 8: Auction Preview Resolver And Score Reveal

**Purpose:** Resolve the starter phase end-to-end with one crew in the lead.

**Files:**
- Create: `src/hollow_lodge/domain/scoring.py`
- Modify: `src/hollow_lodge/server/routes_contracts.py`
- Modify: `src/hollow_lodge/server/projections.py`
- Modify: `src/hollow_lodge/client/render.py`
- Test: `tests/domain/test_scoring.py`
- Test: `tests/server/test_phase_resolution.py`

- [ ] Define scoring inputs: evidence credibility, corroboration, source independence, provenance quality, contradictions, reasoning quality, heat/noise penalties, and occult resonance.
- [ ] Implement deterministic scorer for Auction Preview.
- [ ] Implement phase lock when deadline is reached or enough meaningful actions are committed.
- [ ] Resolve the Gilt Knives clerk action into forged-date correlation.
- [ ] Resolve the Moth Choir moth jar action into door omen.
- [ ] Update crew heat/noise and proof standing.
- [ ] Reveal phase scores after resolution while preserving campaign-hidden facts.
- [ ] Test Gilt Knives takes a strong phase lead from clean provenance contradiction.
- [ ] Test Moth Choir remains viable through alternate occult clue.
- [ ] Test exact hidden truth does not leak in score reveal.
- [ ] Run `pytest tests/domain/test_scoring.py tests/server/test_phase_resolution.py -q`.
- [ ] Commit with message: `feat: resolve auction preview phase`.

Exit criteria:

- The starter walkthrough can be produced by real server state.
- The proof-score loop is visible and learnable after resolution.

## Milestone 9: Local Perspective Sync And Replay

**Purpose:** Make each client maintain a local Eventloom shard that reflects only visible facts.

**Files:**
- Create: `src/hollow_lodge/client/local_log.py`
- Modify: `src/hollow_lodge/client/api.py`
- Modify: `src/hollow_lodge/client/cli.py`
- Test: `tests/client/test_local_log.py`
- Test: `tests/server/test_event_sync.py`

- [ ] Add server route to fetch visible events since sequence.
- [ ] Add local JSONL perspective log.
- [ ] Sync visible server events into local log.
- [ ] Store local Handler drafts and summaries as local-only events.
- [ ] Add CLI command: `hollow lodge sync`.
- [ ] Add CLI command: `hollow lodge replay --since <seq>`.
- [ ] Test server-only hidden truth never syncs to local log.
- [ ] Test local drafts never mutate server truth.
- [ ] Test replay renders chat, proof transfer, action result, and phase reveal in order.
- [ ] Run `pytest tests/client/test_local_log.py tests/server/test_event_sync.py -q`.
- [ ] Commit with message: `feat: add local perspective sync`.

Exit criteria:

- Local logs are perspective, not authority.
- Players can recover context asynchronously.

## Milestone 10: Two-Crew Vertical Slice

**Purpose:** Prove the main gameplay loop from registration through phase result.

**Files:**
- Create: `tests/e2e/test_saints_and_ledgers_preview.py`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-07-the-hollow-lodge-design.md` only if the implementation reveals a spec correction that the user approves

- [ ] Write an end-to-end test that registers two crews.
- [ ] Seed Saints & Ledgers and The Saint's False Finger.
- [ ] Send targeted Moth Choir ledger fragment to Gilt Knives.
- [ ] Run Gilt Knives provenance side check.
- [ ] Send Moth Choir targeted chat offer.
- [ ] Extract a deal draft without binding it.
- [ ] Submit Gilt Knives clerk full action.
- [ ] Submit Moth Choir moth jar full action.
- [ ] Update both crew dossiers.
- [ ] Lock and resolve Auction Preview.
- [ ] Assert Gilt Knives leads after score reveal.
- [ ] Assert Moth Choir retains alternate clue path.
- [ ] Assert all visible events sync correctly to each crew's perspective.
- [ ] Update README with local run instructions for the vertical slice.
- [ ] Run full test suite with `pytest`.
- [ ] Commit with message: `test: prove starter contract vertical slice`.

Exit criteria:

- One command sequence can demonstrate the approved gameplay loop.
- The game has a working server, CLI, chat, action, dossier, and resolver skeleton.

## Roadmap Order

Do not begin with model integration. Build deterministic gameplay first:

1. Event log
2. Identity and crews
3. Brokered chat
4. Starter contract board
5. Proof provenance side actions
6. Freeform action normalization
7. Proof dossiers and Packet Lead
8. Phase resolver and score reveal
9. Local sync/replay
10. End-to-end walkthrough

llmff integration becomes valuable after Milestone 6, when action frames and Handler workflow interfaces exist. Before then, deterministic workflow outputs are enough and easier to test.

## Verification Gates

Every milestone must include:

- focused pytest command for changed behavior
- no server-only event visible in client sync tests
- no local Handler output mutating server state without explicit submission
- no OAuth dependency
- commit after green tests

Before claiming the v1 vertical slice is ready:

```bash
pytest
python -m hollow_lodge.client.cli --help
```

Expected:

- all tests pass
- CLI help renders without connecting to a server

## Plan Coverage Check

This roadmap covers the approved spec requirements:

- naming and starter campaign through Milestones 4 and 10
- invite-code identity through Milestone 2
- central authoritative Eventloom through Milestone 1
- local perspective Eventloom through Milestone 9
- first-party brokered chat through Milestone 3
- contract seed assets through Milestone 4
- freeform-first hybrid actions through Milestone 6
- Handler bounds through Milestones 5, 6, and 9
- proof dossiers and Packet Lead through Milestone 7
- proof scoring and phase result through Milestone 8
- cross-crew targeted proof interaction through Milestones 3, 5, and 10
- heat/noise through Milestones 6 and 8
- starter walkthrough through Milestone 10

The roadmap intentionally defers OAuth, NPC crews, territory, direct sabotage,
voice chat, full advancement trees, and real model-backed Oracle generation.
