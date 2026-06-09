# The Hollow Lodge

The Hollow Lodge is an asynchronous occult-heist multiplayer game for
LLM-native command-line clients.

Players join stable crews, inspect contracts, build proof packets, negotiate
through brokered messages, and submit freeform actions through a local agent
that clarifies consequences without choosing strategy by default.

## Artifact Gameplay Loop

Contracts seed a server-only evidence graph before play. Players see a
visibility-scoped slice of that graph as artifacts. They can inspect artifacts,
transfer copies, cite artifacts in crew dossiers, and submit freeform actions
that unlock additional artifacts. Phase resolution scores dossiers and actions
against the server-owned graph.

## Install

```sh
curl -fsSL https://www.thehollowlodge.com/install.sh | sh
```

The installer uses `uv tool install`, registers the Codex MCP server, launches
first-run onboarding, and runs a redacted `hollow-lodge doctor` readiness
report. Players with an invite can register immediately; players without an
invite can request an access key.

Use `HOLLOW_LODGE_SKIP_DOCTOR=1` if you need to suppress the automatic doctor
report during scripted installation. You can run `hollow-lodge doctor` later to
verify server reachability, saved auth, inbox readiness, Codex MCP
registration, and Codex inbox and what-now render readiness without printing
token or gameplay payload details.

For staging or self-hosted servers, set the server before installing:

```sh
curl -fsSL https://www.thehollowlodge.com/install.sh \
  | HOLLOW_LODGE_SERVER_URL=https://staging.example.invalid sh
```

Use `hollow-lodge doctor --strict` in automation when a registered player must
be fully ready to play; pending or incomplete installs exit non-zero.

Operational deployment, access approval, and event-log backup commands are in
[docs/operations.md](docs/operations.md).

Contract story, artifact graph, and GM authoring guidance is in
[docs/gm-guide.md](docs/gm-guide.md).

## Server Oracle

The server defaults to deterministic resolution:

```sh
HOLLOW_LODGE_ORACLE_PROVIDER=deterministic
```

OpenAI-backed resolution is available behind explicit server environment
variables:

```sh
HOLLOW_LODGE_ORACLE_PROVIDER=openai
HOLLOW_LODGE_ORACLE_MODEL=gpt-4.1-mini
HOLLOW_LODGE_ORACLE_TIMEOUT_SECONDS=20
HOLLOW_LODGE_OPENAI_API_KEY=...
```

Model output is validated by the server before it is committed. Missing API
keys, provider errors, invalid output, or unsafe reveal text fall back to
deterministic resolution.
