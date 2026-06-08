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

Status:

- First activation/rendering slice completed: a second data-defined contract can
  be validated, activated by admin command/API, shown on Codex contract-board
  and inbox surfaces, and expose only its public starting artifact.
- Second-contract phase-resolution smoke completed: `The Ash Window` can be
  activated as data, unlock its own hidden artifact through a crew action,
  resolve its phase through the existing lock route, and render the resolved
  state through Codex surfaces.
- Deferred: richer lifecycle transitions beyond activation/resolution, generic
  phase reward configuration, and full smoke playthroughs for every future
  shipped contract.

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

Status:

- First retention slice completed: resolved contract standings now project into
  crew legacy, visible crew-board reputation/heat/favor/debt state, and
  deterministic future opportunity modifiers on unresolved contracts.
- Deferred: explicit legacy-delta events, multi-day campaign arc authoring,
  scars/death/legacy inheritance, and unlockable contracts based on long-term
  history.

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

Status:

- First social-pressure slice completed: brokered artifact deal proposals now
  emit redacted `contract.rumor.leaked` events to nonparticipant crews, visible
  in recent activity and crew boards without exposing artifact IDs, soft terms,
  player IDs, or deal acceptance state.
- Second social-pressure slice completed: crew-to-crew chat messages that
  attach explicit artifact references now emit redacted system-pressure rumors
  to nonparticipant crews, without exposing message text, artifact IDs, or
  player IDs.
- Third social-pressure slice completed: visible rumors from deals or chat now
  create `rumor_response` pending decisions in inbox and crew board surfaces,
  so players can respond from Codex without hunting through raw activity.
- Fourth social-pressure slice completed: confirmed crew actions can now
  reference a visible rumor, clearing that rumor's pending response while
  preserving the action cost, confirmation, phase lock, and crew-scoped audit
  trail.
- Escrowed deal acceptance remains participant-scoped and server-enforced.
- Deferred: freeform chat body pressure scanning, reputation consequences for
  deal conduct, richer cleanup/counterintelligence effects, and richer rumor
  verification outcomes.

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

Status: completed in `206b8a2`.

Create a repeatable local playthrough script or test that exercises the
Milestone 1 proof gate and renders the resulting Codex packets. This should
identify missing MCP tools or awkward player-facing output before adding more
mechanics.

Expected verification:

- `pytest tests/e2e/test_full_game_loop_with_escrow.py tests/e2e/test_codex_render_surfaces.py -q`
- A script or test output that shows the timeline of player-visible artifacts,
  deals, actions, dossier state, and resolution.

### Slice 2: Codex Activity And Thread Rendering

Status: completed in `2ad3631`.

Add MCP render tools for conversation threads and a visibility-scoped activity
summary. The player should be able to ask what changed without reading raw
event replay.

Expected verification:

- `pytest tests/client/test_codex_session.py tests/test_mcp_server.py tests/client/test_render_packets.py -q`
- `pytest tests/server/test_chat_routes.py -q`

### Slice 3: Pending Decisions

Status: completed in `cb35474` and refined in `809f3d7`.

Add a shared pending-decision projection used by inbox and crew board packets.
Deals, packet-lead votes, incomplete dossier needs, and unresolved action
opportunities should appear as concrete decision prompts.

Expected verification:

- `pytest tests/client/test_render_packets.py tests/client/test_contract_board.py tests/client/test_deal_cli.py -q`
- `pytest tests/server/test_crew_routes.py tests/server/test_deal_routes.py tests/server/test_packet_lead.py -q`

### Slice 4: Production Diagnostics

Status: completed in `9a17c8d`.

Add server diagnostics that expose provider, data-dir, event-log status, and
oracle readiness without leaking secrets. Add config validation for missing or
inconsistent production env.

Expected verification:

- `pytest tests/server/test_app_config.py tests/workflows/test_oracle_factory.py -q`

### Slice 5: Admin Onboarding Completion

Status: completed in `9be279b`.

Complete the access-key request flow with approval and invite creation, then
update the installer/site text when the hosted path is actually usable.

Expected verification:

- `pytest tests/server/test_identity_routes.py tests/client/test_installer_script.py -q`

### Slice 6: Codex-Native Confirmed Mutations

Status: completed in `6383c18`.

Add MCP tools for the confirmed, irreversible actions required by the alpha
loop. These tools must remain explicit and confirmation-oriented: the agent can
translate player intent and submit the command only after the player has
approved the concrete consequence summary.

Initial tool set:

- `submit_action`
- `dossier_contribute`
- `dossier_cite_artifact`
- `propose_deal`
- `accept_deal`
- `transfer_artifact`
- `vote_packet_lead`

Expected verification:

- `pytest tests/client/test_codex_session.py tests/test_mcp_server.py -q`
- `pytest tests/e2e/test_codex_render_surfaces.py tests/e2e/test_full_game_loop_with_escrow.py -q`

### Slice 7: CLI Reachability Gaps

Status: completed in `b48170f`.

Expose server-supported operations that are currently hard to reach from the
CLI: proof fragment transfer, artifact dossier citation, full dossier framing
fields, action edit/cancel, and phase lock/resolve preview.

Expected verification:

- `pytest tests/client/test_cli_commands.py tests/client/test_dossier_cli.py -q`
- `pytest tests/server/test_action_routes.py tests/server/test_phase_resolution.py -q`

### Slice 8: Contract Seed Activation

Status: completed.

Add the first Milestone 4 content pipeline slice: validate a structured
contract seed, activate it through an admin API/CLI path, append normal
event-log lifecycle events, render the second contract through existing Codex
surfaces, and keep hidden truth/artifact graph internals server-only.

Expected verification:

- `pytest tests/server/test_contract_seed_pipeline.py tests/server/test_contract_seed.py tests/server/test_artifact_routes.py -q`
- `pytest tests/client/test_cli_commands.py tests/client/test_api.py -q`
- `pytest tests/e2e/test_codex_render_surfaces.py -q`

### Slice 9: Seeded Contract Resolution Smoke

Status: completed.

Generalize the starter phase-resolution path enough for an activated contract
seed to play through a short loop: action unlocks use the seed's artifact graph,
oracle packets use the seed's hidden truth, artifact graph, scoring hints, and
phase name, and Codex contract-board rendering shows the public resolved state.

Expected verification:

- `pytest tests/server/test_phase_resolution.py tests/server/test_action_routes.py tests/server/test_artifact_routes.py -q`
- `pytest tests/e2e/test_contract_content_pipeline.py -q`

### Slice 10: Crew Legacy And Future Modifiers

Status: completed.

Add the first Milestone 6 retention slice: derive crew legacy from resolved
phase standings, surface reputation/heat/favors/debts/completed contracts on
the Codex crew board, and annotate later active contracts with deterministic
opportunity and risk modifiers.

Expected verification:

- `pytest tests/server/test_crew_legacy_projection.py tests/server/test_crew_routes.py -q`
- `pytest tests/client/test_render_packets.py tests/e2e/test_contract_content_pipeline.py -q`

### Slice 11: Chat-Originated Rumor Pressure

Status: completed.

Extend Milestone 7 system pressure beyond brokered deals: when a private
crew-to-crew chat includes explicit artifact references, emit a redacted rumor
event to nonparticipant crews. The rumor should identify only the pressure
category, source event, conversation scope, and suspected crews. It must not
copy private message bodies, artifact IDs, artifact titles, player IDs, or
instructions from the chat.

Expected verification:

- `pytest tests/server/test_chat_routes.py tests/client/test_render_packets.py -q`
- `pytest -q`

### Slice 12: Actionable Rumor Decisions

Status: completed.

Make existing leak pressure actionable in Codex: any visible redacted rumor can
produce a `rumor_response` pending decision for the bystander crew. The decision
appears in both the crew board and personal inbox, uses only sanitized rumor
fields, and points the player toward verification, ignoring, or answering with a
crew action. This slice does not add a new cleanup mutation yet.

Expected verification:

- `pytest tests/server/test_chat_routes.py tests/server/test_deal_routes.py tests/server/test_crew_routes.py tests/client/test_render_packets.py -q`
- `pytest -q`

### Slice 13: Rumor-Linked Crew Actions

Status: completed.

Let a confirmed freeform crew action answer a visible rumor by passing a
structured `rumor_id`. The server validates that the rumor is visible to the
acting crew, stores only `responds_to_rumor_id` on the submitted action, and
clears the related `rumor_response` pending decision by projection. Canceling
the action reopens the decision naturally.

Expected verification:

- `pytest tests/server/test_action_routes.py tests/client/test_api.py tests/client/test_codex_session.py tests/test_mcp_server.py tests/client/test_action_cli.py tests/client/test_render_packets.py -q`
- `pytest -q`

## Completion Standard

Each slice must:

- Start with failing tests for the player-visible behavior or server invariant.
- Preserve existing CLI and MCP behavior unless the roadmap explicitly changes
  it.
- Commit in small, reviewable units.
- Run focused tests and the full suite before claiming completion.
- Update this roadmap when scope changes or a milestone proof gate is satisfied.
