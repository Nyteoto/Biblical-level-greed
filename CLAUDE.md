# Working on this repo

A local, single-user tech tree for deliberate practice, plus **Trophic**, a
syntax-driven capture app being ported in beside it. FastAPI + SvelteKit,
no auth and no multi-user — do not add either. It runs on both halves of one
dual-boot machine, Fedora and Windows, sharing a single data disk.

The two are **sibling apps in one process**, not one app: `backend/app/` and
`backend/capture/`, `/api/…` and `/api/capture/…`, `data/log/` and
`data/capture/log/`. They share a data root, a venv, a test suite and a tab
bar. They share no models, no events and no fold. Read `TROPHIC.md` before
touching anything under `capture/` or `frontend/src/lib/trophic/` — the port
has an oracle, and guessing at behaviour it already pins is wasted work.

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
- **Never `git restore` / `git checkout` anything under `data/`.** It is live
  application state, not source. A whole-file revert destroys real practice
  history. Fix data forward, by hand, one line at a time.
- **Never put live data back in the repo.** `data/*` is gitignored with exactly
  one exception, `data/seed/` — the six researched trees, as shipped, read-only
  reference. The user's own trees, logs and media are theirs and stay on
  their disk. Copying a live tree into `data/seed/` pushes it to the
  remote, which is the thing this arrangement exists to prevent; a test asserts
  that directory holds those six files and nothing else.
- **Never edit or delete lines in `data/log/*.jsonl` or `data/todos.jsonl`.**
  Append-only is the core design commitment, not a style preference. Everything
  the UI shows is a fold over these files. A wrong event is corrected by
  appending its inverse (`undo`, `reopen`), never by deletion.
- **Never test a destructive path against real data.** Create a scratch domain
  first. Deleting against live data has already cost an unrecoverable photo.
- **Never weaken `backup.sh`'s refusals.** It exits rather than writing when the
  destination resolves to the same device as `data/`, and it has no `--delete`.
  Both look like over-caution and are not: the first is what catches an
  unmounted backup disk, and the second is what stops a local mistake being
  mirrored over the only other copy.

## The shape of the thing

The log is the truth. Everything else is a projection.

```
data/seed/*.toml ── copied once, by install-linux.sh, into ─┐
                                                            ▼
                                          data/domains/*.toml ─┐
                                                               ├─→ state.py ─→ board ─→ API ─→ UI
                                          data/log/*.jsonl ────┘      ↑
                                    index.sqlite (disposable cache; rebuild() replays the log)
```

Only `data/seed/` is in the repo. Everything to the right of it is the user's,
lives on one disk, and is gitignored — see SYNC.md, which is the document that
says what a loss of each file actually costs.

`data/index.sqlite` can be deleted at any moment and reproduced exactly. If a
value cannot be recomputed from the log plus the TOML, it does not belong in the
system.

### Backend modules

| module | owns |
|---|---|
| `models.py` | plain dataclasses and constants. Reads nothing, touches nothing. |
| `config.py` | every path and tunable. Locations are imported from here, never rebuilt. |
| `timeutil.py` | **the only** place doing timezone math. Events carry a precomputed `day`; everything else compares date strings. |
| `loader.py` | reads domain TOML and validates it. Never writes. |
| `writer.py` | serialises a Domain back to TOML. Regenerates the whole file. |
| `edits.py` | pure Domain→Domain transforms. Returns new objects, writes nothing. |
| `eventlog.py` | append-only event log. The source of truth. |
| `index.py` | SQLite projection of the log. Everything here is derived. |
| `state.py` | derives the board. Stores nothing. |
| `conditions.py` | what gates starting a node. Add a gate = one decorated function. |
| `xp.py` | earning (derived) and prices (recorded). See below. |
| `store.py` | holds loaded domains + index connection, serialises access, bumps `version`. |
| `foundation.py` | the `mementomori` domain, compiled in rather than loaded. |
| `watcher.py` | re-reads the TOML when it changes on disk, so hand-edits land without a restart. |
| `media.py` | the blob store, shared with capture. Originals byte for byte, plus a derived display copy. |
| `tools.py` `storage.py` | per-feature, self-describing docstrings. |
| `todos.py` | read-only history. Nothing writes it; `xp.py` still folds it, so deleting it would unearn past XP. |
| `main.py` | thin FastAPI layer: parse, call the store, return derived state. |

`desktop.py` sits at the repo root, outside the table: it is the packaged
entrypoint, not part of the app. It picks a free loopback port, starts uvicorn
and points a WebKitGTK window at it. Nothing else imports it.

Every module opens with a docstring explaining *why it is shaped that way*.
Read it before editing that module — the rationale is usually load-bearing and
usually not obvious from the code. **Keep that convention** in anything you add.

### Frontend

SvelteKit 5 (runes; `.svelte.ts` stores), Tailwind 4, Milkdown Crepe for
markdown. Built to `frontend/build`, which is **gitignored** — reverting or
editing frontend source leaves the app serving stale UI until you run
`npm run build` inside `frontend/`. Rebuild before claiming a UI change works.

## Invariants worth stating

- **`foundation.py` is not deletable from the UI**, by design. It is the domain
  the others attach to.
- **TOML is the source of truth for structure; the app rewrites whole files.**
  Comments and anything outside the schema do not survive a UI edit. That is
  why rationale lives in `docs/` and never in the trees.
- **Structural edits validate before they write**, and write atomically via
  `os.replace`. A rejected edit must leave the file byte-identical.
- **Soft prerequisites (`prefers`) can never block.** They advise. Keep them out
  of `conditions.py` — a hint that can stop you is not a hint.
- **XP earning is a read-only fold, stored nowhere.** Retuning a constant in
  `xp.py` re-scores all history with no migration. **Spending is not derived:**
  the price paid is written into the `unlock` event so retuning tomorrow cannot
  make yesterday's purchase unaffordable. Preserve that asymmetry.
  - Note the history here: XP *used* to be forbidden from affecting the board.
    That rule is gone — `state.py` imports `xp`, and nodes above tier I are
    `sealed` until their price is paid. Older prose asserting otherwise is stale.
- **Out-of-order and duplicated log lines are handled *on read*** — events sort
  by `ts` stably, and the fold is last-wins throughout. See `test_sync.py`. This
  used to exist for `merge=union` in `.gitattributes`, which is gone now that
  the streams are untracked; keep the read-side tolerance anyway, because a
  restored backup or an interrupted write produces the same shapes.
- **Capture is the app.** `/` is Trophic's capture bar; the tech tree is
  support at `/today` and `/tree`. Text and media enter the system through the
  capture bar and nowhere else — the markdown notes system and the PGS
  checklist were removed when that became true.
- **`/log` is the journal, and it is a feed of days.** Not a date ruler — the
  source's one is deleted, deliberately, and TROPHIC.md records what that cost
  the corpus. A day is a sticky header, a contact sheet of its media, then its
  lines. Anything that reintroduces one-day-at-a-time navigation is going
  backwards.
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
- **The shelf's group order is one event carrying the whole order.**
  `order-groups` names the year and lists its headings. A "moved to third"
  event would land somewhere else on a replay, and duplicated or out-of-order
  lines are a shape this log has to survive on read. The album sidebar and the
  year shelf read and write that same order — dragging a heading on either is
  the same act, and neither screen owns it.

## Deliberately absent

Timers, minute tracking, notifications, multi-user, auth, log editing, and
anything adaptive. Metric readings are stored and drawn, **never interpreted**.
These are refusals, not gaps — do not helpfully add them. Per-node cadence is
the one acknowledged gap.

## Commands

```bash
.venv/bin/python -m pytest backend/tests -q     # 463 tests, ~3s. Run them.
./run.sh                                        # build frontend + serve on 8787
uvicorn backend.app.main:app --reload --port 8787   # dev backend
cd frontend && npm run dev                      # dev frontend
cd frontend && npm run check                    # svelte-check
cd frontend && npm run verify:ui                # the corpus, TypeScript side
```

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
  than diff**: "Price the act of starting, and compile in the domain underneath
  it", "Take the prose out of the trees". Match that voice.
- Comments explain *why*, and are worth writing when the reasoning would not
  survive being re-derived. The existing density is the target — neither strip
  it nor pad it.
- `data/domains/*.toml` are hand-authored. To generate a new tree, read
  `docs/authoring-trees.md` and nothing else; research everything, invent
  nothing.
