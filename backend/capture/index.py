"""SQLite projection of the capture log. Delete the file at any time —
`rebuild()` replays the log and reproduces it exactly.

Everything in the `entries` table except `id`, `ts`, `day` and `raw_text` is
computed here by running the parser: `clean_text`, the three capture lists and
the todo line indices are a pure function of `raw_text`, and `todo_done` is a
last-wins fold over the check/uncheck events. That is the whole reason the
Postgres original's `text[]` columns do not survive the port — they were an
index-speed denormalisation of data the raw line already contains, and keeping
them would mean a parser change could only ever apply to entries captured
after it. Here a parser change re-derives all of history on the next rebuild.

Folders and their tags
----------------------
`folders`, `folder_tags` and `entry_folders` are folds over the folder events,
and they are the app's *registry* — the one part of this file that is not
derived from entry text. They are still not stored anywhere but the log:
delete the sqlite file and the registry comes back with everything else.

**There is no folder→entry table, on purpose.** Membership is resolved at
query time, exactly as the source resolves it: an entry is in a folder when one
of its tags is mapped to that folder, or when it was filed there by hand. That
is what makes mapping `<work>` to a folder retroactive — every entry ever
written with `<work>` in it joins the folder the moment the mapping lands, with
nothing to migrate. A junction table would have to be rewritten on every
mapping change and would be wrong in between.

`entry_tags` is the one apparent duplicate: the same tags already sit in
`entries.folders` as JSON. It exists because those two columns answer different
questions — the JSON renders one entry, the table answers "which entries carry
this tag" and "which tags has nothing claimed yet" in one statement instead of
a scan. Both are projections of the same raw line, and both are thrown away
together on rebuild, so there is no way for them to disagree.
"""
from __future__ import annotations

import calendar
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from . import eventlog
from .config import DATE_LOCALE, INDEX_PATH, ensure_dirs
from .parser import parse_entry
from .reminder import resolve_reminders

TABLES = (
    "entries",
    "entry_tags",
    "reminders",
    "folders",
    "folder_tags",
    "entry_folders",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id         TEXT PRIMARY KEY,
    ts         TEXT NOT NULL,
    day        TEXT NOT NULL,
    raw_text   TEXT NOT NULL,
    clean_text TEXT NOT NULL,
    folders    TEXT NOT NULL DEFAULT '[]',
    times      TEXT NOT NULL DEFAULT '[]',
    patterns   TEXT NOT NULL DEFAULT '[]',
    todo_lines TEXT NOT NULL DEFAULT '[]',
    todo_done  TEXT NOT NULL DEFAULT '[]',
    -- Paths under data/media, as a JSON array. Stored rather than derived:
    -- an attachment is a fact about the entry, like the raw line.
    media      TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS entries_by_day ON entries (day, ts);

-- One row per <tag> on an entry. See the module docstring for why this is not
-- redundant with entries.folders.
CREATE TABLE IF NOT EXISTS entry_tags (
    entry_id TEXT NOT NULL,
    tag      TEXT NOT NULL,
    PRIMARY KEY (entry_id, tag)
);
CREATE INDEX IF NOT EXISTS entry_tags_by_tag ON entry_tags (tag);

-- One row per line that named a future time. Derived: the due date is a
-- function of the line and of when the line was written, both of which are in
-- the capture event. `dismissed` is the fold of the dismiss events.
CREATE TABLE IF NOT EXISTS reminders (
    entry_id  TEXT NOT NULL,
    line      INTEGER NOT NULL,
    line_text TEXT NOT NULL,
    due_at    TEXT NOT NULL,
    dismissed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (entry_id, line)
);
CREATE INDEX IF NOT EXISTS reminders_by_due ON reminders (dismissed, due_at);

CREATE TABLE IF NOT EXISTS folders (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    color      TEXT NOT NULL,
    created_ts TEXT NOT NULL
);

-- `tag` is the primary key, not a pair: one tag belongs to at most one
-- folder. The source spells the same rule `@@unique([userId, tagName])`.
CREATE TABLE IF NOT EXISTS folder_tags (
    tag       TEXT PRIMARY KEY,
    folder_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS folder_tags_by_folder ON folder_tags (folder_id);

-- Filed by hand rather than by syntax.
CREATE TABLE IF NOT EXISTS entry_folders (
    entry_id  TEXT NOT NULL,
    folder_id TEXT NOT NULL,
    PRIMARY KEY (entry_id, folder_id)
);
CREATE INDEX IF NOT EXISTS entry_folders_by_folder ON entry_folders (folder_id);
"""

COLUMNS = (
    "id, ts, day, raw_text, clean_text, folders, times, patterns, "
    "todo_lines, todo_done, media"
)

# Reads carry the manual filing along with the entry: it is one more thing the
# row means, and the log view needs it to tick the right folder in the assign
# menu. `group_concat` is safe here because ids are hex.
SELECT_ENTRIES = (
    f"SELECT {COLUMNS}, (SELECT group_concat(folder_id) FROM entry_folders "
    "WHERE entry_id = entries.id) AS manual FROM entries"
)


def _open(target: Path) -> sqlite3.Connection | None:
    """Connect and prove the file is actually a database — `sqlite3.connect`
    opens anything and only fails at the first statement."""
    conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except sqlite3.DatabaseError:
        conn.close()
        return None
    return conn


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open the index, discarding it if it is unreadable. Nothing here is not
    derived, so throwing it away costs a rebuild and never any data."""
    ensure_dirs()
    target = Path(path or INDEX_PATH)
    conn = _open(target)
    if conn is None:
        target.unlink(missing_ok=True)
        conn = _open(target)
        if conn is None:  # a fresh file that still will not open: not our bug
            raise sqlite3.DatabaseError(f"cannot create a capture index at {target}")
    return conn


def derive(raw_text: str) -> dict:
    """Run the parser and shape its output for storage.

    The `--directive` joins `folders` rather than living in a field of its
    own, so `--work` files the entry under the tag `work`, exactly where
    `<work>` would have put it. That is what makes the directive need no
    special case downstream: a folder claims the tag of its own name when it
    is created, so the directive reaches the folder through the ordinary tag
    mapping, and when no folder answers to that name the tag simply waits in
    the unassigned pool like any other. The source instead resolves the
    directive against the folder table at write time and drops it if nothing
    matches — which loses it, and is the one place the port refuses to follow.
    """
    parsed = parse_entry(raw_text)
    folders = list(parsed.folders)
    if parsed.directive and parsed.directive not in folders:
        folders.append(parsed.directive)
    return {
        "clean_text": parsed.clean_text,
        "folders": folders,
        "times": parsed.times,
        "patterns": parsed.patterns,
        "todo_lines": parsed.todo_lines,
    }


def derive_reminders(event: dict) -> list[tuple]:
    """The reminder rows a capture event implies.

    **`now` is the moment the line was written, not the moment of the
    rebuild.** That is what makes this derivable at all: `{2d}` typed on the
    15th means the 17th forever, so replaying the log a year later produces
    the same dates it produced the first time. The source stores resolved
    reminders in a table because its client resolves them; here the resolver
    is a pure function of two things the log already holds.
    """
    written = datetime.fromisoformat(event["ts"])
    return [
        # Stored in UTC, always. A duration inherits the offset the entry was
        # written at and an absolute date resolves at UTC midnight, so the
        # column would otherwise hold two offsets and the `due_at <= ?`
        # comparison — which is a string comparison — would be nonsense.
        (
            event["id"],
            r.line_index,
            r.line_text,
            r.due_at.astimezone(timezone.utc).isoformat(),
            0,
        )
        for r in resolve_reminders(
            event.get("text", ""), now=written, locale=DATE_LOCALE
        )
    ]


def _row(event: dict, done: list[int], media: list[str] | None = None) -> tuple[tuple, list[str]]:
    """The `entries` row for a capture event, and the tags to file beside it.

    `media` is passed in rather than read off the event: files that finished
    uploading after the line was written arrive as their own `attach-media`
    events, and the fold is what knows about both.
    """
    d = derive(event.get("text", ""))
    row = (
        event["id"],
        event["ts"],
        event["day"],
        event.get("text", ""),
        d["clean_text"],
        json.dumps(d["folders"], ensure_ascii=False),
        json.dumps(d["times"], ensure_ascii=False),
        json.dumps(d["patterns"], ensure_ascii=False),
        json.dumps(d["todo_lines"]),
        json.dumps(sorted(done)),
        json.dumps(list(event.get("media", []) if media is None else media), ensure_ascii=False),
    )
    return row, d["folders"]


def fold(events: list[dict]) -> dict:
    """Replay every event into the state the tables hold. Pure — it touches no
    database, which is what lets `rebuild` and the targeted mirrors in
    `store.py` be checked against each other by deleting the index.

    Last-wins throughout, and tolerant throughout: an event naming a folder
    that does not exist (deleted, or a line restored out of order from a
    backup) is dropped rather than resurrecting it.
    """
    captures: dict[str, dict] = {}
    done: dict[str, set[int]] = {}
    media: dict[str, list[str]] = {}
    dismissed: dict[str, set[int]] = {}
    folders: dict[str, dict] = {}
    tag_to_folder: dict[str, str] = {}
    manual: dict[str, set[str]] = {}

    for event in events:
        kind = event["kind"]
        subject = event["id"]

        if kind == eventlog.CAPTURE:
            # Last-wins on the capture's own list; attachments accumulate on
            # top of it, in the order they landed.
            media[subject] = list(event.get("media", []))
            # Last-wins on a duplicated id, which only happens if a log file
            # was restored twice. Re-applying the same line is then a no-op.
            captures[subject] = event
            done.setdefault(subject, set())
        elif kind == eventlog.CHECK:
            done.setdefault(subject, set()).add(int(event.get("line", 0)))
        elif kind == eventlog.UNCHECK:
            done.setdefault(subject, set()).discard(int(event.get("line", 0)))
        elif kind == eventlog.ATTACH_MEDIA:
            attached = media.setdefault(subject, [])
            for ref in event.get("media", []):
                if ref not in attached:  # a replayed line must not duplicate
                    attached.append(ref)
        elif kind == eventlog.DISMISS:
            dismissed.setdefault(subject, set()).add(int(event.get("line", 0)))

        elif kind == eventlog.CREATE_FOLDER:
            folders[subject] = {
                "name": event.get("text", ""),
                "color": event.get("color", ""),
                "created_ts": event["ts"],
            }
        elif kind == eventlog.RENAME_FOLDER:
            if subject in folders:
                folders[subject]["name"] = event.get("text", "")
        elif kind == eventlog.DELETE_FOLDER:
            folders.pop(subject, None)
            # Cascade, the same one Prisma declares on FolderTag and the same
            # one the source gets from `onDelete: Cascade`. A mapping to a
            # folder that no longer exists would make its tag look claimed.
            tag_to_folder = {
                tag: fid for tag, fid in tag_to_folder.items() if fid != subject
            }
            for filed in manual.values():
                filed.discard(subject)

        elif kind == eventlog.MAP_TAG:
            tag = event.get("tag")
            if tag and subject in folders:
                tag_to_folder[tag] = subject
        elif kind == eventlog.UNMAP_TAG:
            tag = event.get("tag")
            # Only unmap what this folder actually holds: an `unmap-tag` that
            # arrives after the tag moved elsewhere must not steal it back.
            if tag and tag_to_folder.get(tag) == subject:
                del tag_to_folder[tag]

        elif kind == eventlog.ASSIGN:
            folder_id = event.get("folder")
            if folder_id in folders:
                # Replaces, never adds — `assignFolderId` overwrites the whole
                # array in the source, and the assign menu is a radio group.
                manual[subject] = {folder_id}
        elif kind == eventlog.UNASSIGN:
            folder_id = event.get("folder")
            if folder_id:
                manual.get(subject, set()).discard(folder_id)

    return {
        "captures": captures,
        "done": done,
        "media": media,
        "dismissed": dismissed,
        "folders": folders,
        "tag_to_folder": tag_to_folder,
        "manual": manual,
    }


def rebuild(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    """Drop and replay. Returns (events indexed, log warnings)."""
    events, warnings = eventlog.read_all()
    state = fold(events)

    rows: list[tuple] = []
    tag_rows: list[tuple[str, str]] = []
    reminder_rows: list[tuple] = []
    for entry_id, event in state["captures"].items():
        row, tags = _row(
            event,
            sorted(state["done"].get(entry_id, set())),
            state["media"].get(entry_id, []),
        )
        rows.append(row)
        tag_rows += [(entry_id, tag) for tag in tags]
        gone = state["dismissed"].get(entry_id, set())
        reminder_rows += [
            (eid, line, text, due, 1 if line in gone else 0)
            for eid, line, text, due, _ in derive_reminders(event)
        ]

    with conn:
        for table in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.executescript(SCHEMA)
        conn.executemany(
            f"INSERT INTO entries ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.executemany(
            "INSERT INTO entry_tags (entry_id, tag) VALUES (?, ?)", tag_rows
        )
        conn.executemany(
            "INSERT INTO reminders (entry_id, line, line_text, due_at, dismissed) "
            "VALUES (?, ?, ?, ?, ?)",
            reminder_rows,
        )
        conn.executemany(
            "INSERT INTO folders (id, name, color, created_ts) VALUES (?, ?, ?, ?)",
            [
                (fid, f["name"], f["color"], f["created_ts"])
                for fid, f in state["folders"].items()
            ],
        )
        conn.executemany(
            "INSERT INTO folder_tags (tag, folder_id) VALUES (?, ?)",
            list(state["tag_to_folder"].items()),
        )
        conn.executemany(
            "INSERT INTO entry_folders (entry_id, folder_id) VALUES (?, ?)",
            [
                (entry_id, folder_id)
                for entry_id, filed in state["manual"].items()
                for folder_id in sorted(filed)
                # An entry can be filed by hand and then never captured only
                # if the log lost its capture line; skip rather than orphan.
                if entry_id in state["captures"]
            ],
        )

    return len(events), warnings


def add_capture(conn: sqlite3.Connection, event: dict) -> None:
    """Mirror a freshly appended capture into the index."""
    row, tags = _row(event, [])
    with conn:
        conn.execute(
            f"INSERT OR REPLACE INTO entries ({COLUMNS}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )
        conn.execute("DELETE FROM entry_tags WHERE entry_id = ?", (event["id"],))
        conn.executemany(
            "INSERT INTO entry_tags (entry_id, tag) VALUES (?, ?)",
            [(event["id"], tag) for tag in tags],
        )
        conn.execute("DELETE FROM reminders WHERE entry_id = ?", (event["id"],))
        conn.executemany(
            "INSERT INTO reminders (entry_id, line, line_text, due_at, dismissed) "
            "VALUES (?, ?, ?, ?, ?)",
            derive_reminders(event),
        )


def set_done(conn: sqlite3.Connection, entry_id: str, done: list[int]) -> None:
    """Mirror a check/uncheck. The list is the folded result, not a delta."""
    with conn:
        conn.execute(
            "UPDATE entries SET todo_done = ? WHERE id = ?",
            (json.dumps(sorted(set(done))), entry_id),
        )


def set_media(conn: sqlite3.Connection, entry_id: str, refs: list[str]) -> None:
    """Mirror an attach. The list is the folded result, not a delta."""
    with conn:
        conn.execute(
            "UPDATE entries SET media = ? WHERE id = ?",
            (json.dumps(refs, ensure_ascii=False), entry_id),
        )


def dismiss_reminder(conn: sqlite3.Connection, entry_id: str, line: int) -> None:
    with conn:
        conn.execute(
            "UPDATE reminders SET dismissed = 1 WHERE entry_id = ? AND line = ?",
            (entry_id, line),
        )


def due_reminders(conn: sqlite3.Connection, as_of: str) -> list[dict]:
    """Reminders that have come due and have not been dismissed, soonest
    first. `as_of` is an ISO instant — the caller's clock, not this module's,
    because nothing here is allowed to read one."""
    return [
        {
            "entry_id": row["entry_id"],
            "line": row["line"],
            "line_text": row["line_text"],
            "due_at": row["due_at"],
        }
        for row in conn.execute(
            "SELECT entry_id, line, line_text, due_at FROM reminders "
            "WHERE dismissed = 0 AND due_at <= ? ORDER BY due_at, entry_id, line",
            (as_of,),
        ).fetchall()
    ]


# ── Mirrors of the folder events ──────────────────────────────────────────
#
# Each of these does to the tables what `fold` does to its dicts, so that a
# write does not cost a full replay. They are the half of the projection most
# likely to drift, which is why `test_capture_folders.py` deletes the index
# after every one of them and asserts the rebuild agrees.


def add_folder(conn: sqlite3.Connection, event: dict) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO folders (id, name, color, created_ts) "
            "VALUES (?, ?, ?, ?)",
            (event["id"], event.get("text", ""), event.get("color", ""), event["ts"]),
        )


def rename_folder(conn: sqlite3.Connection, folder_id: str, name: str) -> None:
    with conn:
        conn.execute("UPDATE folders SET name = ? WHERE id = ?", (name, folder_id))


def drop_folder(conn: sqlite3.Connection, folder_id: str) -> None:
    with conn:
        conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        conn.execute("DELETE FROM folder_tags WHERE folder_id = ?", (folder_id,))
        conn.execute("DELETE FROM entry_folders WHERE folder_id = ?", (folder_id,))


def map_tag(conn: sqlite3.Connection, tag: str, folder_id: str) -> None:
    """Point `tag` at `folder_id`, moving it off whatever held it before."""
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO folder_tags (tag, folder_id) VALUES (?, ?)",
            (tag, folder_id),
        )


def unmap_tag(conn: sqlite3.Connection, tag: str, folder_id: str) -> None:
    with conn:
        conn.execute(
            "DELETE FROM folder_tags WHERE tag = ? AND folder_id = ?",
            (tag, folder_id),
        )


def set_manual_folder(
    conn: sqlite3.Connection, entry_id: str, folder_id: str | None
) -> None:
    """File an entry by hand, or clear the filing. Replaces, never adds."""
    with conn:
        conn.execute("DELETE FROM entry_folders WHERE entry_id = ?", (entry_id,))
        if folder_id is not None:
            conn.execute(
                "INSERT INTO entry_folders (entry_id, folder_id) VALUES (?, ?)",
                (entry_id, folder_id),
            )


# ── Reads ─────────────────────────────────────────────────────────────────


def _as_entry(row: sqlite3.Row) -> dict:
    manual = row["manual"] if "manual" in row.keys() else None
    return {
        "id": row["id"],
        "ts": row["ts"],
        "day": row["day"],
        "raw_text": row["raw_text"],
        "clean_text": row["clean_text"],
        "folders": json.loads(row["folders"]),
        "times": json.loads(row["times"]),
        "patterns": json.loads(row["patterns"]),
        "todo_lines": json.loads(row["todo_lines"]),
        "todo_done": json.loads(row["todo_done"]),
        "media": json.loads(row["media"]),
        "manual_folders": sorted(manual.split(",")) if manual else [],
    }


def get(conn: sqlite3.Connection, entry_id: str) -> dict | None:
    row = conn.execute(
        f"{SELECT_ENTRIES} WHERE id = ?", (entry_id,)
    ).fetchone()
    return _as_entry(row) if row else None


def entries(
    conn: sqlite3.Connection,
    start: str | None = None,
    end: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Newest first, as the log reads. `start`/`end` are inclusive day keys."""
    sql = SELECT_ENTRIES
    args: list = []
    if start and end:
        sql += " WHERE day >= ? AND day <= ?"
        args += [start, end]
    sql += " ORDER BY ts DESC, id DESC LIMIT ?"
    args.append(limit)
    return [_as_entry(r) for r in conn.execute(sql, args).fetchall()]


# ── Folders ───────────────────────────────────────────────────────────────


def folders(conn: sqlite3.Connection) -> list[dict]:
    """Every folder, oldest first, each with the tags that point at it.

    Creation order rather than name order, matching the source: the list is a
    place you learn the position of, and sorting it by name would reshuffle it
    every time a folder is renamed.

    `rowid` breaks ties rather than `id`, because `created_ts` has second
    resolution and two folders made in the same second would otherwise sort by
    a random hex string. Rows are inserted in event order by both `rebuild`
    and `add_folder`, so the implicit rowid *is* the creation order.
    """
    tags: dict[str, list[str]] = {}
    for row in conn.execute(
        "SELECT tag, folder_id FROM folder_tags ORDER BY tag"
    ).fetchall():
        tags.setdefault(row["folder_id"], []).append(row["tag"])

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "color": row["color"],
            "created_ts": row["created_ts"],
            "tags": tags.get(row["id"], []),
        }
        for row in conn.execute(
            "SELECT id, name, color, created_ts FROM folders "
            "ORDER BY created_ts, rowid"
        ).fetchall()
    ]


def folder(conn: sqlite3.Connection, folder_id: str) -> dict | None:
    for item in folders(conn):
        if item["id"] == folder_id:
            return item
    return None


def tag_owner(conn: sqlite3.Connection, tag: str) -> str | None:
    """Which folder holds this tag, if any. At most one, by construction."""
    row = conn.execute(
        "SELECT folder_id FROM folder_tags WHERE tag = ?", (tag,)
    ).fetchone()
    return row["folder_id"] if row else None


def folder_name_taken(
    conn: sqlite3.Connection, name: str, except_id: str | None = None
) -> bool:
    """Names are matched case-insensitively because `--directive` is. Two
    folders called `Work` and `work` would make `--work` a coin toss."""
    row = conn.execute(
        "SELECT id FROM folders WHERE lower(name) = lower(?) AND id IS NOT ?",
        (name, except_id),
    ).fetchone()
    return row is not None


def folder_entries(conn: sqlite3.Connection, folder_id: str) -> list[dict]:
    """Everything in a folder, newest first.

    The union is the whole membership rule: tagged into it, or filed into it
    by hand. Neither half is stored as membership — see the module docstring.
    """
    return [
        _as_entry(row)
        for row in conn.execute(
            f"{SELECT_ENTRIES} WHERE id IN ("
            "  SELECT entry_id FROM entry_tags WHERE tag IN ("
            "    SELECT tag FROM folder_tags WHERE folder_id = ?)"
            "  UNION"
            "  SELECT entry_id FROM entry_folders WHERE folder_id = ?"
            ") ORDER BY ts DESC, id DESC",
            (folder_id, folder_id),
        ).fetchall()
    ]


def _counted(counts: dict[str, int], key: str) -> list[dict]:
    """Commonest first. The source leaves ties in whatever order Postgres
    returned them; ties are broken by name here so a reload cannot reorder a
    list the user is reading."""
    return [
        {key: name, "count": count}
        for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def folder_sentiments(conn: sqlite3.Connection, folder_id: str) -> list[dict]:
    """`\\pattern` counts across a folder's entries — the folder screen's only
    reading, drawn and never interpreted."""
    counts: dict[str, int] = {}
    for entry in folder_entries(conn, folder_id):
        for name in entry["patterns"]:
            counts[name] = counts.get(name, 0) + 1
    return _counted(counts, "name")


def unassigned_tags(conn: sqlite3.Connection) -> list[dict]:
    """Tags the user has written that no folder has claimed, commonest first.

    This is the mapping screen's entire input, and the reason the port keeps
    an unmapped tag working: a `<tag>` is a real thing the moment it is typed,
    and filing it is a separate, optional act.
    """
    rows = conn.execute(
        "SELECT tag, count(*) AS n FROM entry_tags "
        "WHERE tag NOT IN (SELECT tag FROM folder_tags) "
        "GROUP BY tag"
    ).fetchall()
    return _counted({r["tag"]: r["n"] for r in rows}, "tag")


def dates(conn: sqlite3.Connection) -> dict[str, int]:
    """Day key → entry count. Drives the timeline's density marks."""
    rows = conn.execute(
        "SELECT day, count(*) AS n FROM entries GROUP BY day"
    ).fetchall()
    return {r["day"]: r["n"] for r in rows}


def cumulative(conn: sqlite3.Connection, up_to: str) -> dict:
    """Everything the log draws below the entries, as of a chosen day.

    Ported from `api-contracts/entries/cumulative/route.ts`. Two windows, on
    purpose: the word count is all of history up to `up_to` (a total is a
    total), while the tag bars and the sentiment chart use a rolling three
    months, so a tag you stopped using in March cannot crowd out one you are
    using now.

    The weekday figure is an *average per day you wrote*, not a total: the
    divisor is how many distinct days of that weekday carried any pattern at
    all. Without that, Mondays win simply for being numerous.
    """
    end = date.fromisoformat(up_to)
    # Three months back, clamped rather than overflowed — this is a rolling
    # window, so landing on the 28th instead of the 31st costs nothing.
    month = end.month - 3
    year = end.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    window_start = date(
        year, month, min(end.day, calendar.monthrange(year, month)[1])
    ).isoformat()

    rows = conn.execute(
        "SELECT day, clean_text, folders, patterns FROM entries WHERE day <= ?",
        (up_to,),
    ).fetchall()

    word_count = 0
    folder_counts: dict[str, int] = {}
    pattern_dow: dict[str, list[int]] = {}
    dow_days: list[set[str]] = [set() for _ in range(7)]

    for row in rows:
        text = row["clean_text"].strip()
        if text:
            word_count += len(text.split())

        if row["day"] < window_start:
            continue

        for tag in json.loads(row["folders"]):
            folder_counts[tag] = folder_counts.get(tag, 0) + 1

        patterns = json.loads(row["patterns"])
        if not patterns:
            continue
        dow = date.fromisoformat(row["day"]).weekday()  # Monday = 0
        dow_days[dow].add(row["day"])
        for name in patterns:
            counts = pattern_dow.setdefault(name, [0] * 7)
            counts[dow] += 1

    sentiments = [
        {
            "name": name,
            "total": sum(counts),
            "dow": [
                round(c / len(dow_days[i]), 2) if dow_days[i] else 0
                for i, c in enumerate(counts)
            ],
        }
        for name, counts in pattern_dow.items()
    ]
    sentiments.sort(key=lambda s: -s["total"])

    return {
        "folders": sorted(
            ({"name": n, "count": c} for n, c in folder_counts.items()),
            key=lambda f: -f["count"],
        ),
        "word_count": word_count,
        "sentiments": sentiments,
    }


def vocab(conn: sqlite3.Connection, recent: int = 500) -> dict:
    """Everything the capture bar needs to know about itself.

    The three word lists are what the autocomplete offers: every tag, time and
    pattern the user has actually written, from the most recent entries (the
    source caps at 500 too). Sorted, because the trie's ordering is insertion
    order and a stable input is what makes its suggestions stable.

    `folders` and `tag_to_folder` are the registry, and they are here rather
    than behind a second request because the validation layer needs all of it
    on every keystroke: a `--directive` has to be checked against folder
    *names*, and a `<tag>` against the mapping, to know whether the two
    disagree about where the line is going.

    A mapped tag joins the vocabulary even if nothing has been written with it
    yet — the source does the same. Mapping a tag is a statement that you
    intend to use it, and the autocomplete should know it before the first
    time rather than after.
    """
    rows = conn.execute(
        "SELECT folders, times, patterns FROM entries "
        "ORDER BY ts DESC LIMIT ?",
        (recent,),
    ).fetchall()
    tags: set[str] = set()
    times: set[str] = set()
    patterns: set[str] = set()
    for row in rows:
        tags.update(json.loads(row["folders"]))
        times.update(json.loads(row["times"]))
        patterns.update(json.loads(row["patterns"]))

    mapping = {
        row["tag"]: row["folder_id"]
        for row in conn.execute("SELECT tag, folder_id FROM folder_tags").fetchall()
    }
    tags.update(mapping)

    return {
        "folders": [
            {"id": f["id"], "name": f["name"], "color": f["color"]}
            for f in folders(conn)
        ],
        "tag_to_folder": mapping,
        "tags": sorted(tags),
        "times": sorted(times),
        "patterns": sorted(patterns),
    }
