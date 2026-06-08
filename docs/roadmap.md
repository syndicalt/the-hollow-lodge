# The Hollow Lodge Development Roadmap

This roadmap tracks the path from the current prototype to a playable, hosted
alpha. It is organized around player-visible release gates, not backend
subsystems. A milestone is complete only when its proof gate has been exercised
from the point of view of a player using Codex plus the Hollow Lodge MCP tools.

## Current Baseline

The repo already contains the core shape of the game:

- Authoritative FastAPI server with invite registration, crews, brokered chat,
  contracts, artifacts, proofs, actions, deals, event sync, and health routes.
- Append-only JSONL event log with visibility filtering.
- CLI client with onboarding, crew creation and join, chat, contract board,
  inbox, crew board, artifacts, artifact transfer, local sync/replay, freeform
  actions, proof dossier commands, Packet Lead votes, and escrowed deal
  commands.
- Codex MCP server with read surfaces for inbox, contract board, crew board,
  artifacts, artifact detail, visible deals, and deal-acceptance previews.
- Deterministic and OpenAI-backed resolution oracle boundary.
- End-to-end tests for the artifact loop, phase resolution, Codex render
  surfaces, and escrowed artifact deals.

The next work should harden the actual game loop before expanding content.

## Roadmap Principles

- Keep the game playable inside Codex. Shell commands may exist, but important
  state must be visible through MCP render packets.
- Server state is authoritative. Local logs are player perspective caches, not
  sources of truth.
- Freeform actions remain agent-native, but the local agent clarifies
  consequences and translates intent; it does not choose strategy by default.
- Mutations must be explicit and confirmation-oriented. Read-only previews are
  preferred before irreversible actions.
- Use deterministic implementations as test or fallback paths for model-backed
  behavior.
- Add content through data and contract seeds rather than hard-coded branches.
- No reward hacking: tests must prove player-facing behavior or server
  invariants, not implementation trivia.

## Milestone 1: Playable Alpha Loop

Goal: a fresh player can enter from Codex and complete one contested contract
loop with a crew.

Scope:

- Render a useful "what is happening now" landing state inside Codex.
- Make every major player object visible in MCP: inbox, contract board, crew
  board, artifacts, artifact detail, visible deals, deal preview, and the
  relevant pending decisions.
- Keep CLI and MCP read surfaces aligned.
- Preview consequences for irreversible operations before execution.
- Document a complete two-crew playthrough that can be run against a local
  server.

Proof gate:

- Starting with a clean local data directory, create two crews, inspect the
  starter contract, inspect artifacts, exchange brokered messages, propose and
  accept an escrowed artifact deal, submit a freeform action, contribute to a
  dossier, resolve the auction preview phase, and render the final state inside
  Codex-facing packets.

Likely files:

- `src/hollow_lodge/client/codex_session.py`
- `src/hollow_lodge/client/render_packets.py`
- `src/hollow_lodge/mcp_server.py`
- `src/hollow_lodge/client/cli.py`
- `scripts/mock_full_game_loop.py`
- `tests/e2e/test_full_game_loop_with_escrow.py`
- `tests/e2e/test_codex_render_surfaces.py`
- `tests/client/test_codex_session.py`
- `tests/test_mcp_server.py`

## Milestone 2: Crew Coordination

Goal: asynchronous crew play is legible without leaving the Codex session.

Scope:

- Add a crew activity timeline that summarizes visible crew-relevant events.
- Render brokered conversation threads through MCP, not only CLI.
- Surface incoming and outgoing deals as pending crew decisions.
- Make Packet Lead status, votes, and replacement history visible.
- Improve dossier display so claims, evidence, artifact citations,
  contributions, weaknesses, and provenance concerns are easy to scan.

Proof gate:

- A player can ask Codex what changed since their last sync and receive a
  visibility-scoped activity summary with concrete next actions.

Likely files:

- `src/hollow_lodge/client/codex_session.py`
- `src/hollow_lodge/client/render_packets.py`
- `src/hollow_lodge/mcp_server.py`
- `src/hollow_lodge/server/projections.py`
- `src/hollow_lodge/server/services.py`
- `tests/client/test_codex_session.py`
- `tests/client/test_render_packets.py`
- `tests/server/test_chat_routes.py`
- `tests/server/test_packet_lead.py`

## Milestone 3: Game Master And Oracle Maturity

Goal: phase resolution feels like bounded game-master output, not a raw model
response.

Scope:

- Harden oracle prompts and output schemas.
- Keep server truth, player reveal text, and agent context separate.
- Persist oracle audit records that explain inputs, provider, fallback, and
  validation outcomes.
- Guarantee deterministic fallback on provider error, timeout, unsafe reveal
  text, or invalid model output.
- Reveal score reasoning after resolution without exposing hidden server-only
  graph data.

Proof gate:

- The same phase can be resolved under deterministic and model-backed oracle
  providers, both producing validated standings, player-safe reveal text, and
  audit evidence.

Likely files:

- `src/hollow_lodge/workflows/oracle_boundary.py`
- `src/hollow_lodge/workflows/openai_oracle.py`
- `src/hollow_lodge/workflows/deterministic_oracle.py`
- `src/hollow_lodge/workflows/oracle_factory.py`
- `src/hollow_lodge/server/services.py`
- `tests/workflows/test_openai_oracle.py`
- `tests/workflows/test_oracle_boundary.py`
- `tests/server/test_resolution_oracle.py`

## Milestone 4: Contract Content Pipeline

Goal: add and operate new contracts without changing core server logic.

Scope:

- Define a contract seed format for campaigns, phases, dossier needs, hidden
  evidence graph nodes, visible starting artifacts, unlock rules, and scoring
  hints.
- Add validation for seed files before they are activated.
- Add an admin command to seed or activate a contract.
- Track contract lifecycle: draft, active, resolving, archived.
- Keep mock simulations for every shipped contract.

Proof gate:

- A second contract can be added as data, activated on a local server, played
  through a smoke simulation, and rendered through existing Codex surfaces.

Likely files:

- `src/hollow_lodge/server/seed_data.py`
- `src/hollow_lodge/server/artifact_seed.py`
- `src/hollow_lodge/server/artifact_unlocks.py`
- `src/hollow_lodge/server/routes_contracts.py`
- `src/hollow_lodge/client/cli.py`
- `tests/server/test_contract_seed.py`
- `tests/server/test_artifact_seed.py`
- `tests/e2e/test_saints_and_ledgers_preview.py`

## Milestone 5: Production Operations

Goal: real users can install, onboard, and play against the hosted server
without manual intervention from the developer.

Scope:

- Validate required server environment variables at startup.
- Make data directory and event-log paths explicit in health or diagnostics.
- Add admin commands for invite inventory, key-request approval, and basic
  player lookup.
- Add event-log integrity verification and documented backup/export commands.
- Restore the public installer path only when hosted onboarding is reliable.
- Add deployment documentation for `www.thehollowlodge.com` and
  `server.thehollowlodge.com`.

Proof gate:

- A clean machine can install the CLI from the site, request or redeem access,
  register MCP, and render the inbox against the hosted server.

Likely files:

- `src/hollow_lodge/server/app.py`
- `src/hollow_lodge/server/auth.py`
- `src/hollow_lodge/server/routes_identity.py`
- `src/hollow_lodge/eventlog/jsonl_store.py`
- `src/hollow_lodge/client/cli.py`
- `site/index.html`
- `site/install.sh`
- `scripts/install.sh`
- `tests/server/test_app_config.py`
- `tests/server/test_identity_routes.py`
- `tests/client/test_installer_script.py`

## Milestone 6: Retention And Campaign Layer

Goal: prior play changes future opportunities.

Scope:

- Add persistent player profile and crew history.
- Track crew heat, reputation, contract outcomes, scars, favors, and debts.
- Introduce multi-day campaign arcs that build on shorter contracts.
- Add contract unlocks based on prior outcomes.
- Keep death or legacy consequences mechanically valuable without making one
  bad result erase all progress.

Proof gate:

- Completing a contract changes later visible opportunities or risks for that
  crew.

Likely files:

- `src/hollow_lodge/domain/identity.py`
- `src/hollow_lodge/domain/crews.py`
- `src/hollow_lodge/domain/contracts.py`
- `src/hollow_lodge/server/projections.py`
- `src/hollow_lodge/server/services.py`
- `tests/domain/test_scoring.py`
- `tests/server/test_phase_resolution.py`

## Milestone 7: Social Pressure And Leaky Secrets

Goal: opportunism is possible, but the system gives players ways to detect,
respond, and remember.

Scope:

- Add private-message leak mechanics as system pressure, not arbitrary GM fiat.
- Track rumor fragments and discovered private arrangements.
- Connect deal reputation to future contract and crew-board context.
- Keep escrowed artifact swaps reliable; betrayal should live in soft terms,
  leaks, omissions, and timing, not broken trade plumbing.

Proof gate:

- A private arrangement can become partially discoverable through game
  mechanics, while artifact escrow still resolves reliably.

Likely files:

- `src/hollow_lodge/domain/chat.py`
- `src/hollow_lodge/domain/deals.py`
- `src/hollow_lodge/eventlog/visibility.py`
- `src/hollow_lodge/server/routes_chat.py`
- `src/hollow_lodge/server/deal_service.py`
- `tests/eventlog/test_visibility.py`
- `tests/server/test_chat_routes.py`
- `tests/server/test_deal_service.py`

## Immediate Execution Queue

### Slice 1: Playable Alpha Audit And Script

Create a repeatable local playthrough script or test that exercises the
Milestone 1 proof gate and renders the resulting Codex packets. This should
identify missing MCP tools or awkward player-facing output before adding more
mechanics.

Expected verification:

- `pytest tests/e2e/test_full_game_loop_with_escrow.py tests/e2e/test_codex_render_surfaces.py -q`
- A script or test output that shows the timeline of player-visible artifacts,
  deals, actions, dossier state, and resolution.

### Slice 2: Codex Activity And Thread Rendering

Add MCP render tools for conversation threads and a visibility-scoped activity
summary. The player should be able to ask what changed without reading raw
event replay.

Expected verification:

- `pytest tests/client/test_codex_session.py tests/test_mcp_server.py tests/client/test_render_packets.py -q`
- `pytest tests/server/test_chat_routes.py -q`

### Slice 3: Pending Decisions

Add a shared pending-decision projection used by inbox and crew board packets.
Deals, packet-lead votes, incomplete dossier needs, and unresolved action
opportunities should appear as concrete decision prompts.

Expected verification:

- `pytest tests/client/test_render_packets.py tests/client/test_contract_board.py tests/client/test_deal_cli.py -q`
- `pytest tests/server/test_crew_routes.py tests/server/test_deal_routes.py tests/server/test_packet_lead.py -q`

### Slice 4: Production Diagnostics

Add server diagnostics that expose provider, data-dir, event-log status, and
oracle readiness without leaking secrets. Add config validation for missing or
inconsistent production env.

Expected verification:

- `pytest tests/server/test_app_config.py tests/workflows/test_oracle_factory.py -q`

### Slice 5: Admin Onboarding Completion

Complete the access-key request flow with approval and invite creation, then
update the installer/site text when the hosted path is actually usable.

Expected verification:

- `pytest tests/server/test_identity_routes.py tests/client/test_installer_script.py -q`

## Completion Standard

Each slice must:

- Start with failing tests for the player-visible behavior or server invariant.
- Preserve existing CLI and MCP behavior unless the roadmap explicitly changes
  it.
- Commit in small, reviewable units.
- Run focused tests and the full suite before claiming completion.
- Update this roadmap when scope changes or a milestone proof gate is satisfied.
