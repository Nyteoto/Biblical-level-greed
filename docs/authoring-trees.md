# How to generate a tree

Read this file and nothing else. It is deliberately self-contained: you do not
need the rest of the repository to author a domain, and reading it would waste
tokens on code that has no bearing on curriculum decisions.

Trigger: **"generate roadmap for: X"**.

---

## Who this is for

One self-taught practitioner who **learns by building projects**, not by taking
courses. Assume they have already shipped things in the domain, or in a
neighbouring one, and are stuck on *what comes next*.

That assumption changes the job. The frequent answer to "what next" is **going
back**: the foundations a project-first learner skipped, and is now paying for.
Two real examples from the person this app is for:

- **Drumming** — skipped sight-reading, rudiments and tempo training. Self-taught
  the wrong way, hit a ceiling, and had no idea where to find material to repair
  it.
- **Electrical engineering** — skipped the maths, because asking a model "what
  component, what code" produces an answer without it. No price paid yet, and a
  well-founded suspicion that the bill is coming.

So a tree is not a beginner's path. It is a **map of the whole domain including
the parts a capable practitioner is most likely to have skipped**, enterable at
any point. Do not compress or omit early tiers on the assumption they are known.
Name the foundations explicitly, and where a foundation is commonly skipped by
self-taught people, say so in its `note`.

---

## What "correct" means

A tree is correct when all seven hold. Every one is checkable by someone who did
not write it; none of them is a matter of taste.

1. **Sourced.** The *sequence* is adopted from a real, named, published
   curriculum — an institution's syllabus, an official body's requirements, a
   canonical program. Cite it. Do not invent an ordering.
2. **Shaped by how the source is actually run.** `ladder` / `strands` / `cycles`
   is read off the real program's concurrency, not chosen for neatness.
3. **Separable from the institution.** Every node is doable without enrolling.
   A syllabus is separable from a test centre: adopt the syllabus, drop the
   enrolment. Only a node whose entire point is external scoring may be
   `kind = "exam"`.
4. **Self-assessable.** Every `gate` is something the learner can check alone,
   without an instructor, examiner or employer. If a gate needs someone else's
   judgement, it is the wrong gate — rewrite it as an observable.
5. **Startable.** Every node carries `entry`: 3–5 lines naming a canonical text,
   a free alternative, and search strings that actually return the right thing.
   A thoroughly sourced tree with no `entry` is unusable by anyone who does not
   already know the field. Prefer free; label paid things as paid.
6. **Honest.** Anything you chose rather than found is written down as chosen.
   This is the criterion that separates a defensible tree from a confident one.
7. **Fit stated.** Say plainly what the source curriculum does *not* cover. HSK
   is a good syllabus for reading and a poor one for speaking; the Chinese tree
   says so and adds a `social` node to cover it. Name the gap and place a node
   against it, or state that it cannot be covered here.

Correct does **not** mean optimal, complete, or right about durations. Estimates
are hypotheses; the app measures them against reality and reports the gap.

---

## What to put in, beyond the sequence

### Find what practitioners actually value most

The published curriculum tells you the order. It does not reliably tell you
which capability separates a competent practitioner from a mediocre one — that
knowledge lives with people doing the work.

Find it, and include it. It may be a drill, a `social` node, a habit, or a
piece of taste that no syllabus lists. **If it sits high in the sequence, do not
just place it at the top and leave it stranded — work backwards and author the
bridging nodes that make it reachable.** A tree whose most valuable node is
unreachable has described the destination and omitted the road.

### Check the domain for a recent shift

Before generating, look for **credible, current, dated** change in how the field
is practised or taught. A top CS program now carries a "working with models"
credit that did not exist three years ago; comparable shifts are happening in
other domains and will not be in your training data.

Cite what you find, with a date. If you find nothing credible, say so — an
invented trend is worse than none.

### Eject anything that only serves an employer

If a node exists because employers screen for it, and not because it makes the
practitioner deeper or more durable in the domain, **leave it out**. Ceremony,
tooling fashion, certification theatre, portfolio performance. The test: *would
someone who never had to be hired still need this to be good at the thing?* If
no, cut it.

---

## No hallucinations

This is a hard requirement, not a preference. Curriculum facts are exactly the
kind of thing a model reproduces confidently and wrongly.

**Search the web for every factual claim. Do not answer from memory.** Course
codes, prerequisite chains, published hour counts, book titles and editions,
exam formats, pass marks, prices, free tiers, and whether a resource still
exists — all of it drifts, and all of it is checkable.

- Every sequencing claim needs a source you actually retrieved.
- If a fact cannot be verified, **omit it or label it as judgement.** Never
  split the difference by stating it plainly and hoping.
- Do not invent: course codes, prerequisite chains, hour figures, exam formats,
  pass marks, institution names, book editions, or URLs.
- `entry` lines prefer **titles and search strings over URLs** — a search for
  "40 essential rudiments vic firth" still works in five years; the link
  probably does not.
- Record every source in `docs/sources.md` under a heading for the domain.

End the work with a **"what I chose rather than found"** section covering, at
minimum: estimates, `decay_days`, any metric targets, and anything you could not
verify. Write it as prose the user can argue with.

---

## The file

One TOML file at `data/domains/<id>.toml`. **No comments** — the app regenerates
this file whenever the user edits a season or a node through the UI, and
comments do not survive that. Rationale goes in `docs/sources.md`.

```toml
id       = "domain-id"          # lowercase slug, matches the filename
title    = "Domain Title"
priority = 40                    # lower sorts higher. The user's ranking, not yours
cadence  = "daily"               # daily | weekdays | every_n_days
color    = "sky"                 # amber | sky | emerald | rose | violet | slate
shape    = "strands"             # ladder | strands | cycles
strands  = ["theory", "craft"]   # required when shape = "strands"

[season]
state = "low"                    # high | low | off — start at low; the user decides

[[node]]
id       = "node-id"
title    = "Node Title"
tier     = 1                     # 1 upward. Tier is the spine of the tree
kind     = "drill"               # drill | study | project | exam | social
strand   = "theory"              # required when shape = "strands"
estimate = 40                    # distinct days you think it takes. A hypothesis
requires = ["earlier-node"]      # HARD prerequisite — locks the node
prefers  = ["advisory-node"]     # SOFT — advises, never locks
min_each = "45 min"              # display-only contract; never enforced
gate     = "What done means, self-assessable, no instructor."
entry    = [
  "Free: <canonical free resource> — what it is",
  "Book: <author, title> — why this one",
  "Search: <query that returns the right thing>, <alternative query>",
]
note     = "Anything worth knowing, e.g. that self-taught players skip this."
decay_days    = 30               # drills only: idle days before it goes stale
metric        = "bpm"            # optional measurable gate
metric_target = 120
phases        = ["prep", "shoot", "post"]   # project nodes only; replaces estimate
scheduled     = "2026-11-15"     # exam nodes only; leave blank unless real
```

**Node kinds** — pick by how the work actually accrues:

| kind | accrues | use when |
|---|---|---|
| `drill` | distinct days | repetition that decays without upkeep — set `decay_days` |
| `study` | distinct days | comprehension; holds once held |
| `project` | phases | one indivisible burst; declare `phases`, no `estimate` |
| `exam` | prep days + a date | scored by someone else, on their calendar |
| `social` | occasions | needs other people; never forced to complete |

**Shapes** — read off the real program:

| shape | active at once | when |
|---|---|---|
| `ladder` | one | levels that genuinely nest (HSK) |
| `strands` | one per strand | tracks a real curriculum runs concurrently (Berklee) |
| `cycles` | a project plus the craft feeding it | repeated whole productions (AFI) |

**Edges.** `requires` is a hard claim that the second thing is incoherent
without the first. `prefers` is advice. Most domains want mostly soft edges —
people ship working software knowing none of the theory, every day. Use hard
edges only where the dependency is real.

**Tier ≥ 2 costs XP to unlock**, priced automatically from the tier. You do not
set a price. But it means tier is a real commitment gate: do not inflate tiers
to look thorough, and do not stack a foundation the user needs early behind
three tiers of prerequisites.

---

## Before you hand it over

- [ ] Every sequencing claim traces to a source you retrieved this session
- [ ] Shape matches how the real program runs
- [ ] No node requires enrolment, an instructor, or an employer
- [ ] Every `gate` is self-assessable alone
- [ ] Every node has 3–5 `entry` lines, free-first, search strings over URLs
- [ ] The capability practitioners value most is present, and reachable
- [ ] Any recent shift in the field is included and dated, or its absence stated
- [ ] Nothing present only because employers screen for it
- [ ] Foundations a self-taught practitioner commonly skips are explicit and early
- [ ] What the source does *not* cover is stated, and covered or declared
- [ ] `docs/sources.md` has a section for this domain
- [ ] A "chosen rather than found" accounting exists
- [ ] The `.toml` parses and carries no comments
