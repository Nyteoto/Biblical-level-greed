# Backups, and moving to another machine

**The repo holds the app. This machine holds everything you have done with it.**

That is the whole of this document. Nothing under `data/` is version-controlled
except one read-only directory of reference trees:

| | |
|---|---|
| `seed/*.toml` | the six researched curricula, as shipped · **tracked** |
| `domains/*.toml` | your trees, as you have edited them · **not tracked** |
| `log/YYYY-MM.jsonl` | every check-off, append-only · **not tracked** |
| `todos.jsonl` | the old checklist, append-only, no longer written · **not tracked** |
| `media/` | your photographs and video, kept at full quality · **not tracked** |
| `index.sqlite` | a rebuildable cache · **not tracked**, delete it any time |
| `capture/log/YYYY-MM.jsonl` | every line Trophic captured, append-only · **not tracked** |
| `capture/index.sqlite` | ditto, rebuildable · **not tracked** |

So `git add -A && git commit && git push` now pushes code and nothing else. You
never need to commit in order to practise, and a season switch is not a diff.

## The repo is not a backup

It never was a complete one — media was always out — but it used to
carry your trees and your history, and now it does not. **Everything in the
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

Without it the server task serves the checkout's own `data\` — the six seeded
trees and none of your history — and the backup task refuses outright, because
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
and to already hold a log, some trees or a capture directory. Nothing is
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
| `log/` | every session, completion and paid unlock. XP, level and streak are a fold over this file and are stored nowhere else. **Unrecoverable.** |
| `domains/` | your trees. Re-seedable from `data/seed/`, but any edit you made since is gone. |
| `media/` | your photographs and video. **Unrecoverable**, and now the largest thing on the disk by far. |
| `todos.jsonl` | the old checklist's history. Still folded into XP, so losing it lowers your lifetime total. |
| `capture/log/` | every thought you ever captured in Trophic. The tags, times and patterns are derived from those lines, so they go too. **Unrecoverable.** |
| `index.sqlite`, `capture/index.sqlite` | nothing. They rebuild on next start. |

## Dual boot: the data crosses by disk, the code crosses by git

These are two different mechanisms and confusing them is the way to lose work.

**The data needs no sync at all.** Both operating systems open the same folder
on the same exFAT disk, so there is one log, one set of trees, one media
library. Nothing is copied between them and nothing can diverge. This is why
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

The install script creates `data/` and copies `data/seed/*.toml` into
`data/domains/` — **once, only into an empty directory.** It is not a sync: a
tree you deleted in the UI stays deleted, and a tree you edited is never
reverted by re-running the script.

Then bring your own data across from the backup:

```bash
rsync -a /mnt/data/pgs-backup/ data/
```

Do that *before* first launch if you want your history intact, and let it
overwrite the freshly seeded trees.

## `data/seed/` is reference, not storage

The six trees in there are the researched curricula with their estimates, gates
and entry material — 107 nodes that took a real research pass to produce. They
are checked by `backend/tests/test_shipped_data.py`, which exists because a
stale server process once round-tripped `chinese.toml` through pre-rename code
and silently flattened all twelve estimates to 1.

**Do not park a live tree in there.** It is version-controlled, so anything you
copy in goes to the remote — which is exactly what taking `data/` out of git was
meant to stop. A test asserts the directory holds those six files and nothing
else, so a stray copy fails the suite rather than reaching a push.

## Using a data directory elsewhere

To keep the data off the repo drive — a different disk, an encrypted volume:

```bash
pgs --data-dir /mnt/somewhere/pgs-data
```

The index follows it, so nothing stale is left behind in the checkout.

## Duplicated or out-of-order log lines

The append-only streams used to be tracked with `merge=union` in
`.gitattributes`, so two machines appending different lines merged without a
conflict. That is gone with the tracking.

The read-side tolerance it relied on is still there, and still worth having —
duplicate and out-of-order lines can arrive from a restored backup or an
interrupted write, not only from a merge:

| problem | handled by |
|---|---|
| lines **out of order** | events sort by `ts`, stably |
| lines **duplicated** | sessions, completions and phases are last-wins; todos are keyed by item id |

`backend/tests/test_sync.py` pins it, including the case that makes naive dedupe
wrong: `session, undo, session` inside one second is a real double-click whose
correct outcome is *checked*, so identical lines cannot simply be collapsed.

## If anything ever looks wrong

The index is disposable. Delete it and the log replays:

```bash
rm data/index.sqlite
```

The log is the truth; everything else is a projection of it.
