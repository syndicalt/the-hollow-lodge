# Agent Instructions

<!-- zaxy-memory-activation:start -->
## Zaxy Memory Activation

Before roadmap, implementation, release, review, resume, or high-context work:
- Start Codex through Zaxy when opening a new session: `zaxy activate codex --session-id the-hollow-lodge-default --current-task "<task>" --launch`.
- After `/resume`, Codex update, or MCP/tool reload, record the boundary: `zaxy hook-event resume --eventloom-path /home/cheapseatsecon/Projects/Personal/the-hollow-lodge/.eventloom --session-id the-hollow-lodge-default --source codex --summary "<task>"`.
- If Zaxy MCP tools are unavailable, run CLI checkout before substantial work: `zaxy memory checkout "<task>" --eventloom-path /home/cheapseatsecon/Projects/Personal/the-hollow-lodge/.eventloom --session-id the-hollow-lodge-default`.
- If no fresh activation packet or cited checkout is available, treat memory as degraded and pause substantial work until checkout succeeds.
- Do not rely only on ordinary Codex summaries when Zaxy activation is missing.
<!-- zaxy-memory-activation:end -->

## The Hollow Lodge Codex Play

For game-play sessions, follow `docs/codex-play.md`. The player should see
rendered game state inside Codex, and the agent should use structured render
packet context when advising.
