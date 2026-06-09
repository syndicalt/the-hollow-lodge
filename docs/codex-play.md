# Codex Play Guide

The Hollow Lodge is played inside Codex through game render tools, not by asking
the player to manage raw shell commands.

## Install And Onboard

The installer bootstraps the CLI with `uv tool install` and then launches the
first-run onboarding flow:

```sh
curl -fsSL https://www.thehollowlodge.com/install.sh | sh
```

By default, onboarding connects to the official Lodge server. Power users can
target a custom server with:

```sh
hollow-lodge onboard --server https://example-lodge.invalid --name Ada
```

Players who already have an invite can register immediately:

```sh
hollow-lodge onboard --name Ada --invite alpha-code
```

Players without an invite can request an access key. The CLI stores pending
onboarding state locally while an admin reviews the request:

```sh
hollow-lodge onboard --name Ada --contact ada@example.com
```

Admins can review and approve requests from the CLI:

```sh
hollow-lodge admin key-requests
hollow-lodge admin key-request-approve key_request_0001
```

See [operations.md](operations.md) for deployment checks, backup/export, and
admin inventory commands.

## Session Loop

1. Sync visible events before advising.
2. Render `render_what_now` first for a compact landing state.
3. Render the inbox when the player needs pending decisions, incoming fragments,
   or deal details.
4. Render the contract board when the player asks what is available or contested.
5. Render the crew board before advising on crew actions, proof packets, heat,
   packet-lead votes, or dossier strategy.
6. Show the player the relevant `player_markdown`.
7. Use `agent_context` for reasoning, but do not hide material consequences from
   the player.
8. Clarify consequences and translate intent. Do not choose player strategy by default.
9. Ask for confirmation before submitting irreversible actions, votes, dossier
   changes, proof transfers, or messages.

## Default Landing

When a player says "what's happening" or starts a play session:

1. Call `render_what_now`.
2. Use the returned `summary_counts`, priority lines, and recent events to
   decide which read surface to open next.
3. If there are pending decisions or incoming fragments, call `render_inbox`.
4. If proof, heat, packet lead, or crew status matters, call `render_crew_board`
   or `render_dossier`.
5. Summarize the most important visible changes and offer 2-4 concrete next
   actions.

## Visibility

Treat private conversations and crew boards as visibility-scoped game state.
Do not reveal server-only truth. Do not claim certainty about leaked or copied
information unless the game state exposes that certainty.

Before advising on proof, render artifacts or a specific artifact when the
player references evidence. Treat visible artifact content as source material.
Do not infer hidden graph nodes as facts; frame them as hypotheses unless the
server has revealed them.
