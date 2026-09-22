# Working on this repo

A local, single-user tech tree for deliberate practice, plus **Trophic**, a
syntax-driven capture app being ported in beside it. FastAPI + SvelteKit,
no auth and no multi-user — do not add either. It runs on both halves of one
dual-boot machine, Fedora and Windows, sharing a single data disk.

The two are **sibling apps in one process**, not one app: `backend/app/` and
`backend/capture/`, `/api/…` and `/api/capture/…`, `data/log/` and
`data/capture/log/`. They share a data root, a venv, a test suite and a tab
bar. They share no models, no events and no fold.

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
the colour table and where to fetch the bundle again.

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
- **The journal is two rungs, and `/map` is the top one.** `/map` is the
  **year** and shows no entries at all — which folders exist this year, how big
  each is, when each was busy. `/log?folder=&year=` is the other rung and
  the only one that shows entries: one album, read as a **deck of pages where
  a page is a day**. The source's date ruler is deleted, deliberately: it cost
  the corpus `timeline_draw`'s 22 cases and retired `timeline_interaction`'s
  27, which is a deviation rather than a debt — there is no ruler left for them
  to describe.
  - **A month is a filter, not a rung.** `/folders/[id]/[month]` was a third
    screen with its own copy of the sidebar, the spine, the panels and the
    feed, and the two copies had drifted — a hold worked on one and drew the
    null ring on the other. It is `?month=` on the album now, and a chapter is
    `?chapter=`. One view, cut different ways. Do not give either its own
    screen again.
  - **Travelling is constant-cost; reading is not travelling.** Map's grid,
    the index's month rows, its chapter list and the jump field all land on a
    page directly, so no day is ever more than one gesture away. Turning is
    the *adjacent-day* move and nothing else. This rule used to be spelled
    "scrolling is for reading, never for travelling", and it forbade paging the
    reading view outright — which was right while a page turn was the only way
    to cross a year, and stopped being right once every instrument could land
    on a page. What it was protecting still holds exactly: **anything that
    makes reaching a given day cost a run of turns, or a scroll, is going
    backwards.** Scrolling *inside* a page is reading and is fine.
  - The rules that decide what lands on a page live in `paginate` in `log.ts`,
    not in a component, and `verify:ui`'s local checks hold them to the one
    thing that matters — **a line that is drawn on no page at all** is the
    failure mode here, and it is silent. A heavy day continues onto further
    pages; a page is sized by a tuned line budget rather than by measuring, so
    the answer is the same on every screen and a check can pin it.
    - **The cut is part of that rule, not upstream of it.** `paginate` takes a
      `DeckScope` — the year, a month, or a chapter — and `inScope` beside it
      is what the contact sheet reads, so the deck and the sheet cannot
      disagree about what is in scope. The filter used to sit on the lens,
      *above* `paginate`, which meant the one check that matters began one
      function after the place days could go missing. A day dropped there is
      drawn on no page at all and nothing says so.
  - **A sheet is a fixed surface and `PageDeck` owns it.** Every page is the
    same box — `absolute`, filling the deck, scrolling inside itself — and
    `DayPage` only prints on one. That inversion is what makes the pile
    possible: sheets have to be the same size before their edges can stack, and
    nothing has to be measured for two of them to overlap during a turn. Do not
    give the page its own height back.
  - **The pile behind the page is what is left to read**, capped where sheets
    stop being countable by eye. `stackBehind` in `log.ts` is the reckoning and
    `verify:ui` holds both ends of it — a pile under the last page says there is
    more when there is not. The `n of m` under the deck is not a second copy of
    it: the pile says *there is more*, the counter says *how much*.
  - **One motion, three ways to ask for it.** An edge, a drag and the arrow
    keys all drive the same small state machine, because a drag that finishes
    has to hand over to the animation a press starts. The drag is claimed only
    past 12px *and* off-axis — above `LONG_PRESS_MOVE`, so a hold has already
    cancelled itself, and biased so that reading a long page never turns it.
    Transform and opacity only, and `prefers-reduced-motion` is checked in the
    component, because the blanket rule in `trophic.css` cannot reach a
    transform set from script.
- **The skin is gone, and the measurement that killed it stands.** The green
  phosphor, the ten-layer monitor overlay (scanlines, vignette, grain, sheen,
  bezel, rims), the text bloom and the CRT boot sequence were all deleted
  together, along with the Monitor panel in Settings that tuned them. The app
  was being read through a costume. Do not put any of it back without asking.
  - **No filters over the app, ever, and that is a measurement rather than a
    taste.** The curve was once a real `feDisplacementMap` and it cost **23ms
    of every frame**: 36.4ms while typing against 13.4ms without it. The cost
    is flat in the displacement distance, and `will-change`, a tight filter
    region and `contain: paint` all changed nothing — a filter rasterises its
    subtree on every repaint, and every keystroke is a repaint. That finding
    outlived the effect it was about: animate transform and opacity, which are
    composited, and nothing else.
  - `Lightbox.svelte` still portals itself onto `body`, and the upload bar
    still sits outside `main`. The glass they were escaping is gone; the reason
    that remains is that **a transformed ancestor becomes the containing block
    for anything `fixed` inside it** — and the reading view animates its
    ancestors.
- **A thing is labelled once, in the most legible place.** The album view grew
  three month labels (the header's `AUGUST 2026`, the chapter row's `Aug`, the
  spine's `AUG`) and two year labels (that same header, and the index's
  `2026`). None of them was wrong; together they are noise, and the user does not
  want that anywhere in this app. When a fact is already on screen, the second
  place that states it is the one to delete — pick the space where it reads best
  and strip the rest.
- **The ground is painted on `[data-shell-header]`, not on `html` or `body`.**
  WebKitGTK — the engine `desktop.py` ships — drops the canvas background from
  an offscreen snapshot. Harmless when the ground was near-white; on a dark
  ground the app looks like it failed to load.
- **The shell owns the viewport; every screen scrolls inside itself.**
  `+layout.svelte` is `h-dvh overflow-hidden` and `main` clips — so a page that
  has not said how it scrolls is cut off rather than quietly pushing the
  document past the window. It was `min-h-dvh`, and the arithmetic went wrong
  in a way nobody could see: a screen setting its own `h-dvh` was a full
  viewport *below* the banner, so the app was always taller than the window by
  the height of the strip, and the rail and the banner scrolled away with the
  page. **Do not give a screen `h-dvh` again** — `min-h-0 flex-1` is the
  remainder, and that is the whole of what a lens should ask for.
  - Anything that has to escape the clip is `fixed` and already is: the upload
    bar, the lightbox, `HoldMenu`, `FolderAssignMenu`, the timer takeover. A
    `fixed` box is not clipped by an `overflow: hidden` ancestor — but it *is*
    by a transformed one, which is the note beside the lightbox's portal.
  - `justify-center` on a scrolling column overflows **both** ends, so the top
    of the capture composer was unreachable once a prompt and the syntax row
    were on screen with it. The centred child carries `my-auto` instead, which
    centres while there is room and gives up gracefully when there is not.
- **No hue, one accent, and one exception.** The palette is a cool slate ground
  and a neutral ramp; **white is the accent and it means *the current thing***
  — the open lens, the selected day, a syntax token — and nothing else.
  Selection is inversion, not a tint. Every syntax token is that one value and
  is told apart by its delimiter and its weight; folder colours are real stored
  data and are folded onto the ramp at render time by `toRamp()` (which was
  `phosphorize()`). The single exception is the refusal red, which must never
  be folded in — a refusal that looks like output is not a refusal. The rule
  was never about the green, which is why it survived it.
- **The rail selects the question; the bar selects the subject. Both belong to
  the shell.** `Rail.svelte` is Capture plus four questions — Map (the year),
  Log (a day), Threads (what is open), Record (the folder in figures) — and
  `SubjectBar.svelte` is what they are questions *about*: `{folder, year}` in
  the URL, read by `scope.ts`, surviving every switch. Changing either half
  leaves the other alone, which is what makes them two axes rather than two
  kinds of travel.
  - **Neither half may live on a lens, and that is the lesson.** The subject's
    controls had no home for three steps, so they ended up inside whichever
    lens needed them first — the folder in Map's chip row, the year in Map's
    switcher — and choosing a folder became a *trip to Map* before you could
    read one. Two lenses never said which folder they were showing. The chips
    were also a filter and a door at once, which is why opening a folder took
    two presses on the same control. **If a control changes the scope, it goes
    in the bar.**
  - **The folder list is drawn once**, in `FolderPicker.svelte` under the bar,
    and it carries every power it ever had: hold a row for `FolderPanel`, hold
    or drag a heading for `GroupPanel` and the shelf's order, `+ new folder`.
    It was drawn three times before that — the shelf's cards, Map's chips,
    Record's column — and none of the three was reachable from the other
    lenses.
  - **One shelf, read once**, in `subject.svelte.ts`. Map, the Log and Record
    each fetched their own until the bar made that untenable: the bar edits
    folders and every lens under it reads the result, so a rename has to reach
    the assign menu two screens away. Same shape `banner-state.svelte.ts` uses.
    **The loose tags ride with it**, for the same reason one list down: the
    picker and Record each fetched their own on mount and neither refetched,
    so a tag claimed on Record was still on offer in the picker.
  - **There is no "all folders" album**, so the reading lens genuinely needs a
    folder. It opens the picker rather than redirecting to Map — the app
    deciding you meant to go somewhere else is worse than the app asking.
    - `Opens on: latest` is the one exception, and it lives **on the Log**,
      which is what its own label says ("what the Log opens on"). It was a
      `load` on *Map* that redirected the year away to an album, with `?shelf`
      as the escape hatch — and once the rail owned the lenses nothing set
      `?shelf` any more, so with the setting on, pressing Map never showed you
      the year at all. **A lens must answer the question you pressed.** The
      setting is the reader pre-answering *which folder*, not the app choosing
      a different lens.
  **That is what stops the screens repeating themselves**: each lens shows what
  only it can, so the heatmap lives on Map and the Log has no business
  redrawing the year. A fact that appears on two lenses is a bug in one of
  them; a *control* that appears on two is a control that belongs to the shell.
  - **Map measures and Record edits, and neither does the other's job.**
    Nothing on Map is editable: it says what the year looked like and takes
    you somewhere, and a chip is a filter rather than a thing you own. Every
    power over a folder — make, rename, group, arrange the groups, delete,
    point a loose tag — lives on Record, whose subject *is* the folder. That
    split is what stopped the old shelf, where a card carried five controls
    and a question about the year was answered with a grid of things to press.
    **A folder can only be made on Record**, which is why that list could not
    wait for a later step.
  - **The overview is Record's, and choosing its face is the Log's.** The
    folder's standing description and its picture are the one thing that is not
    a fold over captures, so they sit on the lens whose subject is the folder —
    with Record's own figures rather than the second copy the old card carried.
    The gesture that *picks* the picture stays where the photographs are: a
    hold on one in the reading view. Two lenses, one each, and neither doing
    the other's job.
  - **The Log's index lies down, and the reading lens has no column at all.**
    The months and the chapters of what you are reading are `MonthBand` in the
    header row — the same shape Map draws its chapter band in, because two
    screens drawing the same twelve months should draw them the same way round.
    It was a 218px column that hid itself below 1024px and latched the choice,
    which was most of why the furniture felt unpredictable: four lenses, four
    different left-hand columns, three different widths at which they vanished.
    Lying down there is no rule to get wrong, and the deck runs edge to edge —
    which is the "index collapsed" page the design was liked for.
  - **The chapter band is drawn once, in `ChapterBand.svelte`**, and both
    `MonthBand` and Map draw it. It was written twice and the copies had
    already drifted on the only thing the band says beyond its names: which
    chapter is the current one. `MonthBand` lit the month the deck was cut to;
    Map lit the month containing *today* and never checked that the year on
    screen was this year, so a 2019 album lit its September. The month that
    counts as current is the prop, because it is the one thing that genuinely
    differs between the two lenses.
  - **A lens loads through `lens()` in `lens.svelte.ts`.** Read the scope,
    fetch when the key changes, and not otherwise. All four lenses hand-rolled
    the same `lastKey` latch — Map had it twice over one key string, byte for
    byte — and both ways to get it wrong are silent: a key that changes every
    render refetches on every keystroke, one that never changes never
    refetches. The module also makes the newest ask win, which none of the
    copies did: switching folders twice quickly could land the first answer
    after the second.
- **A chapter is cut by hand, and the cut is its identity.** `split-chapter`
  names a folder and a `YYYY-MM`; the chapter begins there and runs until the
  next cut. **Nothing is chaptered until you say so** — a folder nobody has cut
  has no chapters, and no screen invents a name for one that has no name yet.
  They *were* derived: runs of consecutive months with something in them, named
  from the commonest `\pattern` or `<tag>` inside, which was right often enough
  to be worth doing and wrong often enough to be the irritating part. That
  reading is gone with `name-chapter`, whose own docstring is the argument for
  this one — it could only anchor a name to a month because the thing it named
  had no identity at all.
  - **Cutting and naming are one event**, so a rename is a re-cut of the same
    month and the fold is last-wins on `(folder, month)`. An empty name is a
    chapter cut and not yet named, which is a real state and **not** a
    deletion; `unsplit-chapter` is. The old event conflated the two.
  - **Cuts are a timeline; a year is a window onto it.** They are stored per
    folder, not per album, so a cut made in November is the chapter January
    opens in — clipped to the year on screen, which is why `first_month` and
    `last_month` are clipped and `month` is not.
  - Entries before the first cut belong to **no chapter**, and Record prints
    the number rather than sweeping them into an opening chapter nobody asked
    for. Cutting happens on Record and on the Log's open page; the list and all
    the editing are Record's.
- **Which entries a read is about is a `Scope`, never a `folder_id: str | None`.**
  `index.py` defines three — `Everything`, `Unfiled`, `InFolder(id)` — and
  `AlbumScope` deliberately cannot hold `Everything`, because there is no
  all-folders album. That parameter used to mean four different things
  depending on which function you had called, with three translations of it at
  the wire to keep them apart, and one of those was wrong: a search scoped to
  the pile resolved to `None`, which `search_entries` took for "no filter", so
  it quietly searched the whole archive. None of it was visible from a
  signature. `scope_of` and `album_scope_of` are the only places the wire's
  spelling is read; `UNFILED_ALBUM` is still the word the *log* uses and that
  has not changed.
- **A multi-field folder edit is one call, `store.amend_folder`.** It
  validates the whole patch before appending any of it. The route used to make
  six sequential `store.*` calls, which made it the one write in the app that
  could half-happen — a rename that committed followed by a state that raised
  left the rename in an append-only log behind a 400, and nothing below HTTP
  could see the gesture to test it.
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
  once, reversed once, and the reversal is why the list of what points where is
  readable. **There is no mapping screen any more** — pointing a tag at a
  folder is a fact about the folder, so it happens on Record, under `Unclaimed`
  and in the held panel. `/mapping` is deleted; do not bring it back.
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
- **A thread is a deadline that has been carried forward, and the hop is what
  makes one.** A `{}` whose reply sets the next `{}` — that, and nothing
  looser. A prompt nobody answered is a *reminder* and the banner already has
  it; a reply carrying no date of its own is an answer rather than a date being
  moved. `index.threads` is the whole of the rule and it is a **read**: the
  chain is `reply_to` walked by one recursive CTE, the dates are the reminder
  rows that were already there, and no event kind was added for any of it.
  - **The closing turn is drawn.** A reply with no new date ends the chain and
    is still a turn, because a thread that simply stopped having anything
    pending, with nothing saying why, reads as one you walked away from.
    `closed` is *nothing standing on the newest turn* — no reminder, or one
    dismissed by hand — so telling the app to stop asking closes it too.
  - **The chain is flattened by `ts`, never drawn as a tree.** Answering
    dismisses what it answers, so two replies to one prompt is already an
    unusual shape, and a fork on the spine would be a shape the domain does not
    have.
  - **Threads is the one lens the year does not cut**, and it says so on the
    screen. You answer in February what you asked in November; half a
    conversation is not a smaller answer, it is a wrong one. The folder still
    filters and it matches *any* turn, so a reply tagged elsewhere cannot make
    a thread vanish from the folder you would look in.
  - **Answering stays with the capture bar.** `--reply` answers the oldest
    prompt that has come due, resolved on the server so the client cannot
    disagree with it. A screen offering to answer *this* one would be making a
    promise the write does not keep.
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
  and that number does two jobs.** It is what Map's year grid draws — twelve
  month-columns of thirty-one day-rows, `YearGrid.svelte` over `GET /heat` —
  and, summed over a rolling thirty days, it is the order the shelf comes back
  in. `points()` in `index.py` is the one place the rule is spelled, and
  `test_momentum_agrees_with_the_days_the_heatmap_draws` is what stops the two
  readings drifting: the order of the shelf has to stay explainable by
  pointing at cells. An entry counts the same whether it is a word or a
  paragraph, for the reason nothing else here measures length either.
  - **The cap is the light, not the count.** Ten points is where the ramp tops
    out and a day past it is simply lit. It keeps counting — in the readout
    and in the sum — because a ceiling that also discarded what it clipped
    would make the number you can read disagree with the order you can see.
    `PEAK` lives in `YearGrid.svelte` because it is a drawing decision; nothing
    on the wire is capped.
  - **The ramp stops one rung below white, and that is not a taste.** White
    means *the current thing* — today's ring, the pressed cell — so a heavy
    day cannot also be white without the grid saying two things with one
    colour. The floor matters as much: a day that happened and holds nothing
    is the ramp's own bottom, and drawing it any brighter makes an empty year
    and a busy one the same picture. A day still ahead is drawn *darker* than
    that — an October you have not reached and an October you did nothing in
    are different facts, and only one of them is about you.
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
  lines are a shape this log has to survive on read. Record is the one screen
  that reads and writes that order now — the reading lens used to as well, and
  the two agreeing about it was a thing that had to be maintained rather than a
  thing that was true.

## Deliberately absent

Notifications, multi-user, auth, log editing, and anything adaptive. Metric
readings are stored and drawn, **never interpreted**. These are refusals, not
gaps — do not helpfully add them. Per-node cadence is the one acknowledged gap.

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
.venv/bin/python -m pytest backend/tests -q     # 540 tests, ~3s. Run them.
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
