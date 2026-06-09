# Codex Play Guide

The Hollow Lodge is played inside Codex through game render tools, not by asking
the player to manage raw shell commands.

## Install And Onboard

The installer bootstraps the CLI with `uv tool install` and then launches the
first-run onboarding flow, registers the Codex MCP server, and runs a redacted
`hollow-lodge doctor` readiness report:

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

After onboarding, run the local readiness check:

```sh
hollow-lodge doctor
```

The installer already runs the non-strict form once. Use
`HOLLOW_LODGE_SKIP_DOCTOR=1` only when a scripted install needs to defer that
readiness report.

Use `hollow-lodge doctor --strict` for scripted clean-install checks after a
player has registered. Strict mode prints the same redacted report and exits
non-zero for pending onboarding or any failed readiness line.

For a registered player, `doctor` should verify saved auth, server
reachability, inbox readiness, local event-sync cache writes, Codex inbox render
packet construction, MCP config registration, and `hollow-lodge-mcp` command
availability. The output is intentionally redacted; it should not print bearer
tokens, invite codes, contract titles, event bodies, player markdown, or agent
context. Pending players should see pending onboarding state and MCP readiness,
but auth, inbox, event sync, and render checks are skipped until registration.

If `doctor` reports `codex inbox render: ok surface=inbox`, the local CLI can
construct the same inbox render packet that the MCP `render_inbox` tool will
return inside Codex. If it reports `failed`, fix the earlier failing line first:
auth, inbox reachability, event sync, MCP config, or command availability.

Admins can review and approve requests from the CLI:

```sh
hollow-lodge admin key-requests
hollow-lodge admin key-request-approve key_request_0001
```

See [operations.md](operations.md) for deployment checks, backup/export, and
admin inventory commands.

## Session Loop

Before advising, confirm the player has run `hollow-lodge doctor` after
registration or ask permission to help interpret its output. If the MCP server
is registered and the inbox render check passes, use MCP tools inside Codex
rather than asking the player to copy shell output back into the session.

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
   changes, proof transfers, messages, or phase locks.

## Default Landing

When a player says "what's happening" or starts a play session:

1. Call `render_what_now`.
2. Use the returned `summary_counts`, priority lines, and recent events to
   decide which read surface to open next.
3. If there are pending decisions or incoming fragments, call `render_inbox`.
4. If proof, heat, packet lead, or crew status matters, call `render_crew_board`
   or `render_dossier`.
5. If the player asks what changed since they last checked, call
   `render_activity_delta`.
6. If the player asks what changed for the crew since they last checked, call
   `render_crew_activity_delta`; use `render_crew_activity` for a broader
   recent crew timeline.
7. If social coordination or private offers matter, call `render_conversations`
   before opening a specific `render_thread`.
8. Review Packet Lead vote and replacement history before advising who can
   edit dossier framing.
9. Summarize the most important visible changes and offer 2-4 concrete next
   actions.

## Phase Resolution

Use `phase_lock` for the end-of-phase resolution workflow inside Codex. Start
with `confirm=false`; the tool reads the contract board and returns a preview
packet without mutating the server. Explain that a confirmed phase lock resolves
the current contract phase, invokes the oracle, records standings, may award
phase rewards, and cannot be undone by the player.

Only call `phase_lock` with `confirm=true` after the player explicitly approves
the lock. After a confirmed lock, render `render_contract_board` and
`render_crew_board` so the player can see standings, phase result text, rewards,
heat/legacy changes, and the next available work.

## Brokered Messages

Use `send_message` when a player wants to coordinate from inside Codex. Start
with `confirm=false`; the tool returns a preview packet and does not mutate the
server. Supported scopes are `direct`, `crew`, and `crew_to_crew`.

For direct messages, include `recipient_player_id`. For crew messages, omit
`crew_id` to use the configured active crew, or pass a specific `crew_id`. For
crew-to-crew messages, include `recipient_crew_id`; omit `sender_crew_id` to use
the active crew. `artifact_ids` can attach visible artifacts to the brokered
message.

Only send with `confirm=true` after the player approves the exact body,
recipient scope, and attachments. After a confirmed message, render
`render_thread` or `render_conversations` so the player and agent can see the
visible conversation state.

## Action Revisions

Use `edit_action` or `cancel_action` when a player wants to revise a submitted
crew action before the phase is locked. Start with `confirm=false`; the tool
returns a preview packet and does not mutate the server.

Only call either tool with `confirm=true` after the player approves the exact
action id and consequence. After a confirmed edit or cancel, render
`render_crew_board` or `render_activity_delta` so the player can see the
current action state before resolution.

## Visibility

Treat private conversations and crew boards as visibility-scoped game state.
Do not reveal server-only truth. Do not claim certainty about leaked or copied
information unless the game state exposes that certainty.

Before advising on proof, render artifacts or a specific artifact when the
player references evidence. Treat visible artifact content as source material.
Do not infer hidden graph nodes as facts; frame them as hypotheses unless the
server has revealed them.
