# Bringing up the Windows half

**Read this before touching anything under a `.ps1`.** It exists because the
Windows side was written on the Linux side, by someone who could not run a line
of it, and the gap between "written" and "working" is the whole of the task
left. Delete this file when the checklist at the bottom is green — it is a
handoff, not documentation, and a stale bring-up guide is worse than none.

Written 2026-08-24, from Fedora, commit `36eebde` on branch `phosphor`.
**Picked up the same day, on Windows.** Everything below that can be proved
from this side has been; what is left needs the phone, a reboot, or a
Tailscale sign-in, and is ticked off at the bottom. The scripts have met an
interpreter now, and six more bugs came out of it — the reading-only list
further down is no longer the whole of it.

## What is already true

The decision was made and does not need remaking: **two home-screen icons.**
Each OS install is its own Tailscale device with its own MagicDNS name, iOS
binds an icon to an origin, and the alternatives were weighed and lost. See the
"Dual boot: two devices, two icons" section of MOBILE.md, and the three new
invariants in CLAUDE.md. Do not spend effort collapsing them into one.

The data disk needs nothing done to it. Both operating systems open one folder
on one exFAT volume, so there is one log and nothing to reconcile. **Data
crosses by disk; code crosses by git.** Do not add a sync mechanism to either.

Committed and pushed from Linux:

| file | state |
|---|---|
| `install-windows.ps1` | written, **never executed** |
| `backup.ps1` | written, **never executed** |
| `install-windows-tasks.ps1` | written, **never executed** |
| `desktop.py` | WebView2 + Tailscale branches, both smoke-tested on Linux by forcing `sys.platform` |
| `backend/app/backup.py` | picks the script by platform; both argv shapes pinned by tests |
| docs | README, SYNC, MOBILE, CLAUDE all updated |

463 tests pass on Linux. They do not exercise any PowerShell, and cannot.

## Facts you cannot get from that side

- **The shared volume** is labelled `Extreme SSD`, exFAT, serial `0663-9718`
  (Linux calls it UUID `0663-9718`; Windows shows the same digits). It is
  `/mnt/ssd` on Linux and the data is `/mnt/ssd/pgs-data`. **The Windows drive
  letter is `F:`** — checked by serial rather than guessed, and the placeholder
  `E:` that every document carried has been corrected everywhere:

  ```powershell
  Get-Volume | Where-Object FileSystemLabel -eq 'Extreme SSD'
  ```

  It can move. If it ever does, the serial is what identifies the disk, and the
  letter appears in SYNC.md, README.md, `install-windows-tasks.ps1`'s `-DataDir`
  default and the installer's closing lines.

- **That directory already holds a real history** — `capture/`, `domains/`,
  `log/`, `media/`, `notes/`, `seed/`, `tools/`, `todos.jsonl`, `index.sqlite`.
  It is years of the user's practice and photographs, it is not in git, and
  `media/` is off limits to read. This is the thing all the refusals exist to
  protect.

- **Tailscale**, Linux side: node `p`, `p.tail1a906a.ts.net`, `100.67.160.15`,
  with `serve` already proxying `https://p.tail1a906a.ts.net` → `127.0.0.1:8787`.
  The tailnet is `tail1a906a.ts.net`. The Windows node will get its own name;
  that is expected and is the second icon.

- **Toolchain on Linux**, for reference only — the two sides do not share a venv
  or a `node_modules`, and do not need matching versions: Python 3.14.7, Node
  v22.23.1, npm 10.9.8. ~~Prefer Python 3.13 on Windows.~~ **Not needed** —
  checked rather than assumed, and `pillow-heif`, `pywebview` and `Pillow` all
  ship `cp314` wheels for `win_amd64` now. This side runs 3.14.4 and Node 25
  with nothing built from source. The caution was right when it was written and
  cost nothing to disprove:

  ```powershell
  python -m pip download --only-binary=:all: --no-deps -d $env:TEMP pywebview pillow-heif
  ```

## The bugs already found by reading

Four were caught and fixed in `backup.ps1` without ever running it. They are
listed because they name the *class* of thing to look for, and because finding
one already fixed and "fixing" it again is how a working script stops working:

1. `elseif` on its own line after a closing brace — a parse error in
   PowerShell, where a newline ends the statement.
2. `[System.IO.Path]::GetFullPath` resolves against .NET's current directory,
   which `Set-Location` does not change. It anchored the volume check to the
   wrong path.
3. Robocopy is parsed by the C runtime: a path ending in a backslash arrives as
   `"E:\pgs-data\"`, the backslash escapes the quote, and the next argument is
   swallowed. Hence `Unslash`.
4. PowerShell 7.4 turns a native command's nonzero exit into a terminating
   error, and robocopy's exit code **1 means "files were copied"** — the
   success case. Both scripts clear
   `$PSNativeCommandUseErrorActionPreference` for this reason. Do not remove it.

Assume more of the same. Nothing here has met an interpreter.

## The bugs found by running them

Seven, and none of them was findable by reading. The last three share one
lesson and it is the one worth carrying: **run these under `powershell`, not
`pwsh`.** 5.1 is what that word means on a Windows machine, what the scheduled
task runs, what `backup.py` shells out to and what every instruction in this
repo names — and it differs from pwsh 7 in exactly the places these scripts
live.

1. **The frontend did not build at all.** `Banner.svelte` and `banner.svelte.ts`
   differ only in case, and Windows resolves `./banner.svelte` to the component
   rather than the store. The store is now `banner-state.svelte.ts`.
2. **The installer said it had built anyway.** It clears
   `$PSNativeCommandUseErrorActionPreference` so a failing test can be reported
   rather than crash the run, and that is also the setting that would have
   caught npm. Both npm calls read their exit code now.
3. **31 of the 463 tests failed**, all on assumptions rather than on the app:
   an index deleted while a store still held it open (a POSIX behaviour), a
   backup stub written in `sh` and handed to powershell.exe, a tree read as
   cp1252, and a posix path built with `Path` that comes back with backslashes.
4. **The Start Menu shortcut did nothing.** `pythonw.exe` starts with no console
   and Python sets both standard streams to None, so the first `print` in
   `main` raised before a window existed. It only fails when detached, which is
   to say it only fails the way a user launches it.
5. **The logon task would not register.** `-User $env:USERNAME` is refused —
   Task Scheduler wants a qualified name, `PEKKA\PEKKA` here.
6. **Windows PowerShell 5.1 could not parse two of the three scripts.** It reads
   a `.ps1` with no BOM as cp1252, every em-dash becomes three characters ending
   in a curly quote, and PowerShell counts curly quotes as string delimiters.
   `pwsh` never sees it; `powershell.exe` is what the task, the app's backup
   button and the documented install command all run. All three carry a BOM now
   and `.gitattributes` says why.

7. **The installer failed twice under 5.1** having passed cleanly under pwsh.
   5.1 will not pass an embedded double quote to a native command, so the
   Python version probe came back empty and the script announced a Python too
   old to use without naming a version; and it wraps a native command's stderr
   in ErrorRecords once merged into the pipeline, so with `Stop` set the first
   npm warning became a terminating error on a build that had succeeded.

The shape of all seven: the Linux side could not have caught any of them, and
each was invisible until the exact command a user would type was typed, in the
interpreter that user would have.

## Do this in an order that cannot lose data

The repo's standing rule is **never test a destructive path against real data**,
and it is written in blood: a previous violation cost an unrecoverable
photograph. `backup.ps1` never deletes, but it is unproven, so:

1. **Prove the backup against scratch first.** Note that the two scratch paths
   this section first named were both on `C:`, which is step 2's refusal rather
   than step 1's happy path — a scratch run needs two volumes, the same way the
   real one does. What was actually run: a throwaway source on the SSD,
   `F:\pgs-scratch-src`, holding junk files, a nested directory and an
   `index.sqlite` at both levels, copied to `C:\tmp\pgs-scratch-dst`. Checked
   three things: the files arrive, **neither** `index.sqlite` does — `/XF`
   matches by name at every depth — and `.last-backup` parses
   (`[datetime]::Parse((Get-Content C:\tmp\pgs-scratch-dst\.last-backup))`).
   The source is only ever read, so a scratch directory beside the real one is
   safe; delete it afterwards.
2. **Prove both refusals.** Point source and destination at the same volume and
   confirm it exits non-zero and says so — it does, and it declines before
   creating the destination directory at all. Then the missing `/MIR`, which is
   worth proving in both directions: delete a file from the destination and
   confirm the next run brings it back, and delete one from the *source* and
   confirm the destination keeps it. The second is the one that matters.
3. **Only then** run it against the real data directory.

For the app itself the net is already in place: `config.check_data_dir` refuses
to start when `PGS_DATA_DIR` is set but the directory holds no log, trees or
capture dir. A wrong drive letter therefore produces a refusal, not a second
empty history. If you see that refusal, the letter is wrong — do not create the
directory to make it go away.

## Done looks like

- [x] `install-windows.ps1` runs clean and ends with `463 passed`
- [x] `pgs` opens a real window, rendered by WebView2 — not an unstyled column,
      which is what mshtml gives and means `PYWEBVIEW_GUI` did not take.
      Confirmed from the process tree: the app is the parent of the
      `msedgewebview2.exe` group, which mshtml would never produce
- [x] the window shows the user's actual trees and capture history, i.e. it is
      reading the shared disk and not a fresh `data\` — seven trees, the 2026
      shelf, twelve folders and the real contact sheets
- [ ] a capture written on Windows is visible from Linux after a reboot, with
      no copying step in between. **Half proved, half not provable from here:**
      one was written from this side and is on the exFAT disk in
      `capture/log/2026-08.jsonl`, and a separate process replaying that log
      sees it. The reboot is the half only you can do
- [x] `backup.ps1` proven against scratch, both refusals confirmed, then run for
      real once — 2.62 GB, 43 files against the source's 44, both
      `index.sqlite` excluded, stamp written and parsed back
- [x] `install-windows-tasks.ps1` registers both tasks; `Get-ScheduledTaskInfo`
      shows the server task running, and `PGS Backup` has run once for real
      with `LastTaskResult 0`
- [ ] `tailscale serve` configured on this node too — it is per-device, so the
      Linux setup does not carry over. **Tailscale is not installed on this
      side yet**, and signing in is interactive, through the tray app rather
      than the CLI. Nothing else waits on it: the server task already serves
      `127.0.0.1:8787`, which is exactly what `serve` needs to sit in front of
- [ ] the second icon added to the phone, renamed so the two are tellable apart
- [x] every placeholder `E:` corrected across the docs — the letter is `F:`
- [ ] this file deleted, and anything durable folded into SYNC.md. The task
      environment note is folded in already; delete the rest once the three
      boxes above are ticked

Commit the fixes as you go, in this repo's voice — prose, imperative, intent
rather than diff. The Linux side pulls them back the same way they arrived.
