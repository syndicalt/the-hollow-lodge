# The Hollow Lodge

The Hollow Lodge is an asynchronous occult-heist multiplayer game for
LLM-native command-line clients.

Players join stable crews, inspect contracts, build proof packets, negotiate
through brokered messages, and submit freeform actions through a local agent
that clarifies consequences without choosing strategy by default.

## Install

```sh
curl -fsSL https://www.thehollowlodge.com/install.sh | sh
```

The installer uses `uv tool install` and then launches first-run onboarding.
Players with an invite can register immediately; players without an invite can
request an access key.

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
