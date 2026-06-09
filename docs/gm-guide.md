# GM Guide

This guide is for human GMs and content authors building contracts for The
Hollow Lodge. It explains the setting, the kind of stories that fit the game,
and the practical structure a contract seed needs before it can be activated on
the server.

The goal is to reduce GM load without surrendering contract authorship to an
oracle. For alpha, contracts should be human-approved. An LLM can draft,
critique, and validate, but a person should own the premise, hidden truth,
artifact topology, unlock path, and final approval.

## What The Game Is

The Hollow Lodge is a competitive occult investigation game about proof,
custody, and leverage.

Players do not usually win by stealing the thing. They win by proving what the
thing is, proving who lied about it, proving where it came from, or proving why
someone else needs the truth suppressed. The action is heist-shaped, but the
main resource is information.

Every contract begins with a sealed truth known to the server. Crews receive
visibility-scoped artifacts, trade or leak copies, submit freeform actions, and
build proof dossiers. At phase lock, the server scores the dossiers and
confirmed actions against the hidden evidence graph.

The best contracts feel like contested provenance:

- a relic may be genuine, forged, misattributed, or occult in a way that makes
  the public question too simple
- an auction lot may be legal property, stolen property, debt collateral, or a
  lure
- a witness may be lying, mistaken, compromised, or telling a true story for the
  wrong reason
- an artifact may prove one lane while poisoning another

## World Backdrop

The Hollow Lodge is a hidden broker of occult contracts. It does not give crews
truth. It gives crews access to contested work, partial records, and a way to be
paid when their proof holds up.

The public world is close to ours, but with a concealed economy of relics,
sealed ledgers, church-adjacent fraud, estate law, debt marks, private
collections, auction houses, family archives, restoration labs, and old
institutions that keep records they should have burned.

The Lodge is not a wizard academy or a monster-hunting guild. It is closer to a
private clearing house for dangerous provenance.

Common institutions:

- auction houses and preview rooms
- chapel archives and reliquary vaults
- restoration labs and conservators
- private collectors and estate lawyers
- debt offices, insurers, and old banks
- city clerks, undertakers, and parish record keepers
- occult reading rooms hidden inside ordinary bureaucracy

Common pressure sources:

- a patron wants a lot authenticated before public sale
- a collector wants a rival discredited
- a family wants an inheritance object buried
- a church wants a relic quietly disproved
- an insurer wants proof without admitting exposure
- a cult wants ownership, not publicity
- the Lodge wants to know which crew can handle harder work

## Tone

The tone is stylish dark adventure. It should be precise, tactile, and human.
Use occult implication more than spectacle.

Prefer:

- ledgers, seals, wax, soot, old handwriting, wrong dates, missing receipts
- favors, debts, blackmail, provenance chains, and social pressure
- relics whose danger is legal, spiritual, reputational, or historical
- horror that arrives through what the evidence implies
- names that sound like institutions, families, records, streets, and saints

Avoid:

- generic fantasy quests
- direct combat as the main solution
- monsters as the central proof object
- puzzle boxes with only one clever answer
- lore dumps that players cannot act on
- public text that states the hidden truth outright

Good Hollow Lodge phrasing:

- "The chapel seal is real. The custody claim is not."
- "The soot cooled before the fire began."
- "The witness remembers the right room from the wrong year."
- "The saint is false, but the debt mark is older than the fraud."
- "The lot card is clean because the dirty record was moved."

Weak phrasing:

- "A cursed item is for sale."
- "Find out if the relic is evil."
- "The players must defeat the cult."
- "The artifact is secretly a demon finger."

## Campaign Frames

A campaign frame is a container for multiple related contracts. It gives GMs a
shared texture, recurring institutions, and a reason contracts build on each
other.

The current first campaign frame is `Saints & Ledgers`.

### Saints & Ledgers

This frame concerns relic auctions, church records, estate debts, forged
custody chains, and devotional objects that have become financial instruments.

Use this frame when a contract involves:

- saints, reliquaries, bone fragments, prayer objects, devotional jewelry
- auction previews and private lots
- false provenance or corrected catalogues
- chapel debts, old parish books, or hidden benefactors
- conservators, clerks, rival collectors, and insurers
- occult traces that can be misread as ordinary fraud

Recurring questions:

- Is the object genuine, forged, misattributed, or something worse?
- Who benefits from the public story?
- Which record was altered, and who had access?
- What debt or obligation follows the object?
- What can a crew prove without exposing how they learned it?

## Contract Anatomy

A contract is not just a premise. It is a sealed evidence system.

Every contract needs:

- public premise
- fixed hidden truth
- proof dossier needs
- artifact graph
- public starting artifacts
- unlock rules
- scoring hints
- safe reveal strings
- smoke-test path

Optional advanced pieces:

- phase rewards
- follow-up contract seeds
- unlock requirements tied to prior crew performance
- campaign arc metadata

## The Public Premise

The public premise is what crews see on the contract board. It should be short,
specific, and playable.

It should answer:

- What is being contested?
- Why does proof matter now?
- What kind of institution or patron is involved?
- What are the obvious proof lanes?

Good premise:

> A townhouse window keeps showing tomorrow's fire in yesterday's soot.

Good premise:

> A black-market reliquary auction claims to hold the finger of Saint Aint, but
> the custody chain has been copied in three different hands.

Weak premise:

> Investigate a cursed relic.

The premise should not reveal the hidden truth. It should create two or three
plausible interpretations.

## Hidden Truth

The hidden truth is fixed before play. It is not improvised in response to
player theories.

A hidden truth should be:

- short enough to summarize in one sentence
- specific enough to score against
- not fully visible in any public artifact
- connected to several artifacts, not one magic clue
- capable of producing partial wins

Examples:

- The finger is a saint-bone forgery, but the chapel debt mark attached to it is
  a real occult obligation.
- The window is a cinder oracle that shows fires before they are set.
- The witness did see the dead patron, but only because the estate clock repeats
  one hour every winter.

Avoid hidden truths that are only flavor:

- "The relic is cursed."
- "The house is haunted."
- "The patron is evil."

Those are moods, not scoreable truths.

## What Players Learn

The hidden truth is not a riddle answer that appears on the contract board. It
is server-side adjudication material. During play, players should only see
artifacts, visible graph links, crew actions, trades, rumors, and safe reveal
text.

At resolution, players should learn a bounded case finding: what the winning
proof established, what remains uncertain, and which visible artifacts carried
the result. This should not dump the raw `hidden_truth.summary` or server-only
truth id. It should translate the hidden truth into player-facing closure.

Good case finding:

> The evidence supports a forged relic with a genuine chapel debt attached. The
> false custody chain lost, but the debt mark survived scrutiny.

Weak case finding:

> Hidden truth: `truth_false_finger_forgery`.

If players never learn what their proof established, the hidden truth becomes a
floating signifier. If they learn it too early or too literally, the contract
stops being an investigation. Keep the raw truth sealed; reveal the consequence
of the proof.

## Proof Lanes

Proof lanes are the ways a crew can build a compelling packet. They give the GM
and the scoring system a way to understand what kind of proof the artifacts
support.

Common lanes:

- `provenance`: custody, ownership, dates, signatures, catalogues
- `material`: ink, bone, soot, glass, residue, restoration marks
- `witness`: testimony, contradictions, social leverage, memory
- `leverage`: motive, debt, blackmail, institutional pressure
- `occult`: omens, impossible timing, ritual marks, inherited obligations

Roles do not gate lanes. A Face can pursue material proof by manipulating a
conservator. A Scholar can pursue witness proof by preparing the contradiction
that breaks testimony.

For alpha, each contract should have three dossier needs, usually one from each
of these clusters:

- factual chain: provenance or chronology
- physical trace: material or occult anomaly
- social pressure: witness or leverage

## Artifact Graphs

The artifact graph is the core of a contract. It is the server-owned evidence
map. Players see only the artifacts and links their crew has access to.

An artifact graph has:

- artifacts
- edges between artifacts
- unlock rules
- public starting artifact ids

### Artifact Count

For alpha contracts, use 4-6 artifacts.

Recommended shape:

- 2 public starting artifacts
- 2 action-unlocked artifacts
- 1 optional high-value artifact
- 1 phase reward or campaign hook artifact, if needed

Too few artifacts makes the proof obvious. Too many artifacts makes authoring
and player comprehension harder.

### Artifact Types

Artifacts are source material, not generic clues. Each artifact should be
something a player can cite.

Good artifacts:

- auction lot card
- copied ledger page
- chapel debt rubbing
- clerk's pencil correction
- soot sample receipt
- conservator's wash note
- witness appointment book
- insurance rider
- parish index card
- restoration photograph

Weak artifacts:

- "a clue"
- "a rumor"
- "mysterious energy"
- "a bad feeling"

Rumors can exist, but they are better as social pressure events than core proof
artifacts unless they have a source chain.

### Artifact Fields

Each artifact should include:

- `artifact_id`: stable machine id
- `contract_id`: owning contract id
- `kind`: short category
- `title`: player-facing name
- `public_summary`: safe summary for visible lists
- `full_text`: inspectable source text
- `tags`: action matching and search handles
- `proof_lanes`: lanes this artifact supports
- `phase_relevance`: phase names where it matters
- `visible_flags`: safe public notes
- `hidden_flags`: server-side notes that must not render to players

Artifact ids should be descriptive:

- `artifact_lot_card`
- `artifact_ledger_rubric`
- `artifact_chapel_debt_mark`
- `artifact_soot_sample`

Avoid ids like:

- `artifact_1`
- `clue_a`
- `secret_truth_piece`

### Edges

Edges are relationships between artifacts. They help agents and players see
what known artifacts imply without revealing hidden truth.

Common edge relations:

- `contradicts`
- `points_to`
- `corroborates`
- `undermines`
- `explains`
- `dates`
- `names`

Each edge needs:

- `source_id`
- `target_id`
- `relation`
- `public_summary`

Good edge:

```json
{
  "source_id": "artifact_lot_card",
  "target_id": "artifact_ledger_rubric",
  "relation": "contradicts",
  "public_summary": "The public lot card and copied ledger disagree on custody."
}
```

The public summary should state the visible relationship, not the hidden truth.

## Unlock Rules

Unlock rules decide how crews discover hidden artifacts.

For alpha, prefer simple action-triggered unlocks:

```json
{
  "rule_id": "unlock-soot-sample",
  "artifact_id": "artifact_soot_sample",
  "contract_id": "contract_ash_window",
  "phase": "Cinder Preview",
  "trigger": "action_mentions_tag",
  "required_terms": ["soot"],
  "award_scope": "crew",
  "award_reason": "Followed the ash notice to the soot sample."
}
```

Design rules:

- Every action-unlocked artifact should have at least one visible breadcrumb.
- Required terms should be fair and likely from public artifacts.
- Avoid requiring exact poetic language.
- Use 1-2 terms for most rules.
- Do not hide all viable proof behind one obscure unlock.
- Do not make every crew receive every artifact automatically.

Good required terms:

- `chapel`
- `clerk`
- `catalogue`
- `soot`
- `cooling`
- `ledger`

Bad required terms:

- `truth_ash_window_future_burn`
- `cinder oracle`
- `debtor-omen`
- an NPC name that never appears publicly

Unlocks should make crews feel clever, not punished for failing to guess the
GM's vocabulary.

## Public Starting Artifacts

Each contract should begin with enough source material for action.

Use 1-2 public artifacts for alpha.

A good starting pair:

- public lot card
- copied ledger page

Another good starting pair:

- ash lot notice
- witness appointment stub

The starting artifacts should create an obvious question and point to at least
one hidden artifact.

## Scoring Hints

Scoring hints are not full scoring logic. They guide phase resolution and safe
reveal text.

Use:

```json
"scoring_hints": {
  "rubric_hooks": [
    "fire chronology",
    "material residue",
    "witness leverage"
  ],
  "allowed_reveal_strings": [
    "Fire chronology is now suspect.",
    "Residual soot points toward another lead."
  ]
}
```

Rubric hooks should correspond to dossier needs and proof lanes.

Allowed reveal strings are player-safe resolution text. They should reveal
consequences or partial truths without dumping the hidden truth unless the phase
is meant to reveal it.

Good reveal string:

- "Auction house provenance is now suspect."

Bad reveal string:

- "The finger is a forged saint bone and the chapel debt mark is the real occult
  object."

## Typed Claims

Typed claims are scored assertions in the crew dossier. They are how the game
avoids turning proof packets into essay contests.

A claim has:

- subject id
- predicate
- object id or value
- cited artifact ids

Example:

```sh
hollow-lodge dossier typed-claim artifact_ledger_rubric \
  contradicts_clean_provenance \
  --object-id artifact_lot_card \
  --citation artifact_ledger_rubric \
  --confirm
```

When designing a contract, imagine the typed claims you want strong crews to
discover.

Examples:

- `artifact_ledger_rubric contradicts_clean_provenance artifact_lot_card`
- `artifact_soot_sample contradicts_fire_chronology artifact_ash_notice`
- `artifact_chapel_debt_mark supports_leverage_against artifact_lot_card`

Predicates should be plain and domain-specific. Avoid requiring an exact hidden
truth phrase. The GM should be able to understand what a claim means without
reading a paragraph.

## Action Design

Players submit freeform actions. The server compiles them into bounded action
intent before resolution.

As a GM, you do not need to write all possible actions. You need to seed public
artifacts and unlock tags so reasonable actions can find more evidence.

Good public breadcrumb:

- Artifact text mentions "chapel seal."
- Unlock rule listens for `chapel`.
- Hidden artifact is a chapel debt mark.

Weak breadcrumb:

- Artifact text mentions "a strange symbol."
- Unlock rule listens for `debtor-omen`.

The second version feels unfair because the players cannot know the term.

## Social Design

Contracts should encourage crews to talk, trade, and doubt each other.

Ways to create social pressure:

- give Crew A an artifact that Crew B can use better
- make one artifact support leverage but not material proof
- include a soft-term risk, such as "do not cite our crew as source"
- make a traded copy useful but provenance-sensitive
- let one crew unlock a clue that completes another crew's visible edge

Do not make betrayal depend on broken trade plumbing. Mechanical artifact swaps
should be reliable. Betrayal should live in timing, omissions, leaks, soft
terms, and selective disclosure.

## Legacy And Future Advantages

Contracts can matter after they resolve, but continuity should mostly flow
through crew legacy, not loose inventory notes.

The server records bounded legacy facts such as:

- `reputation`: the crew is known for reliable proofwork
- `heat`: prior work drew attention
- `favors`: institutions or patrons owe the crew useful access
- `debts`: the crew owes someone, or left obligations behind
- `scars`: named consequences from weak or costly outcomes
- completed contracts: proof that the crew finished a specific contract phase
- deal conduct: whether the crew uses escrowed deals reliably
- rumor memory: bounded history from rumor containment, exploitation, or
  integration

These are crew-level facts. They are designed to be checked by future contracts
without requiring the GM to remember private conversations, raw event payloads,
or bespoke promises.

### The Default Rule

Future advantages should be checkable ledger state.

Prefer:

> Crew has reputation 2, so the restoration lab takes their request seriously.

Avoid:

> The GM remembers that the lab liked them last time.

Prefer:

> Crew completed `contract_false_finger`, so this follow-up contract is visible.

Avoid:

> The crew has "the vibe" of being trusted by auction people.

This keeps continuity auditable, visible, and fair across asynchronous play.

### What Rewards Can Do

A future contract can use crew legacy to:

- unlock the contract for qualified crews
- reveal a better starting artifact
- reduce ambiguity around a public clue
- add a safe future opportunity line on the crew board
- make an NPC or institution easier to approach
- let a crew cite prior work as leverage
- increase risk when heat, debts, or scars follow the crew
- create a harder version of the contract for crews with too much attention

Good future advantage:

```json
{
  "scope": "crew",
  "metric": "reputation",
  "minimum": 2,
  "label": "Known Reliable Proofwork",
  "description": "Prior strong work gives this crew an opening."
}
```

Good future gate:

```json
{
  "scope": "crew",
  "metric": "completed_contract",
  "required_contract_id": "contract_false_finger",
  "minimum": 1,
  "label": "Auction Preview Veteran",
  "description": "This work is offered to crews that resolved the prior auction proof."
}
```

### Carried Artifacts

Phase rewards can grant artifacts, and rewarded artifacts can influence later
play. Use this sparingly.

The normal pattern should not be:

> A key from Contract 1 opens the only door in Contract 2.

That creates brittle inventory continuity:

- Who owns the key?
- Can it be traded?
- Can it be copied?
- What if the key-holder stops playing?
- Does one crew become the only viable participant?
- Does the GM need to remember every object forever?

The Hollow Lodge pattern is:

> A proof win in Contract 1 gives the crew a reputation, favor, or artifact that
> changes how Contract 2 opens.

Good carried artifact:

- a copy of a chapel rubbing that gives leverage with a parish clerk
- a restoration lab note that makes a material test faster
- a sealed invitation that reveals a private auction preview
- a disputed ledger copy that can be cited, but carries provenance risk

Bad carried artifact:

- the only key to the next contract
- a unique object that prevents other crews from meaningfully playing
- an item whose effect is not represented in crew legacy, visibility, or a seed
  rule

If a carried artifact matters, make it:

- crew-scoped
- visible on relevant crew/player surfaces
- non-blocking or replaceable by another harder path
- copyable when trade is part of the intended play
- represented by an explicit phase reward, unlock rule, or future requirement

### Heat, Debts, And Scars Are Also Continuity

Future advantages are not only positive.

Prior heat can make a contract riskier:

> Prior heat makes The Ash Window riskier for this crew.

Debts can create pressure:

> The collector will open the archive, but only if the crew accepts a bad soft
> term.

Scars can change approach:

> The crew's prior public failure makes witness leverage harder, but it also
> makes underworld contacts more candid.

Do not use negative legacy to shut players out entirely unless there is another
available route. Negative continuity should create texture and tradeoffs, not a
dead end.

### GM Rules For Future Advantages

Use these rules when writing campaign continuity:

- Encode future advantages as legacy metrics, completed-contract checks, phase
  rewards, or explicit seed rules.
- Do not rely on private GM notes to decide who gets access.
- Do not make a single carried object the only way to play a future contract.
- Keep advantages crew-level unless player-level persistence is explicitly
  designed for that contract.
- Render enough of the advantage that players know why their crew is being
  treated differently.
- Keep hidden sources hidden; render safe summaries, not private event details.
- Let strong outcomes create opportunity, but let weak outcomes create
  interesting pressure rather than permanent exclusion.

### Authoring Prompt For Continuity

When drafting a follow-up contract, answer:

- Which prior contract can matter?
- Which crew legacy metric does it check?
- What advantage or complication appears?
- Is there a non-legacy fallback path?
- Is the effect visible enough for players to understand?
- Does this advantage reveal hidden truth from the prior contract?

Example:

> Crews with reputation 2 or higher begin with the private restoration ledger.
> Other crews can still find it by pressuring the clerk, but that action raises
> heat.

That is a good Hollow Lodge advantage: prior success matters, but the future
contract remains playable.

## Difficulty

Use this rough scale for alpha contracts.

Easy:

- 3-4 artifacts
- 1 hidden artifact
- 1 obvious contradiction
- 1 unlock term visible in public text
- strong packet can be built without trading

Standard:

- 4-6 artifacts
- 2 hidden artifacts
- 2-3 edges
- at least one useful cross-crew trade
- strong packet needs one unlocked artifact or a good typed claim

Hard:

- 6 artifacts
- several plausible false interpretations
- unlocks require choosing between risk postures
- no crew starts with all lanes
- strong packet likely needs trade or social leverage

Do not start alpha with hard contracts.

## Contract Seed Skeleton

Use this as the starting shape:

```json
{
  "campaign": {
    "campaign_id": "campaign_saints_ledgers",
    "title": "Saints & Ledgers"
  },
  "contract": {
    "contract_id": "contract_example",
    "campaign_id": "campaign_saints_ledgers",
    "title": "The Example Relic",
    "premise": "One sentence public premise.",
    "phase": {
      "name": "Auction Preview",
      "remaining_hours": 6
    },
    "evidence_assets": [
      {
        "asset_id": "asset_public_notice",
        "title": "Public Notice",
        "public_summary": "Safe public summary."
      }
    ],
    "proof_dossier_needs": [
      "provenance chain",
      "material authenticity",
      "auction leverage"
    ],
    "crew_heat": 0
  },
  "hidden_truth": {
    "truth_id": "truth_example",
    "summary": "One sentence server-only truth."
  },
  "artifact_graph": {
    "contract_id": "contract_example",
    "artifacts": [],
    "edges": [],
    "unlock_rules": []
  },
  "public_artifact_ids": [],
  "scoring_hints": {
    "rubric_hooks": [],
    "allowed_reveal_strings": []
  }
}
```

## Authoring Workflow

Use this workflow for a new contract.

1. Write the public premise.
2. Write the hidden truth in one sentence.
3. Choose three proof dossier needs.
4. List 4-6 artifacts.
5. Mark 1-2 artifacts as public starting artifacts.
6. Add 2-3 edges between artifacts.
7. Add 1-2 unlock rules.
8. Write 2-3 likely strong typed claims.
9. Write scoring hints and safe reveal strings.
10. Read all public fields and check that hidden truth is not directly stated.
11. Run seed validation.
12. Run a smoke playthrough.
13. Review the rendered contract board and artifact graph.
14. Approve only if a crew can form a strong packet from visible and unlocked
    evidence.

## GM Review Checklist

Before activation, answer these questions.

Premise:

- Is the contract understandable in one sentence?
- Does it create urgency?
- Does it fit the campaign frame?
- Are there at least two plausible interpretations?

Hidden truth:

- Is it fixed?
- Is it scoreable?
- Is it connected to multiple artifacts?
- Is it absent from public summaries and reveal strings?

Artifact graph:

- Are all artifact ids unique?
- Do edges reference real artifacts?
- Does every hidden artifact have a fair breadcrumb?
- Do public artifacts point toward action?
- Are hidden flags safe from render surfaces?

Unlocks:

- Are required terms visible or inferable?
- Can more than one crew plausibly unlock useful evidence?
- Is at least one strong proof path possible without guessing?

Scoring:

- Do dossier needs match artifact lanes?
- Are typed claims obvious enough to form but not automatic?
- Do reveal strings avoid hidden truth leaks?
- Can a weak packet, partial packet, and strong packet be distinguished?

Social play:

- Is there something worth trading?
- Is there a reason to withhold or selectively reveal?
- Are soft terms meaningful without being server-enforced?

Operations:

- Does the seed validate?
- Does the contract smoke resolve?
- Does rendering omit hidden truth?
- Does the contract fit the current alpha duration?

## Oracle Assistance

An LLM can help author contracts, but it should not publish them directly in
alpha.

Useful oracle tasks:

- draft artifact text from a GM brief
- propose artifact links
- suggest unlock tags
- identify hidden truth leaks
- propose typed claims
- critique whether proof lanes are balanced
- generate safe reveal strings
- rewrite public text for tone

Unsafe oracle tasks:

- autonomously activating contracts
- changing hidden truth during play
- inventing new core artifacts after contract start
- scoring freeform prose directly
- deciding that a player theory becomes true because it is clever

Recommended prompt shape:

```text
Draft a Hollow Lodge contract seed candidate.
Campaign: Saints & Ledgers.
Public premise: ...
Hidden truth: ...
Tone: occult bureaucracy, auction provenance, restrained horror.
Constraints:
- 5 artifacts
- 2 public starting artifacts
- 2 unlock rules using public action terms
- 3 proof dossier needs
- hidden truth must not appear in public_summary, full_text, or reveal strings
- include 3 likely typed claims
Return JSON plus a separate GM review note.
```

The GM should then validate, smoke, and edit. Treat the oracle as a drafting
assistant, not an authority.

## Worked Mini Example

Premise:

> A townhouse window keeps showing tomorrow's fire in yesterday's soot.

Hidden truth:

> The window is a cinder oracle that shows fires before they are set.

Public starting artifact:

- `artifact_ash_notice`: a lot notice says the frame was recovered before the
  fire

Hidden artifact:

- `artifact_soot_sample`: a receipt notes glass soot with an impossible cooling
  pattern

Edge:

- `artifact_ash_notice points_to artifact_soot_sample`

Unlock:

- action mentions `soot`
- award `artifact_soot_sample` to the acting crew

Strong typed claim:

- `artifact_soot_sample contradicts_fire_chronology artifact_ash_notice`

Safe reveal:

- "Fire chronology is now suspect."

This contract works because the public artifact gives players something to do,
the hidden artifact deepens the proof rather than replacing it, and the strong
claim is grounded in cited source material.

## Common Failure Modes

### The Crossword

The GM knows the answer, but players cannot infer the required term. Fix by
putting the unlock term or a close synonym in public artifact text.

### The Single Smoking Gun

One artifact proves everything. Fix by splitting proof across provenance,
material, and leverage lanes.

### The Lore Dump

Artifacts explain the world but do not support a scored claim. Fix by making
each artifact citeable against a specific dossier need.

### The Hidden Truth Leak

Public summary or reveal text says the true answer. Fix by rewriting public
text as contradiction, anomaly, or pressure rather than conclusion.

### The No-Trade Contract

Every crew can get every important artifact alone. Fix by making at least one
artifact more useful to another crew or by giving tradeable copies provenance
cost.

### The Essay Contest

The contract rewards persuasive prose more than evidence. Fix by designing
clear typed claims and making scoring depend on cited artifacts, known edges,
compiled actions, and server state.

## Activation And Smoke

For alpha, do not activate a new contract until it has passed a disposable
smoke.

Current examples:

- starter contract graph: `src/hollow_lodge/server/artifact_seed.py`
- data-defined contract seed: `tests/fixtures/ash_window_contract.json`
- shipped contract smoke registry: `scripts/smoke_shipped_contracts.py`

Expected future tools:

- `hollow-lodge admin contract-validate seed.json`
- `hollow-lodge admin contract-smoke seed.json`
- `scripts/new_contract_seed.py`

Until those exist, use the existing shipped-contract smoke pattern as the model:
activate the seed in a disposable server, create two crews, submit actions, cite
artifacts, lock the phase, and verify rendered surfaces do not leak hidden
truth.

## Minimum Alpha Contract Standard

A contract is alpha-ready when it has:

- one clear public premise
- one fixed hidden truth
- three proof dossier needs
- 4-6 artifacts
- at least two public starting artifacts or one rich starting artifact with a
  clear action path
- at least two artifact edges
- at least one action unlock
- at least two safe reveal strings
- at least three plausible typed claims
- one expected weak packet path
- one expected strong packet path
- one reason crews might trade, leak, or negotiate
- a passing smoke playthrough

If a GM cannot name the expected weak packet and strong packet before play, the
contract is not ready.
