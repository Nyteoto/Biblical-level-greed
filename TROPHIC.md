# Trophic — the capture app, and how it is being ported

Trophic is a syntax-driven thought-capture app being moved out of a Next.js /
Prisma / Postgres codebase and into this stack. `trophic/` holds the reference
bundle: pure TypeScript to port, a Prisma schema to read as a spec, 2058 golden
fixtures generated from the original, and read-only notes on the interaction
design. Read `trophic/README.md` first; it explains itself better than a
summary would.

This file is the decisions the port has already made. It exists so a later
session does not re-litigate them or, worse, quietly reverse one.

## It is a sibling app, not a feature

One process, one port, one `run.sh`, one test suite, one tab bar. Two of
everything else:

| | tech tree | Trophic |
|---|---|---|
| backend | `backend/app/` | `backend/capture/` |
| API | `/api/…` | `/api/capture/…` |
| log | `data/log/*.jsonl` | `data/capture/log/*.jsonl` |
| index | `data/index.sqlite` | `data/capture/index.sqlite` |
| frontend | `src/routes/` + `src/lib/components/` | `src/routes/trophic/` + `src/lib/trophic/` |

They have no event kind, no model and no fold in common, and interleaving their
logs would only teach every existing fold to skip lines it does not care about.
Both are backed up by the same `backup.sh` and covered by the same
`data/*` gitignore.

The one deliberate coupling: `capture/eventlog.py` imports `app/timeutil.py`.
The day boundary is a property of the *user*, not of an app, and this repo's
rule is that exactly one module does timezone math.

## What the port changed on purpose

**No user scoping.** Every Prisma model carries a `userId` and every route
starts with an auth check. There is one user and they are sitting at the
machine. `FolderTag`'s `@@unique([userId, tagName])` becomes a plain unique
index on the tag.

**The log stores the raw line; everything else is derived.** The source stores
`parsed.cleanText` in `rawText` and keeps `folders`/`times`/`patterns` as
Postgres `text[]` beside it. Here the log holds exactly what was typed, and
`clean_text`, the three capture lists and the todo line indices are computed by
`index.derive()` on every rebuild. Two consequences, both wanted: the
`--directive` is recoverable (`cleanText` has it stripped out), and retuning the
parser re-scores all of history with no migration.

**Row mutations became events.** `check`/`uncheck` exist. `assign`/`unassign`
and `map-tag`/`unmap-tag` are named in `eventlog.py` and not yet written by
anything — when folders arrive, use those names.

**A `--directive` files the entry under its own name.** With no folder registry
yet, `--work` puts the entry in `work`, which is exactly the source's behaviour
when a folder has no explicit tag mappings. It is not dropped.

## The corpus is the specification

`trophic/golden/` holds 2058 input→output fixtures generated from the real
TypeScript. The source repo has no tests; this is the only thing that can tell
you a reimplementation is faithful.

```bash
python3 trophic/golden/verify_golden.py            # everything
python3 trophic/golden/verify_golden.py parser     # one module
```

**Read the corpus file's `notes` array before porting its module.** Every
adapter starts as `NotImplementedError` and reports SKIPPED, so the "not yet
covered" count is the honest progress bar.

| module | state |
|---|---|
| `parser` | **ported** to `backend/capture/parser.py` — 1185/1185 |
| `tokenize`, `trie` | **copied verbatim** into `frontend/src/lib/trophic/` |
| everything else | not started — 873 cases still skipped |

`tokenize.ts` and `trie.ts` are TypeScript in the frontend rather than Python in
the backend because only the browser needs them: the live syntax colouring and
the autocomplete are client-side, and the backend needs nothing but the parser.
For a TypeScript target, the faithful port of the file the corpus was generated
from is that file. If a Python tokenizer is ever wanted, its 586 cases are
waiting.

Suggested order for the rest: `reminder` → `import-csv` → `insights/`. Save
`insights/` for last; it is the largest and its fixtures assume the others work.

## The UI is a port of the feel, not of the React

`trophic/reference/ui-behavior/` is read-only. Nothing in it transfers to Svelte
directly; what transfers is the interaction design, and
`ui-behavior/CAPTURE-BAR.md` is the spec for it — every duration in it is a
tuned number, not a default, and normalising them onto CSS variables is exactly
the cleanup that would destroy the feel.

The one thing that matters most, quoting that document: **the native caret is
switched off and replaced with a measured one that glides over 80ms.** That is
what `SmoothTextarea.svelte` is for, and a plain `<textarea>` would make
everything else cosmetic.

Two documented deviations from the source:

- **Colour.** Hue assignments are the product and did not move — blue is a
  folder, rose is a sentiment, purple is time. Lightness did: the originals were
  chosen against white and are unreadable on `#14100c`. See
  `lib/trophic/colors.ts`, which is the only file to change if a light theme
  ever comes back.
- **Type.** The original is IBM Plex Mono, and the doc is right that swapping
  the mono changes the product's character more than any animation. Neither
  Plex nor a fallback is installed here, so it renders in the system mono. Drop
  the woff2 into `frontend/static/` and add an `@font-face` to fix it.

`CAPTURE-BAR.md`'s idle-dim table has the two directions the wrong way round;
the CSS it cites is what shipped, and `lib/trophic/trophic.css` explains which
is which.

## What is not built yet

Folders as entities (name, colour, tag mappings), and with them the whole
validation layer — `useCaptureValidation` can only check a `--directive` and a
`<tag>` against a folder registry, so `locked`, the red token blink and the
inline "create" button are plumbed through and never fire. Also absent: the
codex, mapping, thinking-pond and settings screens, reminders, `--draw`,
`--reply`, images, and onboarding.

The capture bar and the log viewport are the two screens that exist. `--folders`
and `--log` both open the log; the source's other nav commands say so rather
than failing silently.

## Picking this up

State as of the last session: the parser is ported and green against its 1185
fixtures, the backend is `capture/{config,eventlog,index,store,api,parser}.py`
mounted at `/api/capture/`, and the two screens above are built and rendered
end-to-end against a scratch data dir. Everything below passes:

```bash
.venv/bin/python -m pytest backend/tests -q          # 279, of which 12 are capture's
python3 trophic/golden/verify_golden.py              # 1185 passed, 873 not yet covered
cd frontend && npm run check && npm run build        # 0 errors
./run.sh                                             # both apps, port 8787
```

The frontend build is gitignored, so **rebuild before judging any UI change** —
reverting or editing source leaves the app serving the old bundle.

To continue the port, the shape of a session is always the same:

> Continuing the capture port — see `TROPHIC.md`, then `trophic/README.md`.
> Next: port `trophic/reference/logic/<file>` and get
> `python3 trophic/golden/verify_golden.py <corpus-stem>` passing.
> Read that corpus file's `notes` array before starting.

`reminder` is the one to take next: 104 cases, already pure, already takes a
`now`, and it unlocks the reminder strip above the capture box — the last piece
of the capture screen that is specified and missing.

Two traps that have already been hit once each, both recorded here so they cost
nobody a second session:

- **Python is not JavaScript at the edges.** `\p{…}` has no `re` equivalent,
  `\b` is Unicode here and ASCII there, `str.strip()` and JS `trim()` disagree
  on which characters are whitespace, `round()` is banker's and `Math.round` is
  half-up. `golden/README.md`'s "Porting gotchas" lists the rest; every one of
  them produces a *nearly* correct port.
- **Same-language ports are copies.** `tokenize.ts` and `trie.ts` went into the
  frontend verbatim. Rewriting them could only lose fidelity to the file the
  oracle was generated from.

## The bundle is not in git

`trophic/` is gitignored — it is a read-once copy of another repo, not part of
this program. Two things follow, and they are the reason this section exists:

- **The oracle is local.** `trophic/golden/verify_golden.py` lives inside the
  bundle, so a fresh clone has no corpus and no verifier. Anyone continuing the
  port needs the bundle on disk first.
- **So is the adapter wiring.** The parser adapter in `verify_golden.py` —
  a `sys.path` insert for the repo root, `from backend.capture.parser import
  parse_entry`, and a snake_case→camelCase rename in `_parser` — is an edit to
  an untracked file. Re-copying the bundle silently reverts it. If
  `verify_golden.py parser` suddenly reports SKIPPED rather than 1185 passed,
  that is what happened.

To restore it: the bundle came from `/home/pekka/pekka/LearningNext/scheduler`,
branch `pivot`, commit `105181c`. Regenerate the corpus there with
`TZ=UTC pnpm tsx golden/generate.ts` (or `pnpm golden`) and re-copy. The
determinism contract in `golden/README.md` is what makes that reproducible:
`TZ=UTC`, the clock frozen to `2026-08-14T12:00:00.000Z`, and a mulberry32 PRNG
seeded `0x5EED`.
