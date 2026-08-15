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

**Row mutations became events.** `check`/`uncheck`, `assign`/`unassign`,
`map-tag`/`unmap-tag`, `create-folder`/`rename-folder`/`delete-folder`, and
`dismiss`. An event's `id` is its *subject* — the entry's for entry events, the
folder's for folder events — and anything it needs to name second (`folder`,
`tag`, `line`) has its own field.

**A `--directive` files the entry under its own name.** `--work` puts the entry
in the tag `work`, which is exactly where `<work>` would have put it. The source
instead looks the directive up in the folder table at write time and drops it if
nothing matches; that loses it, and is the one place the port refuses to follow.

## Folders, and the taxonomy of tags

Four decisions, none of them reversible without a lot of rework:

**Membership is resolved, never stored.** An entry is in a folder because one of
its tags is mapped there, or because it was filed there by hand. There is no
folder→entry table — the source has none either (`schema.prisma`: "folder
membership is resolved at query time by matching tag names"). This is what makes
mapping retroactive: point `<deploy>` at Work and every entry ever written with
`<deploy>` in it is in Work, with nothing to migrate and nothing to backfill.
Unmap it and they leave again.

**A folder claims the tag of its own name, at creation and at rename.** This is
an addition, not a port: the source upserts that tag lazily, the first time an
entry is filed by a directive into a folder that has no tags. Doing it eagerly
means there is exactly one mechanism — a tag points at a folder — and `--work`
needs no special case anywhere downstream. The rename case is the load-bearing
one: the old name stays mapped, so entries written `--admin` do not silently
fall out of the folder when it becomes `Paperwork`. A folder never *steals* a
name already mapped elsewhere; an explicit mapping does move a tag, because
that is the entire gesture on the mapping screen.

**One tag, one folder.** `folder_tags` is keyed on the tag, which is this log's
spelling of `@@unique([userId, tagName])`. `unmap-tag` names the folder it is
unmapping *from*, so a duplicated line from an old backup cannot unfile a tag
that has since moved.

**Reminders are derived too.** The source writes a `Reminder` row at submit
time. Here a reminder is `resolve_reminders(raw_text, now=the entry's ts)` — a
pure function of two things the log already holds — so a rebuild reproduces
every due date exactly, and `{2d}` means two days after the day it was typed
however long ago that was. Only the dismissal is an event.

## The corpus is the specification

`trophic/golden/` holds 2268 input→output fixtures generated from the real
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
| `reminder` | **ported** to `backend/capture/reminder.py` — 104/104 |
| `next_color` | **ported** to `backend/capture/colors.py` — 11/11 |
| `import-csv` | **ported** to `backend/capture/import_csv.py` — 48/48 across two corpus files |
| `tokenize`, `trie` | **copied verbatim** into `frontend/src/lib/trophic/`, and now **verified there** — 633/633 via `npm run verify:ui` |
| `insights/`, `typo_suggestion` | not started — 77 cases |
| the 11 UI-behaviour files | **138/188**, also via `npm run verify:ui` — see the UI section |

`tokenize.ts` and `trie.ts` are TypeScript in the frontend rather than Python in
the backend because only the browser needs them: the live syntax colouring and
the autocomplete are client-side, and the backend needs nothing but the parser.
For a TypeScript target, the faithful port of the file the corpus was generated
from is that file — and `npm run verify:ui` now proves the copies are faithful
by replaying their 633 cases against the files the app ships, so the Python
adapters for them should stay unwired rather than be filled in.

What is left is `insights/`, deliberately last: it is the largest and its
fixtures assume the others work.

## The UI is a port of the feel, not of the React

`trophic/reference/ui-behavior/` is read-only. Nothing in it transfers to Svelte
directly; what transfers is the interaction design, and
`ui-behavior/CAPTURE-BAR.md` is the spec for it — every duration in it is a
tuned number, not a default, and normalising them onto CSS variables is exactly
the cleanup that would destroy the feel.

**The feel now has an oracle too.** Eleven corpus files pin the interaction
layer the way the other fourteen pin the logic — generated by running the real
React through a fake DOM, so they record behaviour rather than markup:

| file | pins | state |
|---|---|---|
| `timeline_draw` | every canvas call, in order, across all four zoom tiers | **dropped — the ruler is gone, see below** |
| `capture_overlay` | the overlay, ghost text, the suggestion panel, the sliding caret | 26/26 |
| `capture_keys` | the (inverted) arrow keys, accept, quoting, IME passthrough | 18/18 |
| `capture_validation` | the locking rules the bar implements | 32/32 |
| `colorize` | the read-only rendering of a saved line | 25/25 |
| `long_press` | 500ms, 10px radial, one swallowed click | 14/14 |
| `viewport` | device type, the on-screen keyboard, hand mode | 23/23 |
| `timeline_interaction` | wheel easing, drag, pinch, double-tap, clamping, persistence | dropped with it |
| `retry_queue` | the offline queue | see below |
| `iris_close` | the vault iris | not built |
| `design_tokens` | colours, keyframes and every tuned duration, read out of source | snapshot |

Most are **traces**: `input.events` is a script, `expected.trace` is the state
after each step. Replay and compare row by row; the first divergent row is the
behaviour that has not been ported. `design_tokens` is the exception — a
snapshot, with an adapter that is deliberately never wired up, because a port
that restyles on purpose *should* differ from it.

### Running them: `npm run verify:ui`

`verify_golden.py` says it itself — "for a target that keeps the TypeScript,
the faithful adapter is to run the real module". So the UI half is verified by
`frontend/scripts/verify-ui.ts`, which imports the modules the app actually
ships and replays the corpus against them. It runs on Node's type stripping,
needs no build, and takes the same arguments as the Python one:

```bash
cd frontend && npm run verify:ui              # 771 passing
npm run verify:ui capture_overlay -v          # one file, every diff
```

Three things about it are worth knowing before changing it:

- **It still runs under `en_US.UTF-8` and `TZ=Asia/Bangkok`.** The locale
  mattered for the ruler's month names and no longer does; the timezone still
  matters, because one local check pins the midnight bug (see below) and it can
  only fire east of Greenwich. Leave both set.
- **The colour deviation is a declared table, not a blanket excuse.** `THEME`
  in that file lists every colour this port emits and the source colour it
  stands in for; comparison translates and then demands an exact match, so a
  colour that is wrong for a reason other than the dark shell still fails.
  Two entries map to more than one source colour, and the comment says why.
- **`retry_queue.json` cannot be satisfied and is marked `CORPUS?`.** Its
  fixtures contradict the module they were generated from — a successful send
  is expected to leave the entry in storage, two queued entries with two
  scripted responses record one attempt, and every case reports `pending: 0`
  beside a three-entry queue. The generator's harness and the module were
  reading two different localStorage objects. The port follows the file's
  *notes*, which are accurate, and the runner reports the mismatch rather than
  hiding it or failing forever. Delete the entry if a regenerated bundle
  starts passing.

### What replaying them found

Four things, all of them invisible until the corpus asked:

- **The suggestion panel was positioned against the wrong box.** It is
  `position: fixed`, and an ancestor carried `transform: translateX(0)` for
  the send animation — an identity transform, but enough to make that ancestor
  the containing block. The panel rendered hundreds of pixels off-screen and
  nobody had noticed, because nothing had opened it in a screenshot. The
  source portals the panel to `<body>` and never meets this.
- **`ColorizedText` skipped the span on uncoloured tokens**, so segment
  indices did not line up with token indices.
- **The conflict message was reworded** — the corpus compares observation
  strings verbatim.
- **The `--draw` branch of the validation layer had been dropped** as
  unreachable, since `--draw` opens a sketch pad this port does not have. It
  is back: removing it changes what the other branches see, because it returns
  early, and `--draw -Missing <garden>` must report the missing folder and
  never run the conflict check.

### Where the behaviour lives now

To be replayable, the behaviour had to come out of the components. Three
modules were split out, and the rule is worth keeping: **anything that decides
what a screen shows or what a key means goes in the module; the component
keeps the DOM, the timers and the measuring.**

| module | pinned by |
|---|---|
| `capture-bar.ts` | `capture_overlay`, `capture_keys` — the overlay, ghost text, the panel, the caret style, every key |
| `colorize.ts` | `colorize` |
| `validation.ts` | `capture_validation` |
| `longpress.ts` | `long_press` — a `LongPress` class with injected timers, plus the Svelte action around it |
| `device.ts` | `viewport` — pure predicates; the runes live in `device.svelte.ts`, because a `$state` in a plain `.ts` is an undefined call at runtime and renders a blank page |
| `retry-queue.ts` | see above |
| `day.ts`, `pinned.ts` | nothing in the corpus — `localChecks()` in the runner, because they are this port's own and its own mistakes still need an oracle |

Two of them are worth reading even if nothing is being ported today.
`capture_overlay` records that the suggestion panel is rendered upside down (so
`ArrowDown` decrements), and `design_tokens` records the asymmetries — zoom in
1.18 out 0.85, glow in 0.1s out 0.4s, dim out 30s in 0.4s — that a tidy-minded
rewrite flattens without noticing.

The one thing that matters most, quoting that document: **the native caret is
switched off and replaced with a measured one that glides over 80ms.** That is
what `SmoothTextarea.svelte` is for, and a plain `<textarea>` would make
everything else cosmetic.

Three documented deviations from the source:

- **The date ruler is deleted.** `TimelineNav.svelte` and `timeline-draw.ts`
  are gone, and the log is a scrolling feed of day blocks — a sticky header, a
  contact sheet of that day's media, then its text lines. The source's ruler
  was built for a text capture tool with no media in it: a 520px pane showing
  one day at a time through a canvas of tick marks. Against a folder of
  photographs and 2 GB clips it answers "what did I write on the 3rd" and
  cannot answer "how much is in here", which is the question this app is now
  for. **This costs the corpus 22 cases** — `verify:ui` went from 793 to 771 —
  and it retires `timeline_interaction` (27, never wired) as a debt. That is a
  deliberate deviation, not a regression, and it is the reason both numbers
  moved.
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
is which. `design_tokens.json`'s `tokens-idle-dim` case now carries that CSS
verbatim, extracted from `globals.css` at generation time, so the corpus is the
tiebreaker rather than either prose.

## What is not built yet

The codex and thinking-pond screens and the insight engine behind them,
`--draw`, `--reply`, images, and onboarding. Encryption is refused rather than
pending — see `trophic/README.md` for why.

Three hooks from the source are ported: the device classification
(`device.ts`), the on-screen-keyboard test — which earns its keep on the syntax
key bar, not on the layout; the capture box deliberately does *not* reflow when
the keyboard opens — and hand mode. Hand mode is now read by nothing: it put
the ruler on the thumb's side, and the ruler is gone. It is kept because it is
pinned by `viewport` and costs nothing, and because a phone-side control will
want it again. The offline retry queue is
ported too: a capture that fails on a dead connection is queued and replayed
on `online`, and the count of waiting lines is shown under the bar. A capture
that fails because the *server* refused still gives the text back — the two
are different and the screen treats them differently.

Four screens exist: the capture bar, the log, one folder, and mapping. The log
no longer carries the full folder list the source's `/folders` does — folders
are a rail of filter chips across its top, and creating, renaming and deleting
one happens there and on the folder's own page. `--folders` and `--log`
open the log, `--assign` opens mapping, `--settings` leaves for the tech tree's
settings page; the source's other nav commands say they have no screen here
rather than failing silently.

The validation layer now fires. `--nowhere` locks the bar, blinks the token red
and offers to create the folder inline; `--work <garden>` when `<garden>` is
Home's blinks both and refuses to send. Nothing else about a draft is
checkable — a tag no folder has claimed is not a mistake, it is how tags start.

## Picking this up

**Where this stands, 16 Aug 2026.** The port is no longer the work. Capture is
the app, the log was rebuilt around it (see the ruler deviation above), and
what is left of the source bundle is mostly things this app has decided it does
not want. Read this before opening `trophic/` and porting something because it
is next in the list.

Shipped in the last session, all four gates green:

- **A folder has a life** — `set-state`, three states, the empty one default.
  Backend end to end with tests; the control is on the folder's own page.
- **The log is a feed of days** — `DayBlock` + `MediaTile` + `Lightbox`, a
  contact sheet per day over its text lines, filter chips with counts across
  the top. `TimelineNav.svelte` and `timeline-draw.ts` are deleted.
- **The pin** — `pinned.ts` (pure) + `pinned.svelte.ts` (localStorage). Pin a
  folder and every capture appends that folder's tag to the raw line. Read
  `pinned.ts`'s header before changing it: writing the tag into the text rather
  than sending a folder id alongside is the whole design, not a shortcut.
- **The folder page is a project page** — cover, `2 days · 28 Jul → 16 Aug`,
  the state control, a contact-sheet toggle, rename and delete. The log no
  longer carries the folder list; that moved here.

Deliberately left for next time, in the order they were argued for:

1. **Chains** — a `follows` relation between folders, so a project that grew
   out of another one says so, and the candidate list that goes with it. This
   wants projects to exist first, which they now do.
2. **Per-node cadence** on the tech tree — still the one acknowledged gap.
3. **Deleting the tech tree.** Still on the table and still cheap: the log says
   45 events across 3 days and 13 of 14 sessions undone immediately. Decide
   with evidence, not a prediction, and not in the same session as anything
   else.
4. **Pagination beyond a widening window.** The log fetches 200 and offers
   `load more`. That is months of this journal; revisit when it is not.

The thinking pond is dropped outright — it was the habit-tracking side under
another name. The codex is not urgent. Both change what "what is left" means
below: `insights/` feeds screens this app may never build, so port it because
something wants it, not to finish the list.

State of the port itself: parser, reminder, the folder palette and CSV
import are ported and green, the backend is
`capture/{config,eventlog,index,store,api,parser,reminder,colors,import_csv}.py`
mounted at `/api/capture/`, and the four screens above are built and rendered
end-to-end against a scratch data dir. Everything below passes:

```bash
.venv/bin/python -m pytest backend/tests -q          # 334, of which 77 are capture's
python3 trophic/golden/verify_golden.py              # 1348 passed, 920 not yet covered
cd frontend && npm run verify:ui                     # 771 passed, 0 failed
cd frontend && npm run check && npm run build        # 0 errors
./run.sh                                             # both apps, port 8787
```

The two verifiers between them now cover 2119 of the corpus's 2268 cases. What
is left is `insights` and `surfacing` (17) with their two formatting helpers
(40), `typo_suggestion` (20), `retry_queue` (10, unsatisfiable), `iris_close`
(7) and the `design_tokens` snapshot (6) — plus `timeline_draw` (22) and
`timeline_interaction` (27), which are not debt any more but a deviation: there
is no ruler left for them to describe.

The frontend build is gitignored, so **rebuild before judging any UI change** —
reverting or editing source leaves the app serving the old bundle.

To continue the port, the shape of a session is always the same:

> Continuing the capture port — see `TROPHIC.md`, then `trophic/README.md`.
> Next: port `trophic/reference/logic/<file>` and get
> `python3 trophic/golden/verify_golden.py <corpus-stem>` passing.
> Read that corpus file's `notes` array before starting.

`insights/` is what is left, and it was explicitly deferred rather than
forgotten. Its 17 cases are few only because each one is enormous; budget a
session for the engine and another for the screens it feeds (codex, thinking
pond). Notes from the reading done before it was set aside:

- Keep the `run_engine(input) → list[Insight]` seam. It is the one boundary in
  the source that survives the language change unchanged, and `index.ts` is
  written to be replaceable wholesale behind it.
- Port `config.ts` as one file. Every threshold in the engine lives there, and
  the spec's own note is that they will all need retuning.
- Three of the four detectors are pure; `detectProgression` reads `Date.now()`
  and `detectBurstiness` falls back to it. Thread `now` through as a parameter
  — the corpus already passes it as an input field.
- `observation` strings are compared verbatim, so `humanDuration` and
  `toFixed(1)` have to be exact. `Math.round` is half-up and Python's `round`
  is banker's; `toFixed` rounds the *binary* value, so `Decimal(x)` with
  `ROUND_HALF_UP` is the faithful spelling and `f"{x:.1f}"` is not.
- `surface()` sorts by strength descending with a **stable** sort, then
  dedupes, so equal-strength insights keep metric emission order: burstiness,
  sequence, sentiment_lift, progression. Python's `sorted` is stable; its
  `set` is not ordered, and `uniqueLowercase` returns a JavaScript Set spread
  into an array, which is insertion-ordered — use `dict.fromkeys`.

Three traps that have already been hit, recorded here so they cost nobody a
second session:

- **Python is not JavaScript at the edges.** `\p{…}` has no `re` equivalent,
  `\b` is Unicode here and ASCII there, `str.strip()` and JS `trim()` disagree
  on which characters are whitespace, `round()` is banker's and `Math.round` is
  half-up. `golden/README.md`'s "Porting gotchas" lists the rest; every one of
  them produces a *nearly* correct port.
- **Dates are the worst of it.** Three separate ways `reminder.ts` bites: `\d`
  is ASCII in JavaScript and Unicode in Python, so `{٢d}` becomes a real
  reminder if you write `\d+`; `setUTCMonth` *overflows* where
  `relativedelta` *clamps*, so Jan 31 + 1 month is March, not February 28th;
  and `Date.UTC` reads years 0–99 as 1900–1999, which is how the source
  silently rejects a four-digit year below 100. All three produce a port that
  passes a hundred fixtures and fails four. See `reminder.py`'s docstring.
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
branch `pivot`, commit `105181c`. Regenerate the corpus there with `pnpm golden`
and re-copy. The determinism contract in `golden/README.md` is what makes that
reproducible: `TZ=UTC`, `LC_ALL=en_US.UTF-8`, the clock frozen to
`2026-08-14T12:00:00.000Z`, a mulberry32 PRNG seeded `0x5EED`, and — for the UI
half — virtual time at exactly 16ms a frame.

When re-copying, copy `corpus/`, `generate.ts`, `generate-ui.ts`, `harness.ts`
and `README.md`, and **leave `verify_golden.py` alone** or re-apply the adapter
wiring described above. New adapters get appended to its UI-behaviour section
rather than replacing the file.
