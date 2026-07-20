# Running on both OSes

You dual-boot. There are two ways to keep one history across both, and the first
one is much better if your partition layout allows it.

## Option A — one shared folder (no sync at all)

If both operating systems can reach the same partition, point both installs at
the same data directory and there is nothing to reconcile, ever.

```bash
# Linux
pgs --data-dir /mnt/shared/pgs-data
```
```powershell
# Windows
.\.venv\Scripts\python.exe desktop.py --data-dir D:\pgs-data
```

The `index.sqlite` cache is written inside that folder too, and is rebuilt
automatically whenever it is stale or missing — so it does not matter which OS
wrote it last.

**Dual-boot specifics.** Linux reads and writes NTFS fine (`ntfs3`), so a
Windows data partition works from both sides. The reverse — Windows reading
ext4 — needs third-party drivers and is not worth it. If one of your drives is
NTFS, put the data there and use it from both.

> Do not point a shared folder at a drive that Windows Fast Startup keeps
> hibernated. Fast Startup leaves NTFS volumes in a dirty state and Linux will
> mount them read-only. Turn it off (`powercfg /h off`) if you hit that.

## Option B — a git remote

If there is no shared partition, sync through a **private** repo. Your practice
log and journal entries are in it.

```bash
git remote add origin git@github.com:you/pgs.git
git push -u origin main
```

Then on the other OS: clone it, run that OS's install script, and you have the
same tree and the same history.

### The workflow

Before you start, and after you finish:

```bash
git pull --rebase        # get the other OS's work
# ...use the app...
git add -A && git commit -m "practice" && git push
```

If you forget, nothing breaks — the merge is designed for exactly that.

### Why the merge is safe

`.gitattributes` marks the append-only streams `merge=union`:

```
data/log/*.jsonl   merge=union
data/todos.jsonl   merge=union
```

A log line is an immutable fact. Two machines appending different lines have
not conflicted; they have each recorded something true. Union merge keeps both
sides and never raises a conflict.

That leaves two problems, both handled on read rather than on write:

| problem | handled by |
|---|---|
| merged lines are **out of order** | events sort by `ts`, stably — file order stops being meaningful once two machines write the same file |
| merged lines may be **duplicated** | sessions, completions and phases are last-wins; todos are keyed by item id; journal entries dedupe on `(ts, text)` |

Journal entries were the only kind that would visibly double, because they
accumulate instead of resolving. `backend/tests/test_sync.py` pins all of it,
including the case that makes naive dedupe wrong: `session, undo, session`
inside one second is a real double-click whose correct outcome is *checked*, so
identical lines cannot simply be collapsed.

**Domain files are not union-merged.** They are structured TOML and splicing two
versions together produces something that will not parse. Edits there are rare
and small, so a genuine conflict is worth reading by hand.

### If a merge ever looks wrong

The index is disposable. Delete it and replay:

```bash
rm data/index.sqlite     # or: curl -X POST localhost:PORT/api/admin/reindex
```

The log is the truth; everything else is a projection of it.

## Updating

Both scripts are idempotent — re-running is the update path:

```bash
git pull && ./install-linux.sh
```
```powershell
git pull; powershell -ExecutionPolicy Bypass -File install-windows.ps1
```

## What is and is not in the repo

| in | out |
|---|---|
| `data/domains/*.toml` — your trees | `data/index.sqlite` — rebuildable cache |
| `data/log/*.jsonl` — every check-off | `.venv/`, `node_modules/` |
| `data/todos.jsonl` — the checklist | `frontend/build/` — rebuilt by the installer |
