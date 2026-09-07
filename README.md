# Personal Growth System

Two sibling apps in one process, on one dual-boot machine, sharing one data
disk.

**Capture** — *Trophic* — is the app. A syntax-driven capture bar at `/` and a
journal of what it caught. You type a line; the sigils in it file it, mark it,
schedule it or turn it into a checkbox.

**The tech tree** is a local engine for deliberate practice: one question, what
do I work on right now and for how long. Its API, its trees and its XP fold are
live and tested; **its two screens are hidden** — `/today` and `/tree` redirect
to `/`, and deleting `frontend/src/routes/today/+page.ts` and
`frontend/src/routes/tree/+layout.ts` is the whole of putting them back. Hidden
rather than deleted, deliberately: removing the tech tree is a decision to be
made with evidence, not as a side effect of a redesign.

They share a data root, a venv, a test suite and a tab bar. They share no
models, no events and no fold.

The in-app **Manual** (Settings → Manual) explains the syntax and why the log
is append-only; this file is reference.

## Install

```bash
./install-linux.sh
pgs                                # native window, data in ./data
pgs --data-dir /mnt/other/pgs      # data elsewhere
pgs --browser                      # no window
pgs --headless --host tailscale    # serve only; see MOBILE.md
```

On Windows, from its own clone — the Linux checkout is on btrfs and is not
readable from that side:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
pgs --data-dir F:\pgs-data        # the disk shared with Linux; see SYNC.md
powershell -ExecutionPolicy Bypass -File .\install-windows-tasks.ps1   # backups
```

The Windows installer writes `pgs.cmd` and a Start Menu shortcut, and re-running
it after `git pull` is how you update — `frontend/build` is gitignored, so a
pull that changed the UI serves the old one until the build step runs.

Tests: `.venv/bin/python -m pytest backend/tests -q` — 463 tests, ~3 s.
On Windows, `.venv\Scripts\python.exe -m pytest backend\tests -q`.

Dev: `uvicorn backend.app.main:app --reload --port 8787` + `cd frontend && npm run dev`.
`./run.sh` builds the frontend and serves both halves from one port.

- [MOBILE.md](MOBILE.md) — iPad/iPhone over Tailscale
- [SYNC.md](SYNC.md) — backups, dual boot, moving machines
- [docs/sources.md](docs/sources.md) — where the six trees came from
- [docs/domain-shapes.md](docs/domain-shapes.md) — the taxonomy argument
- [docs/authoring-trees.md](docs/authoring-trees.md) — how a new tree gets generated

## Screens

Navigation is three words in one pill, in the same corner of every screen.

| | |
|---|---|
| `/` | **Capture.** The bar, the standing tally, the due reminder, uploads. |
| `/log` | **Log.** The year shelf — every album with anything in it this year. |
| `/folders/{id}` | An album: one folder, one year. `/folders/{id}/{month}` is one volume of it. |
| `/mapping` | Which tags point at which folder, and every tag nothing has claimed. |
| `/settings` | Disk, Folders & tags, Log, Monitor — and the Manual. |
| `/manual` | What the syntax does, and why the log is append-only. |
| `/today` `/tree` | The tech tree. **Hidden**; both redirect to `/`. |

The Log is a feed of days, not a date ruler: a sticky header, a contact sheet
of that day's media, then its lines. Quiet stretches fold, and can be told not
to (Settings → Log).

## The syntax

One line of text, files attached to it, or both. Three triggers and two
directives are parsed out of it; plain words are ignored by design and the raw
line is stored verbatim.

| | | |
|---|---|---|
| `<pointer>` | folder / project tag | `<career>`, `<the backup-system>` |
| `{time-link}` | a temporal marker; comes back when due | `{q3}`, `{2d}`, `{31/12/26}` |
| `\pattern` | counted sentiment | `\win`, `\stuck`, `\burnout` |
| `@place` | where you were | `@helsinki`, `@the-office` |
| `--folder` | file it there; stripped from the text | `--work-log`, `--"the backup system"` |
| `--todo` | that line becomes a checkbox | |
| `--reply` | answers the reminder standing above the bar | |

Captures are trimmed, lowercased and de-duplicated, keeping first-appearance
order. `\ ` is a literal backslash; `@` opens a place only at the start of a
word, because `a@b.com` is an address; text inside `"quotes"` triggers nothing.

Enter sends, Shift+Enter is a newline, Tab takes the autocomplete, and on touch
a rightward swipe sends. A whole line of `--folders` or `--log` opens the log,
`--assign` opens mapping, `--settings` leaves for Settings; `--codex`,
`--logout` and `--dev` say they have no screen here rather than failing
silently.

Validation fires on the draft. `--nowhere` locks the bar, blinks the token red
and offers to create the folder inline; a directive and a tag that disagree
about the destination blink both and refuse to send. A tag no folder has
claimed is *not* a mistake — it is how tags start.

Caps: 20 000 characters a capture, 60 a folder name, 32 a shelf heading. A
capture that fails on a dead connection is queued and replayed when the
connection returns, with the waiting count under the bar; one the *server*
refused gives the text back instead.

## Folders, albums and the shelf

A folder is where lines land. **Membership is resolved on the read, never
stored**, and there are three routes in — a mapped `<tag>`, a `--directive`
naming the folder, and filing an entry by hand — all three of which resolve
from the raw line. Pinning a folder appends its tag to the line you are
writing, so a pinned capture is byte-identical to one you tagged yourself.

A folder claims no tag of its own: the registry holds the words *you* chose to
point somewhere. Renaming never un-files anything — a directive resolves
against every name the folder has ever had.

| | |
|---|---|
| state | `""` (no lifecycle), `active`, `shipped` |
| album | one folder seen through one year; recorded nowhere, derived on the read |
| chapter | a named stretch within an album; nameable by hand |
| group | a heading on one year's shelf. Its order is one event carrying the whole order |
| unfiled | what nothing has claimed, offered as an album of its own |

**Lifting a tag changes how it reads and nothing else.** A lifted `<garden>`
draws as `garden` everywhere and still files exactly where it did. It is a log
event rather than a browser preference, because it is a decision about the
writing. Only `<tags>` can be lifted.

### Points, the heatmap and the order of the shelf

A day in a folder is worth **one point per entry, plus one per twenty minutes
on that folder's clock**. An entry counts the same whether it is a word or a
paragraph.

Those points are drawn twice. The folder's overview has a year of days under
`Readings`, beside the `\pattern` counts — one cell per day, brighter with the
score, topping out at ten and then simply lit. Press a cell and it says what
that day was: the points, the entries, the time. And the same points, summed
over **the last thirty days**, are the order the year shelf comes back in, so
the first card is the thing you are actually working on rather than the thing
you once worked on most. The window rolls and ignores the calendar; a shelf of
a past year has no momentum and reads busiest-first as it always did.

Neither the score nor the order is interpreted anywhere. There is no target,
no streak, and no figure on a card saying how warm a project is.

## Reminders and replies

A `{time}` that has come due surfaces **one** prompt above the capture box,
oldest first. `--reply <thought>` answers it: the command is stripped in the
browser, the link rides on the capture event as `reply_to`, and answering
dismisses the reminder it answered. `replied_by` is the derived other end, so
the log draws the thread from both ends. An answer is otherwise an ordinary
entry — its own `{time}` resolves, and can start the next round.

## Media

Photos and video enter through the capture bar and are attached to the entry
they were sent with.

```
data/media/YYYY-MM/<hex16>.<ext>       the upload, byte for byte
data/media/YYYY-MM/<hex16>.view.jpg    a display copy, if one could be made
```

The original is never touched. Nothing is read into memory — an upload streams
to a temporary file and is `os.replace`d into place, flat in memory whether it
is 40 KB or 4 GB. `GET /media/{path}` answers Range requests with 206, so video
seeks. A video's poster frame is made by the browser, because a server-side one
means ffmpeg on both halves of a dual-boot machine.

## Todos, and the tally

Ten `--todo` lines may stand open at once; the eleventh is refused at the
write, including one entry carrying eleven at a time. A limit you can exceed by
typing faster is not a limit.

What became of the rest is the one figure the capture screen keeps on show — a
standing tally of promises kept over promises made, all of history, in the
bottom-left corner. It answers when either number moves. It is also a toy: take
hold of it, spin it, flick it, and it runs down and settles back. That does
nothing whatsoever, which is the point of it. The same pair, narrowed to one
folder and one year, sits in that folder's overview beside its entry and media
counts, and a todo nobody tagged belongs to the unfiled pile like anything
else. Both are derived on the read: nothing records them.

The markdown notes system and the tech tree's separate checklist were removed
when the capture bar became the only place to type. `data/notes/` and
`data/todos.jsonl` are left on disk untouched; nothing reads the first any
more, and the second is still folded into XP so past errands keep the points
they earned.

## The tech tree

Live behind the API, without screens. The board answers one question.

1. **Within a domain** — the lowest-tier startable node. Ties break on
   declaration order. `available` outranks `open`.
2. **How many** — the domain's `shape`.
3. **Whether at all** — the domain's `season`.
4. **Across domains** — the `priority` integer you typed.

`priority` sorts; `season` schedules. Everything is readable off the `.toml`.

### Node kinds

| kind | accrues | notes |
|---|---|---|
| `drill` | days | decays; set `decay_days` |
| `study` | days | holds once held |
| `project` | phases | must declare `phases`; no estimate |
| `exam` | prep days + `scheduled` | scored by someone else |
| `social` | occasions | needs other people; never forced to complete |

### Domain shapes

| shape | active at once |
|---|---|
| `ladder` | one |
| `strands` | one per declared strand |
| `cycles` | current project + the craft feeding it |

### Seasons

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

### Node schema

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

### Gate, entry, estimate

- **gate** — what done means. Never parsed; you decide.
- **entry** — how to start: book, free course, search string.
- **estimate** — a guess. You may finish under it or log past it; both are
  measured. Sessions after completion are upkeep, excluded from `actual`.

Each domain reports its estimating bias as a ratio of totals over settled nodes.

### Levels and XP

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

Capture, under `/api/capture`:

| | |
|---|---|
| entries | GET `/entries?date=` `?from=&to=` `&limit=` · POST `/entries` · PATCH `/entries/{id}` — tick a box, or file it by hand |
| the bar | GET `/banner`, `/vocab`, `/dates`, `/reminders` · POST `/reminders/dismiss` |
| folders | GET/POST `/folders` · GET/PATCH/DELETE `/folders/{id}` · PUT `.../chapter` `.../group` |
| the shelf | GET `/shelf?year=`, `/album?folder=&year=` · POST `/groups/rename` `/groups/delete` `/groups/order` |
| tags | GET `/tags`, `/tags/unassigned` · POST `/tags/lift` |
| readings | GET `/cumulative?up_to=` |
| admin | POST `/import`, `/reindex` · GET `/health` |

The tech tree, under `/api`:

| | |
|---|---|
| GET | `/health`, `/version`, `/storage`, `/backup`, `/dashboard`, `/domains`, `/domains/{id}` |
| POST | `.../nodes/{n}/session` `/complete` `/phase` `/unlock` |
| tools | GET/POST `/domains/{id}/tools` · PATCH/DELETE `.../tools/{tool_id}` |
| media | POST `/media?name=` · GET `/media/{path}` (Range/206, so video seeks) |
| POST | `/domains/{id}/season`, `/backup`, `/restart`, `/admin/reindex`, `/admin/reload` |
| CRUD | `/domains`, `.../nodes`, `.../edges`, `.../reorder` (POST/PATCH/DELETE) |

Structural edits rewrite the `.toml`, validated before the write, atomic via
`os.replace`. **Comments in the file do not survive a UI edit.**

## Data

```
data/
  seed/*.toml        the six researched trees, as shipped — the ONLY thing in git
  domains/*.toml     your trees, hand-authored and rewritten through the API
  log/YYYY-MM.jsonl  append-only: every session, completion, phase and unlock
  todos.jsonl        append-only, no longer written; still counted by XP
  media/YYYY-MM/     photos and video at full quality, private
                     <hex16>.<ext> is the original; <hex16>.view.jpg is a display copy
  index.sqlite       rebuildable cache — delete it any time
  capture/           Trophic's, and only Trophic's:
    log/YYYY-MM.jsonl  append-only: captures, ticks, filings, folders,
                       chapters, groups, lifted tags, dismissals
    index.sqlite       rebuildable cache — delete it any time
```

**Only `data/seed/` is version-controlled.** The repo is the app; everything
else in that tree is what you have done with it, and lives in one copy on your
disk until you copy it somewhere. `install-linux.sh` seeds `domains/` from
`seed/` once, into an empty directory, and never again. See [SYNC.md](SYNC.md)
for what losing each file actually costs.

The log is not a record of clicks — it is where the app's state lives. A ticked
session *is* a `session` line; unticking appends an `undo` rather than editing
one, which is why toggling shows up as two lines. Capture works the same way:
folders, times, patterns, places, the cleaned text and the todo lines are all
derived on replay and none of them is in the log, so improving the parser
improves every entry you have ever written. Ticking a checkbox appends a
`check`; it edits nothing.

Every event carries a `day` precomputed in the configured zone. Events sort by
timestamp, stably, so duplicated or out-of-order lines resolve identically
however they arrived.

| env | |
|---|---|
| `PGS_DATA_DIR` | the data root. Refuses to start if it is set and not mounted. |
| `PGS_TZ_OFFSET_HOURS` | the day boundary. Default `7`. |
| `PGS_CAPTURE_DATE_LOCALE` | which way `{03/04/26}` reads: `row` (default) or `us`. |
| `PGS_INDEX_PATH` `PGS_CAPTURE_INDEX_PATH` | the two caches, if they belong elsewhere. |
| `PGS_SERVICE` | the unit `POST /api/restart` restarts. Default `pgs.service`. |

## Deliberately absent

Timers, minute tracking, push notifications, multi-user, auth, editing the log,
and anything adaptive. Metric readings, tag bars and the sentiment chart are
stored and drawn, never interpreted.

Not built in capture: the codex and thinking-pond screens and the insight
engine behind them, `--draw`, and onboarding. Encryption is refused rather than
pending. Per-node cadence is the tech tree's one acknowledged gap.
