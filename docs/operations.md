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

Production deployments can require Postgres and fail fast instead of silently
falling back to local SQLite:

```sh
HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION=1
```

When this guard is enabled, server startup rejects a missing projection URL or
any `sqlite:///` projection URL. Local development and tests should leave the
guard unset unless they are intentionally exercising the production cutover
path.

Only the projection database moves to Postgres. The Eventloom JSONL log remains
authoritative. `/diagnostics` reports the active projection backend and redacts
the configured Postgres password before returning operational status. Projection
diagnostics also include the current projection schema version, migration count,
and latest applied migration so operators can verify schema drift before
enabling projection reads.

Before any projection backend cutover, verify the current backend:

```sh
python scripts/smoke_projection_backend.py \
  --server-url https://server.thehollowlodge.com \
  --expected-backend sqlite
```

After configuring `HOLLOW_LODGE_PROJECTION_DATABASE_URL` and redeploying the
server, verify the new backend:

```sh
python scripts/smoke_projection_backend.py \
  --server-url https://server.thehollowlodge.com \
  --expected-backend postgres
```

After the Postgres smoke passes, set `HOLLOW_LODGE_REQUIRE_POSTGRES_PROJECTION=1`
on the server service and redeploy once more. This turns the cutover from a
best-effort configuration into a startup invariant.

The smoke fails if `/health` is not ok, the projection backend is not the
expected backend, projection status is not `available`, projection lag is not
zero, or diagnostics expose an unredacted database URL password.

Rollback is to remove `HOLLOW_LODGE_PROJECTION_DATABASE_URL` from the server
service and redeploy. The server will return to
`$HOLLOW_LODGE_DATA_DIR/server-projections.sqlite3`; the authoritative event
log remains unchanged through the cutover and rollback.

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

Verify the authoritative event log:

```sh
hollow-lodge admin event-log-verify
```

Export a JSON backup:

```sh
hollow-lodge admin event-log-export --output backups/hollow-lodge-events.json
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
