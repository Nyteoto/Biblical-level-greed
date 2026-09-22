# Working on this repo

**The Portal**: a one-day journal wrapped in a premise. Each day's you is an
*Instance*, numbered by days since a true birth (2026-09-22 is 8193), and the
Portal keeps one Record a day so the next Instance knows what happened. FastAPI
+ SvelteKit, local, single-user — no auth and no multi-user; do not add either.
It runs on both halves of one dual-boot machine, Fedora and Windows, sharing a
single data disk.

It replaced two apps — Trophic's capture journal and a tech tree for deliberate
practice — which were burnt on the `portal` branch. Their code is in git
history; their data is still on the disk and nothing reads it.

`README.md` documents *what the app does*. This file documents *what you must
not break*. Read it before changing anything.

## Never

- **Never read or commit `data/media/**`.** Private user content — their faces,
  photographs and video. Listing filenames is fine; opening them is not. If you
  need a sample, make a scratch file.
- **Never edit, rewrite or delete a sealed Record** (`data/portal/records/*.json`).
  Write-once is the whole promise the Portal makes: what 8193 wrote is what 8194
  reads. There is no route that does it, and a "fix" by hand is exactly the thing
  the premise forbids. A PDF may be re-rendered from its Record at any time; the
  Record itself may not be touched.
- **Never `git restore` / `git checkout` anything under `data/`.** It is live
  state, not source.
- **Never put live data in the repo.** `data/*` is gitignored with no exceptions.
  A Record pushed to a remote is a day published.
- **What the old apps left is gone from the live disk, on the user's word**
  (2026-09-22): `capture/`, `log/`, `domains/`, `index.sqlite`, `todos.jsonl`.
  Their only copy is the backup at `/mnt/data/pgs-backup`, which never deletes.
  Do not "tidy" the backup. `notes/`, `tools/` and `seed/` are still on the
  shared disk; `notes/` is the user's and off limits, and nothing is removed
  without them asking.
- **Never test a destructive path against real data.** Termination deletes media;
  run it against a scratch `PGS_DATA_DIR`. Deleting against live data has
  already cost an unrecoverable photo.
- **Never weaken `backup.sh`'s refusals.** It exits rather than writing when the
  destination resolves to the same device as `data/`, and it has no `--delete`.
  The first catches an unmounted backup disk; the second stops a local mistake
  being mirrored over the only other copy.

## The shape of the thing

```
selfie ─▶ today.json (the day in progress; the only file meant to be lost)
              │  commit, inside 19:00–23:00, in one sitting
              ▼
      records/8193.json  ── write-once, the truth ──▶  pdf/8193.pdf (derived)
```

### Backend modules (`backend/app/`)

| module | owns |
|---|---|
| `config.py` | every path and tunable: `BIRTH`, the window, `SITTING_GRACE_SECONDS`, `MAX_MEDIA`. |
| `timeutil.py` | **the only** place doing timezone math. Instance numbers, the window, `PGS_FAKE_NOW`. |
| `day.py` | one day's lifecycle: unborn → awake → sitting → sealed \| terminated. Settling, the sitting, the rules. |
| `records.py` | the sealed Records. Read, latest, and a `write` that refuses to replace. |
| `pdf.py` | renders a Record to an A4 print with ReportLab. `python -m backend.app.pdf --all`. |
| `remarks.py` + `remarks.toml` | what the Portal says on waking: pools keyed by conditions read off the Records. |
| `media.py` | the blob store. Originals byte for byte, plus a derived display copy. |
| `storage.py` `backup.py` `version.py` | the machine: disk use, the backup scripts, the API number. |
| `main.py` | thin FastAPI layer: settle, call `day`/`records`, return state. |

`desktop.py` at the repo root is the packaged entrypoint — a free loopback port,
uvicorn, and a WebKitGTK window. Nothing imports it.

Every module opens with a docstring explaining *why it is shaped that way*. Read
it before editing that module. **Keep that convention** in anything you add.

### Frontend

SvelteKit 5 (runes; `.svelte.ts` stores), Tailwind 4. `/` is the Portal — the
whole flow is `src/routes/+page.svelte` over `src/lib/portal/`. `/settings` is
the machine. Built to `frontend/build`, which is **gitignored** — rebuild
(`npm run build`) before claiming a UI change works.

## Invariants worth stating

- **Every rule is a rule about the clock, and every decision takes `now` as an
  argument.** `day.py` never reads the time; `main.py` passes
  `timeutil.now()` in, and tests pass the instant they mean. Keep it that way —
  a test that reads the real clock passes at noon and fails at 23:30.
- **Settling is lazy and is the only way a day ends without a commit.** No timer
  thread. Every Portal request settles first: a rolled-over date, a passed
  23:00, or a sitting silent past the grace terminates the day. Same answer
  whenever it is asked, which is what lets it run unattended on both OSes.
- **One sitting is enforced by construction, not by rule.** The draft text lives
  only in page memory (`sitting.svelte.ts`) — never `localStorage`, never the
  server — so a reload has nothing to resume from. The token is page memory too.
  `pagehide` sends a beacon that ends the day; the heartbeat catches the
  departures a page cannot report. **Do not add draft autosave anywhere**; it
  would be a way around the one rule the premise rests on.
- **Media are the one part of the draft the server holds**, because a clip can be
  gigabytes and a commit that waited on it could miss the window. They are
  attached to the sitting and deleted with it.
- **A terminated day leaves a tombstone until midnight, and then nothing.** The
  tombstone stops a second sitting on the same day; everything the day held is
  already gone. The only lasting trace of a failed day is the gap in the
  numbering, and `remarks` reads the failures off that gap. Do not start
  recording failures anywhere — "treat it as though it never happened" is the
  spec.
- **JSON is the truth; the PDF is a print.** The PDF was going to be the only
  copy and that was reversed on purpose: a print cannot be reprinted at a better
  scale. A PDF that fails to render never fails the commit.
- **Prints embed originals.** Photographs go into the PDF at the resolution they
  were taken, never from the 2048px display copy. A video prints as its poster
  frame, which the browser makes at 1920px — no ffmpeg on the server, because it
  would have to exist on both OSes.
- **A Record is drawn as a record sheet, and the screen and the paper are one
  form.** `Sheet.svelte` is the form, from the design canvas *Folders and the
  log* → *One day, as a record sheet*. Its elements are there to say the Record
  is filed: sheets underneath, binder holes, a ruled grid of labelled boxes, a
  numbered register, plates on corner mounts, "carried forward" for the wish,
  and the **sealed** stamp. The template and the read-back Record are the same
  component with inputs or ink in the boxes; `pdf.py` draws the same form on
  paper. Change one and you change the others. The tally row holds facts about
  *this* sheet only, never totals across sheets.
- **The print is duplex and bound, so its pages are mirrored.** Odd pages
  (fronts) carry the binder margin and holes on the left, even pages (backs) on
  the right — two page templates in `pdf.py` that alternate. A `--book` pads
  with a blank back so every Record starts on a front; two days must never
  share a sheet. Anything drawn asymmetrically on the page has to know which
  side it is on.
- **The server's rules are the authority; `rules.ts` is a mirror.** The
  checklist shrinks as you type, but `day.missing` decides. Keep the two lists
  saying the same thing in the same words.
- **Every line on `/` is the Portal speaking to an Instance.** The copy is part
  of the mechanism. No "you haven't journaled today", no streaks, no nudges.
  `/settings` is outside the fiction and says so plainly.
- **A thing is labelled once, in the most legible place.** On the screen and on
  the print: the day is the heading's label, "Record" names the body, nothing
  says either twice.
- **No hue, one accent, one exception.** A cool slate ground and a neutral ramp;
  **white is the accent and it means *the current thing*** — selection is
  inversion. The single exception is the refusal red, which terminated days and
  refusals wear. The print is ink on paper with the same structure.
- **No filters over the app, ever — a measurement, not a taste.** A
  `feDisplacementMap` once cost 23ms of every frame while typing. Animate
  transform and opacity, which are composited, and nothing else.
- **The ground is painted on `[data-shell-header]`, not on `html` or `body`.**
  WebKitGTK — the engine `desktop.py` ships — drops the canvas background from
  an offscreen snapshot.
- **The shell owns the viewport; the screen scrolls inside itself.**
  `+layout.svelte` is `h-dvh overflow-hidden`; a screen is `min-h-0 flex-1` and
  never `h-dvh`. `justify-center` on a scrolling column overflows both ends — use
  `my-auto` on the child.
- **During a sitting there is no way off the page.** The Settings link is hidden
  while a token is held, because leaving is what ends the day.
- **Dual boot splits along one line: data crosses by disk, code crosses by
  git.** Both OSes open the same `data/` on the shared exFAT disk. The code is
  two clones meeting at the remote; `frontend/build` is stale on the other side
  until rebuilt there. Do not add a sync mechanism to either half.
- **Two Tailscale devices means two home-screen icons, and that is the
  decision.** See MOBILE.md. Do not try to collapse them.
- **There are two backup scripts and there must be.** `backup.sh` and
  `backup.ps1` restate the same two refusals rather than sharing them.

## Deliberately absent

Notifications, multi-user, auth, editing a sealed Record, browsing the archive
past yesterday's Record, and anything adaptive. The mood is stored and drawn,
**never interpreted** — no averages, no trends, no "you have felt low for three
days". The remarks may quote yesterday's mood; they may not keep score.

## Commands

```bash
.venv/bin/python -m pytest backend/tests -q     # run them
./run.sh                                        # build frontend + serve on 8787
uvicorn backend.app.main:app --reload --port 8787   # dev backend
cd frontend && npm run dev                      # dev frontend
cd frontend && npm run check                    # svelte-check
python -m backend.app.pdf --all                 # reprint every Record

# walk the evening at noon, against scratch data only
PGS_DATA_DIR=/tmp/portal-scratch PGS_FAKE_NOW=2026-09-22T19:05 ./run.sh
```

The Windows side has its own clone and its own venv. `install-windows.ps1`,
`backup.ps1` and `install-windows-tasks.ps1` only ever execute over there, so
neither the suite nor you can exercise them. Change them only with a reason you
could defend without running them — and keep them UTF-8 **with BOM** and CRLF.

**Run them with `powershell`, never `pwsh`.** On Windows that word means 5.1,
which is what the scheduled task runs and what `backup.py` shells out to. 5.1
reads a BOM-less `.ps1` as cp1252, will not pass an embedded double quote to a
native command, and wraps a native command's stderr in ErrorRecords once merged.
A script that passes under pwsh has not been tested.

Tests point at a throwaway data dir via `conftest.py` before the app imports —
they never touch `data/`. Keep it that way.

## Conventions

- **Commit messages read as prose, in the imperative, describing intent rather
  than diff**: "Price the act of starting, and compile in the domain underneath
  it". Match that voice.
- Comments explain *why*, and are worth writing when the reasoning would not
  survive being re-derived. The existing density is the target.
