# The Hollow Lodge Operations

## Railway Services

The production Railway project has two services:

- `hollow-lodge-server` serves `https://server.thehollowlodge.com`.
- `the-hollow-lodge` serves `https://www.thehollowlodge.com`.

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

## Projection Database

The authoritative game record is still the append-only Eventloom JSONL file.
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

Projection storage and authoritative event storage are separate cutovers.
Projection storage can use `DATABASE_URL` for Railway convenience; the
authoritative event log uses Postgres only when
`HOLLOW_LODGE_EVENT_DATABASE_URL` is set explicitly. `/diagnostics` reports the
active projection backend and redacts the configured Postgres password before
returning operational status. Projection diagnostics also include the current
projection schema version, migration count, and latest applied migration so
operators can verify schema drift before enabling projection reads.

Before any projection backend cutover, verify the current backend:

```sh
python scripts/smoke_projection_backend.py \
  --server-url https://server.thehollowlodge.com \
  --expected-backend sqlite \
  --expected-event-backend jsonl \
  --require-current-projection-schema
```

Installed clients can run the same readiness gate without checking out the
repository:

```sh
hollow-lodge admin backend-smoke \
  --server https://server.thehollowlodge.com \
  --expected-backend sqlite \
  --expected-event-backend jsonl \
  --require-current-projection-schema
```

After configuring `HOLLOW_LODGE_PROJECTION_DATABASE_URL`, or attaching a
Railway Postgres database that provides `DATABASE_URL`, and redeploying the
server, verify the new backend:

```sh
python scripts/smoke_projection_backend.py \
  --server-url https://server.thehollowlodge.com \
  --expected-backend postgres \
  --expected-event-backend jsonl \
  --require-current-projection-schema
```

If you intentionally set `HOLLOW_LODGE_EVENT_DATABASE_URL`, verify both
Postgres backends:

```sh
python scripts/smoke_projection_backend.py \
  --server-url https://server.thehollowlodge.com \
  --expected-backend postgres \
  --expected-event-backend postgres \
  --require-current-projection-schema
```

After the backend smoke passes, set `HOLLOW_LODGE_PROJECTION_READS=1` and verify
that all implemented projection read surfaces are enabled:

```sh
python scripts/smoke_projection_backend.py \
  --server-url https://server.thehollowlodge.com \
  --expected-backend postgres \
  --expected-event-backend jsonl \
  --require-projection-reads \
  --require-current-projection-schema
```

The installed-client equivalent is:

```sh
hollow-lodge admin backend-smoke \
  --server https://server.thehollowlodge.com \
  --expected-backend postgres \
  --expected-event-backend jsonl \
  --require-projection-reads \
  --require-current-projection-schema
```

After the Postgres smoke passes, set `HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION=1`
on the server service and redeploy once more. This turns the cutover from a
best-effort configuration into a startup invariant.

The smoke fails if `/health` is not ok, the event-log backend does not match
`--expected-event-backend`, event-log status is not `available` or
`not_created`, the projection backend is not the expected backend, projection
status is not `available`, projection lag is not zero, diagnostics expose an
unredacted database URL password, `--require-current-projection-schema` is set
and the projection schema version, latest migration, or migration count does
not match the installed package, or `--require-projection-reads` is set and any
projection read surface is disabled.

Rollback is to remove `HOLLOW_LODGE_PROJECTION_DATABASE_URL` from the server
service and redeploy. The server will return to
`$HOLLOW_LODGE_DATA_DIR/server-projections.sqlite3`; the authoritative event
log remains unchanged through the cutover and rollback.

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
hollow-lodge admin event-log-export --output backups/hollow-lodge-events.json
```

Before moving the authoritative event log to Postgres, validate the exported
chain without writing:

```sh
python scripts/migrate_event_log_to_postgres.py \
  --source backups/hollow-lodge-events.json \
  --dry-run
```

Installed clients can run the same validator without a repository checkout:

```sh
hollow-lodge admin event-log-import-postgres \
  --source backups/hollow-lodge-events.json \
  --dry-run
```

Then import into an empty Postgres event-log database:

```sh
HOLLOW_LODGE_EVENT_DATABASE_URL=postgresql://user:password@host:5432/database \
python scripts/migrate_event_log_to_postgres.py \
  --source backups/hollow-lodge-events.json
```

The installed-client equivalent is:

```sh
HOLLOW_LODGE_EVENT_DATABASE_URL=postgresql://user:password@host:5432/database \
hollow-lodge admin event-log-import-postgres \
  --source backups/hollow-lodge-events.json
```

The importer refuses to write to a non-empty destination. It preserves existing
event IDs, sequence numbers, timestamps, hash-chain fields, idempotency keys,
and command fingerprints exactly, and it prints only a redacted destination
URL. After the import succeeds, set `HOLLOW_LODGE_EVENT_DATABASE_URL` on the
server, redeploy, and verify the hosted backend:

```sh
python scripts/smoke_projection_backend.py \
  --server-url https://server.thehollowlodge.com \
  --expected-backend postgres \
  --expected-event-backend postgres \
  --require-current-projection-schema
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
