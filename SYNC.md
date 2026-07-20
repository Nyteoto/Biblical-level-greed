# Backups, and moving to another machine

Your data is four kinds of plain file in `data/`:

| | |
|---|---|
| `domains/*.toml` | your trees — hand-editable |
| `log/YYYY-MM.jsonl` | every check-off, append-only |
| `todos.jsonl` | the checklist, append-only |
| `index.sqlite` | a rebuildable cache — **not** tracked, delete it any time |

The repo is the backup. Commit and push whenever you have done a stretch of
work:

```bash
git add -A && git commit -m "practice" && git push
```

Moving to a new machine is a clone plus `./install-linux.sh`.

## If two machines ever write the same history

Not the normal case any more — this is a single-machine app — but the design
still supports it, and it costs nothing to leave in place.

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
| merged lines are **out of order** | events sort by `ts`, stably — file order stops meaning anything once two machines write the same file |
| merged lines may be **duplicated** | sessions, completions and phases are last-wins; todos are keyed by item id; journal entries dedupe on `(ts, text)` |

Journal entries were the only kind that would visibly double, because they
accumulate instead of resolving. `backend/tests/test_sync.py` pins all of it,
including the case that makes naive dedupe wrong: `session, undo, session`
inside one second is a real double-click whose correct outcome is *checked*, so
identical lines cannot simply be collapsed.

**Domain files are not union-merged.** They are structured TOML and splicing two
versions together produces something that will not parse. Edits there are rare
and small, so a genuine conflict is worth reading by hand.

## Using a data directory elsewhere

To keep the data off the repo drive — a different disk, an encrypted volume:

```bash
pgs --data-dir /mnt/somewhere/pgs-data
```

The index follows it, so nothing stale is left behind in the checkout.

## If anything ever looks wrong

The index is disposable. Delete it and the log replays:

```bash
rm data/index.sqlite
```

The log is the truth; everything else is a projection of it.
