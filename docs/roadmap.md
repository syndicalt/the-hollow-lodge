# The Hollow Lodge Development Roadmap

This roadmap tracks the path from the current prototype to a playable, hosted
alpha. It is organized around player-visible release gates, not backend
subsystems. A milestone is complete only when its proof gate has been exercised
from the point of view of a player using Codex plus the Hollow Lodge MCP tools.

## Current Baseline

The repo already contains the core shape of the game:

- Authoritative FastAPI server with invite registration, crews, brokered chat,
  contracts, artifacts, proofs, actions, deals, event sync, and health routes.
- Append-only event log with visibility filtering. JSONL remains the default
  local backend; an explicit Postgres backend is available for the
  authoritative hosted log.
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
- The append-only event log remains authoritative. Database-backed projections
  should become the read-side acceleration layer for contracts, crew legacy,
  artifacts, unlocks, and activity summaries. Hosted authoritative-event
  storage must be an explicit operator choice, not an accidental side effect of
  attaching a platform database.

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
- Shipped-contract smoke coverage completed: every currently shipped contract
  now has a reusable smoke playthrough that activates data-defined seeds when
  needed, submits contract-relevant actions, resolves the phase, and renders
  Codex-safe contract/artifact packets.
- Deferred: every future shipped contract must be added to the smoke registry
  before release.

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
- Platform Postgres projection configuration completed: hosted deployments can
  use Railway-style `DATABASE_URL` as the projection database when the
  Hollow-specific projection URL is unset, while explicit
  `HOLLOW_LODGE_PROJECTION_DATABASE_URL` remains the override and diagnostics
  report which env var selected the backend without leaking credentials.
- Postgres authoritative event-store foundation completed: the event log now
  has a Postgres backend selected only by explicit
  `HOLLOW_LODGE_EVENT_DATABASE_URL`, preserving append-only hash-chain
  validation, idempotency replay/conflict behavior, visibility-scoped reads,
  admin verify/export, and redacted diagnostics.
- Hosted database smoke coverage completed: the first-party backend smoke now
  verifies both authoritative event-log and projection backends, catches stale
  projections, rejects unredacted database credentials, and can require all
  projection read surfaces during hosted cutover.
- Event-log Postgres migration utility completed: operators can validate an
  exported JSON/JSONL event chain, import it into an empty Postgres event-log
  backend while preserving event IDs, sequences, hashes, idempotency metadata,
  and timestamps exactly, and then verify the hosted cutover with the backend
  smoke.
- Required Postgres event-log guard completed: production deployments can now
  set `HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG=1` to fail startup unless the
  authoritative Eventloom backend is explicitly configured with
  `HOLLOW_LODGE_EVENT_DATABASE_URL=postgresql://...`; platform `DATABASE_URL`
  remains projection-only convenience and cannot accidentally select the
  source-of-truth event backend.
- Event-log backup manifest completed: operators can generate content-safe
  manifests for authoritative event-log exports, validating the hash chain and
  recording count, sequence range, chain head, schema versions, and a digest
  over event hashes without exposing event payloads or auth material.
- Manifest-bound event-log import completed: Postgres migration dry-runs and
  imports can now require a matching content-safe backup manifest before
  writing, catching wrong-export or stale-manifest operator mistakes before the
  authoritative event-log backend is changed.
- Hosted event-log manifest smoke completed: backend readiness checks can now
  compare hosted event-log diagnostics against a backup manifest's event count,
  last sequence, and last event hash, proving the deployed authoritative backend
  is at the expected Eventloom chain head without exposing payloads.
- Storage guard readiness smoke completed: `/diagnostics` reports whether
  production Postgres startup guards are enabled for both the authoritative
  Eventloom backend and projection backend, and repository or installed-client
  backend smokes can require those guards before accepting hosted readiness.
- Event-log restore drill completed: installed clients can restore a validated
  export into an empty local JSONL event log with manifest verification, and the
  e2e drill boots a fresh server from that restored chain head.
- Projection refresh diagnostics completed: best-effort projection refresh
  failures after authoritative mutations remain non-blocking but are now visible
  in `/diagnostics` as bounded status, context, exception type, last successful
  sequence, and failure count.
- Postgres event-log metadata diagnostics completed: hosted Postgres
  event-log diagnostics now validate the stored sequence/hash chain and compute
  the content-safe chain digest from metadata columns instead of reading every
  full event payload.
- Projection readiness chain-head diagnostics completed: projected read
  freshness checks now use event-log diagnostics for the authoritative chain
  head instead of replaying the full Eventloom log on each projection-backed
  request.
- Request-scoped Eventloom read reuse completed: dense contract and crew-board
  read paths now share one authoritative event snapshot per request for
  fallback-only unlock, legacy, and pending-decision derivations.
- Crew-specific contract unlock projection completed: contract-board and
  crew-board reads can now use a safe per-crew unlock status read model when the
  projection is fresh, keeping raw seed requirements, hidden truth, and artifact
  graph internals out of the database surface.
- Diagnostics projection lag chain-head completed: `/diagnostics` now reuses
  event-log diagnostics to compute projection lag, avoiding an extra full
  Eventloom replay after the event-log status block has already supplied the
  authoritative chain head.

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
- Persistent player profile surface completed: authenticated players can now
  render their identity and safe crew memberships through a player profile API
  and Codex/MCP surface without exposing tokens, invite material, token hashes,
  or join codes.
- Profile crew legacy summaries completed: player profiles now include safe
  per-crew legacy snapshots with reputation, heat, favors, debts, scars, and
  completed-contract summaries, using projection-backed legacy reads when
  enabled and fresh.
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
- Rumor-escalation unlocks completed: contract seeds can now require prior
  crew containment, exploitation, or integration follow-through from repeated
  credible rumor signals, using only safe aggregate legacy counts to unlock
  future opportunities.
- Follow-up contract activation completed: contract seeds can now carry
  server-only phase-resolved follow-up seeds, letting a resolved chapter
  publish the next arc contract through normal lifecycle events without exposing
  hidden truth or authoring rules.
- Projection database foundation completed: the server now maintains a SQLite
  read-model store rebuilt from the authoritative event log, materializing the
  public contract board without moving live gameplay reads yet. Diagnostics
  report projection health and lag without mutating state.
- Feature-flagged contract-board projection reads completed: `/contracts` can
  read the public contract board from SQLite when the projection is fresh, and
  contract activation, archival, and phase resolution refresh that read model
  after successful authoritative mutations.
- Feature-flagged crew-summary projection reads completed: crew-board roster
  metadata can read from SQLite when the projection is fresh, while crew
  membership checks remain authoritative and visibility-scoped.
- Feature-flagged artifact visibility projection reads completed: `/artifacts`
  can read safe public and scoped artifact surfaces from SQLite when fresh,
  while artifact inspection, transfer authorization, full text, hidden flags,
  unlock rules, and server-only graph internals remain outside the read model.
- Embedded artifact projection reads completed: contract board, inbox, and
  crew board `visible_artifacts` blocks reuse the same fresh SQLite artifact
  projection and stale fallback used by `/artifacts`, keeping Codex-facing
  packets aligned with the dedicated artifact list surface.
- Feature-flagged deal projection reads completed: `/deals` can read
  participant-visible brokered deals from SQLite when the projection is fresh,
  while deal proposal, acceptance, decline, cancellation, authorization, and
  artifact-copy fulfillment remain authoritative service writes against the
  event log.
- Embedded deal projection reads completed: inbox and crew board deal blocks,
  plus contract unlock and crew legacy calculations reached through those
  surfaces, now reuse the same fresh SQLite deal projection and stale fallback
  used by `/deals`, keeping Codex-facing deal context aligned.
- Feature-flagged visible-event projection reads completed: `/events` can read
  player- and crew-visible activity from SQLite when fresh, preserving
  `since_sequence` sync semantics and post-join full-sync recovery while
  keeping server-only and deny-all events out of the activity read model.
- Feature-flagged crew legacy projection reads completed: crew-board legacy can
  read safe retention, rumor, counterintelligence, deal-conduct, completed
  contract, and future-opportunity context from SQLite when fresh, while stale
  state falls back to the existing event-log projection path.
- Feature-flagged pending-decision projection reads completed: inbox and crew
  board `pending_decisions` can read per-player, per-crew action prompts from
  SQLite when fresh, while stale state falls back to the existing event-log
  projection path.
- Feature-flagged action projection reads completed: inbox and crew-board
  pending-decision fallback paths can read current submitted actions from
  SQLite when fresh, while action submission, editing, cancellation,
  authorization, and artifact unlocks remain authoritative event-log writes.
- Platform Postgres projection URL completed: Railway-style `DATABASE_URL`
  can now select the Postgres projection backend when the Hollow-specific
  projection URL is unset, preserving the explicit override and the
  authoritative Eventloom JSONL write model.
- Postgres authoritative event-store foundation completed: the `EventStore`
  interface now has JSONL and Postgres implementations. The app can select the
  Postgres event backend with `HOLLOW_LODGE_EVENT_DATABASE_URL`, while identity
  replay secrets remain in the configured data directory and diagnostics no
  longer assume the authoritative log is file-backed.
- Hosted database smoke coverage completed: `scripts/smoke_projection_backend.py`
  now checks `data.event_log` alongside `data.projection_db`, preserving a
  projection-only compatibility helper for older tests while giving operators a
  single hosted command for event/projection backend readiness.
- Event-log Postgres migration utility completed:
  `scripts/migrate_event_log_to_postgres.py` accepts admin export JSON, JSON
  arrays, or JSONL rows, supports `--dry-run`, validates the source hash chain
  before connecting, and refuses to import into a non-empty Postgres
  destination by default.
- Required Postgres event-log guard completed: hosted production can enforce
  explicit Postgres authoritative event storage with
  `HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG=1`, while local dev and tests keep
  JSONL defaults and Railway-style `DATABASE_URL` remains projection-only.
- Event-log backup manifest completed: `hollow-lodge admin event-log-export`
  can now write an optional content-safe manifest, and
  `hollow-lodge admin event-log-manifest` can validate an existing export and
  write the same chain summary without exposing payloads, actors, visibility,
  idempotency keys, invite hashes, or auth material.
- Manifest-bound event-log import completed: repository and installed-client
  migration commands accept `--manifest`, verify that the manifest matches the
  validated source export before dry-run or import, and report when the manifest
  was verified without printing sensitive export contents.
- Hosted event-log manifest smoke completed: event-log diagnostics now include
  safe chain-head metadata, and repository/installed backend smoke commands can
  require that metadata to match an event-log backup manifest after cutover.
- Hosted event-log chain digest smoke completed: event-log diagnostics now
  expose the same content-safe `event_hash_chain_sha256` summary used by backup
  manifests, and manifest-backed backend smoke requires the deployed digest to
  match.
- Storage guard readiness smoke completed: hosted readiness checks can now
  require `HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG=1` and
  `HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION=1` to be active in the deployed
  process, preventing a passing smoke when production has merely selected
  Postgres without enforcing it as a startup invariant.
- Event-log restore drill completed: operators can validate the other side of
  backup/export by restoring an export plus manifest into an empty local JSONL
  log and booting a clean app at the same safe chain head before relying on the
  backup during a production storage incident.
- Projection refresh diagnostics completed: all mutation routes now use a
  shared projection-refresh helper that records safe success/failure telemetry
  in diagnostics, preventing silent stale read-model incidents while preserving
  the Eventloom write authority boundary.
- Postgres event-log metadata diagnostics completed: `/diagnostics` for the
  Postgres authoritative Eventloom backend now derives event count, chain head,
  and `event_hash_chain_sha256` from metadata columns without loading
  `event_json`, while still failing closed if stored sequence or previous-hash
  continuity is broken.
- Projection readiness chain-head diagnostics completed: shared projection
  readiness checks now compare projection lag against
  `event_store.diagnostics().last_sequence`, letting Postgres-backed
  production requests use the metadata-only chain head rather than a full
  event-log replay before every projected surface read.
- Request-scoped Eventloom read reuse completed: route-level fallback work for
  contract unlocks, inbox pending decisions, and crew-board legacy now reuses a
  single per-request authoritative event snapshot instead of independently
  replaying the Eventloom log for each derived block.
- Feature-flagged contract unlock projection reads completed: crew-scoped
  `unlock_status` rows can now be read from SQLite/Postgres projections by
  `/contracts` and crew boards when fresh, while stale or unavailable state falls
  back to the existing Eventloom-derived unlock calculation.
- Diagnostics projection lag chain-head completed: `/diagnostics` now feeds
  projection diagnostics from the event-log diagnostic `last_sequence`, and
  marks projection lag unavailable if the authoritative event-log diagnostics
  cannot provide a valid chain head.
- Admin oracle audit surface completed: operators can inspect redacted
  provider, validation, fallback, count, and hash evidence for server-only
  oracle audit events without exposing raw oracle inputs, hidden truth, or
  accepted model output.
- Admin oracle audit projection reads completed: the admin audit endpoint can
  read redacted oracle audit rows from the projection database when fresh,
  falling back to Eventloom replay when the projection is stale, disabled, or
  unavailable.
- Artifact inspection projection reads completed: `GET /artifacts/{artifact_id}`
  can read player-visible source text and source-chain fields from the
  projection database when fresh, while hidden flags, hidden truth, and graph
  internals remain excluded from the read model.
- Proof fragment projection reads completed: `GET /proofs/fragments/{fragment_id}`
  can read player-scoped fragment surfaces from the projection database when
  fresh, while provenance flags remain gated behind the explicit provenance
  check command.
- Deferred: deeper death/legacy inheritance, additional long-term unlock paths,
  and migrating heavier campaign reads onto the projection database.

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
- Twelfth social-pressure slice completed: all three rumor escalation modes
  now project bounded future consequences. Containment creates a capped
  quieter-approach modifier, exploitation keeps its leverage modifier, and
  integration creates a capped dossier-framing modifier, all from aggregate
  crew legacy counts rather than raw rumor sources.
- Thirteenth social-pressure slice completed: chat-originated rumor leaks now
  carry a bounded `leak_vector` that distinguishes explicit artifact
  attachments from body-only artifact-name mentions. Rumor decisions,
  responses, verification events, and Codex activity packets can preserve that
  safe enum, and body-only mentions now verify as a distinct
  `credible_artifact_mention_signal` without exposing message text, artifact
  IDs, artifact titles, player IDs, or participant-only chat contents.
- Fourteenth social-pressure slice completed: deal-originated rumor leaks now
  carry the same bounded `leak_vector` shape. Escrow deals with soft terms
  surface only `soft_term_reference`, bare artifact swaps surface
  `escrow_artifact_swap`, and soft-term references verify as a distinct
  `credible_soft_term_signal` without exposing artifact IDs, soft-term text,
  player IDs, acceptance state, or participant-only deal details.
- Escrowed deal acceptance remains participant-scoped and server-enforced.
- Deferred: additional rumor verification sources and deeper long-term
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

### Slice 35: Full Escalation Mode Future Modifiers

Status: completed.

Finish the first pass of mode-specific escalation consequences. The crew
legacy projection already counts contain, exploit, and integrate
`contract.rumor.escalated` events; future modifiers now use all three counts.
Containment adds a capped `rumor_containment` quieter-approach modifier,
exploitation keeps the capped `rumor_exploitation` leverage modifier, and
integration adds a capped `rumor_integration` dossier-framing modifier. Codex
crew-board rendering keeps using generic safe modifier shaping, so source IDs,
private message bodies, artifact IDs, deal terms, suspected crews, and raw
rumor summaries stay out of player markdown and agent context.

Expected verification:

- `pytest tests/server/test_crew_legacy_projection.py::test_contain_and_integrate_rumor_escalations_create_capped_future_modifiers tests/server/test_crew_legacy_projection.py::test_rumor_escalations_create_safe_future_modifiers_without_raw_sources tests/client/test_render_packets.py::test_crew_board_packet_renders_legacy_and_future_modifiers_without_hidden_fields tests/server/test_crew_routes.py::test_crew_board_projects_rumor_escalation_legacy_and_future_modifier tests/server/test_crew_routes.py::test_crew_board_projects_integrated_rumor_escalation_modifier -q`
- `pytest tests/server/test_crew_legacy_projection.py tests/server/test_crew_routes.py tests/server/test_action_routes.py tests/client/test_render_packets.py -q`
- `pytest -q`

### Slice 36: Chat Rumor Leak Vector Verification

Status: completed.

Enrich chat-originated rumor verification without exposing the private chat.
Redacted `contract.rumor.leaked` events from crew-to-crew chat now include a
bounded `leak_vector`: `artifact_attachment` when a message attached an
artifact reference, and `artifact_name_mention` when the body merely named a
visible artifact. The enum is carried through visible rumor projections,
pending decisions, rumor response outcomes, verification events, and Codex
activity packet shaping. Body-only artifact-name mentions now verify as
`credible_artifact_mention_signal` with a safe summary, while message bodies,
artifact IDs, artifact titles, player IDs, and participant-only chat contents
remain outside bystander and activity surfaces.

Expected verification:

- `pytest tests/server/test_chat_routes.py::test_crew_to_crew_artifact_chat_leaks_redacted_rumor_to_bystander_crew tests/server/test_chat_routes.py::test_crew_to_crew_body_artifact_reference_leaks_redacted_rumor tests/server/test_chat_routes.py::test_visible_chat_rumor_becomes_pending_decision_for_bystander_crew tests/server/test_action_routes.py::test_investigating_body_mention_rumor_records_distinct_safe_verification -q`
- `pytest tests/server/test_chat_routes.py tests/server/test_action_routes.py tests/server/test_crew_routes.py tests/client/test_render_packets.py -q`
- `pytest -q`

### Slice 37: Deal Rumor Leak Vector Verification

Status: completed.

Apply the safe verification-source pattern to deal-originated rumors.
Redacted `contract.rumor.leaked` events from proposed deals now include a
bounded `leak_vector`: `soft_term_reference` when an escrow deal includes soft
terms, `escrow_artifact_swap` for bare artifact swaps, and `side_arrangement`
as a defensive fallback. The enum flows through visible rumor projections,
pending decisions, rumor response outcomes, verification events, and existing
Codex render packet shaping. Soft-term references now verify as
`credible_soft_term_signal` with a safe summary, while artifact IDs, artifact
titles, soft-term text, player IDs, deal acceptance state, and participant-only
deal details remain outside bystander and activity surfaces.

Expected verification:

- `pytest tests/server/test_deal_routes.py::test_deal_proposal_leaks_partial_rumor_to_bystander_crew_without_deal_terms tests/server/test_deal_routes.py::test_deal_rumor_becomes_pending_decision_for_bystander_crew tests/server/test_deal_routes.py::test_deal_rumor_without_soft_terms_uses_artifact_swap_leak_vector tests/server/test_action_routes.py::test_deal_rumor_investigation_preserves_contract_id_without_terms -q`
- `pytest tests/server/test_deal_routes.py tests/server/test_action_routes.py tests/server/test_crew_routes.py tests/client/test_render_packets.py -q`
- `pytest -q`

### Slice 38: Rumor Escalation Unlock Requirements

Status: completed.

Connect social-pressure follow-through to the retention layer. Contract seeds
can now use `rumor_containment`, `rumor_exploitation`, or `rumor_integration`
as crew unlock metrics. Those requirements evaluate against the bounded
`rumor_escalation` legacy aggregate, so repeated credible rumor handling can
unlock later contracts without exposing rumor IDs, message text, artifact IDs,
deal terms, source crews, or suspected crews through `unlock_status`.

Expected verification:

- `pytest tests/server/test_contract_seed_pipeline.py::test_contract_seed_accepts_rumor_escalation_unlock_requirement tests/server/test_contract_seed.py::test_rumor_escalation_unlock_requires_matching_crew_follow_through -q`
- `pytest tests/server/test_contract_seed_pipeline.py tests/server/test_contract_seed.py tests/server/test_crew_routes.py tests/server/test_crew_legacy_projection.py tests/client/test_render_packets.py -q`
- `pytest -q`

### Slice 39: Phase-Resolved Follow-Up Contract Activation

Status: completed.

Add the first real campaign-arc authoring hook. Contract seeds can now include
server-only `phase_followups` that embed a validated follow-up contract seed
for the same campaign. When the source phase resolves, the server activates the
follow-up seed with deterministic idempotency keys, publishing only the normal
public board and lifecycle events for the new contract while keeping hidden
truth, artifact graph internals, unlock requirements, and follow-up authoring
rules out of visible event streams. Replaying the phase lock or restarting from
the event log does not duplicate the follow-up activation.

Expected verification:

- `pytest tests/server/test_contract_seed_pipeline.py::test_contract_seed_accepts_phase_resolved_follow_up_contract_seed tests/server/test_contract_seed_pipeline.py::test_contract_seed_rejects_follow_up_for_unknown_phase tests/server/test_contract_seed.py::test_contract_activation_replay_rejects_different_follow_up_seed tests/server/test_phase_resolution.py::test_seeded_phase_resolution_publishes_follow_up_contract_without_hidden_leak -q`
- `pytest tests/server/test_contract_seed_pipeline.py tests/server/test_contract_seed.py tests/server/test_phase_resolution.py tests/server/test_artifact_routes.py tests/e2e/test_contract_content_pipeline.py tests/client/test_render_packets.py -q`
- `pytest -q`

### Slice 40: SQLite Projection Store Foundation

Status: completed.

Start the database-backed read side without changing game authority. The JSONL
event log remains the source of truth, while a new SQLite projection store can
rebuild from the current event stream and materialize the public contract-board
read model. Server diagnostics report the projection database path,
availability, schema version, last applied event sequence, authoritative event
sequence, lag, and contract count without mutating projection state. The first
projection intentionally stores only player-safe contract-board payloads, so
hidden truth and server-only seed internals stay out of the database read model.
Live gameplay reads still use the existing projections unless a later
feature-flagged slice enables a parity-tested read path.

Expected verification:

- `pytest tests/server/test_projection_store.py -q`
- `pytest tests/server/test_projection_store.py tests/server/test_app_config.py tests/server/test_contract_seed.py tests/server/test_phase_resolution.py tests/eventlog/test_jsonl_store.py -q`
- `pytest -q`

### Slice 41: Feature-Flagged Contract Board Projection Reads

Status: completed.

Move the first player-facing read surface onto the SQLite projection path
without making it mandatory. When
`HOLLOW_LODGE_CONTRACT_BOARD_PROJECTION_READS=1` is set, `/contracts` reads the
public contract board from SQLite only if the projection is available and has
zero lag against the authoritative event log. Stale, missing, or unreadable
projection state falls back to the existing JSONL projection path. Projection
store tests assert DB parity with `contract_board_from_events`, and route tests
prove both fresh-projection use and stale fallback behavior.

Expected verification:

- `pytest tests/server/test_projection_store.py -q`
- `pytest tests/server/test_projection_store.py tests/server/test_app_config.py tests/server/test_contract_seed.py tests/server/test_crew_routes.py tests/server/test_phase_resolution.py tests/client/test_contract_board.py tests/client/test_render_packets.py -q`
- `pytest -q`

### Slice 42: Contract Board Projection Refresh

Status: completed.

Keep the feature-flagged SQLite contract-board read path fresh after normal
server-side contract mutations. Admin contract activation, admin archival, and
auction-preview phase resolution now rebuild the contract-board projection
after the authoritative event-log write succeeds, so `/contracts` can continue
using SQLite with zero lag. Projection rebuild remains best-effort: if SQLite
is unavailable after a valid mutation, the mutation still succeeds and the
existing stale-projection fallback keeps reads on the authoritative JSONL path.
Out-of-band event-log changes still show as stale in diagnostics without
diagnostics mutating projection state.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_contract_activation_refreshes_projection_for_flagged_reads tests/server/test_projection_store.py::test_contract_archive_refreshes_projection_for_flagged_reads tests/server/test_projection_store.py::test_phase_resolution_refreshes_projection_for_flagged_reads tests/server/test_projection_store.py::test_contract_mutation_still_succeeds_when_projection_refresh_fails -q`
- `pytest tests/server/test_projection_store.py tests/server/test_contract_seed.py tests/server/test_phase_resolution.py tests/server/test_crew_routes.py tests/client/test_contract_board.py tests/client/test_render_packets.py -q`
- `pytest -q`

### Slice 43: Feature-Flagged Crew Summary Projection Reads

Status: completed.

Move the first safe part of the crew-board surface onto the SQLite projection
path without changing authorization or visibility boundaries. The projection
store now materializes sanitized crew summaries from `crew.created` and
`crew.member.joined` events, excluding join codes. When
`HOLLOW_LODGE_CREW_SUMMARY_PROJECTION_READS=1` is set, `/crews/{crew_id}/board`
uses the projected crew summary only after the normal authoritative crew
existence and membership checks pass and only if the projection has zero lag.
Stale, missing, or unreadable projection state falls back to the existing crew
service. Crew creation and join mutations refresh the projection after the
authoritative event-log write, and projection refresh remains best-effort so
SQLite availability cannot invalidate a successful crew mutation.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_crew_board_reads_fresh_projected_crew_summary_when_enabled tests/server/test_projection_store.py::test_crew_board_falls_back_when_projected_crew_summary_is_stale tests/server/test_projection_store.py::test_crew_creation_still_succeeds_when_projection_refresh_fails -q`
- `pytest tests/server/test_projection_store.py tests/server/test_crew_routes.py tests/server/test_contract_seed.py tests/server/test_phase_resolution.py tests/server/test_app_config.py tests/client/test_render_packets.py tests/client/test_contract_board.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 44: Feature-Flagged Artifact Visibility Projection Reads

Status: completed.

Move the player-visible artifact list onto the SQLite projection path without
moving artifact authority. The projection store now materializes only safe
artifact surfaces and safe visible edges: public graph artifacts, public graph
edges whose endpoints are public, and scoped artifact copy or access surfaces
with their event visibility. It does not persist artifact full text, hidden
flags, unlock rules, server-only graph internals, or hidden truth. When
`HOLLOW_LODGE_ARTIFACT_PROJECTION_READS=1` is set, `/artifacts` reads from
SQLite only if the projection is available and has zero lag. Stale, missing, or
unreadable projection state falls back to `ArtifactService`. Identity
registration and artifact transfer refresh projections best-effort after their
authoritative event writes, while artifact inspection and transfer
authorization remain service-backed.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_artifact_route_reads_fresh_projected_visible_artifacts_when_enabled tests/server/test_projection_store.py::test_artifact_route_falls_back_when_projection_is_stale tests/server/test_projection_store.py::test_artifact_projection_reads_player_and_crew_scoped_surfaces tests/server/test_projection_store.py::test_artifact_transfer_refreshes_projection_for_flagged_reads tests/server/test_projection_store.py::test_projection_store_materializes_visible_artifacts_without_hidden_fields -q`
- `pytest tests/server/test_projection_store.py tests/server/test_artifact_routes.py tests/server/test_artifact_projections.py tests/server/test_artifact_transfer.py tests/server/test_contract_seed.py tests/server/test_phase_resolution.py tests/server/test_crew_routes.py tests/server/test_deal_routes.py tests/client/test_render_packets.py tests/client/test_contract_board.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 45: Embedded Artifact Projection Reads

Status: completed.

Reuse the artifact visibility projection across player packets that embed
artifact lists. Contract board, inbox, and crew board now call a shared
projection helper for `visible_artifacts` when
`HOLLOW_LODGE_ARTIFACT_PROJECTION_READS=1`, the projection is available, and
lag is zero. Stale, missing, or unreadable projection state falls back to
`ArtifactService`, preserving the existing behavior. The helper keeps player
and crew visibility filtering centralized, so Codex-facing surfaces and the
dedicated `/artifacts` route use the same read-model gate and safe artifact
surface shape.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_contract_board_embeds_projected_visible_artifacts_when_enabled tests/server/test_projection_store.py::test_inbox_embeds_projected_visible_artifacts_when_enabled tests/server/test_projection_store.py::test_crew_board_embeds_projected_visible_artifacts_when_enabled tests/server/test_projection_store.py::test_embedded_visible_artifacts_fall_back_when_projection_is_stale -q`
- `pytest tests/server/test_projection_store.py tests/server/test_artifact_routes.py tests/server/test_artifact_projections.py tests/server/test_artifact_transfer.py tests/server/test_contract_seed.py tests/server/test_phase_resolution.py tests/server/test_crew_routes.py tests/server/test_deal_routes.py tests/client/test_render_packets.py tests/client/test_contract_board.py tests/test_mcp_server.py tests/e2e/test_codex_render_surfaces.py -q`
- `pytest -q`

### Slice 46: Feature-Flagged Deal Projection Reads

Status: completed.

Move the dedicated brokered deal list onto the SQLite projection path without
moving deal authority. The projection store now materializes participant-safe
deal surfaces from authoritative deal lifecycle events, including proposed,
fulfilled, declined, and canceled states. `/deals` reads from SQLite only when
`HOLLOW_LODGE_DEAL_PROJECTION_READS=1`, the projection is available, and lag is
zero. Stale, missing, or unreadable projection state falls back to
`DealService`. Deal proposal, acceptance, decline, and cancellation continue to
validate membership, artifact visibility, idempotency, and escrow fulfillment
through the service layer, then refresh the projection best-effort after a
successful event-log write.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_deal_route_reads_fresh_projected_visible_deals_when_enabled tests/server/test_projection_store.py::test_deal_route_falls_back_when_projection_is_stale tests/server/test_projection_store.py::test_deal_accept_refreshes_projection_for_flagged_reads tests/server/test_projection_store.py::test_projection_store_materializes_visible_deals_without_bystander_terms -q`
- `pytest tests/server/test_projection_store.py tests/server/test_deal_routes.py tests/server/test_deal_service.py tests/server/test_crew_routes.py tests/server/test_contract_seed.py tests/client/test_deal_mcp_render.py tests/client/test_deal_render.py tests/client/test_render_packets.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 47: Embedded Deal Projection Reads

Status: completed.

Reuse the deal projection across Codex-facing surfaces that embed deal context.
Inbox and crew board route helpers now call the same
`projected_visible_deals` gate used by `/deals` when
`HOLLOW_LODGE_DEAL_PROJECTION_READS=1`, the projection is available, and lag is
zero. Stale, missing, or unreadable projection state still falls back to
`DealService`. Because those helpers also feed pending decisions, contract
unlock shaping, and crew legacy calculations reached from the inbox and crew
board, embedded deal context now stays aligned with the dedicated deal list
surface without moving deal authority out of the event-log/service path.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_inbox_embeds_projected_visible_deals_when_enabled tests/server/test_projection_store.py::test_crew_board_embeds_projected_visible_deals_when_enabled tests/server/test_projection_store.py::test_embedded_visible_deals_fall_back_when_projection_is_stale -q`
- `pytest tests/server/test_projection_store.py tests/server/test_deal_routes.py tests/server/test_deal_service.py tests/server/test_crew_routes.py tests/server/test_contract_seed.py tests/client/test_deal_mcp_render.py tests/client/test_deal_render.py tests/client/test_render_packets.py tests/client/test_contract_board.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 48: Feature-Flagged Visible Event Projection Reads

Status: completed.

Move the player-visible activity read path onto the SQLite projection layer
without moving event authority. The projection store now materializes only
public, player-visible, and crew-visible events into a
`visible_event_surface`; server-only and deny-all events remain out of that
read model. `/events` reads from SQLite only when
`HOLLOW_LODGE_VISIBLE_EVENT_PROJECTION_READS=1`, the projection is available,
and lag is zero. Stale, missing, or unreadable projection state falls back to
`VisibilityService`. The projected read preserves `since_sequence` filtering
and current crew-membership semantics, so full sync after joining a crew can
recover older crew-visible activity while delta sync still excludes events at
or before the checkpoint. Chat mutations refresh the projection best-effort
after successful event-log writes so Codex activity packets can use the fresh
read model.

Expected verification:

- `pytest tests/server/test_event_sync.py::test_visible_events_route_reads_fresh_projection_when_enabled tests/server/test_event_sync.py::test_visible_events_projection_honors_since_sequence tests/server/test_event_sync.py::test_visible_events_projection_full_sync_recovers_crew_events_after_join tests/server/test_event_sync.py::test_visible_events_route_falls_back_when_projection_is_stale -q`
- `pytest tests/server/test_event_sync.py tests/server/test_projection_store.py tests/server/test_chat_routes.py tests/client/test_local_log.py tests/client/test_codex_session.py tests/client/test_render_packets.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 49: Feature-Flagged Crew Legacy Projection Reads

Status: completed.

Move the crew-board legacy block onto the SQLite projection layer without
moving legacy authority. The projection store now materializes one safe
`crew_legacy` payload per crew from the existing `crew_legacy_from_contracts`
projection, using unlock-aware active contracts, participant-scoped deal rows,
and visible event-derived rumor/counterintelligence data. The stored payload
excludes raw artifact IDs, soft terms, private chat bodies, hidden truth, and
server-only source details because it persists only the already-shaped legacy
surface. `/crews/{crew_id}/board` reads this payload when
`HOLLOW_LODGE_CREW_LEGACY_PROJECTION_READS=1`, the projection is available,
and lag is zero; stale, missing, or unreadable projection state falls back to
the existing event-log projection path. Action mutations now refresh
projections best-effort after successful writes so rumor response and
escalation legacy can stay fresh under the read-model flag.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_crew_board_reads_fresh_projected_crew_legacy_when_enabled tests/server/test_projection_store.py::test_crew_board_falls_back_when_projected_crew_legacy_is_stale tests/server/test_projection_store.py::test_projection_store_materializes_crew_legacy_without_private_deal_terms -q`
- `pytest tests/server/test_projection_store.py tests/server/test_crew_routes.py tests/server/test_crew_legacy_projection.py tests/server/test_action_routes.py tests/server/test_deal_routes.py tests/server/test_contract_seed.py tests/server/test_phase_resolution.py tests/client/test_render_packets.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 50: Dedicated Codex Dossier Rendering

Status: completed.

Add a first-class Codex/MCP read surface for the current crew proof dossier.
`render_dossier` syncs the local event log, fetches the authoritative dossier
for the active or explicit crew, and returns player Markdown plus structured
agent context. The render packet makes claim, evidence IDs, artifact citations,
member contributions, reasoning, weaknesses, and provenance concerns easy to
scan while preserving the existing safe dossier shaping that strips hidden
server fields before text or context reaches the client.

Expected verification:

- `pytest tests/client/test_render_packets.py::test_dossier_packet_renders_claim_citations_contributions_without_hidden_fields tests/client/test_codex_session.py::test_codex_session_renders_dossier_with_active_crew tests/test_mcp_server.py::test_render_dossier_mcp_call_returns_text_and_structured_packet -q`
- `pytest tests/client/test_render_packets.py tests/client/test_codex_session.py tests/test_mcp_server.py tests/client/test_api.py tests/client/test_dossier_cli.py tests/server/test_proof_routes.py tests/server/test_packet_lead.py -q`
- `pytest -q`

### Slice 51: Bounded Oracle Output Schema

Status: completed.

Harden the Milestone 3 oracle boundary by adding shared output-size limits for
score-reasoning lists and generated text fields. Auction preview oracle
results now reject oversized narration, contract state, validation warnings,
standing labels, strengths, weaknesses, penalties, and revealed clues before
they can become accepted game output. The OpenAI structured-output schema uses
the same bounds, so unbounded provider responses fail parsing and flow into the
existing deterministic fallback and audit path.

Expected verification:

- `pytest tests/workflows/test_oracle_boundary.py::test_oracle_result_rejects_unbounded_score_reasoning_lines tests/workflows/test_oracle_boundary.py::test_oracle_result_rejects_unbounded_text_fields tests/workflows/test_openai_oracle.py::test_openai_oracle_rejects_unbounded_parsed_output -q`
- `pytest tests/workflows/test_oracle_boundary.py tests/workflows/test_openai_oracle.py tests/workflows/test_deterministic_oracle.py tests/workflows/test_oracle_factory.py tests/server/test_resolution_oracle.py tests/server/test_phase_resolution.py -q`
- `pytest -q`

### Slice 52: Shipped Contract Smoke Registry

Status: completed.

Close the current Milestone 4 smoke gap with a reusable
`scripts/smoke_shipped_contracts.py` runner and e2e gate. The runner exercises
every currently shipped contract: the built-in starter contract and the
data-defined Ash Window seed. Each smoke creates two players and crews, activates
fixture seeds when needed, submits contract-relevant actions, cites a visible
artifact, locks the auction-preview route, renders Codex contract/artifact
packets, and checks that hidden truth terms do not leak into those rendered
surfaces.

The new smoke also exposed and fixed a projection-store bug: scoped artifact
surfaces are now keyed by artifact id plus visibility scope, so granting the
same non-public artifact to multiple crews no longer breaks SQLite projection
rebuilds.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_projection_store_allows_same_scoped_artifact_for_multiple_crews tests/e2e/test_shipped_contract_smokes.py::test_all_shipped_contracts_have_playthrough_smokes -q`
- `pytest tests/server/test_projection_store.py tests/server/test_artifact_routes.py tests/server/test_contract_seed.py tests/e2e/test_contract_content_pipeline.py tests/e2e/test_codex_render_surfaces.py tests/e2e/test_shipped_contract_smokes.py -q`
- `pytest -q`

### Slice 53: Codex Player Profile Surface

Status: completed.

Add a read-only persistent-character surface for players. The server now
exposes authenticated `/identity/profile` data with player id, display name,
crew count, and safe crew membership summaries. The client API, Codex session,
and MCP server now expose `render_profile`, and the profile render packet gives
players and local agents a stable identity/crew context without leaking tokens,
token hashes, invite codes, invite hashes, or crew join codes.

Expected verification:

- `pytest tests/server/test_identity_routes.py::test_player_profile_returns_safe_crew_memberships_without_auth_material tests/client/test_api.py::test_api_gets_player_profile tests/client/test_render_packets.py::test_profile_packet_renders_persistent_identity_and_crew_memberships_without_hidden_fields tests/client/test_codex_session.py::test_codex_session_renders_profile tests/test_mcp_server.py::test_render_profile_mcp_call_returns_text_and_structured_packet -q`
- `pytest tests/server/test_identity_routes.py tests/server/test_crew_routes.py tests/client/test_api.py tests/client/test_codex_session.py tests/client/test_render_packets.py tests/test_mcp_server.py tests/e2e/test_codex_render_surfaces.py -q`
- `pytest -q`

### Slice 54: Projection Database Backend Configuration

Status: completed.

Prepare the server for a real database-backed projection layer without moving
authority out of the Eventloom JSONL log. App startup now creates the projection
store through a configuration boundary instead of constructing SQLite directly.
SQLite remains the default backend, `HOLLOW_LODGE_PROJECTION_DATABASE_URL` can
point at an explicit local `sqlite:///` projection path, and Postgres URLs fail
fast with secrets redacted until the Postgres projection store is implemented.
Projection diagnostics now report the active backend so hosted operators can
verify whether reads are coming from SQLite or a future database backend.

Expected verification:

- `pytest tests/server/test_app_config.py -q`
- `pytest tests/server/test_projection_store.py tests/server/test_app_config.py -q`
- `pytest -q`

### Slice 55: Postgres Projection Store Adapter

Status: completed.

Add the first production Postgres projection backend while preserving the
append-only Eventloom JSONL log as the source of truth. The server can now
select a `postgresql://` projection URL through
`HOLLOW_LODGE_PROJECTION_DATABASE_URL`, install the required `psycopg` driver in
the package and Railway image, materialize the same projection snapshot used by
SQLite into Postgres tables, and serve the existing projection read interface
for contract boards, crew summaries, crew legacy, artifacts, deals, and visible
events. Hosted diagnostics redact the Postgres password and report backend
status without exposing secrets.

Expected verification:

- `pytest tests/server/test_app_config.py::test_postgres_projection_database_url_selects_postgres_backend tests/server/test_app_config.py::test_server_docker_image_installs_openai_client_for_openai_oracle -q`
- `pytest tests/server/test_projection_store.py tests/server/test_app_config.py -q`
- `pytest -q`

### Slice 56: Projection Backend Cutover Smoke

Status: completed.

Add an operational smoke for safely cutting projection reads between SQLite and
Postgres. `scripts/smoke_projection_backend.py` checks hosted `/health` and
`/diagnostics`, verifies the expected projection backend, requires
`available` status and zero lag, and fails if diagnostics expose an unredacted
database URL password. The operations runbook now includes pre-cutover,
post-cutover, and rollback commands. This keeps the Eventloom JSONL authority
boundary intact while making database backend changes auditable.

Expected verification:

- `pytest tests/e2e/test_projection_backend_smoke.py -q`
- `python scripts/smoke_projection_backend.py --server-url https://server.thehollowlodge.com --expected-backend sqlite`
- `pytest -q`

### Slice 57: Codex What-Now Landing Surface

Status: completed.

Add a read-only first-stop surface for players inside Codex. The client now
aggregates profile, inbox, visible deals, active crew, and recent visible
activity into a `what_now` render packet. The MCP server exposes
`render_what_now`, giving the player and local agent one compact view of active
contracts, pending decisions, incoming fragments, open deals, and recent
visible events before drilling into the inbox, crew board, deal board, or
activity log. The packet is explicitly non-mutating and shapes data through the
same safe render helpers used by the underlying surfaces.

Expected verification:

- `pytest tests/client/test_render_packets.py::test_what_now_packet_aggregates_current_priorities_without_hidden_fields tests/client/test_codex_session.py::test_codex_session_renders_what_now_landing_surface tests/test_mcp_server.py::test_render_what_now_mcp_call_returns_text_and_structured_packet tests/e2e/test_codex_render_surfaces.py::test_codex_render_surfaces_show_player_and_agent_state -q`
- `pytest tests/client/test_render_packets.py tests/client/test_codex_session.py tests/test_mcp_server.py tests/e2e/test_codex_render_surfaces.py -q`
- `pytest -q`

### Slice 58: Codex-Session Alpha Playthrough Proof

Status: completed.

Harden the Milestone 1 proof gate so the full-loop smoke exercises the same
Codex session path used by MCP tools instead of only constructing render
packets directly from server responses. `scripts/mock_full_game_loop.py` now
creates real `CodexGameSession` instances against the in-process server,
syncs local perspective logs, and renders contract board, artifacts, visible
deals, deal preview, inbox, crew board, dossier, `what_now`, contract result,
and activity packets during a two-crew escrow playthrough. The Codex play guide
now starts sessions with `render_what_now`.

Expected verification:

- `pytest tests/e2e/test_full_game_loop_with_escrow.py -q`
- `python scripts/mock_full_game_loop.py`
- `pytest tests/e2e/test_full_game_loop_with_escrow.py tests/e2e/test_codex_render_surfaces.py tests/client/test_codex_session.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 59: Crew-Scoped Activity Timeline

Status: completed.

Add the first Milestone 2 coordination surface for asking what changed for a
specific crew. The render layer now builds a `crew_activity` packet from
already-visible events, including only events that explicitly name the active
crew through safe payload fields, chat endpoints, deal parties, actions,
dossiers, standings, legacy deltas, or crew visibility principals. The Codex
session and MCP server expose `render_crew_activity`, using the active crew by
default while still accepting an explicit crew id. The full-loop smoke now
renders crew activity alongside final `what_now` and global activity packets.

Expected verification:

- `pytest tests/client/test_render_packets.py::test_crew_activity_packet_filters_visible_events_to_named_crew_without_hidden_fields tests/client/test_codex_session.py::test_codex_session_renders_crew_activity_with_active_crew tests/test_mcp_server.py::test_render_crew_activity_mcp_call_returns_text_and_structured_packet -q`
- `pytest tests/e2e/test_full_game_loop_with_escrow.py -q`
- `pytest tests/client/test_render_packets.py tests/client/test_codex_session.py tests/test_mcp_server.py tests/e2e/test_full_game_loop_with_escrow.py -q`
- `pytest -q`

### Slice 60: Packet Lead History Visibility

Status: completed.

Make Packet Lead control legible in Codex. Dossier responses now include safe
`packet_lead_votes` and `packet_lead_replacements` histories derived from
crew-visible packet-lead events, with only event sequence, voter, candidate,
previous lead, and current lead fields. Crew boards and dossier packets render
that history beside the current Packet Lead while stripping idempotency keys,
join codes, server notes, and other upstream command metadata. The full-loop
smoke now replaces the Gilt crew Packet Lead and verifies the final Codex
dossier packet contains vote and replacement history.

Expected verification:

- `pytest tests/server/test_packet_lead.py::test_dossier_exposes_safe_packet_lead_vote_and_replacement_history tests/client/test_render_packets.py::test_dossier_packet_renders_claim_citations_contributions_without_hidden_fields tests/client/test_render_packets.py::test_crew_board_packet_shows_packet_lead_and_dossier_status tests/e2e/test_full_game_loop_with_escrow.py -q`
- `python scripts/mock_full_game_loop.py`
- `pytest tests/server/test_packet_lead.py tests/client/test_render_packets.py tests/e2e/test_full_game_loop_with_escrow.py -q`
- `pytest -q`

### Slice 61: Required Postgres Projection Guard

Status: completed.

Harden the database cutover path without moving game authority out of the
Eventloom JSONL log. Server configuration now supports
`HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION=1`, which rejects missing projection
database URLs and rejects `sqlite:///` projection URLs at startup. Local
development keeps the SQLite default, while production can make the Postgres
projection backend an explicit invariant after the hosted Postgres smoke
passes. Error messages identify the misconfiguration while preserving the
existing redaction boundary for database URLs.

Expected verification:

- `pytest tests/server/test_app_config.py::test_require_postgres_projection_rejects_missing_database_url tests/server/test_app_config.py::test_require_postgres_projection_rejects_sqlite_url_without_secret_leak tests/server/test_app_config.py::test_require_postgres_projection_allows_postgres_backend tests/server/test_app_config.py::test_require_postgres_projection_rejects_invalid_flag_value -q`
- `pytest tests/server/test_app_config.py tests/e2e/test_projection_backend_smoke.py -q`
- `pytest -q`

### Slice 62: Checkpointed Activity Delta Surface

Status: completed.

Make the Milestone 2 "what changed since my last sync" question explicit
inside Codex. The render layer now has an `activity_delta` packet that reports
the prior local checkpoint sequence, max sequence after sync, synced event
count, filtered activity event count, safe event type counts, and recent
visibility-scoped events. `CodexGameSession` captures the local log checkpoint
before syncing and calls `/events?since_sequence=<checkpoint>` instead of
re-fetching the full activity stream. MCP now exposes `render_activity_delta`
for all visible changes and `render_crew_activity_delta` for active-crew or
specified-crew changes, preserving the same hidden-field stripping and
confirmation-free read behavior as the existing activity surfaces.

Expected verification:

- `pytest tests/client/test_render_packets.py::test_activity_delta_packet_reports_checkpoint_and_safe_new_events tests/client/test_render_packets.py::test_activity_delta_packet_filters_to_crew_when_requested tests/client/test_codex_session.py::test_codex_session_renders_activity_delta_since_local_checkpoint tests/client/test_codex_session.py::test_codex_session_renders_crew_activity_delta_with_active_crew tests/test_mcp_server.py::test_render_activity_delta_mcp_call_returns_text_and_structured_packet tests/test_mcp_server.py::test_render_crew_activity_delta_mcp_call_returns_text_and_structured_packet tests/test_mcp_server.py::test_public_mcp_tools_do_not_expose_local_path_overrides -q`
- `pytest tests/client/test_render_packets.py tests/client/test_codex_session.py tests/test_mcp_server.py tests/e2e/test_full_game_loop_with_escrow.py -q`
- `pytest -q`

### Slice 63: Conversation Index Surface

Status: completed.

Make brokered conversation discovery visible inside Codex. The render layer now
builds a `conversations` packet from visible chat events, grouping direct,
crew, and bidirectional crew-to-crew messages into thread ids that can be
opened with `render_thread`. The packet reports message counts, first and last
sequence, last visible sender/body, participant ids, and artifact-reference
counts while stripping server-only fields. `CodexGameSession` and MCP now
expose `render_conversations`, and the full-loop smoke exchanges brokered
crew-to-crew messages before the escrow deal, renders the conversation index,
and asserts the thread summary is visible in the Codex packet sequence.

Expected verification:

- `pytest tests/client/test_render_packets.py::test_conversations_packet_lists_visible_threads_without_hidden_fields tests/client/test_codex_session.py::test_codex_session_renders_conversations_from_synced_visible_events tests/test_mcp_server.py::test_render_conversations_mcp_call_returns_text_and_structured_packet tests/test_mcp_server.py::test_public_mcp_tools_do_not_expose_local_path_overrides tests/e2e/test_full_game_loop_with_escrow.py -q`
- `python scripts/mock_full_game_loop.py`
- `pytest tests/client/test_render_packets.py tests/client/test_codex_session.py tests/test_mcp_server.py tests/e2e/test_full_game_loop_with_escrow.py tests/e2e/test_codex_render_surfaces.py tests/server/test_chat_routes.py -q`
- `pytest -q`

### Slice 64: Proof Dossier Projection Reads

Status: completed.

Move the current proof dossier read model onto the projection database without
moving dossier authority out of the event-log service path. SQLite and
Postgres projection stores now materialize one safe current `proof_dossier`
payload per crew, including claim, evidence ids, member contributions, artifact
citations, Packet Lead, and Packet Lead vote/replacement history while
excluding idempotency keys and command metadata. When
`HOLLOW_LODGE_PROOF_DOSSIER_PROJECTION_READS=1`, standalone dossier reads,
crew-board dossier blocks, and inbox pending-decision inputs use the projected
dossier only if the projection is available and has zero lag. Stale, missing,
or unreadable projection state falls back to the existing `ProofService`
replay path. Dossier framing, contribution, citation, and Packet Lead vote
mutations refresh the projection best-effort after the authoritative event-log
write succeeds.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_projection_store_materializes_current_proof_dossiers_without_command_metadata tests/server/test_projection_store.py::test_dossier_route_reads_fresh_projection_when_enabled tests/server/test_projection_store.py::test_embedded_dossier_surfaces_read_fresh_projection_when_enabled tests/server/test_projection_store.py::test_dossier_route_falls_back_when_projected_dossier_is_stale -q`
- `pytest tests/server/test_projection_store.py tests/server/test_proof_routes.py tests/server/test_packet_lead.py tests/server/test_crew_routes.py tests/server/test_contract_seed.py tests/client/test_render_packets.py tests/client/test_codex_session.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 65: Projection Schema Migration Ledger

Status: completed.

Add production database discipline to the projection read side without moving
authority out of the Eventloom JSONL log. SQLite and Postgres projection stores
now maintain a `projection_schema_migrations` ledger with the applied
projection schema versions and descriptions, and projection diagnostics expose
`schema_version`, `schema_migration_count`, and `latest_schema_migration`.
This slice introduced projection schema version `2` for the proof dossier read
model. The operations guide now documents using diagnostics to verify
projection schema drift before hosted cutovers.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_projection_store_records_schema_migration_ledger tests/server/test_app_config.py::test_postgres_projection_database_url_selects_postgres_backend tests/server/test_app_config.py::test_require_postgres_projection_allows_postgres_backend -q`
- `pytest tests/server/test_projection_store.py tests/server/test_app_config.py tests/e2e/test_projection_backend_smoke.py -q`
- `pytest -q`

### Slice 66: Chat Message Projection Reads

Status: completed.

Move brokered chat discovery onto the projection database without moving chat
writes out of the event-log service path. SQLite and Postgres projection stores
now materialize sanitized `chat_message_surface` rows for player-visible chat
events, keyed by message id, sequence, kind, and normalized conversation id.
The stored chat surface excludes idempotency keys and hash-chain metadata while
preserving the visible message payload needed by Codex conversation and thread
renders. `GET /chat/messages` returns visibility-filtered chat events, using
the projection when `HOLLOW_LODGE_CHAT_PROJECTION_READS=1` and the projection
has zero lag, with stale or unavailable projections falling back to the
existing visibility service. Codex `render_conversations` and `render_thread`
now use this narrower chat endpoint after syncing local perspective logs. This
slice advances the projection schema to version `3`.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_projection_store_materializes_visible_chat_messages_without_bystander_access tests/server/test_projection_store.py::test_chat_messages_route_reads_fresh_projection_when_enabled tests/server/test_projection_store.py::test_chat_messages_route_falls_back_when_projection_is_stale tests/client/test_api.py::test_api_fetches_visible_chat_events tests/client/test_codex_session.py::test_codex_session_renders_thread_with_cli_compatible_matching tests/client/test_codex_session.py::test_codex_session_renders_conversations_from_synced_visible_events -q`
- `pytest tests/server/test_projection_store.py tests/server/test_chat_routes.py tests/server/test_event_sync.py tests/client/test_api.py tests/client/test_codex_session.py tests/client/test_render_packets.py tests/test_mcp_server.py tests/e2e/test_full_game_loop_with_escrow.py -q`
- `pytest -q`

### Slice 67: Pending Decision Projection Reads

Status: completed.

Move the shared inbox and crew-board pending-decision surface onto the
projection database without moving decision authority out of the Eventloom
event log. SQLite and Postgres projection stores now materialize safe
`pending_decision_surface` rows per player, crew, and decision index from
already-shaped contract, deal, proof dossier, action, rumor, and crew legacy
inputs. The stored decisions include actionable labels, ids, missing dossier
needs, deal ids, rumor response prompts, and Packet Lead vote prompts while
excluding private deal terms, raw artifact ids, chat bodies, command
idempotency keys, and hidden artifact graph internals. When
`HOLLOW_LODGE_PENDING_DECISION_PROJECTION_READS=1`, `/inbox` and
`/crews/{crew_id}/board` use the projection only if it is available and has
zero lag, with stale or unavailable projections falling back to the existing
event-log replay path. This slice advances the projection schema to version
`4`.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_projection_store_materializes_pending_decisions_without_private_deal_terms tests/server/test_projection_store.py::test_inbox_and_crew_board_read_fresh_pending_decision_projection_when_enabled tests/server/test_projection_store.py::test_pending_decision_projection_reads_fall_back_when_stale -q`
- `pytest tests/server/test_projection_store.py tests/server/test_app_config.py tests/server/test_pending_decisions.py tests/server/test_crew_routes.py tests/server/test_contract_seed.py tests/server/test_deal_routes.py tests/server/test_chat_routes.py tests/server/test_action_routes.py tests/client/test_render_packets.py tests/client/test_codex_session.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 68: Current Action Projection Reads

Status: completed.

Move current submitted freeform-action reads onto the projection database
without moving action authority out of the Eventloom event log. SQLite and
Postgres projection stores now materialize safe `action_surface` rows for the
latest non-canceled action state per crew, preserving the shaped action payload
needed by pending-decision prompts while excluding idempotency keys and command
metadata. When `HOLLOW_LODGE_ACTION_PROJECTION_READS=1`, inbox and crew-board
pending-decision fallback paths read current actions from the projection only
if it is available and has zero lag. Stale or unavailable projection state
falls back to the existing `ActionService` event replay path. Action
submission, editing, cancellation, crew authorization, phase-lock checks, rumor
outcome events, and artifact unlocks remain authoritative service writes. This
slice advances the projection schema to version `5`.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_projection_store_materializes_current_actions_without_command_metadata tests/server/test_projection_store.py::test_inbox_and_crew_board_read_fresh_action_projection_when_enabled tests/server/test_projection_store.py::test_action_projection_reads_fall_back_when_stale -q`
- `pytest tests/server/test_projection_store.py tests/server/test_app_config.py tests/server/test_action_routes.py tests/server/test_crew_routes.py tests/server/test_pending_decisions.py tests/server/test_contract_seed.py tests/client/test_render_packets.py tests/client/test_codex_session.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 69: Admin Oracle Audit Surface

Status: completed.

Add an operator-facing audit surface for Milestone 3 without widening player
visibility. `GET /admin/oracle/audits` is protected by
`X-Hollow-Lodge-Admin-Token` and returns a redacted list of
`oracle.resolution.*` audit events with sequence, event id, contract, phase,
provider/model/prompt metadata, validation status, failure/fallback fields,
safe crew/standing/warning counts, input packet hash, and accepted output hash.
The route intentionally omits raw oracle input packets, hidden truth, and
accepted model output. The operations guide now documents using the endpoint as
operator evidence for provider behavior and deterministic fallback.

Expected verification:

- `pytest tests/server/test_resolution_oracle.py::test_admin_oracle_audits_require_admin_token_and_omit_raw_outputs tests/server/test_resolution_oracle.py::test_invalid_oracle_result_falls_back_and_is_audited tests/server/test_phase_resolution.py::test_phase_resolution_records_server_only_oracle_audit_events -q`
- `pytest tests/server/test_resolution_oracle.py tests/server/test_phase_resolution.py tests/workflows/test_oracle_boundary.py tests/workflows/test_openai_oracle.py tests/workflows/test_deterministic_oracle.py tests/workflows/test_oracle_factory.py tests/server/test_app_config.py -q`
- `pytest -q`

### Slice 70: Global Projection Read Cutover Switch

Status: completed.

Make the database projection cutover operable as one production switch without
moving authority out of the Eventloom JSONL log. Server configuration now
supports `HOLLOW_LODGE_PROJECTION_READS=1`, which enables every implemented
projection-backed read path while preserving individual surface overrides for
targeted rollback. `/diagnostics` reports the effective projection-read
configuration, and `scripts/smoke_projection_backend.py` can require all
implemented projection read surfaces to be enabled during the hosted Postgres
smoke. Existing per-surface flags remain compatible.

Expected verification:

- `pytest tests/server/test_app_config.py::test_global_projection_read_flag_enables_all_surfaces tests/server/test_app_config.py::test_surface_projection_read_flag_overrides_global_flag tests/server/test_app_config.py::test_projection_read_flag_rejects_invalid_values tests/server/test_projection_store.py::test_contract_board_route_reads_projection_when_global_flag_enabled tests/e2e/test_projection_backend_smoke.py::test_projection_backend_smoke_accepts_available_zero_lag_backend tests/e2e/test_projection_backend_smoke.py::test_projection_backend_smoke_rejects_disabled_projection_read_surfaces -q`
- `pytest tests/server/test_app_config.py tests/server/test_projection_store.py tests/e2e/test_projection_backend_smoke.py -q`
- `pytest -q`

### Slice 71: Admin Oracle Audit CLI

Status: completed.

Make Milestone 3 oracle audit evidence operable from the same first-party admin
CLI used for other production tasks. `HollowLodgeApi` now wraps
`GET /admin/oracle/audits`, and `hollow-lodge admin oracle-audits` prints a
compact redacted row for each oracle audit event: sequence, event type,
contract, phase, provider/model, validation state, fallback state, safe counts,
and packet/output hashes. The CLI intentionally ignores unexpected raw response
fields such as `accepted_output` or hidden truth summaries so operator tooling
does not widen the player-safe audit boundary.

Expected verification:

- `pytest tests/client/test_api.py::test_api_lists_oracle_audits_with_admin_token tests/client/test_cli_commands.py::test_admin_oracle_audits_command_lists_redacted_audits -q`
- `pytest tests/client/test_api.py tests/client/test_cli_commands.py tests/server/test_resolution_oracle.py -q`
- `pytest -q`

### Slice 72: Clean Install Doctor

Status: completed.

Add a first-party local readiness check for the Milestone 5 clean-machine proof
gate. `hollow-lodge doctor` now reports the installed CLI version, selected
server health, registered or pending onboarding state, and whether the Codex MCP
server is registered. The command selects the server from saved player config,
pending onboarding state, or the official default, and it intentionally omits
tokens, invite material, contact handles, and exception details. The public
installer now points users to `hollow-lodge doctor` after install or skipped
onboarding so they can verify server, onboarding, and MCP status.

Expected verification:

- `pytest tests/client/test_api.py::test_api_gets_health_without_auth_headers tests/client/test_codex_mcp_config.py::test_codex_mcp_server_registered_reads_existing_config tests/client/test_cli_commands.py::test_doctor_reports_registered_player_and_mcp_without_secret_material tests/client/test_cli_commands.py::test_doctor_reports_pending_onboarding_without_contact tests/client/test_cli_commands.py::test_doctor_reports_unconfigured_install_and_unreachable_server tests/client/test_installer_script.py::test_install_script_bootstraps_cli_and_runs_onboarding -q`
- `pytest tests/client/test_api.py tests/client/test_cli_commands.py tests/client/test_codex_mcp_config.py tests/client/test_installer_script.py -q`
- `pytest -q`

### Slice 73: Platform Postgres Projection URL

Status: completed.

Make the production database path fit Railway's default environment contract
without weakening explicit configuration. Projection store startup now uses
`HOLLOW_LODGE_PROJECTION_DATABASE_URL` when set, otherwise falls back to
`DATABASE_URL`; `HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION=1` accepts either
Postgres source and still rejects missing or SQLite-backed projection storage.
Postgres projection diagnostics include `database_url_env`, and continue to
redact credentials, so operators can verify whether the Hollow-specific
override or the platform database secret selected the active projection backend.
The authoritative Eventloom JSONL log remains unchanged by this slice.

Expected verification:

- `pytest tests/server/test_app_config.py::test_platform_database_url_selects_postgres_projection_backend tests/server/test_app_config.py::test_explicit_projection_database_url_overrides_platform_database_url tests/server/test_app_config.py::test_require_postgres_projection_accepts_platform_database_url tests/server/test_app_config.py::test_require_postgres_projection_rejects_missing_database_url -q`
- `pytest tests/server/test_app_config.py tests/e2e/test_projection_backend_smoke.py -q`
- `pytest -q`

### Slice 74: Postgres Authoritative Event Store Foundation

Status: completed.

Add a production-oriented Postgres implementation of the authoritative
`EventStore` without changing the default local JSONL backend. The app now
selects JSONL by default and uses Postgres only when
`HOLLOW_LODGE_EVENT_DATABASE_URL` is set explicitly. The Postgres store writes
the same canonical `GameEvent` payload shape, serializes appends under a
transaction-scoped advisory lock, preserves hash-chain validation,
idempotency replay and conflict behavior, visibility-scoped reads, admin
verify/export compatibility, and redacted diagnostics. Identity token/invite
replay files are now rooted in the configured data directory instead of being
derived from a file-backed event store path, so non-file event stores do not
crash during onboarding.

Expected verification:

- `pytest tests/eventlog/test_postgres_store.py tests/eventlog/test_jsonl_store.py tests/server/test_app_config.py::test_diagnostics_reports_safe_operational_status tests/server/test_app_config.py::test_diagnostics_reports_existing_event_log -q`
- `pytest tests/eventlog tests/server/test_app_config.py tests/server/test_identity_routes.py -q`
- `pytest -q`

### Slice 75: Hosted Database Backend Smoke

Status: completed.

Extend the hosted backend smoke so production cutovers can verify both
authoritative event-log storage and projection storage from `/diagnostics`.
`scripts/smoke_projection_backend.py` now accepts
`--expected-event-backend jsonl|postgres`, validates event-log status, rejects
unredacted event-log database URLs, continues to validate projection backend,
freshness, lag, redaction, and optional projection-read surface enablement, and
preserves the existing projection-only validation helper for compatibility.
The operations guide now documents JSONL-event/Postgres-projection and
Postgres-event/Postgres-projection smoke commands separately.

Expected verification:

- `pytest tests/e2e/test_projection_backend_smoke.py -q`
- `pytest tests/e2e/test_projection_backend_smoke.py tests/server/test_app_config.py tests/eventlog/test_postgres_store.py -q`
- `pytest -q`

### Slice 76: Event Log Postgres Migration Utility

Status: completed.

Add an offline migration utility for moving the authoritative event log from a
JSONL/admin-export source into the explicit Postgres event-log backend.
`scripts/migrate_event_log_to_postgres.py` accepts admin export JSON, a raw JSON
array, a single event object, or JSONL rows; `--dry-run` validates the source
chain without requiring a database URL. The Postgres event store now exposes a
guarded `import_events` path that validates the full source chain before
connecting, uses the same advisory lock as appends, refuses non-empty
destinations by default, preserves exact event IDs, sequences, timestamps,
hashes, idempotency keys, and command fingerprints, and prints only redacted
destination URLs. Operations docs now describe verify, export, dry-run, import,
redeploy, and hosted smoke verification.

Expected verification:

- `pytest tests/e2e/test_event_log_migration.py tests/eventlog/test_postgres_store.py -q`
- `pytest tests/e2e/test_event_log_migration.py tests/eventlog tests/server/test_identity_routes.py tests/client/test_cli_commands.py::test_admin_event_log_commands_verify_and_export -q`
- `pytest -q`

### Slice 77: Installed Backend Readiness Command

Status: completed.

Move the hosted database readiness gate into the installed CLI so operators do
not need a repository checkout to verify production storage cutovers.
`hollow-lodge admin backend-smoke` now checks `/health`, fetches public
`/diagnostics`, validates the expected authoritative event-log backend,
projection backend, event-log status, projection status, zero projection lag,
optional projection-read surface enablement, and database URL redaction, then
prints a compact safe status line. The existing
`scripts/smoke_projection_backend.py` now reuses the same package validator so
script and installed-client checks cannot drift.

Expected verification:

- `pytest tests/client/test_api.py::test_api_gets_diagnostics_without_auth_headers tests/client/test_cli_commands.py::test_admin_backend_smoke_command_reports_safe_backend_status tests/client/test_cli_commands.py::test_admin_backend_smoke_command_rejects_unredacted_database_url tests/e2e/test_projection_backend_smoke.py -q`
- `pytest tests/client/test_api.py tests/client/test_cli_commands.py tests/e2e/test_projection_backend_smoke.py -q`
- `pytest -q`

### Slice 78: Installed Event Log Migration Command

Status: completed.

Move the event-log Postgres migration implementation into installed package
code and expose it through `hollow-lodge admin event-log-import-postgres`.
Operators can now validate an admin export with `--dry-run` or import into an
empty `HOLLOW_LODGE_EVENT_DATABASE_URL` destination without checking out the
repository. The existing `scripts/migrate_event_log_to_postgres.py` remains as
a thin wrapper over the package implementation, so script and installed-client
migration behavior share source parsing, hash-chain validation, empty
destination refusal, exact event preservation, and redacted destination output.

Expected verification:

- `pytest tests/client/test_cli_commands.py::test_admin_event_log_import_postgres_dry_run_uses_packaged_migration tests/client/test_cli_commands.py::test_admin_event_log_import_postgres_prints_redacted_destination tests/client/test_cli_commands.py::test_admin_event_log_import_postgres_reports_safe_migration_error tests/e2e/test_event_log_migration.py -q`
- `pytest tests/client/test_cli_commands.py tests/e2e/test_event_log_migration.py tests/eventlog/test_postgres_store.py -q`
- `pytest -q`

### Slice 79: Projection Schema Readiness Gate

Status: completed.

Harden the hosted database readiness smoke against projection schema drift.
`scripts/smoke_projection_backend.py` and `hollow-lodge admin backend-smoke`
now accept `--require-current-projection-schema`, which requires
`/diagnostics` projection metadata to match the installed package's current
projection schema version, latest applied migration, and migration count.
Successful readiness output includes the observed schema and migration count,
and stale hosted projection databases fail before operators enable global
projection reads or enforce Postgres projection storage.

Expected verification:

- `pytest tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py::test_admin_backend_smoke_command_reports_safe_backend_status tests/client/test_cli_commands.py::test_admin_backend_smoke_command_rejects_stale_projection_schema -q`
- `pytest tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py tests/server/test_projection_store.py::test_projection_store_records_schema_migration_ledger -q`
- `pytest -q`

### Slice 80: Backend Sequence Alignment Gate

Status: completed.

Add an explicit sequence-consistency check to the hosted backend readiness
smoke. `scripts/smoke_projection_backend.py` and
`hollow-lodge admin backend-smoke` now accept `--require-sequence-alignment`,
which requires event-log `event_count`, projection `last_sequence`,
projection `authoritative_last_sequence`, and projection `lag` to agree. This
guards database cutovers against internally inconsistent diagnostics where
`lag` alone is zero but the projection has not actually caught up to the
authoritative event stream. Successful readiness output now includes the
event-log count.

Expected verification:

- `pytest tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py::test_admin_backend_smoke_command_reports_safe_backend_status tests/client/test_cli_commands.py::test_admin_backend_smoke_command_rejects_sequence_mismatch -q`
- `pytest tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py tests/server/test_projection_store.py::test_projection_store_records_schema_migration_ledger -q`
- `pytest -q`

### Slice 81: Projection Read Surface Coverage Gate

Status: completed.

Add an explicit installed-package projection read surface coverage check to the
hosted backend readiness smoke. `scripts/smoke_projection_backend.py` and
`hollow-lodge admin backend-smoke` now accept
`--require-current-projection-read-surfaces`, which requires
`/diagnostics.data.projection_reads.surfaces` to contain exactly the projection
read surfaces implemented by the installed package. This catches stale hosted
servers that omit newer projection-backed read paths before operators turn on
`HOLLOW_LODGE_PROJECTION_READS=1`; `--require-projection-reads` still enforces
that the reported surfaces are enabled.

Expected verification:

- `pytest tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py::test_admin_backend_smoke_command_reports_safe_backend_status tests/client/test_cli_commands.py::test_admin_backend_smoke_command_rejects_missing_projection_read_surface -q`
- `pytest tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py tests/server/test_app_config.py::test_global_projection_read_flag_enables_all_surfaces -q`
- `pytest -q`

### Slice 82: Required Postgres Event Log Guard

Status: completed.

Add a production startup invariant for the authoritative Eventloom backend.
`HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG=1` now requires an explicit
`HOLLOW_LODGE_EVENT_DATABASE_URL=postgresql://...` configuration, rejects a
missing event database URL, rejects non-Postgres event-log URLs with redacted
error text, and deliberately does not accept platform `DATABASE_URL` as an
authoritative event-log selector. This lets hosted deployments make Postgres
event storage a hard production invariant after migration without weakening the
append-only Eventloom authority boundary or changing local JSONL defaults.

Expected verification:

- `pytest tests/eventlog/test_postgres_store.py::test_require_postgres_event_log_rejects_missing_event_database_url tests/eventlog/test_postgres_store.py::test_require_postgres_event_log_does_not_accept_platform_database_url tests/eventlog/test_postgres_store.py::test_require_postgres_event_log_allows_explicit_postgres_backend tests/eventlog/test_postgres_store.py::test_require_postgres_event_log_rejects_non_postgres_url_without_secret_leak tests/eventlog/test_postgres_store.py::test_require_postgres_event_log_rejects_invalid_flag_value -q`
- `pytest tests/eventlog/test_postgres_store.py tests/server/test_app_config.py -q`
- `pytest -q`

### Slice 83: Event Log Backup Manifest

Status: completed.

Add a content-safe backup manifest for authoritative Eventloom exports.
`hollow-lodge admin event-log-export` now accepts `--manifest-output` and
validates the exported chain before writing a manifest, while
`hollow-lodge admin event-log-manifest` can validate an existing admin export,
raw event array, or JSONL event file and write the same summary. The manifest
records event count, first and last sequence, first and last event IDs/hashes,
schema versions, and a digest over the event hash chain. It deliberately omits
payloads, actor IDs, visibility principals, idempotency keys, invite hashes,
auth material, and raw event contents so operators can compare backups and
migration sources without opening sensitive exports.

Expected verification:

- `pytest tests/e2e/test_event_log_migration.py::test_event_log_manifest_summarizes_validated_chain_without_payloads tests/client/test_cli_commands.py::test_admin_event_log_export_writes_safe_manifest tests/client/test_cli_commands.py::test_admin_event_log_manifest_command_writes_safe_summary tests/client/test_cli_commands.py::test_admin_event_log_manifest_rejects_corrupted_export -q`
- `pytest tests/e2e/test_event_log_migration.py tests/client/test_cli_commands.py -q`
- `pytest -q`

### Slice 84: Manifest-Bound Event Log Import

Status: completed.

Bind authoritative event-log Postgres migration to the backup manifest when an
operator supplies one. `migrate_event_log_to_postgres`, the repository
`scripts/migrate_event_log_to_postgres.py` wrapper, and
`hollow-lodge admin event-log-import-postgres` now accept a manifest path,
recompute the content-safe manifest from the validated source export, and fail
before dry-run success or Postgres writes if the manifest is missing, invalid,
contains unexpected fields, has an unsupported type/version, or does not match
the source export's count, sequence range, event IDs, event hashes, schema
versions, or chain digest. Successful dry-run/import output reports
`manifest verified` without printing export payloads or credentials.

Expected verification:

- `pytest tests/e2e/test_event_log_migration.py::test_event_log_migration_dry_run_verifies_matching_manifest tests/e2e/test_event_log_migration.py::test_event_log_migration_rejects_mismatched_manifest tests/client/test_cli_commands.py::test_admin_event_log_import_postgres_dry_run_verifies_manifest -q`
- `pytest tests/e2e/test_event_log_migration.py tests/client/test_cli_commands.py -q`
- `pytest -q`

### Slice 85: Hosted Event Log Manifest Smoke

Status: completed.

Add a hosted readiness gate that proves the deployed authoritative event-log
backend is at the expected Eventloom chain head after migration. JSONL and
Postgres event-log diagnostics now include safe `last_sequence` and
`last_event_hash` fields alongside `event_count`. `scripts/smoke_projection_backend.py`
and `hollow-lodge admin backend-smoke` now accept `--event-log-manifest`, load
the content-safe backup manifest, and require hosted diagnostics to match the
manifest's event count, last sequence, and last event hash before reporting
readiness. The gate does not expose payloads, actors, visibility principals,
idempotency keys, invite hashes, auth material, or raw events.

Expected verification:

- `pytest tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_accepts_event_log_manifest_chain_head tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_rejects_event_log_manifest_chain_head_mismatch tests/client/test_cli_commands.py::test_admin_backend_smoke_command_verifies_event_log_manifest tests/eventlog/test_jsonl_store.py::test_jsonl_event_store_diagnostics_include_event_count tests/eventlog/test_postgres_store.py::test_postgres_event_store_diagnostics_redact_database_url -q`
- `pytest tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py tests/eventlog tests/server/test_app_config.py -q`
- `pytest -q`

### Slice 86: Storage Guard Readiness Smoke

Status: completed.

Make production storage invariants observable from hosted diagnostics and
enforceable from the same backend readiness smoke used for database cutovers.
`/diagnostics.data.storage_guards` now reports whether the deployed process has
`HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG` and
`HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION` enabled.
`scripts/smoke_projection_backend.py` and
`hollow-lodge admin backend-smoke` accept
`--require-postgres-event-log-guard` and
`--require-postgres-projection-guard`, failing unless diagnostics prove the
corresponding startup guard is active.

Expected verification:

- `pytest tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_accepts_event_and_projection_backends tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_rejects_missing_required_storage_guards tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_rejects_disabled_required_storage_guards tests/client/test_cli_commands.py::test_admin_backend_smoke_command_verifies_required_storage_guards tests/client/test_cli_commands.py::test_admin_backend_smoke_command_rejects_disabled_event_log_guard tests/server/test_app_config.py::test_diagnostics_reports_safe_operational_status -q`
- `pytest tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py tests/server/test_app_config.py -q`
- `pytest -q`

### Slice 87: Event Log Restore Drill

Status: completed.

Close the production backup loop by making local JSONL restore an installed
operator command and proving the restored chain can boot a fresh server.
`JsonlEventStore.import_events` writes validated exported events into an empty
destination while preserving event IDs, sequence numbers, hashes, timestamps,
idempotency metadata, and command fingerprints exactly. The package restore
helper and `hollow-lodge admin event-log-restore-jsonl` verify an optional
backup manifest before writing, refuse non-empty destinations, and print only
event count plus chain-head metadata. The e2e drill restores an export into a
clean data directory and verifies app diagnostics report the same last
sequence and event hash.

Expected verification:

- `pytest tests/e2e/test_event_log_migration.py::test_event_log_restore_jsonl_drill_boots_fresh_server_at_chain_head tests/client/test_cli_commands.py::test_admin_event_log_restore_jsonl_writes_empty_destination_with_manifest tests/client/test_cli_commands.py::test_admin_event_log_restore_jsonl_refuses_non_empty_destination tests/eventlog/test_jsonl_store.py::test_jsonl_event_store_import_preserves_exported_chain tests/eventlog/test_jsonl_store.py::test_jsonl_event_store_import_refuses_non_empty_destination -q`
- `pytest tests/e2e/test_event_log_migration.py tests/client/test_cli_commands.py tests/eventlog/test_jsonl_store.py -q`
- `pytest -q`

### Slice 88: Projection Refresh Failure Diagnostics

Status: completed.

Make projection refresh health observable without making projection refresh
part of the authoritative write path. Mutation routes now share one
best-effort refresh helper. Successful refreshes record the context and last
successfully projected event sequence; failures preserve mutation success but
record a bounded diagnostic with status, failure count, failure context, and
exception type only. `/diagnostics.data.projection_refresh` exposes that state
without raw exception messages, connection strings, event payloads, or auth
material, giving operators a clear signal when projection-backed reads may be
stale after an authoritative Eventloom write.

Expected verification:

- `pytest tests/server/test_app_config.py::test_diagnostics_reports_safe_operational_status tests/server/test_projection_store.py::test_contract_mutation_still_succeeds_when_projection_refresh_fails -q`
- `pytest tests/server/test_app_config.py tests/server/test_projection_store.py tests/server/test_contract_seed.py tests/server/test_action_routes.py tests/server/test_chat_routes.py tests/server/test_deal_routes.py tests/server/test_proof_routes.py tests/server/test_crew_routes.py tests/server/test_artifact_routes.py tests/server/test_identity_routes.py -q`
- `pytest -q`

### Slice 89: Projection Refresh Readiness Smoke

Status: completed.

Make projection refresh diagnostics actionable during hosted database cutover.
`scripts/smoke_projection_backend.py` and
`hollow-lodge admin backend-smoke` now accept
`--require-projection-refresh-ok`, which requires
`/diagnostics.data.projection_refresh.status` to be `ok`. Failed refresh
readiness reports include only bounded, safe metadata: refresh status, failure
context, and exception type. Raw exception messages, connection strings,
payloads, and auth material remain out of smoke output.

This closes the operational loop from Slice 88: production can now fail a
readiness gate when authoritative writes have succeeded but projection-backed
reads may be stale after a failed refresh.

Expected verification:

- `pytest tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_accepts_event_and_projection_backends tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_rejects_failed_projection_refresh tests/client/test_cli_commands.py::test_admin_backend_smoke_command_reports_safe_backend_status tests/client/test_cli_commands.py::test_admin_backend_smoke_command_rejects_failed_projection_refresh -q`
- `pytest tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py tests/server/test_app_config.py -q`
- `pytest -q`

### Slice 90: Hosted Event Log Chain Digest Smoke

Status: completed.

Strengthen manifest-backed production storage cutover checks beyond event
count, last sequence, and last event hash. JSONL and Postgres event-log
diagnostics now expose the same content-safe `event_hash_chain_sha256` digest
used by backup manifests. When `--event-log-manifest` is supplied,
`scripts/smoke_projection_backend.py` and
`hollow-lodge admin backend-smoke` require the hosted diagnostics digest to
match the manifest digest before reporting readiness.

The digest summarizes only sequence, event id, event hash, and previous hash
rows. It does not expose payloads, actor IDs, visibility principals,
idempotency keys, invite hashes, auth material, or raw event contents.

Expected verification:

- `pytest tests/eventlog/test_jsonl_store.py::test_jsonl_event_store_diagnostics_include_event_count tests/eventlog/test_postgres_store.py::test_postgres_event_store_diagnostics_redact_database_url tests/eventlog/test_postgres_store.py::test_postgres_event_store_diagnostics_include_chain_digest tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_accepts_event_log_manifest_chain_head tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_rejects_event_log_manifest_chain_digest_mismatch tests/client/test_cli_commands.py::test_admin_backend_smoke_command_verifies_event_log_manifest -q`
- `pytest tests/eventlog tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py tests/server/test_app_config.py -q`
- `pytest -q`

### Slice 91: Visible Rumor Projection Reads

Status: completed.

Move crew-board visible rumor reads onto the projection database without
widening leak visibility or moving rumor authority out of the Eventloom log.
SQLite and Postgres projection stores now materialize safe
`visible_rumor_surface` rows per crew using only the whitelisted rumor fields:
rumor id, source summary fields, contract id, suspected crew ids, pressure,
and leak vector. The projection omits raw chat bodies, private deal terms,
artifact ids, idempotency keys, and non-whitelisted event payload fields.

When `HOLLOW_LODGE_RUMOR_PROJECTION_READS=1`, `/crews/{crew_id}/board` reads
visible rumors from the projection only when the projection is available and
has zero lag. Stale or unavailable projections fall back to the existing
event-log visibility replay path. This advances the projection schema to
version `6`.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_projection_store_materializes_visible_rumors_without_private_sources tests/server/test_projection_store.py::test_crew_board_embeds_projected_visible_rumors_when_enabled tests/server/test_projection_store.py::test_crew_board_visible_rumors_fall_back_when_projection_is_stale -q`
- `pytest tests/server/test_projection_store.py tests/server/test_crew_routes.py tests/server/test_chat_routes.py tests/server/test_deal_routes.py tests/server/test_app_config.py tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py -q`
- `pytest -q`

### Slice 92: Inbox Rumor Projection Reads

Status: completed.

Reuse the safe visible-rumor projection for inbox pending-decision fallback
without changing the authoritative Eventloom write path. When
`HOLLOW_LODGE_RUMOR_PROJECTION_READS=1`, `/inbox` now supplies local
pending-decision calculation with `visible_rumor_surface` rows only if the
projection is available and has zero lag. Stale or unavailable projection state
falls back to the existing crew-scoped event-log visibility replay.

This slice does not advance the projection schema because it reuses the
version `6` rumor read model from Slice 91. It also avoids building replayed
rumor inputs when `HOLLOW_LODGE_PENDING_DECISION_PROJECTION_READS=1` has
already supplied fresh pending decisions.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_inbox_pending_decisions_use_projected_visible_rumors_when_enabled tests/server/test_projection_store.py::test_inbox_visible_rumors_fall_back_when_projection_is_stale -q`
- `pytest tests/server/test_projection_store.py tests/server/test_crew_routes.py tests/server/test_chat_routes.py tests/server/test_deal_routes.py tests/server/test_app_config.py tests/client/test_render_packets.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 93: Projection Readiness Cache

Status: completed.

Reduce repeated authoritative event-log replays during projection-backed read
requests. Projected read helpers now share a request-scoped freshness check:
the first enabled projection surface on a request reads the authoritative chain
head, asks the projection store for diagnostics, and caches that bounded
diagnostic packet on `request.state`. Subsequent projection surfaces in the
same request reuse the cached status and lag result before reading their
projection table.

This keeps the Eventloom log authoritative and keeps stale/unavailable
projection fallback semantics unchanged, while avoiding one full event-log read
per enabled projection surface on dense Codex surfaces such as `/inbox` and
crew boards. No projection schema change is required.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_inbox_projection_reads_share_request_freshness_check tests/server/test_projection_store.py::test_inbox_and_crew_board_read_fresh_pending_decision_projection_when_enabled tests/server/test_projection_store.py::test_contract_board_route_reads_projection_when_global_flag_enabled tests/server/test_projection_store.py::test_crew_board_reads_fresh_projected_crew_summary_when_enabled -q`
- `pytest tests/server/test_projection_store.py tests/server/test_app_config.py tests/server/test_crew_routes.py tests/server/test_contract_seed.py tests/server/test_deal_routes.py tests/server/test_chat_routes.py tests/server/test_event_sync.py tests/server/test_artifact_routes.py tests/server/test_proof_routes.py tests/client/test_render_packets.py tests/test_mcp_server.py tests/e2e/test_projection_backend_smoke.py -q`
- `pytest -q`

### Slice 94: Lazy Inbox Decision Fallback Inputs

Status: completed.

Avoid preparing event-log-derived local pending-decision inputs when `/inbox`
has already obtained fresh projected pending decisions. The inbox route now
defers crew-specific deal maps, event-log replay data, and crew legacy
derivation until the pending-decision projection is unavailable or stale. This
keeps projected read behavior identical, preserves fallback behavior, and
removes unnecessary replay work from the common database-backed inbox path.

No projection schema change is required; this is a route-level cutover cleanup
for the existing `pending_decision_surface`.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_inbox_skips_local_decision_inputs_when_pending_projection_is_fresh tests/server/test_projection_store.py::test_inbox_projection_reads_share_request_freshness_check tests/server/test_projection_store.py::test_pending_decision_projection_reads_fall_back_when_stale -q`
- `pytest tests/server/test_projection_store.py tests/server/test_contract_seed.py tests/server/test_crew_routes.py tests/server/test_deal_routes.py tests/server/test_chat_routes.py tests/server/test_app_config.py tests/client/test_render_packets.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 95: Postgres Event-Log Metadata Diagnostics

Status: completed.

Make hosted database diagnostics scale with the authoritative Eventloom log.
Postgres event-log diagnostics now read only sequence, event id, event hash,
and previous hash metadata to validate chain continuity and compute the same
content-safe `event_hash_chain_sha256` used by backup manifests. They no
longer load full `event_json` payloads during `/diagnostics`, avoiding an
operator-read path that grows with payload size while preserving manifest smoke
semantics.

This does not weaken authoritative validation for gameplay reads, imports, or
integrity verification: those paths still validate full events and recompute
event hashes from canonical payloads. The diagnostics path fails closed as
`unavailable` if the stored metadata chain has a sequence gap or previous-hash
break.

Expected verification:

- `pytest tests/eventlog/test_postgres_store.py::test_postgres_event_store_diagnostics_include_chain_digest tests/eventlog/test_postgres_store.py::test_postgres_event_store_diagnostics_reports_unavailable_for_chain_break -q`
- `pytest tests/eventlog/test_postgres_store.py tests/e2e/test_projection_backend_smoke.py tests/server/test_app_config.py -q`
- `pytest -q`

### Slice 96: Projection Readiness Chain-Head Diagnostics

Status: completed.

Remove a full Eventloom replay from the common projection-backed read path.
Shared projection readiness now asks the authoritative event store for its
safe diagnostics chain head and passes that `last_sequence` to projection
diagnostics. Freshness checks still require the projection to be available and
zero-lag, but they no longer call `event_store.read()` just to discover the
authoritative sequence.

This compounds the Slice 95 Postgres improvement: in production, the readiness
check can use metadata-only Postgres event-log diagnostics, while actual
gameplay fallbacks, writes, imports, and integrity checks continue to validate
or replay full events where that authority is required. If event-log
diagnostics are unavailable or malformed, projection readiness fails closed and
the existing route fallback behavior remains in force.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_projection_readiness_uses_event_log_diagnostics_without_replay tests/server/test_projection_store.py::test_projection_readiness_falls_back_when_event_log_diagnostics_unavailable tests/server/test_projection_store.py::test_deal_route_reads_fresh_projected_visible_deals_when_enabled tests/server/test_projection_store.py::test_deal_route_falls_back_when_projection_is_stale -q`
- `pytest tests/server/test_projection_store.py tests/server/test_app_config.py tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py -q`
- `pytest -q`

### Slice 97: Request-Scoped Eventloom Read Reuse

Status: completed.

Reduce repeated authoritative log replays inside dense Codex-facing read
surfaces without changing the Eventloom authority boundary. Read-only route
helpers now share `read_authoritative_events(request)`, a request-scoped
snapshot used for fallback-only derivations such as contract unlock status,
inbox pending-decision legacy context, and crew-board legacy fallback.

This is deliberately not a mutable cache and not a replacement for projected
read models. The cache lasts only for the current request. Mutations,
projection refreshes, imports, and integrity checks still read the authoritative
event store directly. The larger future slice remains crew-specific unlock
status projection; this slice removes duplicate work in the existing fallback
paths.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_inbox_fallback_reuses_authoritative_events_with_projection_reads tests/server/test_projection_store.py::test_inbox_skips_local_decision_inputs_when_pending_projection_is_fresh tests/server/test_projection_store.py::test_pending_decision_projection_reads_fall_back_when_stale -q`
- `pytest tests/server/test_projection_store.py tests/server/test_contract_seed.py tests/server/test_crew_routes.py tests/server/test_deal_routes.py tests/server/test_chat_routes.py tests/server/test_app_config.py tests/client/test_render_packets.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 98: Crew Contract Unlock Projection

Status: completed.

Move crew-specific contract unlock status onto the projection database read
side. Projection rebuilds now materialize `contract_unlock_surface` rows keyed
by crew and contract, storing only the player-safe `unlock_status` payload. The
surface omits raw `unlock_requirements`, hidden truth, server notes, artifact
graph internals, and private event payloads.

`/contracts` and crew boards can read this surface with
`HOLLOW_LODGE_CONTRACT_UNLOCK_PROJECTION_READS=1` when projection diagnostics
show zero lag. If the projection is stale, unavailable, disabled, or missing
crew ids, the routes keep the existing Eventloom-derived fallback. Multi-crew
contract boards merge projected statuses deterministically, preferring an
unlocked status and then the status with the most satisfied requirements.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_projection_store_materializes_contract_unlocks_without_hidden_rules tests/server/test_projection_store.py::test_contract_board_applies_fresh_projected_unlock_statuses tests/server/test_projection_store.py::test_contract_unlock_projection_falls_back_when_stale tests/server/test_projection_store.py::test_crew_board_applies_fresh_projected_unlock_statuses -q`
- `pytest tests/server/test_projection_store.py tests/server/test_contract_seed.py tests/server/test_crew_routes.py tests/server/test_deal_routes.py tests/server/test_app_config.py tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py tests/client/test_render_packets.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 99: Diagnostics Projection Lag Chain-Head

Status: completed.

Remove the extra authoritative Eventloom replay from `/diagnostics` projection
lag reporting. The diagnostics route now computes event-log diagnostics once,
passes that safe `last_sequence` into projection diagnostics, and reports
projection lag from the same chain head already shown in the event-log status
block.

If event-log diagnostics are unavailable or return a malformed chain head,
projection diagnostics fail closed for lag reporting by marking the projection
status unavailable and setting `authoritative_last_sequence` and `lag` to null.
This preserves operational visibility without claiming a fresh read model when
the source-of-truth chain head cannot be established.

Expected verification:

- `pytest tests/server/test_app_config.py::test_diagnostics_uses_event_log_diagnostics_for_projection_lag tests/server/test_app_config.py::test_diagnostics_marks_projection_unavailable_when_event_log_head_unavailable -q`
- `pytest tests/server/test_app_config.py tests/server/test_projection_store.py tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py -q`
- `pytest -q`

### Slice 100: Admin Oracle Audit Projection Reads

Status: completed.

Move the admin oracle audit surface onto the projection database read side
without widening player visibility or moving oracle authority out of the
Eventloom log. SQLite and Postgres projection stores now materialize one
redacted `oracle_audit_surface` row for each `oracle.resolution.*` audit event.
Rows include only operator-safe fields already exposed by the admin audit API:
sequence, event id, event type, contract, phase, provider/model/prompt
metadata, validation and fallback fields, safe count fields, input packet hash,
and accepted output hash.

`GET /admin/oracle/audits` can read this surface with
`HOLLOW_LODGE_ORACLE_AUDIT_PROJECTION_READS=1` when projection diagnostics show
zero lag. If the projection is stale, unavailable, disabled, or raises during
the projected read, the route keeps the existing Eventloom replay fallback. The
projection intentionally omits raw oracle input packets, hidden truth, prompt
packets, raw provider output, accepted model output, and provider exception
messages. This slice advances the projection schema to version `8`.

Expected verification:

- `pytest tests/server/test_resolution_oracle.py::test_projection_store_materializes_redacted_oracle_audits tests/server/test_resolution_oracle.py::test_admin_oracle_audits_read_fresh_projection_when_enabled tests/server/test_resolution_oracle.py::test_admin_oracle_audits_fall_back_when_projection_is_stale -q`
- `pytest tests/server/test_resolution_oracle.py tests/server/test_phase_resolution.py tests/server/test_projection_store.py tests/server/test_app_config.py tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py tests/client/test_api.py -q`
- `pytest -q`

### Slice 101: Artifact Inspection Projection Reads

Status: completed.

Move single-artifact inspection reads onto the projection database without
weakening the source-material gameplay loop. SQLite and Postgres projection
stores now materialize an artifact inspection read model separate from the
shallow visible-artifact list. Public artifact rows include the same
player-visible source text and source-chain fields returned by
`GET /artifacts/{artifact_id}`; scoped rows preserve crew/player visibility for
granted, transferred, and deal-copied artifacts.

`GET /artifacts/{artifact_id}` uses the projection with
`HOLLOW_LODGE_ARTIFACT_PROJECTION_READS=1` only when diagnostics show zero lag.
If the projection is stale, unavailable, disabled, or rejects the requested
artifact, the route keeps the existing Eventloom-derived `ArtifactService`
fallback. The inspection projection intentionally omits hidden flags, hidden
truth, server notes, and artifact graph internals while preserving inspectable
source material. This slice advances the projection schema to version `9`.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_projection_store_materializes_artifact_inspections_without_hidden_fields tests/server/test_projection_store.py::test_artifact_inspection_route_reads_fresh_projection_when_enabled tests/server/test_projection_store.py::test_artifact_inspection_route_falls_back_when_projection_is_stale -q`
- `pytest tests/server/test_projection_store.py tests/server/test_artifact_routes.py tests/server/test_app_config.py tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py tests/client/test_api.py -q`
- `pytest -q`

### Slice 102: Proof Fragment Projection Reads

Status: completed.

Move player proof-fragment lookup onto the projection database without changing
the provenance-check action boundary. SQLite and Postgres projection stores now
materialize `proof_fragment_surface` rows keyed by player and fragment id.
Rows contain only the same safe fragment surface returned by
`GET /proofs/fragments/{fragment_id}`: fragment id, content summary,
source-chain entries, and provenance checked state.

`GET /proofs/fragments/{fragment_id}` can read this surface with
`HOLLOW_LODGE_PROOF_FRAGMENT_PROJECTION_READS=1` when projection diagnostics
show zero lag. If the projection is stale, unavailable, disabled, or missing
the requested player/fragment pair, the route keeps the existing
Eventloom-derived `ProofService` fallback. The projection intentionally omits
provenance flags such as copied-hand and ink-after-binding; those remain
exposed only by the explicit provenance-check command. Proof fragment transfer
and provenance-check mutations now refresh projections so the read surface can
stay zero-lag after proof commands. This slice advances the projection schema
to version `10`.

Expected verification:

- `pytest tests/server/test_projection_store.py::test_projection_store_materializes_proof_fragments_without_provenance_flags tests/server/test_projection_store.py::test_proof_fragment_route_reads_fresh_projection_when_enabled tests/server/test_projection_store.py::test_proof_fragment_route_falls_back_when_projection_is_stale tests/server/test_projection_store.py::test_proof_fragment_transfer_refreshes_projection_for_flagged_reads -q`
- `pytest tests/server/test_projection_store.py tests/server/test_proof_routes.py tests/server/test_app_config.py tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py tests/client/test_api.py -q`
- `pytest -q`

### Slice 103: Postgres Event-Log Append Hardening

Status: completed.

Harden the hosted authoritative Eventloom backend by removing the full
`event_json` replay from ordinary Postgres appends. The append path now takes
the existing advisory transaction lock, validates sequence and previous-hash
metadata from the structured event-log columns, performs idempotent command
replay through an indexed idempotency-key lookup, and appends from the current
chain head. This keeps the append-only authority boundary intact while reducing
write-path payload replay before production Postgres cutover.

Full payload/hash validation remains on read, verify, export, and import
paths. Idempotent replays still validate chain metadata before returning an
existing command event, so a broken metadata chain fails closed rather than
silently replaying a command.

Expected verification:

- `pytest tests/eventlog/test_postgres_store.py -q`
- `pytest tests/eventlog/test_postgres_store.py tests/eventlog/test_jsonl_store.py tests/client/test_cli_commands.py tests/server/test_app_config.py tests/e2e/test_projection_backend_smoke.py -q`
- `pytest -q`

### Slice 104: Postgres Event-Log Head Payload Guard

Status: completed.

Strengthen the hosted authoritative Eventloom append path after the metadata
fast path. Postgres appends now validate the current head event payload against
its stored event hash and metadata before extending a non-empty chain. Targeted
idempotent command replays also validate the returned event payload hash before
returning the existing event.

This keeps Slice 103's no-full-replay write path intact while preventing a new
write from extending a chain whose latest payload row has been tampered with.
Full-log payload/hash validation remains on read, verify, export, import, and
manifest workflows.

Expected verification:

- `pytest tests/eventlog/test_postgres_store.py -q`
- `pytest tests/eventlog/test_postgres_store.py tests/eventlog/test_jsonl_store.py tests/client/test_cli_commands.py tests/server/test_app_config.py tests/e2e/test_projection_backend_smoke.py -q`
- `pytest -q`

### Slice 105: Event-Log Manifest Document Validation

Status: completed.

Tighten production storage cutover readiness by validating backup manifest
documents before using them as smoke-test evidence. Manifest loading now rejects
wrong manifest types, unsupported versions, missing required fields, and
unexpected fields. `hollow-lodge admin backend-smoke --event-log-manifest` and
the shared backend-smoke validator apply the same manifest document validation
before comparing hosted event-log diagnostics to the expected chain head and
chain digest.

This prevents a malformed local manifest file or in-memory manifest dict from
being treated as proof that the hosted Eventloom backend is at the expected
backup chain.

Expected verification:

- `pytest tests/e2e/test_event_log_migration.py::test_event_log_manifest_loader_rejects_manifest_with_missing_fields tests/e2e/test_event_log_migration.py::test_event_log_manifest_loader_rejects_manifest_with_unexpected_fields tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_rejects_malformed_event_log_manifest tests/client/test_cli_commands.py::test_admin_backend_smoke_command_rejects_malformed_event_log_manifest -q`
- `pytest tests/e2e/test_event_log_migration.py tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py -q`
- `pytest -q`

### Slice 106: Postgres Event-Log Bounded Payload Reads

Status: completed.

Reduce hosted event-sync and visibility-filter read cost before full production
Postgres cutover. Bounded `PostgresEventStore.read(start_sequence=...,
end_sequence=...)` now validates the full structured sequence/hash metadata
chain, then loads only the requested `event_json` payload rows. Returned
payloads are still hash-validated and checked against their metadata rows, so a
range read fails closed on selected payload tampering or chain metadata breaks.

Unbounded reads, integrity checks, imports, and exports keep full payload-chain
validation. The optimization is limited to bounded reads where callers already
ask for a sequence window.

Expected verification:

- `pytest tests/eventlog/test_postgres_store.py -q`
- `pytest tests/eventlog/test_postgres_store.py tests/eventlog/test_jsonl_store.py tests/server/test_event_sync.py tests/client/test_cli_commands.py tests/e2e/test_projection_backend_smoke.py -q`
- `pytest -q`

### Slice 107: Storage Guard Backend Consistency Smoke

Status: completed.

Tighten production database cutover evidence so readiness smoke fails closed on
inconsistent storage diagnostics. When
`--require-postgres-event-log-guard` is set, backend smoke now requires both
`/diagnostics.data.storage_guards.require_postgres_event_log=true` and
`/diagnostics.data.event_log.backend=postgres`. When
`--require-postgres-projection-guard` is set, it requires both the projection
guard flag and `data.projection_db.backend=postgres`.

This keeps guard-required smoke runs from accepting contradictory diagnostics
such as a JSONL event backend with the Postgres event-log guard supposedly
enabled, or a SQLite projection backend with the Postgres projection guard
supposedly enabled.

Expected verification:

- `pytest tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_rejects_event_log_guard_with_non_postgres_backend tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_rejects_projection_guard_with_non_postgres_backend tests/client/test_cli_commands.py::test_admin_backend_smoke_command_verifies_required_storage_guards tests/client/test_cli_commands.py::test_admin_backend_smoke_command_rejects_event_log_guard_backend_mismatch -q`
- `pytest tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py tests/server/test_app_config.py -q`
- `pytest -q`

### Slice 108: Safe Startup Projection Bootstrap Failures

Status: completed.

Harden configured-storage startup for production Postgres cutovers. Server
startup still fails fast if authoritative event replay or the initial
projection rebuild fails, but the raised error now reports only the bootstrap
stage and exception type. Raw database URLs, provider messages, invite codes,
and other secret-bearing exception text are not included in the startup error
message.

This covers both identity-service event replay during service construction and
the configured-storage projection rebuild that runs before the app starts
serving requests.

Expected verification:

- `pytest tests/server/test_app_config.py::test_startup_event_replay_failure_reports_safe_context tests/server/test_app_config.py::test_startup_projection_rebuild_failure_reports_safe_context -q`
- `pytest tests/server/test_app_config.py tests/server/test_projection_store.py tests/eventlog/test_postgres_store.py -q`
- `pytest -q`

### Slice 109: Safe Diagnostics Collection Fallbacks

Status: completed.

Make `/diagnostics` resilient to unexpected diagnostics-provider failures. If
`event_store.diagnostics()` raises, the endpoint now returns a safe
`event_log.status=unavailable` block with backend/path metadata when available,
safe counts, and exception type only. If `projection_store.diagnostics()`
raises, the endpoint returns a safe `projection_db.status=unavailable` block
with the known authoritative sequence, lag when computable, zeroed counts, and
exception type only.

This keeps hosted readiness checks from turning into HTTP 500s or leaking raw
database/provider error text while still failing readiness smoke through
unavailable status and nonzero/unknown lag.

Expected verification:

- `pytest tests/server/test_app_config.py::test_diagnostics_reports_safe_unavailable_event_log_on_unexpected_error tests/server/test_app_config.py::test_diagnostics_reports_safe_unavailable_projection_on_unexpected_error -q`
- `pytest tests/server/test_app_config.py tests/server/test_projection_store.py tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py -q`
- `pytest -q`

### Slice 110: Profile Crew Legacy Summaries

Status: completed.

Make the persistent player profile carry safe long-term crew history, not just
identity and membership data. `/identity/profile` now includes one shaped
`legacy` snapshot for each crew the player belongs to: reputation, heat,
favors, debts, scars, deal conduct, counterintelligence, rumor memory, rumor
escalation, completed contracts, and future opportunities. The endpoint uses
the crew-legacy projection when `HOLLOW_LODGE_CREW_LEGACY_PROJECTION_READS=1`
is enabled and fresh, then falls back to one request-scoped authoritative
Eventloom read.

The Codex/MCP profile render packet now shows a compact legacy line and
completed-contract summaries per crew while keeping hidden source fields,
join codes, token hashes, raw invite data, and private evidence out of both
markdown and agent context.

Expected verification:

- `pytest tests/server/test_identity_routes.py::test_player_profile_returns_safe_crew_memberships_without_auth_material tests/server/test_identity_routes.py::test_player_profile_includes_safe_crew_legacy_without_hidden_sources tests/server/test_identity_routes.py::test_player_profile_reads_fresh_projected_crew_legacy_when_enabled tests/client/test_render_packets.py::test_profile_packet_renders_persistent_identity_and_crew_memberships_without_hidden_fields -q`
- `pytest tests/server/test_identity_routes.py tests/server/test_crew_legacy_projection.py tests/server/test_projection_store.py tests/client/test_render_packets.py tests/client/test_codex_session.py tests/client/test_api.py tests/test_mcp_server.py -q`
- `pytest -q`

### Slice 111: Production Postgres Smoke Preset

Status: completed.

Make the production database cutover less error-prone by adding a single
installed-client and checkout-script readiness preset. `hollow-lodge admin
backend-smoke --production-postgres` and `scripts/smoke_projection_backend.py
--production-postgres` now require the full production database invariant:
Postgres authoritative event log, Postgres projection database, both Postgres
startup guards, all implemented projection reads enabled, current projection
schema, aligned authoritative/projection sequences, zero projection lag, and a
successful latest projection refresh. Slice 117 later tightens the same preset
to prove the server is back in read/write mode after a maintenance window.

The preset rejects contradictory backend flags instead of silently overriding
them. Explicit staged-cutover flags remain available for local development,
projection-only cutovers, and pre-guard verification.

Expected verification:

- `pytest tests/client/test_cli_commands.py::test_admin_backend_smoke_command_accepts_production_postgres_preset tests/client/test_cli_commands.py::test_admin_backend_smoke_command_rejects_conflicting_production_preset tests/e2e/test_projection_backend_smoke.py::test_run_smoke_production_postgres_preset_forwards_required_checks -q`
- `pytest tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py tests/server/test_app_config.py -q`
- `pytest -q`

### Slice 112: Hosted Projection Read Cutover

Status: completed.

Deploy the current server to Railway and enable projection-backed reads on the
live `hollow-lodge-server` service. Production now runs current diagnostics and
projection schema `10`, uses Postgres for the projection database, keeps the
authoritative event log on JSONL for the next staged event-log migration, has
`HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION=1` enforced, and has
`HOLLOW_LODGE_PROJECTION_READS=1` enabled across all implemented read surfaces.

The production readiness evidence is the staged smoke gate for the actual
current storage topology: Postgres projections plus JSONL authoritative
Eventloom. The full `--production-postgres` preset remains intentionally red
until the separate authoritative event-log Postgres migration is performed and
`HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG=1` is enabled.

Expected verification:

- `railway up --service hollow-lodge-server --detach`
- `railway variable set --service hollow-lodge-server HOLLOW_LODGE_PROJECTION_READS=1`
- `python scripts/smoke_projection_backend.py --server-url https://server.thehollowlodge.com --expected-backend postgres --expected-event-backend jsonl --require-projection-reads --require-current-projection-read-surfaces --require-current-projection-schema --require-sequence-alignment --require-projection-refresh-ok --require-postgres-projection-guard`
- Render a live MCP inbox for `corelumen` and confirm the contract surface loads
  through the deployed server after projection reads are enabled.

### Slice 113: Event Log Migration Read-Only Mode

Status: completed.

Add an explicit server read-only maintenance mode for the final authoritative
event-log Postgres migration. `HOLLOW_LODGE_MAINTENANCE_READ_ONLY=1` now lets
operators freeze mutating HTTP commands before taking the production JSONL
export, generating its manifest, importing to Postgres, and switching
`HOLLOW_LODGE_EVENT_DATABASE_URL`. The guard keeps GET/HEAD/OPTIONS paths
available so `/health`, `/diagnostics`, event-log verification, and event-log
export still work while gameplay/admin mutations return a bounded HTTP 503
with `Retry-After`.

`/diagnostics.data.maintenance` reports whether read-only mode is active and
names the controlling environment variable. Invalid flag values fail fast at
startup so production cannot silently boot in an ambiguous migration state.

Expected verification:

- `pytest tests/server/test_app_config.py::test_read_only_maintenance_allows_reads_and_blocks_mutations tests/server/test_app_config.py::test_diagnostics_reports_read_write_maintenance_state tests/server/test_app_config.py::test_read_only_maintenance_rejects_invalid_flag -q`
- `pytest tests/server/test_app_config.py tests/server/test_identity_routes.py tests/client/test_cli_commands.py -q`
- `pytest -q`

### Slice 114: Maintenance Freeze Smoke Gate

Status: completed.

Make the final event-log migration freeze verifiable from the same hosted
backend smoke used for storage cutovers. `hollow-lodge admin backend-smoke` and
`scripts/smoke_projection_backend.py` now accept
`--require-maintenance-read-only`, which fails unless
`/diagnostics.data.maintenance.read_only=true`.

This catches two dangerous operator mistakes before the authoritative JSONL
export: deploying an older server that does not expose maintenance diagnostics,
or forgetting to enable `HOLLOW_LODGE_MAINTENANCE_READ_ONLY=1` before taking
the final backup and manifest. The check is additive and does not change
normal production or local development smoke commands.

Expected verification:

- `pytest tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_accepts_required_maintenance_read_only tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_rejects_disabled_required_maintenance_read_only tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_rejects_missing_required_maintenance_diagnostics tests/client/test_cli_commands.py::test_admin_backend_smoke_command_accepts_required_maintenance_read_only tests/client/test_cli_commands.py::test_admin_backend_smoke_command_rejects_missing_required_maintenance -q`
- `pytest tests/e2e/test_projection_backend_smoke.py tests/client/test_cli_commands.py tests/server/test_app_config.py -q`
- `pytest -q`

### Slice 115: Hosted Maintenance Diagnostics Deployment

Status: completed.

Deploy the maintenance diagnostics and freeze-smoke support to the live
`hollow-lodge-server` service without enabling read-only mode yet. Production
now exposes `/diagnostics.data.maintenance` with
`read_only=false`, while the normal staged projection-read smoke still passes
for the current topology: JSONL authoritative Eventloom plus Postgres
projections.

This confirms the server is ready for the next event-log migration step. The
pre-export freeze smoke with `--require-maintenance-read-only` intentionally
fails until `HOLLOW_LODGE_MAINTENANCE_READ_ONLY=1` is set for the actual
maintenance window.

Expected verification:

- `railway up --service hollow-lodge-server --detach`
- `curl -fsS https://server.thehollowlodge.com/diagnostics` reports
  `data.maintenance.read_only=false`
- `python scripts/smoke_projection_backend.py --server-url https://server.thehollowlodge.com --expected-backend postgres --expected-event-backend jsonl --require-projection-reads --require-current-projection-read-surfaces --require-current-projection-schema --require-sequence-alignment --require-projection-refresh-ok --require-postgres-projection-guard`
- `python scripts/smoke_projection_backend.py --server-url https://server.thehollowlodge.com --expected-backend postgres --expected-event-backend jsonl --require-maintenance-read-only` fails with `maintenance read-only mode is not enabled`

### Slice 116: Hosted Event Log Postgres Cutover

Status: completed.

Freeze the live server, export the authoritative JSONL Eventloom, verify its
content-safe manifest, import the frozen chain into Railway Postgres from
inside the deployed service network, and switch production to the Postgres
event backend. The cutover uses the same Railway Postgres database as
projections, with the event backend isolated in its `event_log` table.

The frozen backup manifest is
`backups/hollow-lodge-events-2026-06-09-frozen.manifest.json`: `23` events,
last sequence `23`, last event hash
`0211f43c455e34c8698b45173a5fbc53171338acf89fec4e610703cc52f7629c`, and
chain digest
`e65bf3e22cbc01dec4d3df4cd2f10fa443cec188e12fa05a09228a5d60ff334b`.
Production now reports `event_log.backend=postgres`, `projection_db.backend=postgres`,
zero projection lag, both Postgres startup guards enabled, and maintenance
read-only disabled.

Expected verification:

- `python -m hollow_lodge.client.cli admin backend-smoke --server https://server.thehollowlodge.com --production-postgres --event-log-manifest backups/hollow-lodge-events-2026-06-09-frozen.manifest.json`
- `curl -fsSL https://server.thehollowlodge.com/diagnostics` reports
  `data.event_log.backend=postgres`,
  `data.storage_guards.require_postgres_event_log=true`, and
  `data.maintenance.read_only=false`

### Slice 117: Production Smoke Read/Write Maintenance Gate

Status: completed.

Close the post-maintenance verification gap exposed by the hosted event-log
cutover. `hollow-lodge admin backend-smoke` and
`scripts/smoke_projection_backend.py` now accept
`--require-maintenance-read-write`, which fails unless
`/diagnostics.data.maintenance.read_only=false`.

The `--production-postgres` preset now requires the normal read/write posture
by default, in addition to the Postgres event log, Postgres projections,
storage guards, projection reads, current schema, sequence alignment, zero
lag, and successful projection refresh. Operators can still run
`--production-postgres --require-maintenance-read-only` during an intentional
freeze window; the two explicit maintenance requirements are mutually
exclusive.

Expected verification:

- `pytest tests/e2e/test_projection_backend_smoke.py::test_run_smoke_production_postgres_preset_forwards_required_checks tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_accepts_required_maintenance_read_write tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_rejects_frozen_required_maintenance_read_write tests/e2e/test_projection_backend_smoke.py::test_backend_smoke_rejects_conflicting_maintenance_requirements -q`
- `pytest tests/client/test_cli_commands.py::test_admin_backend_smoke_command_accepts_required_maintenance_read_write tests/client/test_cli_commands.py::test_admin_backend_smoke_command_rejects_frozen_required_read_write tests/client/test_cli_commands.py::test_admin_backend_smoke_command_rejects_conflicting_maintenance_requirements tests/client/test_cli_commands.py::test_admin_backend_smoke_command_accepts_production_postgres_preset -q`
- `python scripts/smoke_projection_backend.py --server-url https://server.thehollowlodge.com --production-postgres --event-log-manifest backups/hollow-lodge-events-2026-06-09-frozen.manifest.json`

### Slice 118: Codex Phase Lock Tool

Status: completed.

Expose contract phase resolution through the Codex-native MCP surface. The
server already supports oracle-backed Auction Preview locking, audit events,
phase rewards, and board rendering; this slice makes that workflow playable
from inside Codex instead of requiring a separate shell command.

`CodexGameSession.phase_lock` follows the same preview/confirm mutation policy
as actions, dossier edits, deals, transfers, and packet-lead votes. With
`confirm=false`, it reads the contract board and returns a non-mutating preview
packet with contract id, title, phase, remaining hours, and submitted
`hours_elapsed`. With `confirm=true`, it calls the existing phase-lock API,
syncs visible events, and returns a safe shaped result containing only status,
contract id, phase, standings, and public contract state. The MCP `phase_lock`
tool exposes only `confirm`, `contract_id`, and `hours_elapsed`; no local path
overrides are public.

Expected verification:

- `pytest tests/client/test_codex_session.py::test_codex_session_phase_lock_preview_reads_board_without_mutation tests/client/test_codex_session.py::test_codex_session_phase_lock_confirm_calls_api_and_syncs tests/client/test_render_packets.py::test_phase_lock_mutation_result_shapes_safe_resolution_fields_only -q`
- `pytest tests/test_mcp_server.py::test_phase_lock_mcp_call_passes_confirmation_to_session tests/test_mcp_server.py::test_public_mcp_tools_do_not_expose_local_path_overrides tests/test_mcp_server.py::test_mutating_mcp_tools_require_confirm_argument -q`
- `pytest tests/client/test_codex_session.py tests/client/test_render_packets.py tests/test_mcp_server.py -q`

### Slice 119: Codex Brokered Message Tool

Status: completed.

Expose brokered chat sending through the Codex-native MCP surface. The server
and CLI already supported direct, crew, and crew-to-crew messages; this slice
makes those social-deal workflows playable from inside Codex without dropping
to shell commands.

`CodexGameSession.send_message` follows the preview/confirm mutation policy.
With `confirm=false`, it validates the requested scope and returns a
non-mutating preview containing scope, recipients, body, and artifact
attachments. With `confirm=true`, it dispatches to the existing direct, crew,
or crew-to-crew API endpoint, syncs visible events, and returns a safe shaped
result containing message id, conversation id, and scope only. The MCP
`send_message` tool exposes game parameters only and requires `confirm`.

Expected verification:

- `pytest tests/client/test_codex_session.py::test_codex_session_send_message_preview_does_not_mutate tests/client/test_codex_session.py::test_codex_session_send_message_confirm_dispatches_and_syncs tests/client/test_codex_session.py::test_codex_session_send_message_validates_required_fields_before_mutation tests/client/test_render_packets.py::test_send_message_mutation_result_shapes_safe_message_fields_only -q`
- `pytest tests/test_mcp_server.py::test_send_message_mcp_call_passes_preview_parameters_to_session tests/test_mcp_server.py::test_public_mcp_tools_do_not_expose_local_path_overrides tests/test_mcp_server.py::test_mutating_mcp_tools_require_confirm_argument -q`
- `pytest tests/client/test_codex_session.py tests/client/test_render_packets.py tests/test_mcp_server.py -q`

### Slice 120: Codex Action Edit/Cancel Tools

Status: completed.

Expose the existing action revision workflow through the Codex-native MCP
surface. The server and CLI already support editing or canceling an action
before phase lock; this slice makes the editable/locked threshold playable from
inside Codex without requiring shell commands.

`CodexGameSession.edit_action` and `CodexGameSession.cancel_action` follow the
preview/confirm mutation policy. With `confirm=false`, each returns a
non-mutating preview. With `confirm=true`, each calls the existing action API,
syncs visible events, and returns a safe shaped result containing action id,
crew id, intent, and status only. The MCP `edit_action` and `cancel_action`
tools expose game parameters only and require `confirm`.

Expected verification:

- `pytest tests/client/test_codex_session.py::test_codex_session_edit_action_preview_does_not_mutate tests/client/test_codex_session.py::test_codex_session_edit_and_cancel_action_confirm_dispatch_and_syncs tests/client/test_codex_session.py::test_codex_session_edit_action_validates_replacement_intent_before_mutation tests/client/test_render_packets.py::test_action_revision_mutation_results_shape_safe_fields_only -q`
- `pytest tests/test_mcp_server.py::test_edit_action_mcp_call_passes_confirmation_to_session tests/test_mcp_server.py::test_cancel_action_mcp_call_passes_confirmation_to_session tests/test_mcp_server.py::test_public_mcp_tools_do_not_expose_local_path_overrides tests/test_mcp_server.py::test_mutating_mcp_tools_require_confirm_argument -q`
- `pytest tests/client/test_codex_session.py tests/client/test_render_packets.py tests/test_mcp_server.py -q`

## Completion Standard

Each slice must:

- Start with failing tests for the player-visible behavior or server invariant.
- Preserve existing CLI and MCP behavior unless the roadmap explicitly changes
  it.
- Commit in small, reviewable units.
- Run focused tests and the full suite before claiming completion.
- Update this roadmap when scope changes or a milestone proof gate is satisfied.
