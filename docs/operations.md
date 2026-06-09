# The Hollow Lodge Operations

## Railway Services

The production Railway project has two services:

- `hollow-lodge-server` serves `https://server.thehollowlodge.com`.
- `the-hollow-lodge` serves `https://www.thehollowlodge.com`.

Current server storage state, verified on 2026-06-09:

- authoritative event log: Railway Postgres
- projection database: Railway Postgres
- projection reads: enabled for all implemented surfaces
- startup guards: Postgres event-log guard and Postgres projection guard
  enabled
- maintenance diagnostics: deployed; read-only mode is currently disabled
- migration backup manifest:
  `backups/hollow-lodge-events-2026-06-09-frozen.manifest.json`
  (`23` events, last sequence `23`)

Deploy the server from the repository root:

```sh
railway up --service hollow-lodge-server --detach
```

Deploy the public site from the `site/` directory:

```sh
railway up site --path-as-root --service the-hollow-lodge --detach
```

## Health Checks

```sh
curl -fsS https://server.thehollowlodge.com/health
curl -fsS https://server.thehollowlodge.com/diagnostics
curl -fsSIL https://www.thehollowlodge.com/install.sh
```

`/diagnostics` reports provider readiness, event-log path/status, and data
directory without returning API keys, admin tokens, invite codes, or player
tokens.

`data.projection_refresh` reports whether the process last refreshed the
projection read model successfully. Failed best-effort refreshes do not reject
the authoritative mutation, but diagnostics expose the safe failure context,
exception type, last successful event sequence, and failure count so operators
can see when projection-backed reads may be stale without leaking connection
strings or raw exception messages.

Startup projection bootstrap failures are fail-fast. If the server cannot
replay authoritative events or rebuild the projection store during startup, the
process raises a bounded error that names the bootstrap stage and exception
type without including raw database URLs, API keys, invite codes, or provider
messages.

Unexpected `/diagnostics` collection failures fail closed. If an event-log or
projection diagnostic provider raises, the endpoint returns an unavailable
diagnostic block with only safe backend metadata and exception type, rather
than returning HTTP 500 or exposing raw database/provider exception text.

## Authoritative Event Log

The authoritative game record is the append-only Eventloom log. Local
development uses JSONL by default:

```sh
$HOLLOW_LODGE_DATA_DIR/server-events.jsonl
```

Hosted production can move authoritative event storage to Postgres only by
setting the Hollow-specific event database URL:

```sh
HOLLOW_LODGE_EVENT_DATABASE_URL=postgresql://user:password@host:5432/database
```

The server intentionally does not use platform `DATABASE_URL` for
authoritative events. Attaching a Railway or PaaS database should not
silently move the append-only source of truth; operators must choose that
cutover explicitly with `HOLLOW_LODGE_EVENT_DATABASE_URL`.

After migrating and verifying the hosted event log, production deployments can
fail fast unless the authoritative backend is explicitly Postgres:

```sh
HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG=1
```

When this guard is enabled, server startup rejects a missing
`HOLLOW_LODGE_EVENT_DATABASE_URL` or any non-Postgres event-log URL. Keep it
unset for local development and tests unless intentionally exercising the
production event-log cutover path.

Postgres event-log appends take an advisory transaction lock, validate
sequence and previous-hash metadata, read idempotent command replays by key,
and append from the current chain head without replaying full event payloads on
every write. Full payload/hash validation remains available through read,
verify, export, and import paths.

Before appending to a non-empty Postgres event log, the server also validates
the current head event payload against its stored hash and metadata. This
prevents a new write from extending a chain whose latest payload has been
tampered with, while still avoiding full-log payload replay on the write path.

Bounded Postgres event reads, such as event sync requests with a starting
sequence, validate the full structured metadata chain and then load only the
requested event payload rows. Each returned payload is still validated against
its hash and metadata. Unbounded reads, integrity checks, exports, and imports
continue to validate full event payload chains.

## Projection Database

The authoritative game record remains the append-only Eventloom log.
The projection database is a read-side cache for contract boards, crew
summaries, artifacts, deals, visible events, chat messages, current actions,
legacy blocks, current proof dossiers, and pending decision surfaces.

By default, the server stores projections at:

```sh
$HOLLOW_LODGE_DATA_DIR/server-projections.sqlite3
```

An explicit SQLite projection path can be configured with:

```sh
HOLLOW_LODGE_PROJECTION_DATABASE_URL=sqlite:////data/server-projections.sqlite3
```

Postgres projection storage can be enabled explicitly with:

```sh
HOLLOW_LODGE_PROJECTION_DATABASE_URL=postgresql://user:password@host:5432/database
```

If `HOLLOW_LODGE_PROJECTION_DATABASE_URL` is unset, the server will also accept
the platform `DATABASE_URL` value used by Railway and other PaaS providers.
The Hollow-specific variable remains the explicit override when both are set.
`/diagnostics` reports `database_url_env` so operators can tell which variable
selected the active Postgres projection backend without exposing the password.

Production deployments can require Postgres and fail fast instead of silently
falling back to local SQLite:

```sh
HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION=1
```

When this guard is enabled, server startup rejects a missing projection URL
from both `HOLLOW_LODGE_PROJECTION_DATABASE_URL` and `DATABASE_URL`, or any
`sqlite:///` projection URL. Local development and tests should leave the guard
unset unless they are intentionally exercising the production cutover path.

Production deployments can enable all implemented projection-backed read paths
with one switch:

```sh
HOLLOW_LODGE_PROJECTION_READS=1
```

Individual surface flags such as `HOLLOW_LODGE_CHAT_PROJECTION_READS=0` can
override the global switch during a targeted rollback. `/diagnostics` reports
the effective projection read configuration in `data.projection_reads`.
Implemented surfaces include contract board, crew-scoped contract unlock
status, crew summary, visible artifacts, visible deals, proof dossiers, chat,
visible events, pending decisions, current actions, crew-board visible rumors,
artifact inspections, proof fragments, and redacted oracle audit records.

Projection storage and authoritative event storage are separate cutovers.
Projection storage can use `DATABASE_URL` for Railway convenience; the
authoritative event log uses Postgres only when
`HOLLOW_LODGE_EVENT_DATABASE_URL` is set explicitly. `/diagnostics` reports the
active projection backend and redacts the configured Postgres password before
returning operational status. Projection diagnostics also include the current
projection schema version, migration count, and latest applied migration so
operators can verify schema drift before enabling projection reads.

Projection-backed read readiness compares projection lag against the
authoritative event-log diagnostics chain head. In Postgres event-log mode,
that means ordinary projected reads can prove freshness from metadata-only
chain diagnostics instead of replaying the full Eventloom log. If the
authoritative event-log diagnostics are unavailable or malformed, projected
reads fail closed and routes use their existing Eventloom fallback paths.

The `/diagnostics` projection database block uses the same event-log diagnostic
chain head for `authoritative_last_sequence` and `lag`. In Postgres event-log
mode, diagnostics therefore do not replay full event payloads just to calculate
projection lag after the event-log status block has already produced safe chain
metadata. If the event-log chain head is unavailable or malformed, projection
lag is reported as unavailable rather than fresh.

When those fallback paths need full events for read-only derivations such as
contract unlocks, crew legacy, or pending-decision context, the server reuses a
request-scoped authoritative event snapshot. The snapshot is not retained
across requests and is not used for mutations, imports, projection refresh, or
integrity checks.

Crew-specific contract unlock reads can be enabled independently with
`HOLLOW_LODGE_CONTRACT_UNLOCK_PROJECTION_READS=1`. The projection stores only
safe `unlock_status` payloads keyed by crew and contract; raw seed
`unlock_requirements`, hidden truth, server notes, artifact graph internals, and
private event payloads remain outside the read model. `/diagnostics` reports
`contract_unlock_count` so operators can confirm the surface is materialized
before enabling the read flag.

Artifact inspection reads use the same
`HOLLOW_LODGE_ARTIFACT_PROJECTION_READS=1` flag as visible artifact lists. The
inspection projection stores player-visible source text and source-chain fields
needed by `GET /artifacts/{artifact_id}`, but keeps hidden flags, hidden truth,
server notes, and artifact graph internals out of the read model. Stale or
unavailable projections fall back to the authoritative Eventloom-derived
artifact service.

Proof fragment reads can be enabled independently with
`HOLLOW_LODGE_PROOF_FRAGMENT_PROJECTION_READS=1`. The projection stores only
player-scoped fragment surfaces for `GET /proofs/fragments/{fragment_id}`:
fragment id, summary, source chain, and provenance checked state. It does not
store provenance flags such as copied-hand or ink-after-binding; those remain
available only through the explicit provenance-check command. Stale or
unavailable projections fall back to the authoritative Eventloom-derived proof
service.

Player profile crew history uses the crew-legacy projection when
`HOLLOW_LODGE_CREW_LEGACY_PROJECTION_READS=1` is enabled and fresh. Stale or
unavailable projections fall back to a request-scoped authoritative Eventloom
read. The profile response includes only the already-shaped crew legacy
snapshot and omits join codes, auth material, hidden sources, raw deal terms,
and private evidence.

Admin oracle audit reads can be enabled independently with
`HOLLOW_LODGE_ORACLE_AUDIT_PROJECTION_READS=1`. The projection stores one
server-only, redacted row for each `oracle.resolution.*` audit event: sequence,
event id, event type, contract, phase, provider/model/prompt metadata,
validation and fallback fields, safe count fields, input packet hash, and
accepted output hash. It does not store raw oracle inputs, hidden truth, prompt
packets, raw provider output, accepted model output, or provider exception
messages. `/diagnostics` reports `oracle_audit_count` so operators can confirm
the surface is materialized before enabling the read flag.

Before any projection backend cutover, verify the current backend:

```sh
python scripts/smoke_projection_backend.py \
  --server-url https://server.thehollowlodge.com \
  --expected-backend sqlite \
  --expected-event-backend jsonl \
  --require-current-projection-read-surfaces \
  --require-current-projection-schema \
  --require-sequence-alignment \
  --require-projection-refresh-ok
```

Installed clients can run the same readiness gate without checking out the
repository:

```sh
hollow-lodge admin backend-smoke \
  --server https://server.thehollowlodge.com \
  --expected-backend sqlite \
  --expected-event-backend jsonl \
  --require-current-projection-read-surfaces \
  --require-current-projection-schema \
  --require-sequence-alignment \
  --require-projection-refresh-ok
```

After configuring `HOLLOW_LODGE_PROJECTION_DATABASE_URL`, or attaching a
Railway Postgres database that provides `DATABASE_URL`, and redeploying the
server, verify the new backend:

```sh
python scripts/smoke_projection_backend.py \
  --server-url https://server.thehollowlodge.com \
  --expected-backend postgres \
  --expected-event-backend jsonl \
  --require-current-projection-read-surfaces \
  --require-current-projection-schema \
  --require-sequence-alignment \
  --require-projection-refresh-ok
```

If you intentionally set `HOLLOW_LODGE_EVENT_DATABASE_URL`, verify both
Postgres backends:

```sh
python scripts/smoke_projection_backend.py \
  --server-url https://server.thehollowlodge.com \
  --expected-backend postgres \
  --expected-event-backend postgres \
  --event-log-manifest backups/hollow-lodge-events.manifest.json \
  --require-current-projection-read-surfaces \
  --require-current-projection-schema \
  --require-sequence-alignment \
  --require-projection-refresh-ok
```

`--event-log-manifest` compares the hosted event-log diagnostics with the
backup manifest's event count, last sequence, last event hash, and
`event_hash_chain_sha256` digest. This proves the deployed authoritative
backend is at the expected Eventloom chain head and ordered hash-chain summary
without exposing event payloads. The smoke validates the manifest document's
type, version, required fields, and unexpected fields before treating it as
readiness evidence.

For the Postgres event-log backend, that diagnostic chain summary is derived
from event metadata columns: sequence, event id, event hash, and previous hash.
The server does not load full event payloads just to answer `/diagnostics`, and
the status fails closed if the stored metadata chain has a sequence gap or
previous-hash break. Full event validation still happens on gameplay reads,
imports, and explicit integrity checks.

After that smoke passes, set `HOLLOW_LODGE_REQUIRE_POSTGRES_EVENT_LOG=1` on
the server service and redeploy once more. This turns the authoritative event
storage cutover from a best-effort configuration into a startup invariant
without allowing platform `DATABASE_URL` to select the event-log backend.
Verify that the hosted process is enforcing the guard:

```sh
python scripts/smoke_projection_backend.py \
  --server-url https://server.thehollowlodge.com \
  --expected-backend postgres \
  --expected-event-backend postgres \
  --event-log-manifest backups/hollow-lodge-events.manifest.json \
  --require-current-projection-read-surfaces \
  --require-current-projection-schema \
  --require-sequence-alignment \
  --require-projection-refresh-ok \
  --require-postgres-event-log-guard
```

For a projection-only cutover where the authoritative event log remains JSONL,
set `HOLLOW_LODGE_PROJECTION_READS=1` after the backend smoke passes and verify
that all implemented projection read surfaces are enabled:

```sh
python scripts/smoke_projection_backend.py \
  --server-url https://server.thehollowlodge.com \
  --expected-backend postgres \
  --expected-event-backend jsonl \
  --require-projection-reads \
  --require-current-projection-read-surfaces \
  --require-current-projection-schema \
  --require-sequence-alignment \
  --require-projection-refresh-ok
```

The installed-client equivalent for that projection-only path is:

```sh
hollow-lodge admin backend-smoke \
  --server https://server.thehollowlodge.com \
  --expected-backend postgres \
  --expected-event-backend jsonl \
  --require-projection-reads \
  --require-current-projection-read-surfaces \
  --require-current-projection-schema \
  --require-sequence-alignment \
  --require-projection-refresh-ok
```

After the Postgres smoke passes, set `HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION=1`
on the server service and redeploy once more. This turns the cutover from a
best-effort configuration into a startup invariant.
Verify that both production storage guards are enforced:

```sh
hollow-lodge admin backend-smoke \
  --server https://server.thehollowlodge.com \
  --production-postgres \
  --event-log-manifest backups/hollow-lodge-events.manifest.json
```

`--production-postgres` is the installed-client preset for the full production
database invariant: Postgres authoritative event log, Postgres projections,
both Postgres startup guards, all implemented projection reads enabled, current
projection schema, zero projection lag, aligned authoritative/projection
sequences, a successful latest projection refresh, and maintenance read-only
mode disabled. During an intentional freeze window, add
`--require-maintenance-read-only`; this checks the frozen posture instead of
the normal read/write posture.

The smoke fails if `/health` is not ok, the event-log backend does not match
`--expected-event-backend`, event-log status is not `available` or
`not_created`, the projection backend is not the expected backend, projection
status is not `available`, projection lag is not zero, diagnostics expose an
unredacted database URL password, `--require-current-projection-schema` is set
and the projection schema version, latest migration, or migration count does
not match the installed package, `--require-current-projection-read-surfaces`
is set and the reported projection read surface names do not match the
installed package, `--require-sequence-alignment` is set and the event count,
projection last sequence, authoritative projection sequence, or projection lag
do not agree, or `--require-projection-reads` is set and any projection read
surface is disabled. When `--require-projection-refresh-ok` is set, the smoke
also fails unless `/diagnostics.data.projection_refresh.status` is `ok`; failure
messages include only the safe refresh context and exception type. When
`--require-postgres-event-log-guard` or
`--require-postgres-projection-guard` is set, the smoke also fails unless
`/diagnostics` reports the corresponding startup guard as enabled and the
guarded backend is actually `postgres`.

Rollback for a projection-only cutover is to remove
`HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION`,
`HOLLOW_LODGE_PROJECTION_DATABASE_URL`, and projection-read flags from the
server service and redeploy. The server will return to
`$HOLLOW_LODGE_DATA_DIR/server-projections.sqlite3`; the authoritative event
log remains unchanged through the cutover and rollback.

If the authoritative event log has also been moved to Postgres, rollback must
be handled as a deliberate event-log restore or migration decision. Do not
remove `HOLLOW_LODGE_EVENT_DATABASE_URL` after new hosted events have been
accepted unless the JSONL log has first been brought to the same verified
sequence and hash-chain state.

## Oracle Audits

Phase resolution writes server-only oracle audit events into the authoritative
Eventloom log. Operators can inspect a redacted audit summary with:

```sh
hollow-lodge admin oracle-audits
```

or directly against the server:

```sh
curl -fsS https://server.thehollowlodge.com/admin/oracle/audits \
  -H "X-Hollow-Lodge-Admin-Token: $HOLLOW_LODGE_ADMIN_TOKEN"
```

The audit surface reports provider, model, prompt version, validation status,
fallback status, safe counts, and input/output hashes. It intentionally omits
raw oracle input packets, hidden truth, and accepted model output.

## Access Requests

Players without an invite request access during onboarding:

```sh
hollow-lodge onboard --name Ada --contact ada@example.com
```

Admins review and approve requests with:

```sh
hollow-lodge admin key-requests
hollow-lodge admin key-request-approve key_request_0001
```

The approval command prints the one-use invite code once. The authoritative
event log stores only invite hashes.

## Inventory And Player Lookup

```sh
hollow-lodge admin invites
hollow-lodge admin players
hollow-lodge admin player player_0001
```

Invite inventory never prints raw invite codes. Player lookup never prints
tokens, token hashes, or crew join codes. The single-player lookup includes
sanitized crew memberships so admins can confirm onboarding state without
opening the event log.

## Event-Log Integrity And Export

The authoritative event log defaults to the local append-only JSONL file at
`$HOLLOW_LODGE_DATA_DIR/server-events.jsonl`. Operators can explicitly place
the authoritative event log in Postgres with:

```sh
HOLLOW_LODGE_EVENT_DATABASE_URL=postgresql://user:password@host:5432/database
```

Unlike projection storage, the event log does not implicitly use `DATABASE_URL`;
this prevents an attached platform database from accidentally becoming the
source of truth before the operator has chosen that cutover. `/diagnostics`
reports `data.event_log.backend` and redacts any Postgres password before
returning `database_url`.

Verify the authoritative event log:

```sh
hollow-lodge admin event-log-verify
```

Export a JSON backup:

```sh
hollow-lodge admin event-log-export \
  --output backups/hollow-lodge-events.json \
  --manifest-output backups/hollow-lodge-events.manifest.json
```

The manifest validates the export and writes only content-safe chain metadata:
event count, first and last sequence, first and last event hashes, schema
versions, and a digest over the event hash chain. It does not include payloads,
actor IDs, visibility principals, idempotency keys, invite hashes, or auth
material.

For an existing export, generate or refresh the manifest with:

```sh
hollow-lodge admin event-log-manifest \
  --source backups/hollow-lodge-events.json \
  --output backups/hollow-lodge-events.manifest.json
```

To drill a local restore from a backup before changing production storage,
restore the export into an empty JSONL event log and boot a server with that
data directory:

```sh
hollow-lodge admin event-log-restore-jsonl \
  --source backups/hollow-lodge-events.json \
  --manifest backups/hollow-lodge-events.manifest.json \
  --destination /tmp/hollow-lodge-restore/server-events.jsonl

HOLLOW_LODGE_DATA_DIR=/tmp/hollow-lodge-restore \
uvicorn hollow_lodge.server.app:app
```

The restore command refuses non-empty destinations, verifies the supplied
manifest before writing, and prints only chain-head metadata. Use
`/diagnostics` or `hollow-lodge admin backend-smoke --event-log-manifest` to
confirm the restored server reports the expected event count, last sequence,
and last event hash.

Before moving the authoritative event log to Postgres, validate the exported
chain without writing:

```sh
python scripts/migrate_event_log_to_postgres.py \
  --source backups/hollow-lodge-events.json \
  --manifest backups/hollow-lodge-events.manifest.json \
  --dry-run
```

Installed clients can run the same validator without a repository checkout:

```sh
hollow-lodge admin event-log-import-postgres \
  --source backups/hollow-lodge-events.json \
  --manifest backups/hollow-lodge-events.manifest.json \
  --dry-run
```

Before taking the final production export, freeze mutating commands so the
JSONL chain head cannot advance between backup, manifest verification, import,
and backend cutover:

```sh
railway variable set --service hollow-lodge-server HOLLOW_LODGE_MAINTENANCE_READ_ONLY=1
```

After the redeploy, confirm `/diagnostics.data.maintenance.read_only=true`.
Health checks, diagnostics, event-log verification, and event-log export remain
available; gameplay and admin mutation commands return HTTP 503 with a
`Retry-After` header. Leave read-only mode enabled until the Postgres import,
`HOLLOW_LODGE_EVENT_DATABASE_URL` cutover, backend smoke with the backup
manifest, and Postgres event-log guard verification have all passed.

Use the backend smoke gate before exporting:

```sh
hollow-lodge admin backend-smoke \
  --server https://server.thehollowlodge.com \
  --expected-backend postgres \
  --expected-event-backend jsonl \
  --require-projection-reads \
  --require-current-projection-read-surfaces \
  --require-current-projection-schema \
  --require-sequence-alignment \
  --require-projection-refresh-ok \
  --require-postgres-projection-guard \
  --require-maintenance-read-only
```

Then import into an empty Postgres event-log database:

```sh
HOLLOW_LODGE_EVENT_DATABASE_URL=postgresql://user:password@host:5432/database \
python scripts/migrate_event_log_to_postgres.py \
  --source backups/hollow-lodge-events.json \
  --manifest backups/hollow-lodge-events.manifest.json
```

The installed-client equivalent is:

```sh
HOLLOW_LODGE_EVENT_DATABASE_URL=postgresql://user:password@host:5432/database \
hollow-lodge admin event-log-import-postgres \
  --source backups/hollow-lodge-events.json \
  --manifest backups/hollow-lodge-events.manifest.json
```

The importer refuses to write to a non-empty destination. It preserves existing
event IDs, sequence numbers, timestamps, hash-chain fields, idempotency keys,
and command fingerprints exactly, verifies the manifest before writing when
`--manifest` is supplied, and prints only a redacted destination URL. After the
import succeeds, set `HOLLOW_LODGE_EVENT_DATABASE_URL` on the
server, redeploy, and verify the hosted backend:

```sh
python scripts/smoke_projection_backend.py \
  --server-url https://server.thehollowlodge.com \
  --expected-backend postgres \
  --expected-event-backend postgres \
  --require-current-projection-read-surfaces \
  --require-current-projection-schema \
  --require-sequence-alignment
```

When the hosted Postgres event-log smoke passes, restore writes by removing the
maintenance flag and redeploying:

```sh
railway variable delete --service hollow-lodge-server HOLLOW_LODGE_MAINTENANCE_READ_ONLY
```

If the platform keeps the old runtime value after deletion, set
`HOLLOW_LODGE_MAINTENANCE_READ_ONLY=0` and redeploy or restart the service.
Verify the writable production posture with the full smoke preset:

```sh
hollow-lodge admin backend-smoke \
  --server https://server.thehollowlodge.com \
  --production-postgres \
  --event-log-manifest backups/hollow-lodge-events.manifest.json
```

Treat exports as sensitive operational data. They include server-visible events
and hashed auth material, but not raw player tokens, raw generated invite codes,
or admin tokens.

## Clean Install Smoke

On a clean machine with `uv` installed:

```sh
curl -fsSL https://www.thehollowlodge.com/install.sh | sh
```

The installer installs the CLI, registers the Codex MCP server, and launches
`hollow-lodge onboard`. Players with an invite can register immediately.
Players without an invite remain in pending onboarding state until an admin
approves their access request and sends them the generated invite code.

Verify the local install without exposing token or invite material:

```sh
hollow-lodge doctor
```

The doctor reports CLI version, selected server health, registered or pending
player state, and whether the Codex MCP server is registered.
