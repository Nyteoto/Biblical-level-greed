# What building six real trees revealed

> **Status: implemented in v0.2.** Every finding below is now enforced by the
> loader and visible in the UI. See `README.md` for the resulting schema and
> `docs/sources.md` for where the six trees came from. The closing section,
> *What implementing it then revealed*, is new and was not visible at analysis
> time.

The v0.1 model was: a node accrues *distinct days checked in*, and completes when
you assert a free-text gate is true. One node type, one cadence per domain, one
kind of edge.

Authoring six researched domains against that model broke it in six specific
places. Each break is listed with the evidence that produced it.

## 1. The accrual unit is wrong for project domains

Chinese vocabulary is genuinely one session per day, indefinitely. So is a
rudiment, so is a scale. `sessions = 60` means something real.

A film is not. `cycle-1` is three weeks of prep, four shoot days, six weeks of
post. The work arrives in bursts of fourteen hours and then nothing for a
fortnight. You cannot do 12% of a shoot day. `sessions = 20` on that node is a
number I made up to fill a required field, and the daily-check-in counter will
mismeasure it in both directions — idle during prep, saturated during the shoot.

The same applies more weakly to `pcb-design` and to EE problem sets, where the
unit of work is a deliverable of variable multi-day size, not a day.

**Implication:** `sessions` is the right primitive for *drill* nodes and the
wrong one for *project* nodes. A project node wants phases and a delivery date,
not a counter.

## 2. Cadence belongs on the node, not the domain

`filmmaking` is currently `every_n_days = 3`, which is right for
`watch-and-break-down` and meaningless for `cycle-3`. Chinese is `daily`, which
is right for every vocabulary node and wrong for `hsk4`, which happens once, on
a date the exam board chose.

One cadence per domain forces a lie in any domain that mixes habit and event.

## 3. Gates are four different things wearing one costume

The app treats `gate` as opaque free text, which is correct as far as it goes —
but the four kinds behave so differently that the UI should know which it has:

| Kind | Example | What it needs |
|---|---|---|
| **Exam** | "Sat HSK 4 and passed" | A date, a registration deadline, a warning ahead of it |
| **Measurable** | "Stone pp.5-7 at 140bpm, clean" | A number you log repeatedly, and a curve |
| **Artifact** | "Sent a four-layer board to fab and it worked" | A link to the thing |
| **Judgement** | "You are not embarrassed by it" | A prompt asking who else saw it |

The measurable case is the clearest loss. Every drumming and guitar gate is a
tempo-and-cleanliness reading. The player takes that reading daily and the app
throws it away, recording only that a day happened. Storing the bpm would turn
the accrual counter into an actual progress signal at no cost to the "no
scoring, nothing adaptive" principle — it is a number the user typed, not a
number the app inferred.

## 4. "Done" does not mean the same thing twice

- **Chinese** decays. HSK 4 vocabulary rots without review. A completed node
  needs to fall back into maintenance, not sit green forever.
- **EE and CS** fade but are re-derivable. Done is close enough to permanent.
- **Guitar and drumming** technique decays and recovers fast. Done is
  provisional but cheap to restore.
- **Filmmaking** does not decay at all — judgement accumulates — but its done is
  *public and permanent*. A released film cannot be un-released.

A single binary `complete` flag serves the middle two and misrepresents the
outer two.

## 5. Blocking is hard in one domain and actively harmful in another

This is the sharpest discrepancy, and it runs opposite at the two ends:

- **Electrical Engineering** — prerequisites are physically real. Attempting
  signals and systems without linear algebra does not produce slow progress, it
  produces zero progress. Locking is a service.
- **Software Development** — prerequisites are soft. People ship working
  products knowing none of the theory. The tree encodes *what stops you being
  blocked by things you cannot name*, which is a weaker claim than "you may not
  proceed."
- **Filmmaking** — blocking is **inverted**. You should make a film above your
  level; that is the pedagogy. AFI puts a camera in your hands in the first
  weeks and has you direct three complete films before you are ready for any of
  them. A locked `cycle-1` would be teaching the opposite of the method.
- **Guitar** — likewise inverted at Berklee, which puts students in ensembles
  from the first semester, below competence, on purpose.

**Implication:** `locked` needs at least two flavours — a hard *cannot* and a
soft *not yet advised, but go ahead*. The second should be enterable with a
shrug, not a block.

## 6. Some nodes cannot be done alone, and the app cannot see it

`guitar/ensemble`, `drumming/play-with-band`, `soft-dev/code-review`,
`filmmaking/cycle-2`, `filmmaking/audience`.

These share properties nothing else in the model has: they require other
people's availability, they must be scheduled in advance, they cannot happen at
11pm on a Tuesday because you felt like it, and they are the nodes most often
missing from self-taught paths *precisely because* they are unpractisable alone.

They are also, in every one of these domains, where the real learning is. The
app currently renders them identically to "practise scales for 20 minutes."

## Proposed node taxonomy

Five types, derived from the six trees rather than invented up front:

| Type | Accrual | Cadence | Completion | Found in |
|---|---|---|---|---|
| `drill` | days checked in | daily | never truly done — decays to maintenance | HSK vocab, rudiments, scales, fretboard |
| `study` | units understood | weekdays | permanent once held | EE maths, CS theory |
| `project` | phases | burst | permanent, often public, irreversible | cycle films, PCB spin, ship-project-1 |
| `exam` | prep sessions + a date | one-shot, scheduled | binary, externally scored, retryable | HSK sittings, recital |
| `social` | scheduled occurrences | others' calendars | ongoing, not completable | ensemble, band, code review, audience |

The current model is `drill` generalised to everything, which is why Chinese fits
it perfectly and filmmaking fits it not at all — Chinese is almost purely drill
plus exam, and filmmaking contains no drill nodes at all except
`watch-and-break-down`.

## The one-line version

**Chinese advances by accumulation against an external calendar. Filmmaking
advances by completed irreversible projects judged by other people.** Everything
above follows from that difference, and the other four domains sit at points
between them:

```
  pure drill                                          pure project
  ├─────────────┼──────────────┼──────────────┼──────────────┤
Chinese     Drumming        Guitar     EE / Soft-dev    Filmmaking
```

Drumming and guitar are drill-dominant with social and project nodes at the top.
EE and software development are study-dominant with a project spine underneath.
Filmmaking is project-dominant with one drill node.


---

# What implementing it then revealed

Three things only showed up once the taxonomy was real and the six trees were
re-authored against it.

## The hard/soft split is measurable, and the two extremes are cleaner than expected

Counting edges after the rewrite:

| domain | hard | soft |
|---|---:|---:|
| Electrical Engineering | 31 | 0 |
| Chinese | 13 | 0 |
| Electric Guitar | 24 | 6 |
| Software Development | 19 | 7 |
| Drumming | 14 | 9 |
| Filmmaking | **4** | **19** |

EE and filmmaking are not merely different, they are *inverted*, and neither
needed a single judgement call to get there — the ratio falls out of the
sourcing. A tree with 31 hard edges and one with 19 soft edges are different
data structures being rendered by the same component, which is exactly the
discrepancy the exercise was looking for.

## Soft edges make two nodes active on day one that never would have been

With the taxonomy live, the board suggests `guitar/ensemble` and
`drumming/play-with-band` immediately — both tier 5+ nodes, both `social`, both
reachable only because every edge into them is soft.

This looked like a bug and is not. It is the Berklee finding executing: four
required semesters of ensemble, starting in semester one, below competence, on
purpose. The old model could not have produced this suggestion at any point in
its life, because those nodes sat behind five tiers of hard prerequisites that
the curriculum does not actually impose.

It is worth watching. If "go play with a band" on day one proves to be bad
advice for drums specifically, the fix is data, not code: make one of
`play-with-band`'s edges hard.

## The Chinese split in the plan was wrong, and the taxonomy is what showed it

The implementation plan called for splitting each HSK level into a `drill`
node (acquire the vocabulary) and an `exam` node (sit the test). Building it
made the redundancy obvious: **the exam *is* the gate.** `kind = "exam"`
already means "sessions are preparation, and completion is scored externally
on someone else's date" — which is precisely what the split was trying to
express, at half the tier depth. Nine levels would have become eighteen tiers
for no gain.

The general lesson: a node kind can absorb a distinction that would otherwise
have to be modelled as topology. Worth checking the other five domains for the
same mistake.

## Still open

- **Cadence is still per-domain.** Finding #2 above is only half-fixed: `kind`
  now carries most of what per-node cadence would have, but an `exam` that
  happens once and a `drill` that happens daily still share one setting.
- **`decay_days` numbers are guesses.** The ordering (hands decay faster than
  theory) is defensible; the values are not sourced. See the honesty section at
  the foot of `docs/sources.md`.
- **`cycles` support-node selection is heuristic.** It shows the current
  project plus its own unmet prerequisites, falling back to the lowest-tier
  craft node. That is predictable and readable off the file, but it is the one
  rule here that was designed rather than found.
