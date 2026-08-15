# Working on this repo

A local, single-user tech tree for deliberate practice, plus **Trophic**, a
syntax-driven capture app being ported in beside it. FastAPI + SvelteKit,
Linux only, no auth and no multi-user — do not add either.

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
- **Membership is resolved, never stored, and the pin does not break that.**
  Pinning a folder appends its tag to the *raw line*, so a pinned capture is
  byte-identical to one you tagged yourself and survives a rebuild. Never add a
  folder id to the capture payload — that would be a second kind of membership
  the fold cannot reproduce.

## Deliberately absent

Timers, minute tracking, notifications, multi-user, auth, log editing, and
anything adaptive. Metric readings are stored and drawn, **never interpreted**.
These are refusals, not gaps — do not helpfully add them. Per-node cadence is
the one acknowledged gap.

## Commands

```bash
.venv/bin/python -m pytest backend/tests -q     # 334 tests, ~1s. Run them.
./run.sh                                        # build frontend + serve on 8787
uvicorn backend.app.main:app --reload --port 8787   # dev backend
cd frontend && npm run dev                      # dev frontend
cd frontend && npm run check                    # svelte-check
cd frontend && npm run verify:ui                # the corpus, TypeScript side
```

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
