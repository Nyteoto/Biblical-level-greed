# Personal Growth System — v0.2

A local tech tree for the things you're trying to get good at. One question:
**what do I work on right now, and for how long?**

```bash
./run.sh          # http://localhost:8787
```

Dev, with hot reload:

```bash
.venv/bin/python -m uvicorn backend.app.main:app --reload --port 8787
cd frontend && npm run dev        # http://localhost:5173, proxies /api
```

Tests: `.venv/bin/python -m pytest backend/tests -q`

## How it decides what to show

There is no weighting and nothing adaptive in this decision. (XP exists — see
*Levels and XP* — but it is a read-only projection and cannot reach any of the
rules below.) Four rules:

1. **Within a domain**, the active node is the lowest-tier startable node. Ties
   break on declaration order in the file. An `available` node always outranks
   a merely `open` one.
2. **How many** nodes are active depends on the domain's `shape` — one for a
   `ladder`, one per strand for `strands`, the current project plus what it is
   waiting on for `cycles`. See *Domain shapes* below.
3. **Whether a domain is acquiring at all** depends on its `season`. A held
   domain shows only what is about to go stale; a parked one shows nothing.
   See *Seasons* below.
4. **Across domains**, rows sort by the `priority` integer you typed.

`priority` sorts; `season` schedules. Sorting alone never says *not today*,
which is why six domains at daily cadence asserted all of themselves, every
day, forever.

Every input is visible by reading the `.toml`: `tier`, declaration order,
`strand`, `shape`. If you can't predict the board at a glance, that's a bug.

## Levels and XP

**This breaks the rule the rest of the app is built on**, and the break is
contained by one constraint that `backend/app/xp.py` obeys everywhere:

> **XP never changes what the board shows you.**

Nothing in it feeds `_pick_active`, `_status`, seasons, cadence or due-ness. It
is a read-only fold over the event log, stored nowhere, derived fresh on every
request. Delete the module and the app still picks the same work. There is a
test asserting `state` does not import `xp`, because that guarantee is worth
more than a code review.

One session scores:

```
SESSION_XP  ×  tier multiplier  ×  streak multiplier  ×  spread multiplier
```

| knob | default | |
|---|---|---|
| `SESSION_XP` | 10 | flat, per node checked off |
| `TIER_BONUS` | +15%/tier | tier 5 pays 1.6×, tier 9 pays 2.2× |
| `STREAK_BONUS` | +2%/day | consecutive days containing a **session** |
| `STREAK_CAP` | +50% | or a year-long streak doubles everything |
| `SPREAD_FREE` | 2 | acquiring domains before the penalty starts |
| `SPREAD_PENALTY` | −15% | per additional acquiring domain, floored at 40% |
| `TODO_XP` | 2 | flat. No tier, no streak, no spread. |

**The spread penalty only counts `high`-season domains.** Upkeep in five held
domains is not what it is aimed at — acquiring in five is. Without that
exemption the scoring would punish exactly the behaviour seasons were built to
encourage, and the two systems would pull against each other. Same four nodes of
work: 47 XP if all four domains are in season, 67 if two of them are merely
held.

**Todos take no multipliers** and do not keep a streak alive. Errands should not
be a way to farm a practice bonus.

Levels cost geometrically more (`LEVEL_BASE` 120, `LEVEL_GROWTH` 1.18), so the
number stays legible: the entire 4,217-session plan in `data/domains/` lands
around **level 30**, a quarter of focused work around **12**.

The bar has two sections: **white** is what yesterday left you with inside your
current level, **yellow** is what today added. Levelling up today collapses the
white to zero, which is right — none of the new level was there yesterday.

Every rate is a named constant at the top of one file, and the bar expands to
show the day's arithmetic, because *"if you can't predict the board at a glance,
that's a bug"* has to keep being true once a number is attached to it. Retuning
any constant re-scores your whole history at once; there is no migration,
because there is no stored state.

## The checklist

The Today screen carries a plain checklist above the board. It is **not** a
tree: no tier, no gate, no accrual, no domain. It is for the specific one-off
things that would be nonsense as nodes — *buy strings, email the studio, book
the HSK slot*.

- **Ticking an item removes it from the list**, immediately and permanently.
- **The list never resets.** An item stays until you tick it, and shows its age
  once it is more than a day old. Things you meant to do do not stop mattering
  at midnight.
- **Oldest first**, so a list that never resets cannot bury the thing you have
  been avoiding for a fortnight under this morning's additions.

It lives in `data/todos.jsonl`, its own append-only stream — separate from
`log/*.jsonl` because those events are keyed by `(domain, node)` and a todo has
neither. Completion appends a `done` op rather than rewriting the file, so the
list forgets the item and the record survives, exactly like node completion.

## Node kinds

A node's `kind` decides how it accrues, whether it completes, and how it
renders. The default is `drill`, so a file that names no kind behaves exactly
as it did in v0.1.

| kind | accrues | completes | notes |
|---|---|---|---|
| `drill` | distinct days vs `estimate` | yes, then decays | set `decay_days` and it returns to `maintenance` when stale |
| `study` | distinct days vs `estimate` | yes, permanently | comprehension doesn't rot the way repetition does |
| `project` | **phases, not days** | yes | must declare `phases`; has no session count at all |
| `exam` | prep days, plus a `scheduled` date | binary | scored by someone else, on their calendar |
| `social` | occasions | optional | needs other people; satisfies dependents once it has happened |

The `project` kind exists because a session counter lies about burst work. A
film shoot is four fourteen-hour days after three idle weeks — you cannot do
12% of a shoot day, so a project ticks phases instead.

## Domain shapes

| shape | active nodes | for |
|---|---|---|
| `ladder` | exactly one | levels that genuinely nest (HSK) |
| `strands` | one per declared strand | curricula that run tracks concurrently |
| `cycles` | the current project + the craft feeding it | project-driven practice |

`strands` domains must declare `strands = [...]` and give every node a
`strand`. It exists because Berklee runs Harmony, Ear Training and Private
Lessons in the same semester on purpose — showing one and hiding the other two
would misrepresent the curriculum and quietly starve whichever strand lost the
tie-break.

## Seasons — deliberate neglect

Six domains acquiring at once is **~10 hours a day**. Six domains merely *held*
is **~33 minutes a day**. You can hold six things; you cannot learn six things
at once. Seasons are the mechanism for that difference.

| state | shows | for |
|---|---|---|
| `high` | the full board, or only the strands the season names | the one or two domains you are actually acquiring |
| `low` | **only nodes about to go stale** | everything else — holding ground, not advancing |
| `off` | nothing at all | domains where nothing decays, parked at zero cost |

```toml
[season]
state   = "high"
strands = ["math", "circuits"]   # width: 2 of 5, not all 5
until   = "2026-10-01"           # the deadline
ends_on = "circuits-ac"          # ...or early, if this ships first
```

**Low season needs no configuration**, because `decay_days` already said what a
held domain owes you. A node surfaces once it is within a quarter of its own
decay window — `grip-and-stroke` (14 days) reappears at 11 idle days,
`hanzi-foundations` (180 days) at 135. On a quiet week a held domain shows
nothing, which is the correct answer and the whole point.

**`off` is only legal where nothing decays**, and the loader enforces it against
the file. `electrical-engineering` declares no `decay_days` anywhere — its own
header says comprehension holds once held — so it can be switched off for a year
at zero cost. `guitar` has nine decaying nodes and is refused, with the reason.
That asymmetry was always in the data; now it is a rule instead of something to
remember.

**Two endings, whichever lands first.** A completion trigger alone deadlocks —
projects stall, which is precisely what `project` models — and a date alone
throws away the reward for shipping early. So a season carries both.

**Nothing auto-applies.** The app reports that a season is over and offers the
switch, for the same reason it never presses `complete` for you.

The dashboard also sums `min_each` across everything active and prints it:
*declared today*. Not a score and not advice — arithmetic on data you typed. It
exists because the daily cost of the board was the one input that was never
visible, and six domains in season came to ten hours a day without ever saying
so.

## Estimates, and calibrating them

`estimate` is **a guess at how many days a node takes**. It is not a target and
not a contract. The `gate` decides when the node is actually done, and the only
reason the number is worth writing down is that the two can disagree:

- **Finish under the estimate** and the guess was high.
- **Keep logging past it** and the guess was low. Nothing clamps, nothing
  blocks, and the progress bar shows the overshoot as its own quantity rather
  than pinning at 100%.

Neither is failure. Both are measurements of the estimate, which is the thing
being tested.

Each node reports `calibration`:

| field | |
|---|---|
| `estimate` | what you guessed |
| `actual` | sessions it actually took |
| `delta` | `actual − estimate`, signed |
| `settled` | the gate has been called, so `actual` is final |

**Sessions logged after completion are upkeep, not cost**, and are excluded from
`actual`. Otherwise a well-maintained drill would look progressively worse
estimated forever, which is the opposite of the truth.

Each domain reports its **bias** across settled nodes — a ratio of totals, not a
mean of ratios, so a 3-session node finishing in 6 doesn't swing the number as
hard as a 70-session node finishing in 140. It shows on the tree header:
*estimates run 138% (152/110 over 4 settled)*.

Nothing acts on any of this. No estimate is ever rewritten for you.

> The old TOML key was `sessions`. It is still accepted so hand-written files
> keep loading; the writer only ever emits `estimate`.

## Hard and soft prerequisites

`requires` is hard: the node is `locked` until every one is complete.
`prefers` is soft: the node is `open` — ordered *after* them on the tree, drawn
with a dashed edge, and startable right now anyway.

Both are validated the same way (must point at an earlier tier, no cycles). The
only difference is whether an unmet edge blocks.

This distinction is not cosmetic. In `electrical-engineering.toml` every edge
is hard, because attempting signals and systems without linear algebra produces
zero progress. In `filmmaking.toml` almost every edge is soft, because AFI has
you direct three complete films before you are ready for any of them — a locked
`cycle-1` would teach the opposite of the method. The same tree structure means
opposite things in the two files, and the file has to say which.

## Measurable gates

A node with a `metric` (`"bpm"`, say) can carry a number with each check-off.
The app stores the number you typed and charts it. It never infers one, never
scores you on it, and never changes what it shows you because of it — this
stays a log, not a coach.

Every drumming and guitar gate is a tempo reading taken daily. Before this the
app recorded only that a day happened.

## What the app tracks, and what it doesn't

Each node has two independent halves:

- **Accrual** — for most kinds, the app counts *distinct days you checked in*.
  One click, one day, one session. A `project` counts **phases ticked**
  instead, because burst work has no meaningful daily denominator.
- **Gate** — free text describing what "done" actually means. The app never
  parses or evaluates it. You press **complete** when you decide it's true.

There is a third thing, which is neither: **`entry`**. A gate says where a node
*ends*; `entry` says where it *begins* — the book, the free course, the search
string that actually returns the right thing. It is a list of lines, stored and
displayed and never parsed, exactly like `gate`.

It exists because a tree of titles and gates is only usable by someone who
already knows the field. "Guitar Chords 101" is a Berklee course code: searching
it returns beginner open-chord blogs, when the node means drop 2 voicings. The
node knew what done looked like and never said how to start. Every node in
`data/domains/` now carries one — see *Where the trees came from*.

`entry` renders on a card only until the first session is logged, then gets out
of the way; it stays in the node panel permanently.

`min_each` ("25 min") is a contract with yourself, shown on the card. A click
carries no duration, so the app never records minutes it didn't measure. If a
node declares a `metric`, the click may also carry a number you typed — that is
the one quantity the app stores beyond "a day happened", and it still never
acts on it.

## Building a tree in the UI

**Tech Tree** tab. The left rail is your domains (the reference's nation flags);
`+` creates one. Inside a tree:

- **`+ node`** at the foot of a tier column opens the node dialog: kind,
  strand, tier, accrual target or phases, metric, decay, gate, entry. The form adapts
  to the kind — pick `project` and the session field is replaced by phases;
  pick `exam` and you get a date. You name it up front because the id is
  slugged from that name and then **never changes** — every log entry
  references the node by id, so renaming would orphan history. The title stays
  editable; the id does not.
- **`→`** on the right edge of a node starts an edge. Click the node that should
  require it. Esc cancels.
- **Clicking a node** opens the panel: params on one tab, an append-only journal
  on the other. `unlink` removes a prerequisite; `↑ ↓` reorders within a tier,
  which is what decides who goes active first when two siblings unlock together.
- **edit** beside the domain title opens the domain dialog: title, **shape**,
  strands, priority, cadence, colour, delete.

Changing shape migrates the nodes with it. Switching a domain *to* `strands`
moves every unassigned node into the first strand, and switching away clears
them. Without that the change is impossible: a node cannot name a strand until
the domain declares one, and the domain cannot declare one while its nodes are
strandless. The dialog says which nodes it will move before you save.

Changing a node's **kind** in the panel reconciles the fields that no longer
apply — converting to `project` asks for phases and drops the session count,
converting away drops the phases.

Hard edges draw solid, soft edges draw dashed. A `locked` node is dimmed; an
`open` one is dashed-bordered and fully clickable, because "usually after X" is
advice and the UI must not make it look like a wall.

Deleting a domain removes the `.toml` only — its log events stay on disk, so
deleting by mistake costs you no history.

### Editing writes the file

A UI edit rewrites the whole `.toml`, so **comments in that file do not
survive** — stdlib ships a TOML reader and no writer, and the small emitter here
doesn't round-trip them. Hand-editing still works exactly as before; the two
paths just aren't comment-safe in the file-then-UI direction.

Edits are validated *before* the write, so a rejected change (a cycle, a
dangling prerequisite, a backward-tier edge) leaves the file on disk untouched.
Writes are atomic via `os.replace`.

## Data

Plain files are the source of truth. `data/index.sqlite` is a disposable
projection — delete it any time and `POST /api/admin/reindex` replays the log.

```
data/
  domains/*.toml     hand-authored; the app reads these and never writes them
  log/YYYY-MM.jsonl  append-only; one line per click, never rewritten
  todos.jsonl        append-only; the checklist, add and done ops
  index.sqlite       rebuildable cache
```

Every event carries a `day` precomputed in **GMT+7**, so the midnight rollover is
a string comparison and timezone math lives in exactly one function
(`backend/app/timeutil.py`).

### A domain file

```toml
id       = "guitar"
title    = "Electric Guitar"
priority = 20            # lower sorts higher. This is the ranking.
cadence  = "daily"       # "daily" | "weekdays" | { every_n_days = N }
color    = "amber"       # amber | sky | emerald | rose | violet | slate
shape    = "strands"     # ladder | strands | cycles
strands  = ["technique", "theory"]   # required when shape = "strands"

[[node]]
id       = "guitar-scales-101"
title    = "Guitar Scales 101 — modes and fingerings"
tier     = 4
kind     = "drill"       # drill | study | project | exam | social
strand   = "technique"
requires = ["harmony-1"] # hard: locks this node
prefers  = ["your-sound"]# soft: advises, never locks
estimate = 55            # a GUESS at how many days, not a target
min_each = "30 min"      # displayed, never enforced
metric   = "bpm"         # optional measurable gate
metric_target = 132
decay_days = 30          # drill only: goes stale after this many idle days
gate     = "Any mode, any root, any position, without hunting for the shape"
entry    = [             # how to START. Never parsed, same contract as gate.
  "Book: Leavitt, A Modern Method for Guitar Vol 2",
  "Free: jazzguitar.be scale lessons",
  "Search: guitar modes explained chord relationship",
]
```

A `project` node replaces `estimate` with `phases`, and an `exam` node may
carry `scheduled = "2026-11-14"`:

```toml
[[node]]
id     = "cycle-1"
title  = "Cycle 1 — a silent three-minute film"
tier   = 4
kind   = "project"
phases = ["prep", "shoot", "post", "show it"]
prefers = ["editing-grammar"]
```

Edit while the server runs; `watchdog` picks it up. A malformed file surfaces its
error on the dashboard and leaves the other domains working.

Validation rejects: unknown prerequisites, duplicate ids, cycles, and
prerequisites at the same or a later tier (which would render as a backward
edge) — for soft edges as well as hard ones. Also: unknown `kind` or `shape`,
an edge listed as both hard and soft, a `project` with no `phases`, `phases` on
a non-project, a `strands` domain that declares none, and a node naming a
strand that doesn't exist.

## API

| Method | Path | |
|---|---|---|
| GET | `/api/dashboard` | today's board, domains in priority order |
| GET | `/api/domains/{id}` | one tree with every node's derived status |
| POST | `/api/domains/{id}/nodes/{node}/session` | toggle today's check-off; optional `value` logs a metric reading |
| POST | `/api/domains/{id}/nodes/{node}/phase` | tick one phase of a project |
| POST | `/api/domains/{id}/nodes/{node}/complete` | toggle completion |
| POST | `/api/domains/{id}/nodes/{node}/journal` | append an entry |
| POST | `/api/domains/{id}/season` | switch a domain between acquiring, holding, parked |
| POST / DELETE | `/api/todos` · `/api/todos/{id}` | add a checklist item; tick one off |
| POST | `/api/admin/reindex` | rebuild the index from the log |
| POST | `/api/admin/reload` | re-read the domain files |

Toggle bodies take `{"on": true|false}`, or omit it to flip the current state.

These rewrite the domain's `.toml`:

| Method | Path | |
|---|---|---|
| POST / DELETE | `/api/domains` · `/api/domains/{id}` | create, delete a domain |
| PATCH | `/api/domains/{id}` | title, priority, cadence, colour |
| POST / DELETE | `/api/domains/{id}/nodes` · `.../nodes/{node}` | add, delete a node |
| PATCH | `/api/domains/{id}/nodes/{node}` | title, tier, estimate, gate, … |
| POST / DELETE | `/api/domains/{id}/edges` | draw, remove a prerequisite |
| POST | `/api/domains/{id}/nodes/{node}/reorder` | move within its tier |

## Where the trees came from

`data/domains/` holds six researched trees — HSK 3.0, Berklee guitar and drums,
MIT 6-5, Teach Yourself CS, AFI. Their sourcing lives in
[`docs/sources.md`](docs/sources.md), because a UI edit rewrites the file and
the header comments do not survive. The design argument for the taxonomy above
is in [`docs/domain-shapes.md`](docs/domain-shapes.md).

Two different kinds of source, kept apart on purpose:

- **Provenance** — where the *shape* came from. Berklee's curriculum PDF, MIT's
  degree chart, the AFI cycle-film structure. These justify the tiers and the
  edges. They teach you nothing.
- **Materials** — what you actually learn from, in `entry`. MIT OCW, Stone's
  *Stick Control*, dspguide.com, Blackmagic's free Resolve training books.

Conflating them is what made the earlier version of this repo unusable
solo: it was thoroughly sourced and still never said what to read.

## Deliberately absent

Timers, minute tracking, notifications, multi-user, auth, editing or deleting
journal entries (the log is append-only), and anything adaptive. Metric readings
are stored and drawn, never interpreted: nothing in the app changes what it
shows you because of a number you logged.

*Streak mechanics used to be on this list.* They are now in the XP layer, which
is the one deliberate exception — and it is fenced off from every decision the
app makes rather than being allowed to leak into them.

Per-node cadence is still missing and is the next obvious gap — an `exam` that
happens once and a `drill` that happens daily currently share their domain's
one cadence setting.
