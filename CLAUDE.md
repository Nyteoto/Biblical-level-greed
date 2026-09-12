# Working on this repo

**Trophic**: a local, single-user, syntax-driven capture app. FastAPI +
SvelteKit, no auth and no multi-user — do not add either. It runs on both
halves of one dual-boot machine, Fedora and Windows, sharing a single data disk.

The repo used to hold two sibling apps in one process — a tech tree for
deliberate practice, and Trophic beside it. **The tech tree is gone**: its
modules, routes, screens, trees and tests were removed on 2026-08-27. What
survives of that arrangement is the package split, and it now means something
different from what it used to:

- `backend/app/` is the **host and the shared floor** — the process, the data
  directory, the blob store, the backup, the frontend. It is about the machine.
- `backend/capture/` is **the app** — the log, the parser, the fold. It is
  about what the user wrote.

A module that knows about both is the thing this repo has spent its history not
being.

**Capture was ported from another codebase, and the port has an oracle.** The
`trophic/` bundle — gitignored, local to this disk — holds 2268 input→output
fixtures generated from the original TypeScript, and they are the specification
for `backend/capture/` and `frontend/src/lib/trophic/`. Before changing
behaviour in either, run both verifiers and know what they say; guessing at
something the corpus already pins is wasted work, and a "cleanup" that
normalises a tuned constant will fail a fixture rather than a review.

```bash
python3 trophic/golden/verify_golden.py     # the Python side, 1348 passing
cd frontend && npm run verify:ui            # the TypeScript side, 770 passing
```

A fresh clone has neither the bundle nor the verifier. `trophic/README.md`
explains the bundle; `frontend/scripts/verify-ui.ts` carries the deviations,
the colour table and where to fetch the bundle again. There is no `TROPHIC.md`
any more and there should not be one again: a second account of the app beside
the app drifted out of true and was still being read as current.

If you find prose anywhere in this repo describing a board, a node, a tier, XP,
a season or a domain, it is stale and predates the removal. Delete it rather
than working around it.

`README.md` documents *what the app does*. This file documents *what you must
not break*. Read it before changing anything; it exists because the repo has
outgrown what one session can hold, and the failures that follow are always the
same kind: a rule that was load-bearing but only discoverable by reading code.

## Never

- **Never read or commit `data/media/**`.** Private user content — their
  photographs and video. Listing filenames is fine; opening them is not. It is
  gitignored. If you need a sample, make a scratch file. (`data/notes/**` was
  the same and the notes system is gone; any files still there are the user's
  and are equally off limits.)
- **Never read the contents of `data/capture/log/**`.** The same rule as the media and for the same reason:
  this is what the user wrote, and a journal that an agent has read is a
  journal with someone else in it. **Grepping counts.** The harm is not in how
  much came back — it is that the line was opened, and a grep opens every line
  in the file to decide. So no `grep`, no `cat`, no `head`, no `jq`, no
  "just the one entry to see the shape".
  - The derived copies are the same act by a longer route.
    `data/capture/index.sqlite` is a projection of the log and holds the raw
    text verbatim; so does any `/api/capture/…` response. Reading one of those
    instead is not a way round this.
  - **What is fine is the shape**, and the shape is almost always what was
    actually needed: count the lines, list the filenames, read the event kinds
    out of `capture/eventlog.py`, follow the fold through `capture/index.py`.
    Every field is documented in the code, which is where it is safe to learn
    it.
  - When you need data that behaves like real data — a UI change, a
    destructive path, a migration — **generate it**: `scripts/fixture.py`
    builds a whole data directory that exercises nearly every screen. It is
    the answer to every question that begins "I only need to see one real
    entry".
- **Never `git restore` / `git checkout` anything under `data/`.** It is live
  application state, not source. A whole-file revert destroys real history.
  Fix data forward, by hand, one line at a time.
- **Never put live data back in the repo.** `data/*` is gitignored with **no
  exception** — the one that existed, `data/seed/`, went with the tech tree.
  What the user wrote and what they photographed are theirs and stay on their
  disk. Sample data comes from `scripts/fixture.py`, which generates it.
- **Never edit or delete lines in `data/capture/log/*.jsonl`.** Append-only is
  the core design commitment, not a style preference. Everything the UI shows is
  a fold over these files. A wrong event is corrected by appending its inverse
  (`uncheck`, `unassign`, `unmap-tag`), never by deletion.
- **Never test a destructive path against real data.** Build a fixture data
  directory first — `python scripts/fixture.py` — and point the app at it with
  `--data-dir`. Deleting against live data has already cost an unrecoverable
  photo. The tech tree removal is the largest destructive change this repo has
  had, and it touched no file under `data/`; hold that line.
- **Never weaken `backup.sh`'s refusals.** It exits rather than writing when the
  destination resolves to the same device as `data/`, and it has no `--delete`.
  Both look like over-caution and are not: the first is what catches an
  unmounted backup disk, and the second is what stops a local mistake being
  mirrored over the only other copy.

## The shape of the thing

The log is the truth. Everything else is a projection.

```
data/capture/log/*.jsonl ──→ index.py ──→ store ──→ /api/capture/… ──→ UI
        │                       ↑
        │        capture/index.sqlite (disposable cache; rebuild() replays the log)
        │
data/media/YYYY-MM/…  ── referenced by the events, never derived from them
```

None of it is in the repo. All of it is the user's, lives on one disk, and is
gitignored — see SYNC.md, which is the document that says what a loss of each
file actually costs.

`data/capture/index.sqlite` can be deleted at any moment and reproduced
exactly. If a value cannot be recomputed from the log, it does not belong in
the system. The one thing that is *not* recoverable that way is the media
itself: the log holds references, and the files behind them have one copy.

### Backend modules

`backend/app/` — the machine. Nothing here knows what a capture is.

| module | owns |
|---|---|
| `config.py` | every path and tunable. Locations are imported from here, never rebuilt. |
| `timeutil.py` | **the only** place doing timezone math. Events carry a precomputed `day`; everything else compares date strings. |
| `media.py` | the blob store. Originals byte for byte, plus a derived display copy. |
| `storage.py` | what the app is costing on disk, split by what a loss would mean. |
| `backup.py` | starts `backup.sh`/`backup.ps1` and reads back their stamp. Reimplements none of it. |
| `version.py` | the number the browser and the server have to agree on. Bump it when a route or payload changes. |
| `main.py` | thin FastAPI layer: the machine's routes, capture's router, and the SPA. |

`backend/capture/` — the app. This half has an oracle; run the verifiers above
before changing what it does.

| module | owns |
|---|---|
| `config.py` | capture's own paths and caps, under the shared data root. |
| `parser.py` | raw line in, metadata out. Pure, and pinned by 1185 golden fixtures. |
| `reminder.py` | `{time}` in, a due date out. Pure; the clock is a parameter. 104 fixtures. |
| `eventlog.py` | append-only event log. The source of truth. |
| `index.py` | SQLite projection of the log. Everything here is derived. |
| `store.py` | holds the index connection, serialises access, bumps `version`. Every write goes through `_commit`. |
| `colors.py` | the folder palette and the rule for picking the next colour. |
| `import_csv.py` | the one caller allowed to backdate an event. |
| `api.py` | the `/api/capture/…` router: parse, call the store, return derived state. |

`desktop.py` sits at the repo root, outside both tables: it is the packaged
entrypoint, not part of the app. It picks a free loopback port, starts uvicorn
and points a WebKitGTK window at it. Nothing else imports it.

Every module opens with a docstring explaining *why it is shaped that way*.
Read it before editing that module — the rationale is usually load-bearing and
usually not obvious from the code. **Keep that convention** in anything you add.

### Frontend

SvelteKit 5 (runes; `.svelte.ts` stores), Tailwind 4. Built to
`frontend/build`, which is **gitignored** — reverting or editing frontend
source leaves the app serving stale UI until you run `npm run build` inside
`frontend/`. Rebuild before claiming a UI change works.

`$lib/trophic/` is the app; `$lib/api.ts` is the machine's four endpoints
(storage, backup, version, restart) and nothing else. There is no `$lib/components/`
any more — it held the tech tree's node and domain UI and went with it.

## Invariants worth stating

- **Out-of-order and duplicated log lines are handled *on read*** — events sort
  by `ts` stably, and the fold is last-wins throughout. See `test_sync.py`. This
  used to exist for
  `merge=union` in `.gitattributes`, which is gone now that the stream is
  untracked; keep the read-side tolerance anyway, because a restored backup or
  an interrupted write produces the same shapes. `test_capture.py` and
  `scripts/fixture.py` both keep a duplicated line around on purpose.
- **Capture is the whole app now.** `/` is the capture bar, `/log` the journal,
  `/folders/…` the albums, `/mapping` the tag registry, `/settings` and
  `/manual` the two support screens. Text and media enter the system through
  the capture bar and nowhere else — the markdown notes system, the PGS
  checklist and the tech tree were each removed as that became true.
- **The journal is three rungs, and `/log` is the top one.** `/log` is the
  **year shelf** and shows no entries at all — which albums exist this year,
  how big each is, when each was busy. `/folders/[id]` is one album (one folder
  through one year) and `/folders/[id]/[month]` is one month of it; the feed of
  days lives in those two, where a day is a sticky header, a contact sheet of
  its media, then its lines. The source's date ruler is deleted, deliberately:
  it cost the corpus `timeline_draw`'s 22 cases and retired
  `timeline_interaction`'s 27, which is a deviation rather than a debt —
  there is no ruler left for them to describe.
  **Scrolling is for reading, never for travelling** — the year rail, the month
  spine, the chapter list and the jump field are all constant-cost, and
  anything that reintroduces one-day-at-a-time navigation, or pages the reading
  view, is going backwards.
- **The monitor is a layer, not a style.** The scanlines, vignette, grain, glow,
  sheen, rim and bezel are seven fixed `pointer-events: none` siblings in
  `+layout.svelte` that know nothing about the app. Content can be rewritten
  freely without touching any of it, and that separation is the whole point — do
  not push the effect down into components.
  - **There is no filter, and putting one back needs a measurement first.** The
    curve was a real `feDisplacementMap` and it cost **23ms of every frame**:
    36.4ms per frame while typing against 13.4ms without it, every frame over
    32ms. The cost is flat in the displacement distance (4px and 28px price the
    same), and `will-change`, a tight filter region and `contain: paint` all
    changed nothing — a filter rasterises its subtree on every repaint, and
    every keystroke is a repaint. The curve is suggested with static paint now:
    a specular sheen, a lit rim, darkened corners and a rounded bezel, all of
    which cost nothing per frame. Straight lines stay straight, and that is the
    known, accepted price.
  - `Lightbox.svelte` still portals itself onto `body`, and the upload bar still
    sits outside `main`. The filter that originally forced both is gone; the
    reason that remains is z-order — **a full-size photograph is never
    scanlined or tinted.** Thumbnails are.
- **A thing is labelled once, in the most legible place.** The album view grew
  three month labels (the header's `AUGUST 2026`, the chapter row's `Aug`, the
  month spine's `AUG`) and two year labels (that same header, and the sidebar's
  `2026`). None of them was wrong; together they are noise, and the user does not
  want that anywhere in this app. When a fact is already on screen, the second
  place that states it is the one to delete — pick the space where it reads best
  and strip the rest.
- **The ground is painted on `[data-shell-header]`, not on `html` or `body`.**
  WebKitGTK — the engine `desktop.py` ships — drops the canvas background from
  an offscreen snapshot. Harmless when the ground was near-white; on a dark
  ground the app looks like it failed to load.
- **One hue, and one exception.** Every syntax token is the same lit phosphor
  and is told apart by its delimiter and its weight, not its colour; folder
  colours are real stored data and are folded onto the ramp at render time by
  `phosphorize()`. The single exception is the refusal red, which must never be
  folded in — a refusal that looks like output is not a refusal.
- **Membership is resolved, never stored, and the pin does not break that.**
  Pinning a folder appends its tag to the *raw line*, so a pinned capture is
  byte-identical to one you tagged yourself and survives a rebuild. Never add a
  folder id to the capture payload — that would be a second kind of membership
  the fold cannot reproduce.
- **There are three routes into a folder and all three are resolved:** a mapped
  `<tag>`, a `--directive` naming the folder, and a filing by hand. A folder
  claims **no tag of its own** — the registry holds the words the user chose to
  point somewhere, and a word per folder that nobody typed is noise in the one
  list that has to stay meaningful. A directive resolves against `folder_names`,
  every name the folder has ever had, so a rename never un-files anything.
  Do not put the folder's name back in the tag registry; that decision was made
  once, reversed once, and the reversal is why the mapping screen is readable.
- **Lifting a tag changes how it reads and nothing else.** A lifted `<garden>`
  is drawn as `garden` wherever a captured line is rendered, and still files
  exactly where it always did: the raw line is untouchable and membership is
  still resolved from it. It is a log event (`lift-tag`) rather than a browser
  preference, because it is a decision about the writing rather than about this
  machine. Only `<tags>` can be lifted — a tag is the one kind whose sigil
  wraps the word on both sides, so it is the only one whose removal leaves the
  sentence reading as it was written.
- **`--` opens three commands: `--todo`, `--reply`, `--"folder name"`.** The
  first two are suggested ahead of folder names, which is a declared deviation
  from the corpus — the source completes folder names only, so the most used
  command in the app could never be completed. A command is **not** a missing
  folder: `--reply` is a `directive` token because 395 tokenize fixtures say so,
  and `validation.ts` is where that stops meaning "no such folder".
- **A reply is stored, not derived, and the prefix never reaches the log.**
  `--reply` is stripped client-side as the source strips it (40 parser fixtures
  pin `cleanText` as keeping it), the link rides on the capture event as
  `reply_to`, and answering dismisses the reminder it answers. `replied_by` is
  the derived other end. Do not try to recover the thread from the text: the
  line said "reply" and never said to what.
- **Dual boot splits along one line: data crosses by disk, code crosses by
  git.** Both operating systems open the same `data/` on the shared exFAT
  disk, so there is one log and nothing to reconcile — this is what the exFAT
  choice buys and why the checkout must never live there. The code is two
  clones meeting at the remote, so uncommitted work does not cross and
  `frontend/build` (gitignored) is stale on the other side until it is rebuilt
  there. Do not add a sync mechanism to either half; the first needs none and
  the second already has one.
- **Two Tailscale devices means two home-screen icons, and that is the
  decision.** Identity is per-install, so each OS has its own MagicDNS name,
  and iOS binds an icon to an origin. The alternatives — never serving from
  Windows, sharing a node key, an always-on box — were weighed and lost; see
  MOBILE.md. Only one is ever live, because one machine boots one OS. Do not
  try to collapse them.
- **There are two backup scripts and there must be.** `backup.sh` and
  `backup.ps1` restate the same two refusals — never write to the same volume
  as the data, never delete — rather than sharing them, because `rsync` and
  `df` have no Windows equivalent worth shimming and a refusal buried in a
  platform conditional is one that gets removed in a hurry. They write to
  different disks by necessity (ext4 is unreadable from Windows) and that is
  two complete copies, not two halves.
- **A folder's clock is a sum of sessions, and the session is the subject.**
  `log-time` carries its own id with the folder in the `folder` field, not the
  other way round. That is not a style choice: every other fold in this log is
  last-wins on a state, so a duplicated line says the same thing twice and
  lands the same way, while a *summed* fold keyed on the folder would count a
  restored backup's line twice and inflate a total nobody can check by eye.
  Keyed on the session, applying the same line twice is the same total. The
  inverse is `unlog-time` on that session id — never a negative duration, which
  would make the total right and the history absurd. Totals are
  `sum(seconds)`, derived on every read, stored nowhere, and cut by year for an
  album exactly as `entry_count` is.
  - **The running timer is not in the log, and must not be.** It lives in
    `localStorage` via `timer.svelte.ts` until you stop it, because a session
    is a draft until it ends — the same bargain the capture bar's text makes.
    A `start` event would put an unmatched start in an append-only file for
    every timer anyone ever forgot, and no fold could tell those from the real
    ones. The cost is accepted: close the tab mid-session and that time is on
    that machine only. Elapsed is computed from wall-clock stamps and never
    accumulated by a tick, because a background tab's timers are throttled and
    a sleeping phone's stop entirely.
  - **A pomodoro logs its work and never its rest.** `pomodoroAt` in
    `timer.ts` cuts one elapsed number into phases, and `stop()` writes
    `workedMs`. A cycle that banked its own breaks would make an hour at the
    desk read as an hour and ten, and the figure on the card would stop
    meaning "time worked" — which is the only thing it is allowed to mean.
    **The phase is derived from elapsed time, never flipped by a callback**,
    for the same reason the clock is: the `setTimeout` that would end the work
    stretch does not fire in a slept tab, so a phone locked mid-stretch would
    wake an hour later still "working". Deriving it makes the answer after any
    sleep simply correct, and the pinned table in `localChecks()` is what holds
    that — it is the most load-bearing pure function this port owns, because
    its output is what reaches an append-only log.
  - The chime is synthesised in `chime.ts` rather than shipped as a file: two
    sine tones, rising into work and falling into rest. The audio context is
    unlocked on the press that starts the timer, because a boundary forty
    minutes later has no user gesture near it. One chime on waking, however
    many boundaries were slept through — what you want to be told is which
    phase you are in now.
- **A day is worth one point per entry and one per twenty minutes clocked,
  and that number does two jobs.** It is what a folder's heatmap draws — the
  grid in the overview's `Readings`, beside the `\pattern` counts — and,
  summed over a rolling thirty days, it is the order the year shelf comes back
  in. `points()` in `index.py` is the one place the rule is spelled, and
  `test_momentum_agrees_with_the_days_the_heatmap_draws` is what stops the two
  readings drifting: the order of the shelf has to stay explainable by
  pointing at cells. An entry counts the same whether it is a word or a
  paragraph, for the reason nothing else here measures length either.
  - **The cap is the light, not the count.** Ten points is where the ramp tops
    out and a day past it is simply lit. It keeps counting — in the readout
    and in the sum — because a ceiling that also discarded what it clipped
    would make the number you can read disagree with the order you can see.
    `PEAK` lives in `Heatmap.svelte` because it is a drawing decision; nothing
    on the wire is capped.
  - **The window is a rolling month and does not respect the year.** Asked on
    the 3rd of January what you have been doing lately, a shelf cut to the
    calendar would answer "nothing, the year is new" — which is an answer
    about the planet rather than about the work. `store.shelf()` reads the
    clock and hands `index` a day; `index` never reads one. A past year has no
    momentum at all and falls all the way back to the old order, busiest first
    then by name, which is why every shelf you are not living in reads exactly
    as it did.
  - **`momentum` is a sort key and is never drawn.** It rides on the shelf
    payload so the order has a stated cause, and that is the whole of its job.
    A number per project that rises when you work and falls when you stop is a
    score, and the clock was let into this app on the promise of not becoming
    one. A heatmap draws days; a figure on a card would be a verdict.
- **The shelf's group order is one event carrying the whole order.**
  `order-groups` names the year and lists its headings. A "moved to third"
  event would land somewhere else on a replay, and duplicated or out-of-order
  lines are a shape this log has to survive on read. The album sidebar and the
  year shelf read and write that same order — dragging a heading on either is
  the same act, and neither screen owns it.

## Deliberately absent

Notifications, multi-user, auth, log editing, and anything adaptive. What is
captured is stored and drawn, **never interpreted**: no sentiment scoring on
`\patterns`, no suggestions, no summaries of the user's own week. These are
refusals, not gaps — do not helpfully add them.

Also absent, and not coming back: the tech tree. Boards, nodes, tiers, XP,
seasons, domains, `.toml` curricula and the six seed trees. Removed on
2026-08-27 at the user's request, in full.

**Timers and minute tracking used to head that list, and no longer do.** A
folder has a clock now — see the invariant above. The refusal was written when
the only thing that could have been timed was a practice session, and timing
those is the thing that turns practice into a score you can lose at. Capture
has no score, and time on a project is a fact about the project rather than a
judgement about you: `41h` beside `96 entries` reads the way `96 entries`
does. What the old rule was protecting still holds and is worth keeping —
**the number is drawn and never interpreted.** No targets, no streaks, no
average session length, no "you have not worked on this in nine days". The
heatmap and the shelf's order are not exceptions and must not become the road
to one: a grid of days is a record of what happened, and the moment it grows a
streak count or a target it has stopped being that.

## Commands

```bash
.venv/bin/python -m pytest backend/tests -q     # 290 tests. Run them.
python scripts/fixture.py                       # → data.fixture/, a whole fake data dir
python desktop.py --data-dir data.fixture       # ...and look at it
./run.sh                                        # build frontend + serve on 8787
uvicorn backend.app.main:app --reload --port 8787   # dev backend
cd frontend && npm run dev                      # dev frontend
cd frontend && npm run check                    # svelte-check
cd frontend && npm run verify:ui                # the corpus, TypeScript side
```

`scripts/fixture.py` is how you look at a screen without looking at the user's
log. It builds five folders across twenty-five days and thirty captures
carrying every token the syntax knows — a renamed folder, a deleted one, a
lifted tag, all three folder states, a named chapter, a shelf with groups and
an order, a due reminder, a dismissed one, a reply, todos checked and
unchecked, and a mosaic of thirteen photographs at eight aspect ratios. It
refuses to write anywhere it did not create, so `--out` cannot be aimed at real
data by accident.

The Windows side has its own clone and its own venv; nothing here runs from
the Linux checkout. `install-windows.ps1`, `backup.ps1` and
`install-windows-tasks.ps1` are the three files that only ever execute over
there — which means the suite cannot exercise them and neither can you.
Change them only with a reason you could defend without running them.

**Run them with `powershell`, never `pwsh`.** On a Windows machine that word
means 5.1, and 5.1 is what the scheduled task runs, what `backup.py` shells out
to and what every instruction in this repo names. Three of the seven bugs the
bring-up found were 5.1-versus-pwsh-7 differences, and all three were invisible
under the interpreter that is nicer to test with: 5.1 reads a BOM-less `.ps1`
as cp1252, will not pass an embedded double quote to a native command, and
wraps a native command's stderr in ErrorRecords once merged into the pipeline.
A script that passes under pwsh has not been tested.

Tests point at a throwaway data dir via `conftest.py` before the app imports —
they never touch `data/`. Keep it that way.

## Conventions

- **Commit messages read as prose, in the imperative, describing intent rather
  than diff**: "Give the send, the hold and the feed one place each", "Fold the
  log and mirror a write with the same code". Match that voice.
- Comments explain *why*, and are worth writing when the reasoning would not
  survive being re-derived. The existing density is the target — neither strip
  it nor pad it.
- Sample data is **generated, never written by hand and never committed**:
  `scripts/fixture.py` is the only source of it, and the reason is in its
  docstring.
