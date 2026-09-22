# Backups, and moving to another machine

**The repo holds the app. This machine holds everything you have done with it.**

That is the whole of this document. Nothing under `data/` is version-controlled:

| | |
|---|---|
| `portal/records/*.json` | every sealed Record — write-once · **not tracked** |
| `portal/pdf/*.pdf` | their prints, rendered from them · **not tracked**, reprintable |
| `portal/today.json` | the day in progress, deleted when it ends · **not tracked** |
| `media/` | selfies, photographs and video, at full quality · **not tracked** |
| `capture/`, `log/`, `domains/`, `index.sqlite`, `todos.jsonl` | what the apps before the Portal left. Read by nothing, deleted by nothing · **not tracked** |

So `git add -A && git commit && git push` pushes code and nothing else. A
Record pushed to a remote would be a day published.

## The repo is not a backup

It never was one. **Everything in the
table above marked "not tracked" exists in exactly one copy on this disk.**

So there is a backup, and it runs on a timer:

```bash
./backup.sh                     # by hand, any time, safe to repeat
systemctl --user list-timers pgs-backup.timer
cat /mnt/data/pgs-backup/.last-backup
```

```powershell
.\backup.ps1                                    # the same, on the other side
Get-ScheduledTaskInfo 'PGS Backup'
Get-Content C:\pgs-backup\.last-backup
```

`backup.ps1` is a second script rather than a portable one: `rsync`, `df
--output=source` and `date -Iseconds` have no Windows equivalent worth
shimming, and the two refusals below are easier to trust stated twice than
found inside a platform conditional. It carries both of them — robocopy with
no `/MIR`, and a volume comparison before it writes a byte.

The Windows daily run is a Scheduled Task with `StartWhenAvailable`, the
counterpart of the timer's `Persistent=true`. On a dual-boot machine that
setting is doing more work than it does on either side alone: most days one of
the two operating systems was not running when its backup was due.

`pgs-backup.timer` runs `backup.sh` once a day, `Persistent=true` so a machine
that was asleep when it was due catches up on the next boot rather than silently
skipping. It copies everything except `index.sqlite`, which replays from the log
and is the only thing you may lose without consequence. The exclude has no
leading slash, so it covers `capture/index.sqlite` too — both apps' caches are
skipped and both apps' logs are copied.

Two refusals are built in, because a backup that quietly does nothing is worse
than no backup at all:

- **It will not write to the same device as your data.** If `/mnt/data` is not
  mounted it is just an empty directory on the system disk, and a copy there
  protects nothing. The script exits non-zero and says so.
- **It never deletes.** No `--delete`, so a truncated log, a tree lost to a
  misclick or a notes folder wiped by a bad command is *not* mirrored into the
  backup. The destination only grows, which for a few hundred kilobytes a year
  is a trade worth making.

**Where things actually live now.** The data moved off the system disk onto the
external SSD, so both of this machine's operating systems can reach one copy of
it:

| | Linux | Windows |
|---|---|---|
| data | `/mnt/ssd/pgs-data` — `sdb1`, exFAT | `F:\pgs-data` — the same disk, the same files |
| backup | `/mnt/data/pgs-backup` — `sda2`, ext4 | `C:\pgs-backup` — the internal NTFS disk |
| checkout | `~/pekka/dev/…` — btrfs | its own clone, on `C:` |

exFAT for the data disk is the whole reason either side can read it: it is the
one filesystem both operating systems mount without a third-party driver. The
cost is that it carries no permissions and no symlinks, which is why only
`data/` lives there and never the checkout.

**`F:` is a letter, not the disk.** Windows assigns it and can reassign it; the
disk is labelled `Extreme SSD` with serial `0663-9718`, which is what Linux
calls its UUID and what Windows shows for the same volume. Identify it by the
serial and never by position:

```powershell
Get-Volume | Where-Object FileSystemLabel -eq 'Extreme SSD'
```

If the letter ever moves, it appears in this file, `README.md`,
`install-windows-tasks.ps1`'s `-DataDir` default and the installer's closing
lines. A wrong letter is not silent: `config.check_data_dir` refuses to start
when `PGS_DATA_DIR` names a directory holding none of `portal/`, `media/` or
what came before them, so the failure is a refusal rather than a second empty history. Do not
create the directory to make that refusal go away.

**The two backups do not meet, and do not need to.** `/mnt/data` is ext4, which
Windows cannot read, so the Windows side writes its own copy to the internal
disk instead. Both read the same shared data directory and neither ever
deletes, so these are two complete copies of one source rather than two halves
of anything. More copies is the point.

Both are `fstab` mounts, deliberately, and not the desktop's `/run/media`
auto-mounts: those only exist while somebody is logged in, and a backup timer
that depends on a login is a backup timer that does not run. This one did not,
for over a week — see below. Both entries carry `nofail`, so an absent disk
cannot stop the machine booting, which matters because one of them is meant to
be unplugged.

`pgs.service` and `pgs-backup.service` both carry `PGS_DATA_DIR`, so anything
started by hand needs it too:

```bash
PGS_DATA_DIR=/mnt/ssd/pgs-data ./run.sh
```

The two Scheduled Tasks carry no environment of their own, so on that side
`PGS_DATA_DIR` is set once for the user and both tasks inherit it:

```powershell
[Environment]::SetEnvironmentVariable('PGS_DATA_DIR', 'F:\pgs-data', 'User')
```

Without it the server task serves the checkout's own `data\` — an empty Portal
and none of your Records — and the backup task refuses outright, because
`data\` and `C:\pgs-backup` are then both on `C:` and the same-volume check
fires. The refusal is the safe direction and is how the missing variable
announces itself; a `LastTaskResult` of 1 on `PGS Backup` is worth reading as
this first. Set at *User* scope rather than in the task, so that a shell, the
Start Menu shortcut and both tasks all agree about where the data is.

**The app refuses to start on an unmounted disk.** When a removable drive is
absent its mount point is an ordinary empty directory, and without the check
the app would build a fresh tree inside it and start writing a second, parallel
history — the same trap `backup.sh` refuses for the copy, and worse for the
original. `config.check_data_dir` requires a configured data directory to exist
and to already hold `portal/`, `media/`, or what the apps before the Portal
left. Nothing is
created. `test_data_dir.py` pins it.

The backup disk was originally `sda2` (ext4, label `data`) at `/mnt/data` — a
physically separate device from the NVMe that carries `/home`. That protects
against the system disk failing. It does **not** protect against theft, fire or
the machine being destroyed; for that, copy `/mnt/data/pgs-backup` somewhere
off-site, or run `./backup.sh /run/media/you/ssd` against an external disk when
you plug one in.

Worth knowing what each loss actually costs:

| lost | consequence |
|---|---|
| `portal/records/` | every day that was kept. The next Instance reads the newest of these, and the remarks count the gaps between them. **Unrecoverable.** |
| `media/` | every face and every clip a Record points at. **Unrecoverable**, and the largest thing on the disk by far. |
| `portal/pdf/` | nothing. `python -m backend.app.pdf --all` prints them again from the Records. |
| `portal/today.json` | today's selfie and sitting — which is what a terminated day costs anyway. |

## Dual boot: the data crosses by disk, the code crosses by git

These are two different mechanisms and confusing them is the way to lose work.

**The data needs no sync at all.** Both operating systems open the same folder
on the same exFAT disk, so there is one set of Records and one media library. Nothing is copied between them and nothing can diverge. This is why
the data moved off the system disk in the first place.

**The code is not shared, and does not sync itself.** The Linux checkout is on
btrfs, which Windows cannot read; the Windows one is its own clone with its own
`.venv` and its own `node_modules`, neither of which is portable across
operating systems anyway. They meet only at the remote:

```bash
git push                  # before rebooting out of an OS
git pull                  # after rebooting into the other one
```

Three things follow from that, and all three have teeth:

- **Uncommitted work does not cross.** A dirty working tree is invisible to the
  other side. `git status` before rebooting is the whole discipline.
- **A branch with no upstream does not cross either**, even after `git push` on
  some other branch. `git push -u origin <branch>` once, per branch.
- **`frontend/build` is gitignored, so a pull is never enough.** The UI you are
  served is the last one built *on that machine*. After pulling anything that
  touched the frontend, run the installer again — it is idempotent and rebuilds
  — or `npm run build` by hand. This is the usual explanation for "I pulled and
  it looks the same".

**Only one side can serve the phone at a time**, and they are two different
Tailscale devices with two different names, so there are two home-screen icons.
That is a decision rather than an oversight — see MOBILE.md.

## Moving to a new machine

```bash
git clone <repo> && cd <repo> && ./install-linux.sh
```

The install script creates an empty `data/portal/`. Then bring your own data
across from the backup, before first launch:

```bash
rsync -a /mnt/data/pgs-backup/ data/
```

## Using a data directory elsewhere

To keep the data off the repo drive — a different disk, an encrypted volume:

```bash
pgs --data-dir /mnt/somewhere/pgs-data
```

The directory must already exist and hold something of ours — `portal/` or
`media/` — or the app refuses to start, because an empty directory at a mount
point is what an unmounted disk looks like. `--data-dir` makes `portal/` for
you; that is the difference between asking and assuming.

## If anything ever looks wrong

A Record is a JSON file; open it. The print is derived from it and can be made
again at any time:

```bash
python -m backend.app.pdf --all
```

Never edit or delete a Record by hand. It is the one thing in the system that
promises not to change.
