# Escrowed Artifact Deals Design

Date: 2026-06-08
Status: draft planning spec

## Scope

Add a brokered deal system for The Hollow Lodge. The first version focuses on
server-enforced artifact swaps between crews. This replaces honor-only artifact
trading with an authoritative deal object that players and local agents can
inspect, reason about, accept, and fulfill.

This spec does not add a marketplace, auction house, fiat currency, generic
item inventory, legal contract system, reputation economy, or AI-negotiated
strategy. Deals are still player-authored and player-confirmed.

## Product Goal

Asynchronous CLI play needs reliable exchange. If players cannot trust the
basic mechanics of a trade, they will avoid trading or invent clumsy
workarounds. Betrayal should come from incomplete information, contaminated
evidence, soft promises, selective disclosure, and later strategic choices, not
from the server failing to enforce a simple artifact swap.

The v1 goal is:

- players can propose an artifact-for-artifact deal between crews
- both sides can review concrete terms before accepting
- the server validates that each side can escrow its offered artifact
- accepted concrete artifact swaps resolve atomically
- soft promises are recorded for later accountability but are not enforced
- all deal state is visibility-scoped and replayable from Eventloom

## Design Position

Use a hybrid deal model:

- **Concrete artifact terms are enforceable.**
  If both sides accept, the server transfers copies of the offered artifacts to
  the receiving side. Either all concrete artifact transfers happen, or none do.

- **Soft promise terms are recorded.**
  Promises like "do not cite us", "keep this quiet", "share future chapel
  leads", or "stand down next phase" are visible deal terms. The server does
  not automatically enforce them in v1.

- **Betrayal remains possible above the transaction layer.**
  A crew can trade a genuine artifact that is misleading, contaminated, or only
  part of the picture. A crew can later break a recorded soft promise, creating
  leverage, heat, or reputation hooks in later work.

## Core Concepts

### Deal

A deal is an authoritative server object with:

- `deal_id`
- `contract_id`
- `proposer_crew_id`
- `recipient_crew_id`
- `status`
- `offered_artifact_ids`
- `requested_artifact_ids`
- `soft_terms`
- `expires_phase`
- `proposer_player_id`
- `accepted_by_player_id`
- timestamps derived from committed events

V1 statuses:

```text
proposed
accepted
fulfilled
declined
canceled
```

For v1, `fulfilled` follows immediately after `accepted` when all artifact
escrow checks and transfers succeed.

Reserved later statuses:

```text
expired
broken
```

### Artifact Escrow

Escrow is logical, not a new inventory container. On acceptance, the server:

1. Verifies the accepting player is a member of the recipient crew.
2. Verifies the proposed deal is still `proposed`.
3. Verifies the proposer crew can still view every offered artifact.
4. Verifies the recipient crew can still view every requested artifact.
5. Creates transfer copies for both sides using existing artifact transfer
   provenance.
6. Appends a deal fulfillment event with all resulting copy ids.

Deal fulfillment grants the resulting copies to the receiving crews, not only
to the accepting player. A member can accept on behalf of the crew, but the
artifact access created by the deal is crew-scoped.

If any validation fails, the server rejects acceptance and leaves the deal in
`proposed` unless the failure means it should be expired or canceled by a later
explicit command.

This avoids a half-completed swap.

### Soft Terms

Soft terms are plain text strings attached to the deal. They are not executed
by the server in v1.

Examples:

```text
Do not cite our crew as source.
Do not publish this before Auction Lock.
Share any chapel follow-up artifacts this phase.
```

Later mechanics can let crews mark a deal as broken, cite broken terms in
dossiers, or use broken terms as leverage. V1 only records them and renders
them.

## Event Types

Add these authoritative event types:

```text
deal.proposed
deal.accepted
deal.fulfilled
deal.declined
deal.canceled
```

Reserved later event types:

```text
deal.expired
deal.broken
```

Visibility:

- Deal events are visible to both involved crews.
- Deal artifact transfers remain visible according to the existing artifact
  transfer event visibility.
- No deal event is public in v1.
- Server-only validation details should not be exposed unless they are already
  visible through artifact events.

## API Shape

Add deal routes under `/deals`.

### Propose Deal

```text
POST /deals
```

Request:

```json
{
  "contract_id": "contract_false_finger",
  "proposer_crew_id": "crew_0001",
  "recipient_crew_id": "crew_0002",
  "offered_artifact_ids": ["artifact_ledger_rubric"],
  "requested_artifact_ids": ["artifact_chapel_debt_mark"],
  "soft_terms": ["Do not cite our crew as source."],
  "expires_phase": "Auction Preview"
}
```

Rules:

- proposer must provide `proposer_crew_id`
- proposer must be a member of `proposer_crew_id`
- recipient crew must exist
- proposer must currently see every offered artifact
- requested artifact ids are allowed to be unknown to proposer; they are
  validated against recipient visibility on acceptance
- idempotency key replay must match

### Accept Deal

```text
POST /deals/{deal_id}/accept
```

Rules:

- actor must be a member of recipient crew
- deal must be `proposed`
- artifact visibility checks for both crews must pass
- server appends `deal.accepted`
- server appends the required artifact transfer events
- server appends `deal.fulfilled`
- idempotency replay returns the fulfilled deal

### Decline Deal

```text
POST /deals/{deal_id}/decline
```

Rules:

- actor must be a member of recipient crew
- deal must be `proposed`
- server appends `deal.declined`

### Cancel Deal

```text
POST /deals/{deal_id}/cancel
```

Rules:

- actor must be a member of proposer crew
- deal must be `proposed`
- server appends `deal.canceled`

### List Deals

```text
GET /deals
```

Returns deals visible to the current player through crew membership.

## Client And Codex Surface

CLI commands should be concrete and scriptable:

```text
hollow-lodge deals
hollow-lodge deal propose --from-crew crew_0001 --to-crew crew_0002 \
  --offer artifact_ledger_rubric --request artifact_chapel_debt_mark \
  --soft-term "Do not cite our crew as source."
hollow-lodge deal accept deal_000001
hollow-lodge deal decline deal_000001
hollow-lodge deal cancel deal_000001
```

Codex render surfaces should show:

- incoming proposed deals in inbox
- active and recent deals on crew board
- offered/requested artifact ids
- soft terms
- status
- whether acceptance will trigger escrowed transfer

The local agent may summarize deal consequences and draft deal proposals, but
it must not accept, cancel, or propose without player confirmation.

## Data Flow

1. A player sees an artifact and a possible cross-crew exchange.
2. The local agent drafts terms from player intent.
3. Player confirms `deal propose`.
4. Server validates proposer crew membership and offered artifact visibility.
5. Server appends `deal.proposed`.
6. Recipient sees the incoming deal in inbox and crew board.
7. Recipient accepts.
8. Server validates recipient crew membership and both sides' current artifact
   visibility.
9. Server creates artifact copy transfers for both sides.
10. Server appends `deal.accepted` and `deal.fulfilled`.
11. Both crews see the fulfilled deal and new artifact copies.

## Failure Handling

Validation failures should be explicit:

- `403 not a crew member`
- `404 deal not found`
- `404 crew not found`
- `404 artifact not found`
- `409 deal not proposed`
- `409 idempotency key conflict`
- `409 artifact no longer available`

No partial fulfillment is allowed. If one transfer fails, the accept command
must fail before appending fulfillment. The implementation should perform all
visibility checks before appending transfer or fulfillment events.

## Testing

Tests should cover:

- proposing a visible artifact deal between crews
- recipient sees incoming deal
- accepting atomically creates artifact transfer copies for both crews
- hidden or unavailable offered artifact rejects proposal
- requested artifact unavailable to recipient rejects acceptance
- replaying propose/accept with same idempotency key returns same result
- reusing an idempotency key with different payload returns conflict
- non-member cannot propose, accept, decline, or cancel
- fulfilled deals render in inbox/crew board
- soft terms are preserved but not enforced

## Out Of Scope

- escrow for proof fragments
- currency
- marketplace search
- automatic reputation penalties
- automatic enforcement of soft promises
- public deal feeds
- multi-party deals
- partial fulfillment
- anonymous deals

## Open Extension Points

- Mark a soft term as broken.
- Add deal-derived leverage to proof dossiers.
- Add heat or reputation consequences for broken terms.
- Add expiry at phase lock.
- Add artifact contamination warnings before acceptance.
- Add local-agent extraction from chat messages into draft deal proposals.
