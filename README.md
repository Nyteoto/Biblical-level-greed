# Personal Growth System

A local tech tree for deliberate practice. One question: **what do I work on
right now, and for how long?**

Linux only. The in-app **Manual** tab explains the model and why it is shaped
this way; this file is reference.

The **Trophic** tab is a second app sharing this one's shell and disk — a
syntax-driven capture bar and a log of what it caught. It is documented in
[TROPHIC.md](TROPHIC.md) and summarised under [Trophic](#trophic) below.

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
- [SYNC.md](SYNC.md) — backups, moving machines
- [docs/sources.md](docs/sources.md) — where the six trees came from
- [docs/domain-shapes.md](docs/domain-shapes.md) — the taxonomy argument
- [docs/authoring-trees.md](docs/authoring-trees.md) — how a new tree gets generated

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

## Notes, checklist

- **notes** — `data/notes/<domain>/<slug>.md`. A domain owns a folder of freely
  titled markdown documents, mutable and hand-editable. Photos append here.
  There is no separate journal: a thing you write while working is both the
  knowledge and the record, and having to choose was friction. Old per-node
  files carry over as notes titled after their filename.
- **checklist** — errands. No tier, no gate. Ticking removes; never resets.

## Levels and XP

XP began as decoration under the rule that it must never change what the board
shows. That rule is gone: **starting a node above tier I costs XP**, so a node
whose prerequisites are all met still reads `sealed` until it is paid for.

What survives is the half worth keeping — an asymmetry:

- **Earning is derived.** A read-only fold over the log, stored nowhere, so
  retuning a constant re-scores all history with no migration.
- **Spending is recorded.** The price is written into the `unlock` event, so
  retuning tomorrow cannot make yesterday's purchase unaffordable. There is no
  refund; spending is the one permanent toggle in the app.

Two pools: `earned` is lifetime and drives the level, never going down. `bank`
is earned minus spent, and is what you actually buy with.

```
SESSION_XP × tier × streak × focus
```

Defaults in `backend/app/xp.py`: 8/session, +15%/tier, +2%/day streak capped at
+50%, focus +25% while acquiring in ≤2 domains and shrinking from there to a
floor of 50%. Todos are flat 2 with no multipliers — errands should not farm a
practice bonus. Focus counts only `high`-season domains; upkeep is not spread.

`sleep` and `movement` in the foundation domain earn at double streak rate and
buff everything else once held a fortnight. Nothing else compounds like sleeping
properly, so nothing else is paid like it.

## API

| | |
|---|---|
| GET | `/api/health`, `/api/storage`, `/api/dashboard`, `/api/domains`, `/api/domains/{id}` |
| POST | `.../nodes/{n}/session` `/complete` `/phase` `/unlock` |
| notes | GET/POST `/api/domains/{id}/notes` · GET/PUT/DELETE `.../notes/{slug}` |
| tools | GET/POST `/api/domains/{id}/tools` · PATCH/DELETE `.../tools/{tool_id}` |
| media | POST `/api/media?domain=&node=&caption=` · GET `/media/{path}` |
| POST | `/api/domains/{id}/season` |
| POST/DELETE | `/api/todos`, `/api/todos/{id}` |
| POST | `/api/admin/reindex`, `/api/admin/reload` |
| CRUD | `/api/domains`, `.../nodes`, `.../edges`, `.../reorder` (POST/PATCH/DELETE) |

Structural edits rewrite the `.toml`, validated before the write, atomic via
`os.replace`. **Comments in the file do not survive a UI edit.**

## Data

```
data/
  seed/*.toml        the six researched trees, as shipped — the ONLY thing in git
  domains/*.toml     your trees, hand-authored and rewritten by the UI
  log/YYYY-MM.jsonl  append-only: every session, completion, phase and unlock
  todos.jsonl        append-only
  notes/*/*.md       mutable, private
  media/             images, private
  index.sqlite       rebuildable cache — delete it any time
  capture/           Trophic's, and only Trophic's:
    log/YYYY-MM.jsonl  append-only: every captured line, every tick
    index.sqlite       rebuildable cache — delete it any time
```

**Only `data/seed/` is version-controlled.** The repo is the app; everything
else in that tree is what you have done with it, and lives in one copy on your
disk until you copy it somewhere. `install-linux.sh` seeds `domains/` from
`seed/` once, into an empty directory, and never again. See [SYNC.md](SYNC.md)
for what losing each file actually costs.

The log is not a record of clicks — it is where the app's state lives. A ticked
session *is* a `session` line; unticking appends an `undo` rather than editing
one, which is why toggling shows up as two lines. XP, level, streak and every
paid unlock are a fold over that file and are stored nowhere else.

Every event carries a `day` precomputed in GMT+7. Events sort by timestamp,
stably, so duplicated or out-of-order lines resolve identically however they
arrived.

## Trophic

A second app under its own tab, being ported from a Next.js/Postgres original.
Type a line; three triggers and two directives are parsed out of it:

| | | |
|---|---|---|
| `<pointer>` | folder / project tag | `<career>`, `<the backup-system>` |
| `{time-link}` | a temporal marker | `{q3}`, `{31/12/26}` |
| `\pattern` | counted sentiment | `\win`, `\burnout` |
| `--folder` | file it there; stripped from the text | `--work-log` |
| `--todo` | that line becomes a checkbox | |

Plain words are ignored by design, and the raw line is stored verbatim. Enter
sends, Shift+Enter is a newline, Tab takes the autocomplete, and `--folders`
opens the log.

Same architecture as the tree: `data/capture/log/*.jsonl` is append-only truth,
`data/capture/index.sqlite` is a projection you can delete. Everything the
parser finds — folders, times, patterns, the cleaned text, the todo lines — is
derived on replay and is *not* in the log, so improving the parser improves
every entry you have ever written. Ticking a checkbox appends a `check`; it
edits nothing.

| | |
|---|---|
| GET | `/api/capture/entries?date=` `?from=&to=` `&limit=`, `/dates`, `/vocab`, `/cumulative?up_to=`, `/health` |
| POST | `/api/capture/entries` |
| PATCH | `/api/capture/entries/{id}` — `{"toggle_line": n}` |

## Deliberately absent

Timers, minute tracking, notifications, multi-user, auth, editing the log, and
anything adaptive. Metric readings are stored and drawn, never interpreted —
which now covers Trophic's tag bars and sentiment chart too.

Per-node cadence is the next obvious gap.
