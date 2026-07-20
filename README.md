# Personal Growth System

A local tech tree for deliberate practice. One question: **what do I work on
right now, and for how long?**

Linux only. The in-app **Manual** tab explains the model and why it is shaped
this way; this file is reference.

## Install

```bash
./install-linux.sh
pgs                                # native window, data in ./data
pgs --data-dir /mnt/other/pgs      # data elsewhere
pgs --browser                      # no window
pgs --headless --host tailscale    # serve only; see MOBILE.md
```

Tests: `.venv/bin/python -m pytest backend/tests -q`

Dev: `uvicorn backend.app.main:app --reload --port 8787` + `cd frontend && npm run dev`

- [MOBILE.md](MOBILE.md) — iPad/iPhone over Tailscale
- [SHORTCUTS.md](SHORTCUTS.md) — sending photos from iOS
- [SYNC.md](SYNC.md) — backups, moving machines
- [docs/sources.md](docs/sources.md) — where the six trees came from
- [docs/domain-shapes.md](docs/domain-shapes.md) — the taxonomy argument

## What decides the board

1. **Within a domain** — the lowest-tier startable node. Ties break on
   declaration order. `available` outranks `open`.
2. **How many** — the domain's `shape`.
3. **Whether at all** — the domain's `season`.
4. **Across domains** — the `priority` integer you typed.

`priority` sorts; `season` schedules. Everything is readable off the `.toml`.

## Node kinds

| kind | accrues | notes |
|---|---|---|
| `drill` | days | decays; set `decay_days` |
| `study` | days | holds once held |
| `project` | phases | must declare `phases`; no estimate |
| `exam` | prep days + `scheduled` | scored by someone else |
| `social` | occasions | needs other people; never forced to complete |

## Domain shapes

| shape | active at once |
|---|---|
| `ladder` | one |
| `strands` | one per declared strand |
| `cycles` | current project + the craft feeding it |

## Seasons

Six domains acquiring at once is ~10 h/day; six merely held is ~33 min/day.

| state | shows |
|---|---|
| `high` | full board, or only the strands the season names |
| `low` | only nodes within a quarter of their decay window |
| `off` | nothing. Rejected unless the domain has no decaying nodes. |

```toml
[season]
state   = "high"
strands = ["math", "circuits"]   # width
until   = "2026-10-01"           # ends here...
ends_on = "circuits-ac"          # ...or when this ships, whichever first
```

Nothing auto-applies; the app reports the season is over and offers the switch.

## Node schema

```toml
[[node]]
id       = "guitar-scales-101"   # never changes; the log references it
title    = "Modes across the neck"
tier     = 4
kind     = "drill"               # drill | study | project | exam | social
strand   = "technique"           # required when shape = "strands"
requires = ["harmony-1"]         # hard: locks
prefers  = ["your-sound"]        # soft: advises, never locks
estimate = 55                    # a GUESS at how many days, not a target
min_each = "30 min"              # displayed, never enforced
metric   = "bpm"                 # optional measurable reading
metric_target = 132
decay_days = 30                  # drill only
scheduled = "2026-11-14"         # exam only
phases   = ["prep", "shoot"]     # project only, replaces estimate
gate     = "Any mode, any root, without hunting for the shape"
note     = "..."
entry    = ["Book: …", "Free: …", "Search: …"]   # how to START
```

`sessions` is accepted as a legacy alias for `estimate`.

Validation rejects: unknown/duplicate/cyclic prerequisites, edges to the same
or later tier, unknown `kind`/`shape`, an edge that is both hard and soft, a
`project` without `phases`, `phases` on a non-project, a `strands` domain
declaring none, an undeclared strand, `season.state = "off"` where nodes decay.

## Gate, entry, estimate

- **gate** — what done means. Never parsed; you decide.
- **entry** — how to start: book, free course, search string.
- **estimate** — a guess. You may finish under it or log past it; both are
  measured. Sessions after completion are upkeep, excluded from `actual`.

Each domain reports its estimating bias as a ratio of totals over settled nodes.

## Journal, notes, checklist

- **journal** — one entry per node per day, written at day's end. Keyed by day,
  so writing again revises it; the log keeps every version.
- **notes** — `data/notes/<domain>/<node>.md`. Mutable markdown, full screen.
  Photos from iOS append here.
- **checklist** — errands. No tier, no gate. Ticking removes; never resets.

## Levels and XP

Breaks the no-scoring rule, contained by one constraint: **XP never changes
what the board shows.** Read-only fold over the log, stored nowhere; a test
asserts `state` does not import `xp`.

```
SESSION_XP × tier multiplier × streak multiplier × spread multiplier
```

Defaults in `backend/app/xp.py`: 10/session, +15%/tier, +2%/day streak capped
at +50%, −15% per acquiring domain beyond 2 (floored at 40%), todos flat 2 with
no multipliers. Spread counts only `high`-season domains — upkeep is not
spreading.

## API

| | |
|---|---|
| GET | `/api/dashboard`, `/api/domains`, `/api/domains/{id}`, `/api/active` |
| POST | `.../nodes/{n}/session` `/phase` `/complete` `/journal` |
| GET/PUT | `.../nodes/{n}/note` |
| POST | `/api/media?domain=&node=&caption=` · GET `/media/{path}` |
| POST | `/api/domains/{id}/season` |
| POST/DELETE | `/api/todos`, `/api/todos/{id}` |
| POST | `/api/admin/reindex`, `/api/admin/reload` |
| CRUD | `/api/domains`, `.../nodes`, `.../edges`, `.../reorder` |

Structural edits rewrite the `.toml`, validated before the write, atomic via
`os.replace`. **Comments in the file do not survive a UI edit.**

## Data

```
data/
  domains/*.toml     hand-authored
  log/YYYY-MM.jsonl  append-only, one line per click
  todos.jsonl        append-only
  notes/*/*.md       mutable
  media/             images — NOT in git
  index.sqlite       rebuildable cache — NOT in git
```

Every event carries a `day` precomputed in GMT+7. Events sort by timestamp,
stably, so a merged log resolves identically on any machine.

## Deliberately absent

Timers, minute tracking, notifications, multi-user, auth, editing the log, and
anything adaptive. Metric readings are stored and drawn, never interpreted.

Per-node cadence is the next obvious gap.
