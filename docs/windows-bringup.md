# Bringing up the Windows half

**Read this before touching anything under a `.ps1`.** It exists because the
Windows side was written on the Linux side, by someone who could not run a line
of it, and the gap between "written" and "working" is the whole of the task
left. Delete this file when the checklist at the bottom is green — it is a
handoff, not documentation, and a stale bring-up guide is worse than none.

Written 2026-08-24, from Fedora, commit `36eebde` on branch `phosphor`.

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
  letter is unknown** — every doc says `E:` as a placeholder and nobody has
  checked. Identify it by serial, not by guessing:

  ```powershell
  Get-Volume | Where-Object FileSystemLabel -eq 'Extreme SSD'
  ```

  If it is not `E:`, fix the letter in SYNC.md, README.md and
  `install-windows-tasks.ps1`'s `-DataDir` default rather than leaving three
  documents lying.

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
  v22.23.1, npm 10.9.8. **Prefer Python 3.13 on Windows.** 3.14 is new enough
  that `pillow-heif` and `pywebview` wheels may not exist for it there, and
  building either from source on Windows is a bad afternoon.

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

## Do this in an order that cannot lose data

The repo's standing rule is **never test a destructive path against real data**,
and it is written in blood: a previous violation cost an unrecoverable
photograph. `backup.ps1` never deletes, but it is unproven, so:

1. **Prove the backup against scratch first.** Make `C:\tmp\src` with a couple
   of junk files and a `index.sqlite`, run
   `.\backup.ps1 -Destination C:\tmp\dst` with `PGS_DATA_DIR=C:\tmp\src`, and
   check three things: the files arrive, `index.sqlite` does **not**, and
   `.last-backup` parses (`[datetime]::Parse((Get-Content C:\tmp\dst\.last-backup))`).
2. **Prove both refusals.** Point source and destination at the same volume and
   confirm it exits non-zero and says so. Delete a file from the destination,
   re-run, and confirm it comes back rather than the destination shrinking —
   that is the missing `/MIR`.
3. **Only then** run it against the real data directory.

For the app itself the net is already in place: `config.check_data_dir` refuses
to start when `PGS_DATA_DIR` is set but the directory holds no log, trees or
capture dir. A wrong drive letter therefore produces a refusal, not a second
empty history. If you see that refusal, the letter is wrong — do not create the
directory to make it go away.

## Done looks like

- [ ] `install-windows.ps1` runs clean and ends with `463 passed`
- [ ] `pgs` opens a real window, rendered by WebView2 — not an unstyled column,
      which is what mshtml gives and means `PYWEBVIEW_GUI` did not take
- [ ] the window shows the user's actual trees and capture history, i.e. it is
      reading the shared disk and not a fresh `data\`
- [ ] a capture written on Windows is visible from Linux after a reboot, with
      no copying step in between
- [ ] `backup.ps1` proven against scratch, both refusals confirmed, then run for
      real once
- [ ] `install-windows-tasks.ps1` registers both tasks; `Get-ScheduledTaskInfo`
      shows the server task running
- [ ] `tailscale serve` configured on this node too — it is per-device, so the
      Linux setup does not carry over
- [ ] the second icon added to the phone, renamed so the two are tellable apart
- [ ] every placeholder `E:` corrected across the docs if the letter differs
- [ ] this file deleted, and anything durable folded into SYNC.md

Commit the fixes as you go, in this repo's voice — prose, imperative, intent
rather than diff. The Linux side pulls them back the same way they arrived.
