# Portal

You live for one day. Each day's you is an **Instance**, numbered by the days
since a true birth — 2026-09-22 is Instance 8193. The **Portal** is the
adjutant that keeps the day's memory so the next Instance knows what happened
yesterday and carries on.

It is one screen, one day, one template, on one dual-boot machine sharing one
data disk. No auth, no multi-user.

## The day

1. **Open the app.** The Portal asks for a selfie, reflects it back —
   *Greetings, Instance 8193* — and says something dry about the state of
   things (`backend/app/remarks.toml`).
2. **OK.** Three instructions: read the latest Record, decide what to do,
   write your Record. Miss the deadline and the day is terminated.
3. **Read {previous}'s Record.** The last one sealed, read-only. Video plays.
4. **Done.** Today's template — locked until the window opens.

**The window is 19:00–23:00 (GMT+7).** Inside it the Instance may *begin a
sitting*, and the Record has to be written in that one sitting: leaving the
page, reloading it, or going silent past the grace (5 minutes) ends the day.

**Committable** means every text field holds at least one letter or digit, a
mood from 1 to 10 is chosen, and there is at least one picture — the selfie
counts. The template:

- the date, the instance number and the selfie — the Portal's, not written;
- up to four photos or clips, each with an optional note under it;
- the Record itself;
- *What do you want 8194 to do?*;
- a signature, which starts as the instance number;
- *On a scale of 1 to 10, how do you feel?*

**Commit** seals it, and a sealed Record never changes again. **Failing**
deletes everything the day held — the selfie, every clip — and the next
Instance keeps reading the last Record that was sealed. The only trace a failed
day leaves is a gap in the numbering, which is how the Portal knows how many
Instances did not make it.

## Install

```bash
./install-linux.sh
pgs                                # native window, data in ./data
pgs --data-dir /mnt/other/pgs      # data elsewhere
pgs --browser                      # no window
pgs --headless --host tailscale    # serve only; see MOBILE.md
```

On Windows, from its own clone:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
pgs --data-dir F:\pgs-data        # the disk shared with Linux; see SYNC.md
powershell -ExecutionPolicy Bypass -File .\install-windows-tasks.ps1   # backups
```

`frontend/build` is gitignored, so a pull that changed the UI serves the old
one until the build step runs.

Tests: `.venv/bin/python -m pytest backend/tests -q`.
Dev: `uvicorn backend.app.main:app --reload --port 8787` + `cd frontend && npm run dev`.

**Walking the evening at noon.** The window only opens at night, so the clock
can be pinned — always against a scratch data directory:

```bash
PGS_DATA_DIR=/tmp/portal-scratch PGS_FAKE_NOW=2026-09-22T19:05 ./run.sh
```

- [MOBILE.md](MOBILE.md) — iPad/iPhone over Tailscale
- [SYNC.md](SYNC.md) — backups, dual boot, moving machines

## Data

```
data/
  portal/
    records/8193.json   a sealed Record — write-once, the truth
    pdf/8193.pdf        its print, rendered from it; reproducible
    today.json          the day in progress; deleted when it seals or ends
  media/YYYY-MM/        selfies, photos and clips at full quality, private
                        <name>.<ext> is the original; <name>.view.jpg a display copy
```

Nothing under `data/` is in git. **A Record is JSON and the PDF is a print of
it**, so the whole archive can be reprinted when the layout or the scale
changes:

```bash
python -m backend.app.pdf --all
```

Prints are A4 unless `PGS_PRINT_PAGE` says otherwise, set in Noto Sans Mono (vendored, OFL), with every photograph
embedded from the original at the resolution it was taken. A clip prints as its
poster frame and its filename.

What the apps before the Portal left — `data/capture/`, `data/log/`,
`data/domains/`, `index.sqlite` — stays on the disk untouched. Nothing reads it.

| env | |
|---|---|
| `PGS_DATA_DIR` | the data root. Refuses to start if it is set and not mounted. |
| `PGS_TZ_OFFSET_HOURS` | the day boundary. Default `7`. |
| `PGS_SITTING_GRACE` | seconds a sitting may go unheard. Default `300`. |
| `PGS_FAKE_NOW` | pin the clock to an ISO instant. For scratch data only. |
| `PGS_PRINT_PAGE` | `A4` (default) or `LETTER`. Reprint with `--all` after changing it. |
| `PGS_SERVICE` | the unit `POST /api/restart` restarts. Default `pgs.service`. |

## API

| route | |
|---|---|
| `GET /api/portal` | the day: instance, phase, window, remark, previous, failed |
| `POST /api/media?name=` | store a file, byte for byte. Claims nothing on its own |
| `POST /api/portal/selfie` | wake: attach the stored selfie |
| `GET /api/portal/latest` | the newest Record sealed before today |
| `POST /api/portal/sitting` | open the day's one sitting; returns its token |
| `POST /api/portal/beat` | the heartbeat |
| `POST /api/portal/leave` | the page is going (a `sendBeacon`) — ends the day |
| `POST /api/portal/media` · `/media/detach` | attach or drop a photo or clip |
| `POST /api/portal/commit` | seal the Record, then print it |
| `GET /api/portal/pdf/{n}` | the print |

## Deliberately absent

Notifications, multi-user, auth, editing a sealed Record, browsing the archive
past yesterday, and anything adaptive. The mood is stored and drawn, never
interpreted.
