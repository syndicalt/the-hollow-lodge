# Resolution Oracle Design

## Scope

The first server Oracle slice adds model-assisted resolution for Auction Preview
in The Saint's False Finger. It evaluates each crew's proof dossier and locked
actions, then produces a scored reveal packet for the existing phase resolver.

This is not a general GM, campaign generator, chat bot, or autonomous strategy
engine. It is a bounded resolver workflow with deterministic fallback.

## Product Goal

The game loop should feel agent-native: crews assemble proof packets, the server
Oracle reads the packets against hidden truth and rubric factors, and the final
reveal explains why one crew leads.

The player-facing output should be dramatic and legible. The server-facing
output must be structured, auditable, and safe to commit to the authoritative
event log.

## Authority Model

The Oracle does not own game authority by itself. The authoritative server owns:

- phase state
- hidden truth custody
- visibility rules
- command idempotency
- event append
- score bounds
- accepted reveal payload shape

The model provider returns a candidate judgment. The server validates that
candidate, clamps numeric values to allowed ranges, removes forbidden hidden
truth leakage, and appends only the accepted result.

If the model call fails, times out, returns invalid JSON, or leaks forbidden
material, the server uses the existing deterministic scorer.

## Workflow Boundary

Create a new workflow boundary for server-side Oracle tasks.

Suggested module:

```text
src/hollow_lodge/workflows/oracle_boundary.py
src/hollow_lodge/workflows/deterministic_oracle.py
src/hollow_lodge/workflows/openai_oracle.py
```

Core interface:

```python
class ResolutionOracle(Protocol):
    def resolve_auction_preview(
        self,
        packet: AuctionPreviewOraclePacket,
    ) -> AuctionPreviewOracleResult:
        ...
```

The packet contains only the information needed to judge the phase:

- contract id and phase name
- hidden truth summary and rubric hooks
- redacted contract state
- each crew's dossier framing
- submitted action frames
- exposed evidence ids and public summaries
- heat/noise impacts
- server scoring constraints

The result contains:

- per-crew total score
- standing label
- strengths
- weaknesses
- penalties
- revealed clues safe for this phase
- brief public reveal narration
- model metadata when a model was used
- validation status

## Provider Strategy

Use an environment-driven provider selector:

```text
HOLLOW_LODGE_ORACLE_PROVIDER=deterministic|openai
HOLLOW_LODGE_ORACLE_MODEL=<model name>
HOLLOW_LODGE_ORACLE_TIMEOUT_SECONDS=...
HOLLOW_LODGE_OPENAI_API_KEY=...
```

Default remains `deterministic`, including production unless the provider is
explicitly enabled. That keeps deployments runnable without an API key and keeps
tests deterministic.

The OpenAI provider must use Structured Outputs with a strict JSON-schema
response contract. It must not use older JSON mode. It must not stream for this
first slice. It must set conservative timeout and retry limits. It must never
receive player tokens, invite codes, or private chat outside the phase packet.

Structured Outputs reduce format drift, but they do not replace game-rule
validation. The server still checks crew ids, score ranges, evidence ids,
visibility safety, and hidden-truth leakage before committing any result.

## Event Log Shape

Resolution should append an auditable event before or inside the existing phase
resolved event.

Recommended event types:

```text
oracle.resolution.requested
oracle.resolution.completed
oracle.resolution.failed
contract.phase.resolved
```

The committed Oracle events should include:

- oracle provider
- model name when used
- prompt/schema version
- input packet hash
- accepted output
- validation warnings
- fallback reason, if any

Raw prompts and raw model output should not be public visible by default. They
may contain hidden truth. They should be server-only events or stored as hashes
plus compact diagnostics until we have an admin-only inspection path.

## Data Flow

1. A phase lock triggers Auction Preview resolution.
2. `ContractService` builds the existing score inputs.
3. The server transforms those inputs into an `AuctionPreviewOraclePacket`.
4. The configured `ResolutionOracle` returns a candidate result.
5. The server validates the candidate:
   - known crew ids only
   - one result per eligible crew
   - score range bounded
   - no hidden truth phrases outside allowed reveal strings
   - no unknown evidence ids
   - stable ordering by score then crew id
6. The server appends Oracle audit events.
7. The server appends `contract.phase.resolved` using the accepted reveal.

## Prompt Contract

The model prompt must be boring and explicit:

- evaluate proof quality, not writing style alone
- reward corroborated evidence and contradiction discovery
- penalize noisy, contaminated, or unsupported claims
- preserve campaign-hidden facts
- output only valid JSON matching schema
- explain the lead in phase-safe language

The system prompt must state that the server will reject outputs that reveal
hidden truth beyond the provided allowed reveal list.

## Deterministic Fallback

The existing `score_auction_preview` function remains the fallback resolver.
It must be wrapped as `DeterministicResolutionOracle` so both providers share
the same interface and tests can exercise the same code path.

Fallback happens when:

- provider is deterministic
- API key is missing
- model request errors
- model response is invalid
- validation rejects output
- configured timeout is exceeded

Fallback must be visible in server-only audit events.

## Security And Privacy

The Oracle must not receive:

- player auth tokens
- invite codes
- admin tokens
- unrelated private messages
- full event-log history
- hidden truth not needed for this phase

The Oracle may receive hidden truth needed for resolution, but only through the
server-generated packet. Model output is treated as untrusted until validated.

Player-visible reveal text must be derived from allowed reveal strings or
validated phase-safe narration.

## Testing

Add tests at three levels:

- domain/workflow tests for packet/result schema validation
- service tests proving deterministic fallback and audit events
- route/e2e tests proving resolved phase output stays player-safe

Required cases:

- deterministic provider preserves current scoring behavior
- OpenAI provider mock output can be accepted
- invalid model JSON falls back
- model output with unknown crew id is rejected and falls back
- model output leaking forbidden hidden truth is rejected and falls back
- resolved reveal contains score, standing, strengths, weaknesses, penalties,
  and safe clues only
- idempotent phase resolution does not call the provider twice

No test should call a real external LLM API.

## Rollout

1. Implement boundary models and deterministic provider.
2. Refactor current resolver through the boundary without behavior change.
3. Add server config and provider factory.
4. Add mocked OpenAI provider with strict schema tests.
5. Add real OpenAI provider behind env flags.
6. Deploy with deterministic provider still active.
7. Enable OpenAI provider in a controlled Railway environment only after audit
   events and fallback behavior are verified.

## Non-Goals

- automatic new campaign generation
- autonomous GM improvisation
- player strategy selection
- voice or Discord integration
- direct local-agent-to-server model delegation
- replacing deterministic validation with model judgment
