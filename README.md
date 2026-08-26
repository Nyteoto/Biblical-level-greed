# Trophic

A syntax-driven capture app, on one dual-boot machine, with one data disk.

A capture bar at `/` and a journal of what it caught. You type a line; the
sigils in it file it, mark it, schedule it or turn it into a checkbox. Nothing
is edited afterwards — the log is append-only, and every folder, tag, time and
checkbox you see is derived from it on read. It is documented at length in
[TROPHIC.md](TROPHIC.md).

This repo also held a tech tree for deliberate practice, as a sibling app in
the same process. **It was removed on 2026-08-27** — screens, API, trees, XP,
and the six researched curricula — and it is not coming back. Anything you find
elsewhere describing a board, a node, a tier or a season is stale.

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

Tests: `.venv/bin/python -m pytest backend/tests -q` — 243 tests.
On Windows, `.venv\Scripts\python.exe -m pytest backend\tests -q`.

Dev: `uvicorn backend.app.main:app --reload --port 8787` + `cd frontend && npm run dev`.
`./run.sh` builds the frontend and serves it from the same port as the API.

Sample data, for looking at a screen without opening your own log:
`python scripts/fixture.py` → `data.fixture/`, then `pgs --data-dir data.fixture`.

- [TROPHIC.md](TROPHIC.md) — the capture app, the port, and its corpus
- [MOBILE.md](MOBILE.md) — iPad/iPhone over Tailscale
- [SYNC.md](SYNC.md) — backups, dual boot, moving machines

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
`data/todos.jsonl` are left on disk untouched and nothing reads either one any
more — `todos.jsonl` was still folded into XP until the tech tree went, and now
has no reader at all. Both are yours to delete whenever you like; the app has
no opinion and will not do it for you.

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

The machine, under `/api` — the installation rather than anything you wrote:

| | |
|---|---|
| GET | `/health`, `/version`, `/storage`, `/backup` |
| POST | `/backup`, `/restart` |
| media | POST `/media?name=` · GET `/media/{path}` (Range/206, so video seeks) |

Everything else the app serves is the SPA. An unmatched `/api/…` path returns
404 rather than the app shell, so a mistyped endpoint fails loudly instead of
reporting success and doing nothing.

## Data

```
data/
  media/YYYY-MM/     photos and video at full quality, private
                     <name>.<ext> is the original; <name>.view.jpg is a display copy
  capture/
    log/YYYY-MM.jsonl  append-only: captures, ticks, filings, folders,
                       chapters, groups, lifted tags, dismissals
    index.sqlite       rebuildable cache — delete it any time
```

**Nothing under `data/` is version-controlled.** The repo is the app;
everything in that tree is what you have written with it, and lives in one copy
on your disk until you copy it somewhere. See [SYNC.md](SYNC.md) for what
losing each file actually costs.

The log is not a record of clicks — it is where the app's state lives. Folders,
times, patterns, places, the cleaned text and the todo lines are all derived on
replay and none of them is in the log, so improving the parser improves every
entry you have ever written. Ticking a checkbox appends a `check`; it edits
nothing, and unticking appends an `uncheck` rather than removing the first.

Every event carries a `day` precomputed in the configured zone. Events sort by
timestamp, stably, so duplicated or out-of-order lines resolve identically
however they arrived.

| env | |
|---|---|
| `PGS_DATA_DIR` | the data root. Refuses to start if it is set and not mounted. |
| `PGS_TZ_OFFSET_HOURS` | the day boundary. Default `7`. |
| `PGS_CAPTURE_DATE_LOCALE` | which way `{03/04/26}` reads: `row` (default) or `us`. |
| `PGS_CAPTURE_INDEX_PATH` | the cache, if it belongs elsewhere. |
| `PGS_SERVICE` | the unit `POST /api/restart` restarts. Default `pgs.service`. |

## Deliberately absent

Timers, minute tracking, push notifications, multi-user, auth, editing the log,
and anything adaptive. Tag bars and the sentiment chart are stored and drawn,
never interpreted.

Not built: the codex and thinking-pond screens and the insight engine behind
them, `--draw`, and onboarding. Encryption is refused rather than pending.

Removed, and not coming back: the markdown notes system, the PGS checklist, and
the tech tree.
