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
- First lifecycle transition slice completed: admins can archive contracts
  through an idempotent lifecycle event; archived contracts remain visible on
  the contract board as archived history but leave active inbox and crew-board
  work queues.
- Generic phase reward configuration completed: contract seeds can define
  server-only phase-resolution rewards that grant configured follow-up
  artifacts to the phase leader without hard-coding a contract-specific branch.
- Deferred: full smoke playthroughs for every future shipped contract.

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

Status:

- Production diagnostics, hosted deployment docs, installer path, access-key
  request approval, invite inventory, event-log verify/export, and admin
  player lookup are implemented.
- Admin player detail lookup completed: admins can inspect one player's
  sanitized status and crew memberships without exposing tokens, token hashes,
  invite hashes, raw invite codes, or crew join codes.

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
- Explicit legacy-delta events completed: phase resolution now records
  sanitized public `crew.legacy.delta.recorded` events for each standing, and
  crew legacy projections prefer those auditable events while preserving
  derived fallback for older logs.
- Data-defined contract unlocks completed: contract seeds can declare
  server-only crew legacy requirements, and Codex contract boards show safe
  locked/unlocked status while inbox and crew-board work queues omit locked
  contracts until the crew qualifies.
- Public campaign arc metadata completed: contract seeds can now declare
  player-safe arc id, title, chapter, sequence, summary, previous-contract
  links, and next hints that render through Codex contract and crew boards
  without mixing arc presentation with hidden truth or unlock mechanics.
- Scar burden modifiers completed: weak outcomes now leave named scars visible
  on Codex crew boards and add deterministic future risk modifiers on unresolved
  contracts without exposing hidden resolution data.
- Arc continuity validation completed: contract seed activation now rejects
  public arc links whose previous contract is not already published in the same
  campaign, preventing broken multi-contract campaign chains before seed events
  are appended.
- Completed-contract unlocks completed: contract seeds can now require a crew
  to have completed a specific prior contract, with safe crew-scoped
  `unlock_status` projection and no raw unlock requirements in visible events.
- Campaign arc progress rendering completed: Codex contract boards now summarize
  visible arc progress across chapters with safe resolved, active, locked, and
  archived counts before the per-contract details.
- Deferred: multi-day campaign arc authoring, deeper death/legacy inheritance,
  and richer long-term unlock paths.

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
- Fifth social-pressure slice completed: rumor-linked crew actions now append a
  crew-visible `contract.rumor.responded` outcome event, giving players a
  sanitized activity record that an investigation or answer has started without
  revealing private chat bodies, artifact IDs, deal terms, or participant-only
  details.
- Sixth social-pressure slice completed: rumor-linked actions now support an
  explicit response mode. The default `investigate` path preserves prior
  behavior, while deliberate `contain` counterintelligence records a sanitized
  containment outcome and adds a visible crew heat cost.
- Seventh social-pressure slice completed: investigate-mode rumor responses
  now append a crew-visible `contract.rumor.verified` event with a bounded
  assessment, confidence, and summary, giving the investigating crew a result
  trail without exposing private message bodies, artifact IDs, deal terms,
  suspected crew IDs, or participant-only details.
- Eighth social-pressure slice completed: verified rumor results now feed a
  crew-scoped long-term `rumor_memory` projection and Codex crew-board render
  block, preserving assessment counts and recent safe summaries without
  carrying source IDs, private message bodies, artifact IDs, deal terms, or
  suspected crew IDs into legacy context.
- Ninth social-pressure slice completed: repeated credible rumor verification
  results now create a safe `rumor_escalation` pending decision in Codex inbox
  and crew-board surfaces, using only aggregate assessment counts so players
  can decide whether to contain, exploit, or fold the pattern into contract
  strategy.
- Tenth social-pressure slice completed: confirmed freeform crew actions can
  now answer repeated credible rumor escalation prompts with a bounded
  contain, exploit, or integrate mode. The server validates the current
  aggregate signal, records only safe action fields, appends a sanitized
  `contract.rumor.escalated` event, and clears or reopens the pending decision
  based on submitted/canceled action state.
- Eleventh social-pressure slice completed: rumor escalation follow-through
  now feeds crew legacy and future contract modifiers. Crew boards show only
  bounded contain, exploit, integrate, and credible-signal counts, while
  exploit follow-through creates a capped `rumor_exploitation` modifier for
  active unresolved contracts without exposing source IDs, private message
  bodies, artifact IDs, deal terms, or suspected crews.
- Escrowed deal acceptance remains participant-scoped and server-enforced.
- Deferred: richer rumor verification sources and deeper long-term
  consequences from repeated credible signal follow-through.

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

### Slice 14: Oracle Audit Schema Hardening

Status: completed.

Tighten Milestone 3 operator evidence without widening player visibility:
oracle resolution now writes versioned server-only audit records with attempted
provider metadata, validation status, failure stage/type, deterministic fallback
classification, safe summary counts, and an accepted-output hash. Existing
pre-schema audit records remain replayable so recovery does not duplicate or
conflict with prior requested/failed audit events.

Expected verification:

- `pytest tests/server/test_phase_resolution.py tests/server/test_resolution_oracle.py tests/workflows/test_oracle_boundary.py tests/workflows/test_deterministic_oracle.py tests/workflows/test_openai_oracle.py tests/workflows/test_oracle_factory.py -q`
- `pytest -q`

### Slice 15: Player-Safe Score Reasoning

Status: completed.

Expose validated post-resolution score reasoning in Codex-facing contract board
packets without projecting oracle inputs, server-only audit records, hidden
truth, or artifact graph internals. Render packets now map each resolved
standing's public strengths, weaknesses, penalties, and revealed clues into a
bounded `score_reasoning` object, and contract-board markdown shows a compact
Reasoning section under each standing.

Expected verification:

- `pytest tests/client/test_render_packets.py tests/client/test_phase_render.py tests/e2e/test_contract_content_pipeline.py -q`
- `pytest -q`

### Slice 16: Deal Conduct Reputation

Status: completed.

Connect reliable escrowed deal conduct to crew-board legacy and future contract
context without modeling soft-term betrayal. Crew legacy now includes a
participant-scoped `deal_conduct` aggregate derived only from server-verifiable
deal lifecycle facts: fulfilled deals add reliability, proposer-canceled deals
cost reliability, declined and open deals are counted but not penalized. Future
contract modifiers can now include `deal_reliability`, while legacy/render
packets omit artifact IDs, deal copy IDs, soft terms, and rumor-derived claims.

Expected verification:

- `pytest tests/server/test_crew_legacy_projection.py tests/server/test_crew_routes.py tests/server/test_deal_service.py tests/client/test_render_packets.py tests/e2e/test_escrowed_artifact_deals.py tests/e2e/test_full_game_loop_with_escrow.py -q`
- `pytest -q`

### Slice 17: Chat Body Rumor Pressure

Status: completed.

Extend leaky private-message pressure beyond explicit `artifact_ids`: a
crew-to-crew message that names an artifact visible to the sender by ID or
title now emits the same redacted system-pressure rumor to nonparticipant
crews. The scanner is deterministic and bounded to visible artifacts, and the
rumor payload still omits message body text, artifact IDs, artifact titles,
player IDs, and participant-only deal state.

Expected verification:

- `pytest tests/server/test_chat_routes.py tests/server/test_crew_routes.py tests/client/test_render_packets.py -q`
- `pytest -q`

### Slice 18: Rumor Response Outcomes

Status: completed.

Make rumor-linked crew actions leave a player-visible result trail: after a
confirmed action references a visible rumor, the server now appends a
crew-visible `contract.rumor.responded` event that records the action, source
rumor, pressure category, optional contract id, and a sanitized outcome summary.
Codex activity packets render the outcome while omitting private chat bodies,
artifact IDs, artifact titles, deal terms, participant-only deal state, and
hidden server context.

Expected verification:

- `pytest tests/server/test_action_routes.py tests/client/test_render_packets.py tests/client/test_codex_session.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 19: Deliberate Rumor Containment

Status: completed.

Add an explicit `rumor_response_mode` to rumor-linked crew actions. Existing
calls default to `investigate`; a confirmed action with
`rumor_response_mode=contain` records a sanitized `containment_started` rumor
response, adds a bounded crew heat cost, and surfaces counterintelligence
counts on the crew board. CLI, Codex session, MCP, and API mutation paths all
pass the mode through explicitly while preserving confirmation-first behavior.

Expected verification:

- `pytest tests/server/test_action_routes.py tests/server/test_crew_routes.py tests/server/test_crew_legacy_projection.py -q`
- `pytest tests/client/test_api.py tests/client/test_codex_session.py tests/client/test_action_cli.py tests/client/test_render_packets.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 20: Contract Archive Lifecycle

Status: completed.

Add the first post-activation contract lifecycle transition. Admins can archive
a contract through an idempotent `contract.lifecycle.changed` event. Archived
contracts stay visible on the contract board with `lifecycle_status=archived`,
while inbox and crew-board active work queues exclude them so players are not
prompted to keep acting on completed or retired work.

Expected verification:

- `pytest tests/server/test_contract_seed.py tests/server/test_contract_seed_pipeline.py tests/server/test_crew_routes.py tests/server/test_phase_resolution.py -q`
- `pytest tests/client/test_api.py tests/client/test_cli_commands.py tests/client/test_render_packets.py tests/client/test_contract_board.py tests/e2e/test_contract_content_pipeline.py tests/e2e/test_codex_render_surfaces.py -q`
- `pytest -q`

### Slice 21: Data-Defined Phase Rewards

Status: completed.

Move phase-resolution artifact rewards into contract seed configuration. Seeded
contracts can now define server-only `phase_rewards` that award a configured
artifact to the standing leader when the phase resolves. The server persists
the reward rules with the server-only artifact graph payload, validates reward
artifact references at seed load time, keeps legacy starter reward behavior
compatible, and preserves idempotent crew-scoped artifact grants.

Expected verification:

- `pytest tests/server/test_contract_seed_pipeline.py tests/server/test_phase_artifact_rewards.py -q`
- `pytest tests/server/test_phase_resolution.py tests/server/test_action_routes.py tests/server/test_artifact_routes.py tests/e2e/test_contract_content_pipeline.py -q`
- `pytest -q`

### Slice 22: Explicit Legacy Delta Events

Status: completed.

Record auditable crew legacy changes when a phase resolves. Each public
`crew.legacy.delta.recorded` event contains only sanitized contract, phase,
standing, score, outcome, and legacy delta fields. Crew legacy projection now
prefers explicit delta events when present and falls back to derived standings
for older logs, avoiding double counting. Codex activity packets and local
replay render the new event as a human-readable legacy update.

Expected verification:

- `pytest tests/server/test_phase_resolution.py::test_phase_resolution_records_public_legacy_delta_events_for_each_standing tests/server/test_phase_resolution.py::test_phase_lock_replay_and_duplicate_lock_do_not_append_duplicate_reveals tests/server/test_crew_legacy_projection.py tests/server/test_crew_routes.py::test_crew_board_legacy_changes_future_contract_risk_and_opportunity tests/client/test_render_packets.py::test_activity_summary_packet_shapes_visible_events_without_server_only_fields tests/client/test_local_log.py::test_local_log_tracks_max_server_sequence_and_replays_visible_events -q`
- `pytest tests/server/test_phase_resolution.py tests/server/test_crew_legacy_projection.py tests/server/test_crew_routes.py tests/client/test_render_packets.py tests/client/test_local_log.py tests/e2e/test_contract_content_pipeline.py -q`
- `pytest -q`

### Slice 23: Admin Player Detail Lookup

Status: completed.

Make hosted onboarding operations easier without exposing auth material.
Admins can now request sanitized detail for a single registered player through
`GET /identity/admin/players/{player_id}` and
`hollow-lodge admin player <player_id>`. The response includes player id,
display name, token revocation state, crew ids, and crew count, while omitting
tokens, token hashes, invite hashes, raw invite codes, and crew join codes.

Expected verification:

- `pytest tests/server/test_identity_routes.py::test_admin_player_detail_lookup_returns_crews_without_auth_material tests/client/test_api.py::test_api_gets_admin_player_detail_with_admin_token tests/client/test_cli_commands.py::test_admin_player_command_shows_sanitized_player_detail -q`
- `pytest tests/server/test_identity_routes.py tests/client/test_api.py tests/client/test_cli_commands.py tests/client/test_installer_script.py -q`
- `pytest -q`

### Slice 24: Rumor Verification Results

Status: completed.

Give investigate-mode rumor responses a bounded result trail. When a confirmed
rumor-linked action uses the default `investigate` mode, the server now appends
a crew-visible `contract.rumor.verified` event with a deterministic assessment,
confidence, and player-safe summary. Containment remains containment-only. The
activity packet renders the verification while omitting private chat bodies,
artifact IDs, artifact titles, deal terms, suspected crew IDs, participant-only
state, and hidden server context.

Expected verification:

- `pytest tests/server/test_action_routes.py::test_investigating_rumor_appends_sanitized_verification_result tests/server/test_action_routes.py::test_rumor_action_can_start_containment_with_visible_heat_cost tests/server/test_action_routes.py::test_rumor_action_replay_checks_rumor_reference_and_cancel_reopens_decision -q`
- `pytest tests/client/test_render_packets.py::test_activity_summary_packet_shapes_visible_events_without_server_only_fields -q`
- `pytest tests/server/test_action_routes.py tests/server/test_crew_routes.py tests/server/test_crew_legacy_projection.py -q`
- `pytest tests/client/test_render_packets.py tests/client/test_codex_session.py tests/test_mcp_server.py tests/client/test_action_cli.py tests/client/test_api.py -q`
- `pytest -q`

### Slice 25: Legacy-Gated Contract Unlocks

Status: completed.

Add data-defined contract unlock requirements for long-term crew progression.
Contract seeds can now define server-only crew legacy requirements using
positive-progress metrics such as reputation, favors, and deal conduct score.
The server stores raw requirements with the server-only artifact graph seed,
projects only safe `unlock_status` summaries onto player contract boards, and
keeps locked contracts out of inbox and crew-board actionable queues until the
crew qualifies. Activation replay now rejects idempotency-key reuse with
different seed-derived unlock payloads.

Expected verification:

- `pytest tests/server/test_contract_seed_pipeline.py::test_contract_seed_accepts_data_defined_unlock_requirements tests/server/test_contract_seed_pipeline.py::test_contract_seed_rejects_unsupported_unlock_metric tests/client/test_render_packets.py::test_contract_board_packet_renders_locked_contract_requirements -q`
- `pytest tests/server/test_contract_seed.py::test_legacy_locked_contract_is_visible_but_not_actionable_until_crew_qualifies tests/server/test_contract_seed.py::test_contract_activation_replay_rejects_different_unlock_requirements -q`
- `pytest tests/server/test_contract_seed_pipeline.py tests/server/test_contract_seed.py tests/server/test_crew_routes.py tests/server/test_crew_legacy_projection.py tests/server/test_phase_resolution.py -q`
- `pytest tests/client/test_render_packets.py tests/client/test_contract_board.py tests/e2e/test_contract_content_pipeline.py tests/e2e/test_codex_render_surfaces.py -q`
- `pytest -q`

### Slice 26: Public Campaign Arc Metadata

Status: completed.

Add the first multi-contract campaign authoring primitive. Contracts can now
carry a typed public `arc` object with arc id, title, chapter, sequence,
public summary, optional previous contract id, and optional next contract hint.
Arc metadata is stored on the public `contract.board.published` payload,
validated as presentation-only data, rendered through Codex contract boards,
and preserved through crew-board contract shaping. Hidden truth, unlock
requirements, and server-only notes remain outside arc metadata; unknown arc
fields are rejected at seed validation.

Expected verification:

- `pytest tests/server/test_contract_seed_pipeline.py::test_contract_seed_accepts_public_campaign_arc_metadata tests/server/test_contract_seed_pipeline.py::test_contract_seed_rejects_arc_previous_link_to_self tests/server/test_contract_seed_pipeline.py::test_contract_seed_rejects_unknown_arc_fields tests/server/test_contract_seed.py::test_contract_board_renders_public_campaign_arc_metadata tests/server/test_contract_seed.py::test_contract_activation_replay_rejects_different_arc_metadata tests/server/test_crew_routes.py::test_crew_board_shapes_contracts_and_dossier_at_server_boundary tests/client/test_render_packets.py::test_contract_board_packet_renders_campaign_arc_metadata_without_hidden_fields -q`
- `pytest tests/server/test_contract_seed_pipeline.py tests/server/test_contract_seed.py tests/server/test_crew_routes.py -q`
- `pytest tests/client/test_render_packets.py tests/client/test_contract_board.py tests/e2e/test_contract_content_pipeline.py tests/e2e/test_codex_render_surfaces.py -q`
- `pytest -q`

### Slice 27: Scar Burden Legacy Modifiers

Status: completed.

Make weak contract outcomes mechanically meaningful without adding permanent
death yet. Existing weak-result legacy deltas now surface their named scars on
Codex crew boards, and those scars add a safe `scar_burden` risk modifier to
future unresolved contracts. The modifier is deterministic and count-based, and
the render packet keeps hidden resolution data, server notes, private artifact
IDs, and soft deal terms out of player markdown and agent context.

Expected verification:

- `pytest tests/server/test_crew_legacy_projection.py::test_weak_outcome_creates_scar_burden_for_future_contracts tests/client/test_render_packets.py::test_crew_board_packet_renders_legacy_and_future_modifiers_without_hidden_fields -q`
- `pytest tests/server/test_crew_legacy_projection.py tests/server/test_crew_routes.py tests/client/test_render_packets.py tests/e2e/test_contract_content_pipeline.py -q`
- `pytest -q`

### Slice 28: Campaign Arc Continuity Validation

Status: completed.

Harden multi-contract campaign authoring by validating public arc links at
activation time. If a seed declares `contract.arc.previous_contract_id`, the
server now requires that contract to already be published in the same campaign
before appending any new seed events. Invalid links return a normal admin seed
validation error, while idempotent activation replay and existing public arc
rendering remain unchanged.

Expected verification:

- `pytest tests/server/test_contract_seed.py::test_contract_activation_rejects_arc_previous_contract_that_is_not_published tests/server/test_contract_seed.py::test_failed_arc_previous_validation_leaves_idempotency_key_reusable tests/server/test_contract_seed.py::test_contract_activation_rejects_arc_previous_contract_from_other_campaign -q`
- `pytest tests/server/test_contract_seed.py tests/server/test_contract_seed_pipeline.py tests/server/test_crew_routes.py::test_crew_board_shapes_contracts_and_dossier_at_server_boundary tests/client/test_render_packets.py::test_contract_board_packet_renders_campaign_arc_metadata_without_hidden_fields -q`
- `pytest -q`

### Slice 29: Completed-Contract Unlock Requirements

Status: completed.

Add the first contract-specific long-term unlock path. Contract seeds can now
declare a crew-scoped `completed_contract` unlock requirement with an explicit
`required_contract_id`. The server validates that target against already
published contracts in the same campaign, stores the raw requirement only in
server-only seed events, and projects a safe `unlock_status` with the target id,
current completion value, and satisfaction flag. Follow-up contracts stay out of
inbox and crew-board work queues until that specific crew has completed the
required prior contract.

Expected verification:

- `pytest tests/server/test_contract_seed_pipeline.py::test_contract_seed_accepts_completed_contract_unlock_requirement tests/server/test_contract_seed_pipeline.py::test_contract_seed_rejects_completed_contract_requirement_without_target tests/server/test_contract_seed_pipeline.py::test_contract_seed_rejects_zero_minimum_for_completed_contract_requirement tests/server/test_contract_seed_pipeline.py::test_contract_seed_rejects_required_contract_on_numeric_unlock_metric tests/server/test_contract_seed.py::test_completed_contract_unlock_requires_crew_completion_before_actionable tests/server/test_contract_seed.py::test_completed_contract_unlock_rejects_missing_required_contract tests/server/test_contract_seed.py::test_completed_contract_unlock_is_scoped_to_the_acting_crew tests/client/test_render_packets.py::test_contract_board_packet_renders_completed_contract_unlock_requirement -q`
- `pytest tests/server/test_contract_seed_pipeline.py tests/server/test_contract_seed.py tests/server/test_crew_routes.py tests/server/test_crew_legacy_projection.py tests/client/test_render_packets.py tests/e2e/test_contract_content_pipeline.py tests/e2e/test_codex_render_surfaces.py -q`
- `pytest -q`

### Slice 30: Codex Campaign Arc Progress

Status: completed.

Make multi-contract campaign arcs easier to scan inside Codex. Contract board
render packets now derive a player-safe `arc_progress` summary from public
contract arc metadata, lifecycle status, phase status, and unlock status. The
markdown shows each visible arc before individual contract sections with
resolved, active, locked, and archived counts plus ordered chapter lines. Agent
context receives the same compact derived summary without hidden truth, raw
unlock requirements, server notes, or phase-result internals.

Expected verification:

- `pytest tests/client/test_render_packets.py::test_contract_board_packet_renders_campaign_arc_progress_without_hidden_fields tests/client/test_render_packets.py::test_contract_board_arc_progress_counts_phase_locked_contracts tests/client/test_render_packets.py::test_contract_board_agent_context_omits_hidden_upstream_fields -q`
- `pytest tests/client/test_render_packets.py tests/client/test_contract_board.py tests/client/test_codex_session.py tests/test_mcp_server.py tests/e2e/test_codex_render_surfaces.py tests/e2e/test_contract_content_pipeline.py -q`
- `pytest -q`

### Slice 31: Crew Rumor Memory

Status: completed.

Turn verified rumor checks into durable crew context. The crew legacy projection
now derives a bounded `rumor_memory` aggregate from crew-scoped
`contract.rumor.verified` events, including verification count, assessment
counts, and recent player-safe summaries. Codex crew boards render that memory
near counterintelligence so players and local agents can see what the crew has
already verified, while omitting source IDs, private message bodies, artifact
IDs, deal terms, suspected crew IDs, and other upstream private fields.

Expected verification:

- `pytest tests/server/test_crew_legacy_projection.py::test_verified_rumors_create_safe_long_term_crew_memory tests/client/test_render_packets.py::test_crew_board_packet_renders_legacy_and_future_modifiers_without_hidden_fields tests/server/test_crew_routes.py::test_crew_board_legacy_remembers_verified_rumors_without_private_sources -q`
- `pytest tests/server/test_crew_legacy_projection.py tests/server/test_crew_routes.py tests/client/test_render_packets.py -q`
- `pytest -q`

### Slice 32: Credible Rumor Escalation Decisions

Status: completed.

Make repeated credible rumor checks actionable without exposing private
sources. Pending-decision projection now accepts optional crew legacy context
and creates a `rumor_escalation` decision when a crew has at least two
credible rumor verifications. Crew boards and inboxes pass safe crew legacy
into the projection, and Codex render packets preserve only aggregate
`credible_count` and `assessment_counts` for the decision while dropping source
IDs, private bodies, artifact IDs, deal terms, suspected crew IDs, and raw
verification recency.

Expected verification:

- `pytest tests/server/test_pending_decisions.py::test_repeated_credible_rumor_memory_creates_escalation_decision tests/server/test_crew_routes.py::test_repeated_credible_rumors_create_escalation_decision_on_boards tests/client/test_render_packets.py::test_crew_board_packet_shows_packet_lead_and_dossier_status tests/client/test_render_packets.py::test_inbox_packet_prioritizes_actionable_items_for_codex -q`
- `pytest tests/server/test_pending_decisions.py tests/server/test_crew_routes.py tests/server/test_chat_routes.py tests/server/test_deal_routes.py tests/client/test_render_packets.py -q`
- `pytest -q`

### Slice 33: Rumor Escalation Follow-Through Actions

Status: completed.

Close the loop on repeated credible rumor prompts. Confirmed freeform crew
actions can now include `responds_to_rumor_escalation` plus a bounded
`rumor_escalation_mode` of contain, exploit, or integrate. The server validates
that the acting crew currently has repeated credible rumor signals, stores only
the safe escalation response fields on the submitted action, appends a
crew-visible `contract.rumor.escalated` outcome event with aggregate counts and
summary, and lets cancellation reopen the escalation decision. API, Codex
session, MCP, and CLI paths pass the fields explicitly, while render packets
keep private source IDs, message bodies, artifact IDs, deal terms, suspected
crew IDs, and verification recency out of mutation and activity surfaces.

Expected verification:

- `pytest tests/server/test_action_routes.py::test_rumor_escalation_action_records_safe_outcome_and_reopens_after_cancel tests/server/test_action_routes.py::test_rumor_escalation_action_requires_current_credible_escalation tests/server/test_pending_decisions.py::test_submitted_rumor_escalation_action_clears_escalation_decision tests/client/test_render_packets.py::test_submit_action_mutation_result_includes_safe_rumor_response_mode tests/client/test_render_packets.py::test_activity_summary_packet_shapes_visible_events_without_server_only_fields tests/client/test_api.py::test_api_submits_action_with_rumor_reference tests/client/test_codex_session.py::test_codex_session_preview_submit_action_does_not_call_mutating_api tests/client/test_codex_session.py::test_codex_session_confirm_submit_action_calls_api_with_active_crew tests/test_mcp_server.py::test_submit_action_mcp_call_passes_confirmation_to_session tests/client/test_action_cli.py::test_act_command_confirms_and_submits -q`
- `pytest tests/server/test_action_routes.py tests/server/test_pending_decisions.py tests/server/test_crew_routes.py tests/client/test_api.py tests/client/test_codex_session.py tests/client/test_action_cli.py tests/test_mcp_server.py tests/client/test_render_packets.py -q`
- `pytest -q`

### Slice 34: Rumor Escalation Legacy Consequences

Status: completed.

Make repeated credible rumor follow-through matter after the immediate
decision clears. The crew legacy projection now derives a bounded
`rumor_escalation` aggregate from crew-scoped `contract.rumor.escalated`
events, counting contain, exploit, integrate, and total credible signal weight
without carrying raw source fields. Exploit follow-through creates a capped
`rumor_exploitation` future modifier for active unresolved contracts, and
Codex crew boards render the aggregate beside rumor memory so players and
local agents can understand the strategic footprint without seeing private
message bodies, artifact IDs, deal terms, source IDs, or suspected crew IDs.

Expected verification:

- `pytest tests/server/test_crew_legacy_projection.py tests/client/test_render_packets.py::test_crew_board_packet_renders_legacy_and_future_modifiers_without_hidden_fields tests/server/test_crew_routes.py::test_crew_board_projects_rumor_escalation_legacy_and_future_modifier -q`
- `pytest tests/server/test_crew_legacy_projection.py tests/server/test_crew_routes.py tests/server/test_action_routes.py tests/client/test_render_packets.py -q`
- `pytest -q`

## Completion Standard

Each slice must:

- Start with failing tests for the player-visible behavior or server invariant.
- Preserve existing CLI and MCP behavior unless the roadmap explicitly changes
  it.
- Commit in small, reviewable units.
- Run focused tests and the full suite before claiming completion.
- Update this roadmap when scope changes or a milestone proof gate is satisfied.
