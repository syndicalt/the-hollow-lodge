# Codex Play Guide

The Hollow Lodge is played inside Codex through game render tools, not by asking
the player to manage raw shell commands.

## Session Loop

1. Sync visible events before advising.
2. Render the inbox first.
3. Render the contract board when the player asks what is available or contested.
4. Render the crew board before advising on crew actions, proof packets, heat,
   packet-lead votes, or dossier strategy.
5. Show the player the relevant `player_markdown`.
6. Use `agent_context` for reasoning, but do not hide material consequences from
   the player.
7. Clarify consequences and translate intent. Do not choose player strategy by default.
8. Ask for confirmation before submitting irreversible actions, votes, dossier
   changes, proof transfers, or messages.

## Default Landing

When a player says "what's happening" or starts a play session:

1. Call `render_inbox`.
2. If there are active contracts, call `render_contract_board`.
3. If an active crew is configured, call `render_crew_board`.
4. Summarize the most important visible changes and offer 2-4 concrete next
   actions.

## Visibility

Treat private conversations and crew boards as visibility-scoped game state.
Do not reveal server-only truth. Do not claim certainty about leaked or copied
information unless the game state exposes that certainty.
