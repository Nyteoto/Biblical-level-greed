# Backups, and moving to another machine

**The repo holds the app. This machine holds everything you have done with it.**

That is the whole of this document. Nothing under `data/` is version-controlled
except one read-only directory of reference trees:

| | |
|---|---|
| `seed/*.toml` | the six researched curricula, as shipped · **tracked** |
| `domains/*.toml` | your trees, as you have edited them · **not tracked** |
| `log/YYYY-MM.jsonl` | every check-off, append-only · **not tracked** |
| `todos.jsonl` | the checklist, append-only · **not tracked** |
| `notes/*/*.md` | your writing · **not tracked** |
| `media/` | your photographs · **not tracked** |
| `index.sqlite` | a rebuildable cache · **not tracked**, delete it any time |

So `git add -A && git commit && git push` now pushes code and nothing else. You
never need to commit in order to practise, and a season switch is not a diff.

## The repo is not a backup

It never was a complete one — notes and media were always out — but it used to
carry your trees and your history, and now it does not. **Everything in the
table above marked "not tracked" exists in exactly one copy on this disk.**

If it matters, copy it. All of it is ordinary files:

```bash
rsync -a data/ /mnt/backup/pgs/ --exclude index.sqlite
```

That one line covers trees, log, checklist, notes and photographs. The index is
the only thing you may lose without consequence — it replays from the log.

Worth knowing what each loss actually costs:

| lost | consequence |
|---|---|
| `log/` | every session, completion and paid unlock. XP, level and streak are a fold over this file and are stored nowhere else. **Unrecoverable.** |
| `domains/` | your trees. Re-seedable from `data/seed/`, but any edit you made since is gone. |
| `notes/`, `media/` | your writing and your photographs. **Unrecoverable.** |
| `todos.jsonl` | the checklist and its history. |
| `index.sqlite` | nothing. It rebuilds on next start. |

## Moving to a new machine

```bash
git clone <repo> && cd <repo> && ./install-linux.sh
```

The install script creates `data/` and copies `data/seed/*.toml` into
`data/domains/` — **once, only into an empty directory.** It is not a sync: a
tree you deleted in the UI stays deleted, and a tree you edited is never
reverted by re-running the script.

Then bring your own data across by hand, from wherever you copied it:

```bash
rsync -a /mnt/backup/pgs/ data/
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
