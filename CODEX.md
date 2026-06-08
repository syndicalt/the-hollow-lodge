# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. OS-Grade Authority Rules

**Ainix is security substrate work. Treat authority paths as hostile until proven safe.**

- No security placeholder may look production-ready. Stub crypto, auth,
  sandboxing, policy, or trust checks must use explicit stub names, be confined
  to local-dev/prototype scope, and be called out in docs and tests.
- Broker APIs must be typed at module boundaries. Avoid adding new stringly
  typed JSON payloads inside runtime logic; serialize only at the transport
  edge.
- Replay, nonce, actor, path, and capability selectors must be canonicalized
  once. Storage, comparison, audit, and recovery paths must use the same
  canonical representation.
- Imported paths are hostile. Any path from manifests, lattice records, sync,
  extensions, or remote/imported metadata must reject absolute paths, `..`, and
  symlink or prefix escape before host filesystem writes.
- Authority code needs clear module ownership. Capability checks, broker
  routing, replay guards, persistence, extension execution, lattice export, and
  local API transport should live in focused modules with narrow public APIs.
- Every local API or IPC surface needs a threat-model note covering who can
  connect, socket/file permissions, request size limits, concurrency or
  backpressure, replay behavior, and sanitized denial payloads.
- Authority features require negative tests as well as happy-path UAT: wrong
  actor, missing/revoked capability, replayed nonce or guard, malformed request,
  path escape, and stale/recovered state where relevant.
- Do not expand giant runtime or CLI files casually. If a change materially
  grows `ainix-runtime/src/lib.rs` or `ainix-cli/src/main.rs`, extract an owning
  module in the same change or record a blocking refactor item before adding
  more surface area there.

## 6. Verification Before Handoff

**No ready/complete claim without current evidence.**

Before handoff, review, commit, or milestone completion, run the appropriate
focused checks plus:

```bash
cargo fmt --all --check
cargo test --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
```

If the worktree is intentionally broken or mid-edit, label it as WIP and name
the exact failing command and error.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
