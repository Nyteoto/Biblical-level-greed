# Working on this repo

A local, single-user tech tree for deliberate practice. FastAPI + SvelteKit,
Linux only, no auth and no multi-user — do not add either.

`README.md` documents *what the app does*. This file documents *what you must
not break*. Read it before changing anything; it exists because the repo has
outgrown what one session can hold, and the failures that follow are always the
same kind: a rule that was load-bearing but only discoverable by reading code.

## Never

- **Never read or commit `data/notes/**` or `data/media/**`.** Private user
  content — their writing and their photographs. Listing filenames is fine;
  opening them is not. Both are gitignored. If you need a sample, make a scratch
  file.
- **Never `git restore` / `git checkout` anything under `data/`.** It is live
  application state, not source. A whole-file revert destroys real practice
  history. Fix data forward, by hand, one line at a time.
- **Never edit or delete lines in `data/log/*.jsonl` or `data/todos.jsonl`.**
  Append-only is the core design commitment, not a style preference. Everything
  the UI shows is a fold over these files. A wrong event is corrected by
  appending its inverse (`undo`, `reopen`), never by deletion.
- **Never test a destructive path against real data.** Create a scratch domain
  first. Deleting against live data has already cost an unrecoverable photo.

## The shape of the thing

The log is the truth. Everything else is a projection.

```
data/domains/*.toml ─┐
                     ├─→ state.py ─→ derived board ─→ API ─→ UI
data/log/*.jsonl ────┘      ↑
                     index.sqlite (disposable cache; rebuild() replays the log)
```

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
| `notes.py` `media.py` `tools.py` `todos.py` `storage.py` | per-feature, self-describing docstrings. |
| `main.py` | thin FastAPI layer: parse, call the store, return derived state. |

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
- **`merge=union` on the append-only streams** (`.gitattributes`) is correct
  there and nowhere else. Domain TOML is explicitly `-merge`. Out-of-order and
  duplicated lines after a merge are handled *on read* — see `test_sync.py`.
- **The checklist does not reset daily**, and ticking deletes from the list but
  nothing from the file.

## Deliberately absent

Timers, minute tracking, notifications, multi-user, auth, log editing, and
anything adaptive. Metric readings are stored and drawn, **never interpreted**.
These are refusals, not gaps — do not helpfully add them. Per-node cadence is
the one acknowledged gap.

## Commands

```bash
.venv/bin/python -m pytest backend/tests -q     # 254 tests, ~1s. Run them.
./run.sh                                        # build frontend + serve on 8787
uvicorn backend.app.main:app --reload --port 8787   # dev backend
cd frontend && npm run dev                      # dev frontend
cd frontend && npm run check                    # svelte-check
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
