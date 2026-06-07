# The Hollow Lodge Design

Date: 2026-06-07
Status: approved planning spec

## Naming

- Game: The Hollow Lodge
- First campaign: Saints & Ledgers
- Starter contract: The Saint's False Finger

The Hollow Lodge is both the game title and the in-world hidden contract
society. Players belong to occult heist crews that compete over contested
contracts, trade or leak evidence, manage heat, and build proof dossiers around
dangerous relics, patrons, and sealed histories.

## Product Goal

The first version should prove a compelling asynchronous multiplayer gameplay
loop for LLM-client users. The game should be playable from Codex-style CLI
sessions while players are also doing other work.

The v1 target is gameplay first:

- stable 3-5 player crews
- contested occult contracts that resolve over hours
- freeform-first actions, normalized before submission
- cross-crew social dealing and targeted proof leaks
- server-authoritative hidden resolution
- local Handler assistance that clarifies and translates without choosing
  strategy
- Eventloom-backed replay and visibility-scoped perspective logs

The v1 target is not a full MMO, territory simulation, human-GM-run roleplay
server, or open-ended MUD.

## Core Loop

The primary player landing page is the personal inbox. It answers:

- what needs me now?
- what changed while I was away?
- what contract phase is about to lock?
- what private offers, proof fragments, or risks need attention?

The contract board is the main game object. It shows available, active, and
contested contracts, phase timers, broad risk language, rival presence, and
entry points into contract play. The crew dashboard supports the loop with crew
heat, members, assets, active contracts, and recent fallout.

The basic loop is:

1. Check inbox.
2. Review contract board.
3. Take side actions such as shallow provenance checks, deal extraction, and
   contradiction review.
4. Take full actions by writing freeform prose that the Handler normalizes.
5. Confirm the normalized action frame.
6. Let the central server validate and resolve actions.
7. Update the living proof dossier.
8. Trade, leak, or inspect proof fragments.
9. Resolve the phase.
10. Review proof standing, heat, rewards, marks, and campaign hooks.

The game should feel like asynchronous occult heist by evidence packet, not a
dungeon crawl.

## Architecture

The game uses a hybrid authoritative/local event model.

The central server is the only authority for game truth. It owns identity, crew
membership, contract state, phase timers, hidden truth, proof asset custody,
heat, visibility, scoring, and final outcomes. It maintains the authoritative
Eventloom log. Every accepted command, generated contract seed,
visibility-scoped message, proof transfer, action submission, resolution,
packet update, score reveal, payout, and campaign transition is appended there.

Each LLM client session keeps a local Eventloom shard. This shard contains the
player's visible server events, local drafts, Handler notes, private summaries,
and player-confirmed submissions. It is a perspective log, not truth. It may be
used for replay, local memory, and async recovery, but the server revalidates
all commands against authoritative state.

The local agent is the player's Handler. In v1, Handler limits are UX policy,
not gameplay mechanics. The Handler sees only the player's visibility-scoped
local log. It clarifies consequences, translates intent, extracts deal terms,
summarizes inbox state, performs shallow side-action checks, and drafts
normalized action frames. It does not choose strategy by default, invent hidden
facts, resolve outcomes, mutate official state, or submit without confirmation.

llmff is a bounded workflow dispatcher, not game authority. It can run typed LLM
pipelines for action parsing, ambiguity detection, proof packet critique, Oracle
narration, campaign and contract seed generation, schema validation, replay/eval
comparisons, and local Handler summaries. The central server validates and
commits outputs before they become game facts.

The Oracle generates contract and campaign seed assets before play begins,
inside authored templates and constraints. The server validates, seals, and
commits those assets into the authoritative log. During play, Oracle workflows
reveal, summarize, and narrate committed facts. They do not retcon core evidence
to match player actions.

## Identity

V1 identity uses invite-code registration and a server-issued local CLI token.
OAuth is out of scope for v1. The account model should not prevent later OAuth
linking for GitHub, Discord, or other providers if the game needs broader
onboarding.

## Crews And Characters

Players join stable crews of 3-5. Crews are the main unit of competition and
heat.

Characters are persistent specialists with heist-functional base roles:

- Face
- Thief
- Fixer
- Lookout
- Cleaner
- Scholar
- Heavy

Roles do not gate proof lanes. Any character can pursue material, provenance,
or witness proof, but roles weight risk, quality, and available interpretation.
For example, a Face can contribute to material proof by manipulating a
conservator into performing a test, while a Scholar can contribute to witness
proof by preparing the contradiction that breaks a witness's story.

Progression exists in v1 as light signals, not a full advancement tree. Players
can receive visible marks, scars, debts, contacts, and specialization drift
hints. Heist-functional roles may later evolve into occult archetypal
specializations through emergent consequences.

## Contracts And Campaigns

Contracts are contested by multiple crews. A contract is generated and sealed
before play begins, with hidden truth, evidence assets, proof hooks, phase
structure, and scoring rubric committed to the authoritative Eventloom.

The starter contract, The Saint's False Finger, is an authenticity proof heist.
Crews compete to prove whether a black-market reliquary auction is selling a
genuine saintly relic, a fraud, or a misrepresented occult object. For v1, the
relic's truth is fixed from the start and known to the server.

Campaigns can be generated by the Oracle as play progresses, but only inside
authored templates, tone constraints, mechanics, and continuity from Eventloom.
Human admin review may exist during alpha, but normal gameplay should not depend
on a human GM.

## Contract Assets

Contract seed assets are generated before the contract opens and then treated as
server truth. Examples include:

- relic description
- hidden authenticity state
- auction house ledger
- chapel timestamp
- conservator nickname
- witness roster
- forged provenance chain
- material anomaly
- occult omen table
- possible leak events
- scoring rubric hooks

The Oracle may generate candidate seed assets, but the server validates and
commits them before play. After play begins, the Oracle reveals and narrates
committed facts; it does not freely invent new core proof assets just because a
player looked somewhere.

Emergent presentation assets can be generated during play from existing facts
and resolution outputs. These include flavor text, witness phrasing, rumor
versions, Handler summaries, and narrated consequences.

## Phases

Contracts resolve across phases lasting hours. A phase can resolve at its
deadline or earlier when enough meaningful actions are locked.

The starter phase pattern is:

```text
Preview -> Access -> Verification -> Auction Lock -> Fallout
```

For the first playable slice, only Auction Preview needs to be fully modeled.

## Actions

Players have two action types per phase.

Side actions are limited per player and lighter weight. They are used for
shallow provenance checks, Handler-assisted deal extraction, inbox summaries,
contradiction checks, and minor preparation.

Full actions are freeform-first hybrid actions that can change contract state.
A player writes prose. The Handler normalizes it into:

- intent
- scope
- approach
- risk posture
- exposed assets

The player confirms before submission.

Players may submit multiple full actions, but extra full actions add crew
noise. Crew noise can raise heat risk, increase leak pressure, make later
actions more watched, or weaken extraction conditions.

Actions are private until result. They are editable or cancelable until phase
lock, then resolve together.

## Proof Dossiers

Each crew maintains a living proof dossier for the contract. The dossier
includes:

- claim
- evidence
- reasoning
- weaknesses
- submitted proof fragments
- known provenance concerns

A campaign-appointed Packet Lead controls dossier framing and final submission.
Other crew members contribute evidence and notes. The Packet Lead is a separate
office from character role, selected at campaign start, and replaceable by a
visible simple-majority crew vote.

Packet contamination is emergent and social. The server does not label sabotage.
It shows contradictions, omitted evidence, weak reasoning, and scoring penalties
after resolution. The crew decides whether the Packet Lead was careless,
compromised, unlucky, or opportunistic.

## Cross-Crew Interaction

V1 supports indirect competition only. Crews can trade, leak, sell, or
selectively reveal proof fragments, but cannot directly sabotage another crew's
tools or actions.

Proof fragments are targeted, copyable, and provenance-tracked. Recipients do
not see full provenance by default. They can spend side actions for shallow
verification, or full actions for deeper verification that risks heat or
exposure.

Private messages are visibility-scoped server events. The server may leak
metadata, rumors, or partial game-relevant fragments through system pressure,
especially heat, cursed channels, risky contracts, or failed deals.

## Heat And Failure

Heat is crew-level only in v1. Heat rises from noisy actions, public exposure,
sloppy evidence handling, leaks, failed covers, and contract fallout. Heat
decays slowly over time, but meaningful reduction requires deliberate cleanup:
bribes, false trails, burned identities, cleanup contracts, or sacrificed
leverage.

Contracts fail forward. A losing or failed crew may still gain partial proof,
campaign hooks, scars, debts, or leverage. Loss remains real through higher
heat, lost assets, weaker payout, damaged credibility, or worse future contract
terms.

## Resolution And Rewards

Proof score is the main contract resolution system. The server scores proof
dossiers against fixed hidden truth and rubric factors:

- evidence credibility
- corroboration
- source independence
- provenance quality
- contradictions
- reasoning quality
- heat/noise penalties
- occult resonance

Scores are hidden during play and visible after resolution. The reveal should
explain why one crew leads or wins without exposing hidden facts that remain
campaign-relevant.

Rewards use a three-part payout:

- Crew gain: money, safehouse/tool progress, heat mitigation, contract access
- Character mark: scar, debt, contact, specialization drift, personal
  consequence
- World leverage: artifact, secret, clue, blackmail, campaign key, occult claim

For The Saint's False Finger, v1 success means one crew takes a visible phase
lead through a cleaner proof dossier, while the rival crew retains a viable
alternate clue path.

## Starter Walkthrough

Contract: The Saint's False Finger
Phase: Auction Preview
Crews: The Gilt Knives vs. The Moth Choir
Phase deadline: 2h 30m
Goal: improve the crew proof dossier before the auction locks.

A player opens Codex during downtime and runs:

```text
/game inbox
```

They see:

```text
INBOX - Gilt Knives

Contract: The Saint's False Finger
Phase: Auction Preview
Time left: 2h 18m
Crew heat: Low, rising

You are needed:
- The proof dossier lacks a verified provenance chain.
- Moth Choir sent you a copied auction ledger fragment.
- Handler read: provenance unclear, passed through at least two hands.
- Packet Lead has marked current claim as "likely false relic."
- You have 2 side actions remaining.
```

The player checks the copied fragment:

```text
/check ledger-fragment-7 provenance
```

Handler responds:

```text
Surface read:
- Fragment appears copied from an auction house ledger.
- Origin masked before it reached Moth Choir.
- The handwriting note may be summary, not transcript.
- Confidence: useful but unsafe as primary proof.

This is a side action. Confirm? y
```

Meanwhile, a Moth Choir player sees:

```text
INBOX - Moth Choir

Gilt Knives inspected your ledger fragment.
No leak detected yet.
Your Packet Lead has not incorporated the reliquary dream-note.
Auction Preview closes in 2h 04m.
```

Moth Choir sends a targeted message:

```text
/msg @gilt-knives.face
"We'll trade the conservator's nickname for your chapel timestamp. No public
claims until lock."
```

The Gilt Knives player asks the Handler to structure it:

```text
/deal extract last-message
```

Handler drafts:

```text
Possible deal:
- Type: targeted proof exchange
- They offer: conservator nickname
- They request: chapel timestamp
- Term: neither side publishes before phase lock
- Enforcement: reputational/logged promise only
- Ambiguity: "public claims" may not include private resale

Confirm proposal? n
```

The player declines and takes a full action instead:

```text
/act
I pose as a bored clerk correcting bidder credentials and compare the auction
ledger's saint-date entries against the chapel timestamp we recovered earlier.
I am looking for copied errors, not trying to steal the ledger.
```

Handler normalizes:

```text
Intent: test ledger authenticity against known chapel timestamp
Approach: deception / provenance analysis
Risk posture: cautious
Assets exposed: false clerk identity, chapel timestamp
Scope: one verification attempt, no theft
Crew noise: normal

Confirm? y
```

Server accepts the action and keeps it private until resolution.

Moth Choir takes a stranger action:

```text
/act
I whisper the relic's auction name into a moth jar and watch whether the insects
settle into a fingerbone pattern.
```

Handler normalizes:

```text
Intent: test occult resonance of the relic's name
Approach: occult observation
Risk posture: standard
Assets exposed: moth jar, ritual attention
Scope: one symbolic test
Crew noise: normal

Confirm? y
```

At phase lock, the server resolves both crews' actions.

Gilt Knives result:

```text
RESULT - private to Gilt Knives

Your clerk identity held.

The ledger fragment contains a copied dating error that also appears in a known
forged chapel index. This does not prove the finger is false, but it weakens the
auction house provenance.

Evidence added:
- forged-date correlation
- chapel timestamp comparison
- ledger credibility reduced

Heat: +1 trace, no public exposure
```

Moth Choir result:

```text
RESULT - private to Moth Choir

The moths formed no fingerbone.

They formed a door.

Handler read: the relic may be less important as a body part than as a key or
credential. This is not strong proof of authenticity, but it may matter later.

Evidence added:
- symbolic door-pattern omen
- uncertain occult relevance

Heat: no change
Leak pressure: minor, ritual channel noticed
```

Packet Leads update dossiers.

Gilt Knives dossier:

```text
Claim: The finger is likely false or misrepresented.
Best evidence:
- forged-date correlation
- chapel timestamp comparison
- masked ledger provenance
Weakness:
- no direct material test yet
```

Moth Choir dossier:

```text
Claim: The relic's advertised identity is incomplete.
Best evidence:
- moth jar door omen
- conservator nickname lead
Weakness:
- omen has no corroboration
- provenance packet is contaminated
```

Phase score reveal after resolution:

```text
AUCTION PREVIEW - PHASE RESULT

Current proof standing:
1. Gilt Knives - Strong lead
   Strength: clean provenance contradiction
   Weakness: no material confirmation
   Penalty: minor heat trace

2. Moth Choir - Viable but unstable
   Strength: occult clue may unlock alternate lane
   Weakness: uncorroborated omen, contaminated ledger chain
   Penalty: none

Contract state:
- Auction house provenance is now suspect.
- Material inspection lane remains open.
- Witness lane remains open.
- Moth Choir's door omen may become relevant in the next phase.
```

## V1 Out Of Scope

- OAuth login
- territory control
- NPC crews as active competitors
- direct crew-on-crew sabotage
- within-crew betrayal as an explicit v1 mechanic
- full character advancement trees
- local Handler as an in-game upgrade/stat system
- human GM dependency for normal contract operation
- fully public launch onboarding
- mobile or graphical client
- exact odds display for hidden resolution

## Open Follow-Ups

- Define the exact starter command grammar.
- Define Eventloom event schemas for server truth and local perspective logs.
- Define the first contract seed schema.
- Define the proof scoring rubric in executable terms.
- Decide the implementation stack for the server and CLI client.
- Write the first implementation plan after this spec is reviewed.
