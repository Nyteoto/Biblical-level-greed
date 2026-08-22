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
from collections.abc import Iterable
from datetime import date, datetime, timezone
from pathlib import Path

from . import eventlog
from .config import DATE_LOCALE, INDEX_PATH, ensure_dirs
from .parser import normalize_tag, parse_entry
from .reminder import resolve_reminders

# The unfiled pile, as a subject an event can name. It is an album you can open
# like any other, so it is one you can name a chapter in — and it needs a
# spelling in the log for that. A word rather than an empty string, and one no
# folder id can collide with: ids are twelve hex characters.
UNFILED_ALBUM = "unfiled"

TABLES = (
    "entries",
    "entry_tags",
    "reminders",
    "folders",
    "folder_tags",
    "entry_folders",
    "folder_names",
    "folder_groups",
    "chapter_names",
    "lifted_tags",
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
    -- @places. Derived like folders and patterns, and stored beside them for
    -- the same reason: so "every place I have written" is one query rather
    -- than a scan of every raw line.
    places     TEXT NOT NULL DEFAULT '[]',
    todo_lines TEXT NOT NULL DEFAULT '[]',
    todo_done  TEXT NOT NULL DEFAULT '[]',
    -- Paths under data/media, as a JSON array. Stored rather than derived:
    -- an attachment is a fact about the entry, like the raw line.
    media      TEXT NOT NULL DEFAULT '[]',
    -- The `--directive`, lowercased, or empty. Derived like everything else on
    -- this row; it is a column rather than one more word in `folders` because
    -- a directive names a *folder* and a tag names a word, and only one of
    -- them belongs in the registry. See `_BY_DIRECTIVE`.
    directive  TEXT NOT NULL DEFAULT '',
    -- The entry this one answers, or ''. **Stored, not derived** — the only
    -- other column here that is, besides `media`, and for the same reason: the
    -- line said `--reply`, it did not say to what. See `capture` in
    -- eventlog.py.
    reply_to   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS entries_by_directive ON entries (directive);
-- The reverse of `reply_to`: what answered this entry. A query rather than a
-- second column, so the pair cannot disagree.
--
-- On `(reply_to, ts)` rather than `reply_to` alone: the read takes the *oldest*
-- answer, and an index that stops at `reply_to` leaves sqlite sorting the
-- matches in a temp b-tree once per row of every entry read. Pinned by
-- `test_the_newest_first_reads_do_not_scan_the_whole_log`, which is how that
-- was noticed rather than shipped.
CREATE INDEX IF NOT EXISTS entries_by_reply_to ON entries (reply_to, ts);
CREATE INDEX IF NOT EXISTS entries_by_day ON entries (day, ts);
-- Newest-first, which is how the log reads and how the capture bar rebuilds
-- its vocabulary. Both queries are `ORDER BY ts DESC ... LIMIT n` with no
-- WHERE, and `entries_by_day` cannot serve them: its leading column is the
-- day, so sqlite fell back to scanning every row and sorting the lot in a
-- temp b-tree to hand back twenty. That is work proportional to all of
-- history for a screenful, and `vocab()` pays it after *every* capture. At
-- 150k entries it measured 82ms for `entries(20)` and 71ms for `vocab()`,
-- against 0.3ms and 1.8ms with this index; it costs 2% of a rebuild and
-- about 5MB. `id` is in it because the sort breaks ties on it.
CREATE INDEX IF NOT EXISTS entries_by_ts ON entries (ts DESC, id DESC);

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
    created_ts TEXT NOT NULL,
    -- "active", "shipped", or empty for a folder with no lifecycle — which is
    -- what an ongoing interest is, as opposed to a project.
    state      TEXT NOT NULL DEFAULT '',
    -- The overview: a standing description of the project and one picture for
    -- it. Derived like everything else here — the text is the last
    -- `set-overview` event's, the ref the last `set-overview-media`'s.
    overview       TEXT NOT NULL DEFAULT '',
    overview_media TEXT NOT NULL DEFAULT ''
);

-- Every name a folder has ever answered to, normalised the way a tag is. What
-- a `--directive` matches against.
--
-- **Every name, not just the current one, and that is the point.** Entries
-- written `--admin` reach the folder by its name; renaming it to Paperwork
-- would drop them out of the folder they were filed into, which no rename
-- should ever do. The old name stays here and goes on answering.
--
-- `name_key` is the primary key, so a name belongs to one folder — the same
-- shape as `folder_tags`, for the same reason. A folder taking a name takes it
-- *back* from whatever used to answer to it: a name means what it means now,
-- and the fold applies that rule on every replay so it cannot drift.
--
-- A separate table rather than `lower(name)` in the query because sqlite's
-- `lower()` is ASCII-only and a folder is not required to be.
CREATE TABLE IF NOT EXISTS folder_names (
    name_key  TEXT PRIMARY KEY,
    folder_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS folder_names_by_folder ON folder_names (folder_id);

-- A folder's group, per year. The primary key is the pair because that is
-- exactly the fact: a folder has one group *in a year*, and the same folder in
-- another year is free to sit somewhere else. `seq` is the fold counter at the
-- moment the group was first named in that year, and it is what orders the
-- groups on the shelf — first named, first drawn — so the order survives a
-- rebuild without anyone recording it.
CREATE TABLE IF NOT EXISTS folder_groups (
    folder_id TEXT NOT NULL,
    year      TEXT NOT NULL,
    name      TEXT NOT NULL,
    seq       INTEGER NOT NULL,
    PRIMARY KEY (folder_id, year)
);
CREATE INDEX IF NOT EXISTS folder_groups_by_year ON folder_groups (year);

-- A chapter named by hand. Keyed on the month it was anchored to rather than
-- on the chapter, because a chapter is a run of months and a run is derived —
-- see `name-chapter` in eventlog.py for why a month is a safe anchor and what
-- happens when two named runs merge. `folder_id` is a folder or the literal
-- `unfiled`, which is an album like any other.
CREATE TABLE IF NOT EXISTS chapter_names (
    folder_id TEXT NOT NULL,
    year      TEXT NOT NULL,
    month     INTEGER NOT NULL,
    name      TEXT NOT NULL,
    PRIMARY KEY (folder_id, year, month)
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

-- Tags whose brackets the app has stopped drawing. One column, because there
-- is nothing to say about a lifted tag except that it is one.
--
-- It is not a column on `folder_tags`: lifting is a fact about a *word*, and
-- most of the words it is wanted for are tags no folder ever claimed. A tag can
-- be lifted, mapped later and unmapped again without any of that touching this
-- table, which is the point — see `lift-tag` in eventlog.py.
CREATE TABLE IF NOT EXISTS lifted_tags (
    tag TEXT PRIMARY KEY
);
"""

COLUMNS = (
    "id, ts, day, raw_text, clean_text, folders, times, patterns, places, "
    "todo_lines, todo_done, media, directive, reply_to"
)
PLACEHOLDERS = ", ".join("?" * len(COLUMNS.split(",")))

# Reads carry the manual filing along with the entry: it is one more thing the
# row means, and the log view needs it to tick the right folder in the assign
# menu. `group_concat` is safe here because ids are hex.
SELECT_ENTRIES = (
    f"SELECT {COLUMNS}, (SELECT group_concat(folder_id) FROM entry_folders "
    "WHERE entry_id = entries.id) AS manual, "
    # What answered this line, if anything. Carried on the read because the log
    # draws the thread from both ends — a reply points back and the original
    # points forward — and asking per row would be a query per line on screen.
    "(SELECT r.id FROM entries r WHERE r.reply_to = entries.id "
    " ORDER BY r.ts LIMIT 1) AS replied_by FROM entries"
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

    **The `--directive` is its own field and is not a tag.** It used to join
    `folders`, so `--work` filed the entry under the tag `work` and reached the
    folder through the ordinary mapping — which worked because every folder
    claimed the tag of its own name the moment it was created. That claim is
    gone: it filled the registry with a word per folder that nobody had ever
    typed, and the registry is supposed to hold the words *you* chose, the
    non-obvious ones you want pointed somewhere. A directive is the other
    gesture — naming the folder outright — so it resolves against the folder's
    name at read time instead, and stores nothing. See `_BY_DIRECTIVE`.

    Nothing is lost by the change, which is what the source got wrong and this
    still refuses to follow: it resolves the directive at *write* time and
    drops it when no folder matches. Here the word is on the raw line forever
    and in this column on every rebuild, so a folder created next year picks up
    every `--directive` that has been waiting for it.
    """
    parsed = parse_entry(raw_text)
    return {
        "clean_text": parsed.clean_text,
        "folders": list(parsed.folders),
        "directive": parsed.directive or "",
        "times": parsed.times,
        "patterns": parsed.patterns,
        "places": parsed.places,
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
        json.dumps(d["places"], ensure_ascii=False),
        json.dumps(d["todo_lines"]),
        json.dumps(sorted(done)),
        json.dumps(list(event.get("media", []) if media is None else media), ensure_ascii=False),
        d["directive"],
        event.get("reply_to", ""),
    )
    return row, d["folders"]


def order_seqs(drawn: list[str], order: list[str]) -> dict[str, int]:
    """The new `seq` for every group on one year's shelf, as one rule.

    `drawn` is the year's groups in the order they are drawn now; `order` is
    what the `order-groups` event asked for. The named ones take the front, in
    the order given; everything the event did not mention keeps its relative
    place behind them, and a name that no longer stands on this shelf is
    dropped rather than reserving a slot.

    Written once because `fold` and the targeted mirror below both need the
    same answer, and an ordering the replay disagreed with would reshuffle the
    shelf on the next launch — which is exactly the failure the `seq` column
    exists to prevent.
    """
    here = set(drawn)
    named = [name for name in dict.fromkeys(order) if name in here]
    rest = [name for name in drawn if name not in set(named)]
    return {name: slot for slot, name in enumerate(named + rest)}


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
    # (folder, year) -> (group name, the seq that group was first named at)
    groups: dict[tuple[str, str], str] = {}
    group_seq: dict[tuple[str, str], int] = {}
    # Tags the reader draws without their brackets. A set, folded last-wins
    # like everything else here.
    lifted: set[str] = set()
    # Every name a folder has answered to -> the folder answering. Keyed on the
    # name, so taking a name takes it back from whoever held it; see
    # `folder_names`.
    names: dict[str, str] = {}
    # (folder, year, month) -> the name given to the chapter anchored there.
    chapter_names: dict[tuple[str, str, int], str] = {}

    for seq, event in enumerate(events):
        kind = event["kind"]
        subject = event["id"]

        def claim_name(folder_id: str, name: str) -> None:
            """`folder_id` answers to `name` from here on, and nothing else
            does. The same rule the targeted mirror keeps, in the same order —
            see `_claim_name`."""
            key = normalize_tag(name)
            if key:
                names[key] = folder_id

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
            claim_name(subject, event.get("text", ""))
            folders[subject] = {
                "name": event.get("text", ""),
                "color": event.get("color", ""),
                "created_ts": event["ts"],
                "state": "",
                "overview": "",
                "overview_media": "",
            }
        elif kind == eventlog.RENAME_FOLDER:
            if subject in folders:
                folders[subject]["name"] = event.get("text", "")
                # The old name is not dropped: entries written `--oldname`
                # reach this folder by it, and a rename must not un-file them.
                claim_name(subject, event.get("text", ""))
        elif kind == eventlog.SET_STATE:
            if subject in folders:
                folders[subject]["state"] = event.get("text", "")
        elif kind == eventlog.SET_OVERVIEW:
            if subject in folders:
                folders[subject]["overview"] = event.get("text", "")
        elif kind == eventlog.SET_OVERVIEW_MEDIA:
            if subject in folders:
                # A list, because that is the field the log already has for a
                # media ref. One entry, or none to clear it.
                refs = event.get("media") or []
                folders[subject]["overview_media"] = refs[0] if refs else ""
        elif kind == eventlog.SET_GROUP:
            year = event.get("year") or ""
            name = event.get("text", "")
            if subject in folders and year:
                if name:
                    groups[(subject, year)] = name
                    # First naming wins the ordering slot. Moving another
                    # folder into an existing group must not jump that group to
                    # the end of the shelf.
                    group_seq.setdefault((year, name), seq)
                else:
                    groups.pop((subject, year), None)
        elif kind == eventlog.RENAME_GROUP:
            year = event.get("year") or ""
            new = event.get("text", "")
            if year and new and new != subject:
                hit = [k for k, v in groups.items() if k[1] == year and v == subject]
                for key in hit:
                    groups[key] = new
                was = group_seq.pop((year, subject), None)
                # `setdefault`, so renaming onto a name the year already uses
                # keeps the older slot rather than dragging the survivor to
                # wherever the group being renamed happened to sit.
                if hit and was is not None:
                    group_seq.setdefault((year, new), was)
        elif kind == eventlog.ORDER_GROUPS:
            # `id` is the year: what is being arranged is the shelf, not any
            # one of the groups standing on it.
            year = subject
            here: dict[str, int] = {}
            for (folder_id, in_year), name in groups.items():
                if in_year == year:
                    here.setdefault(name, group_seq.get((year, name), 0))
            drawn = sorted(here, key=lambda name: (here[name], name))
            for name, slot in order_seqs(drawn, event.get("order") or []).items():
                group_seq[(year, name)] = slot
        elif kind == eventlog.DELETE_GROUP:
            year = event.get("year") or ""
            if year:
                groups = {
                    k: v for k, v in groups.items() if not (k[1] == year and v == subject)
                }
                group_seq.pop((year, subject), None)
        elif kind == eventlog.NAME_CHAPTER:
            year = event.get("year") or ""
            month = int(event.get("month") or 0)
            name = event.get("text", "")
            # `unfiled` is a real album to name a chapter in and is the one
            # subject here that is not a folder id.
            known = subject == UNFILED_ALBUM or subject in folders
            if known and year and 1 <= month <= 12:
                if name:
                    chapter_names[(subject, year, month)] = name
                else:
                    chapter_names.pop((subject, year, month), None)
        elif kind == eventlog.DELETE_FOLDER:
            folders.pop(subject, None)
            names = {key: fid for key, fid in names.items() if fid != subject}
            groups = {k: v for k, v in groups.items() if k[0] != subject}
            chapter_names = {k: v for k, v in chapter_names.items() if k[0] != subject}
            # Cascade, the same one Prisma declares on FolderTag and the same
            # one the source gets from `onDelete: Cascade`. A mapping to a
            # folder that no longer exists would make its tag look claimed.
            tag_to_folder = {
                tag: fid for tag, fid in tag_to_folder.items() if fid != subject
            }
            for filed in manual.values():
                filed.discard(subject)

        elif kind == eventlog.LIFT_TAG:
            # No `if subject in folders` guard, and deliberately: a tag is not a
            # folder's property. Most tags worth lifting are ones nothing ever
            # claimed, and a tag lifted today must stay lifted through the
            # folder that later claims it being created, renamed and deleted.
            if subject:
                lifted.add(subject)
        elif kind == eventlog.UNLIFT_TAG:
            lifted.discard(subject)

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
        "groups": groups,
        "group_seq": group_seq,
        "chapter_names": chapter_names,
        "lifted": lifted,
        "names": names,
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
            f"INSERT INTO entries ({COLUMNS}) VALUES ({PLACEHOLDERS})",
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
            "INSERT INTO folders "
            "(id, name, color, created_ts, state, overview, overview_media) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    fid,
                    f["name"],
                    f["color"],
                    f["created_ts"],
                    f["state"],
                    f.get("overview", ""),
                    f.get("overview_media", ""),
                )
                for fid, f in state["folders"].items()
            ],
        )
        conn.executemany(
            "INSERT INTO folder_tags (tag, folder_id) VALUES (?, ?)",
            list(state["tag_to_folder"].items()),
        )
        conn.executemany(
            "INSERT INTO folder_groups (folder_id, year, name, seq) "
            "VALUES (?, ?, ?, ?)",
            [
                (fid, year, name, state["group_seq"].get((year, name), 0))
                for (fid, year), name in state["groups"].items()
            ],
        )
        conn.executemany(
            "INSERT INTO folder_names (name_key, folder_id) VALUES (?, ?)",
            # A name whose folder is gone goes with it: `delete-folder` drops
            # them in the fold, and a name restored out of order from a backup
            # must not resurrect one either.
            [
                (key, fid)
                for key, fid in state["names"].items()
                if fid in state["folders"]
            ],
        )
        conn.executemany(
            "INSERT INTO lifted_tags (tag) VALUES (?)",
            [(tag,) for tag in sorted(state["lifted"])],
        )
        conn.executemany(
            "INSERT INTO chapter_names (folder_id, year, month, name) "
            "VALUES (?, ?, ?, ?)",
            [
                (fid, year, month, name)
                for (fid, year, month), name in state["chapter_names"].items()
            ],
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
            f"VALUES ({PLACEHOLDERS})",
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


def home_folder(conn: sqlite3.Connection, entry_id: str) -> str | None:
    """Which album to open in order to be looking at this entry.

    Resolved, never stored — the same rule as membership itself. An entry's
    `folders` are *tags*; a tag points at a folder or at nothing, and an entry
    can also have been filed by hand. Either route counts, and a hand filing
    wins because it is the one somebody chose deliberately.

    `None` means the unfiled pile, which is a real album you can open rather
    than an absence. An entry in two folders has two right answers and gets the
    first — this is a place to be taken to, not a claim about where it lives.
    """
    row = conn.execute(
        "SELECT folder_id FROM entry_folders WHERE entry_id = ? LIMIT 1", (entry_id,)
    ).fetchone()
    if row:
        return row["folder_id"]
    row = conn.execute(
        "SELECT ft.folder_id AS folder_id FROM entry_tags et "
        "JOIN folder_tags ft ON ft.tag = et.tag "
        "WHERE et.entry_id = ? ORDER BY et.tag LIMIT 1",
        (entry_id,),
    ).fetchone()
    if row:
        return row["folder_id"]
    # And the directive, which names its folder outright — last only because a
    # mapped tag is the more specific statement when an entry carries both.
    row = conn.execute(
        "SELECT fn.folder_id AS folder_id FROM entries e "
        "JOIN folder_names fn ON fn.name_key = e.directive "
        "WHERE e.id = ? AND e.directive <> '' LIMIT 1",
        (entry_id,),
    ).fetchone()
    return row["folder_id"] if row else None


def open_todos(conn: sqlite3.Connection) -> list[dict]:
    """Every `--todo` line nobody has ticked, oldest first.

    Derived on the read like everything else: `todo_lines` is a pure function
    of the raw text and `todo_done` is the fold of the `check`/`uncheck`
    events, so nothing anywhere records that a todo is open — it is open
    because it is a todo line whose index is not in the done list.

    Oldest first, because the banner shows one at a time and the one worth
    showing is the one that has been waiting longest. It is the order you would
    have to argue *against*, which is what makes it the right default.
    """
    out: list[dict] = []
    for row in conn.execute(
        # `rowid`, not `id`, as the tiebreak. A `ts` is second-resolution, so
        # three todos written in one second share one, and `id` is a random
        # uuid — ordering by it would shuffle them against the order they were
        # actually written. `rowid` follows insertion, and a rebuild inserts in
        # log order, so it agrees with the log both live and after a replay.
        # This is the table's spelling of `eventlog.read_all`'s stable sort.
        "SELECT id, ts, day, raw_text, todo_lines, todo_done FROM entries "
        "WHERE todo_lines != '[]' ORDER BY ts, rowid"
    ).fetchall():
        lines = json.loads(row["todo_lines"])
        done = set(json.loads(row["todo_done"]))
        text_lines = row["raw_text"].split("\n")
        for line in lines:
            if line in done:
                continue
            out.append(
                {
                    "entry_id": row["id"],
                    "line": line,
                    "text": text_lines[line].strip() if line < len(text_lines) else "",
                    "ts": row["ts"],
                    "day": row["day"],
                }
            )
    return out


def count_open_todos(conn: sqlite3.Connection) -> int:
    """How many stand unchecked. Counted the same way `open_todos` lists them,
    by calling it — two implementations of "open" could disagree, and the one
    that gates the write must not be the one that is wrong."""
    return len(open_todos(conn))


def todo_tally(entries: Iterable[dict]) -> dict:
    """`{made, done}` over a set of entries: promises written, promises kept.

    Folded from the same two fields `open_todos` reads rather than counted by a
    query of its own, so the two cannot drift: `made` is how many indices are
    in `todo_lines`, `done` is how many of *those* the check events left set,
    and `made - done` is therefore exactly the length of the list `open_todos`
    returns. The cap is enforced against that difference, so a second way of
    counting a todo is a way for the banner and the folder card to disagree by
    one about a number the user can see in both places at once.

    `done` is intersected with `todo_lines` rather than measured on its own. A
    `check` names a line index and the fold does not ask whether that line is a
    todo — a stray one from a restored backup is ignored by `open_todos`, and
    must be ignored here too or the tally reads as more kept than were made.
    """
    made = 0
    done = 0
    for entry in entries:
        lines = entry["todo_lines"]
        ticked = set(entry["todo_done"])
        made += len(lines)
        done += sum(1 for line in lines if line in ticked)
    return {"made": made, "done": done}


def rows_tally(rows: Iterable[sqlite3.Row]) -> dict:
    """`todo_tally` over raw rows, which carry the two lists as JSON.

    Here rather than at each call site so that every tally in the app — the
    badge's, an album's, a shelf card's — is arrived at by the same two lines.
    """
    return todo_tally(
        {
            "todo_lines": json.loads(row["todo_lines"]),
            "todo_done": json.loads(row["todo_done"]),
        }
        for row in rows
    )


def todo_totals(conn: sqlite3.Connection) -> dict:
    """The tally over the whole log — every promise ever made here, filed or
    not.

    Not a sum over the folders, and that is the point: membership is resolved
    from an entry's tags, so a todo written on a line nobody tagged is in no
    folder at all. Adding the folders up would quietly leave those out and
    print a total smaller than the list the banner draws from.
    """
    return rows_tally(
        conn.execute(
            "SELECT todo_lines, todo_done FROM entries WHERE todo_lines != '[]'"
        ).fetchall()
    )


def upcoming_reminders(conn: sqlite3.Connection, as_of: str) -> list[dict]:
    """Reminders still ahead of `as_of`, soonest first — the countdown.

    The mirror of `due_reminders`, which only ever answered for what had
    already come due. A reminder you cannot see until it is late is a reminder
    that failed; the point of writing `{14/09}` is the fortnight before it.
    """
    return [
        {
            "entry_id": row["entry_id"],
            "line": row["line"],
            "line_text": row["line_text"],
            "due_at": row["due_at"],
        }
        for row in conn.execute(
            "SELECT entry_id, line, line_text, due_at FROM reminders "
            "WHERE dismissed = 0 AND due_at > ? ORDER BY due_at, entry_id, line",
            (as_of,),
        ).fetchall()
    ]


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


def set_overview(conn: sqlite3.Connection, folder_id: str, text: str) -> None:
    with conn:
        conn.execute("UPDATE folders SET overview = ? WHERE id = ?", (text, folder_id))


def set_overview_media(conn: sqlite3.Connection, folder_id: str, ref: str) -> None:
    with conn:
        conn.execute(
            "UPDATE folders SET overview_media = ? WHERE id = ?", (ref, folder_id)
        )


def add_folder(conn: sqlite3.Connection, event: dict) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO folders "
            "(id, name, color, created_ts, state, overview, overview_media) "
            "VALUES (?, ?, ?, ?, '', '', '')",
            (event["id"], event.get("text", ""), event.get("color", ""), event["ts"]),
        )
        _claim_name(conn, event["id"], event.get("text", ""))


def rename_folder(conn: sqlite3.Connection, folder_id: str, name: str) -> None:
    """Mirror of the `rename-folder` branch of `fold`.

    The old name is *kept* — see `folder_names`. Entries written `--oldname`
    go on reaching this folder, which is the one thing a rename must not
    change.
    """
    with conn:
        conn.execute("UPDATE folders SET name = ? WHERE id = ?", (name, folder_id))
        _claim_name(conn, folder_id, name)


def _claim_name(conn: sqlite3.Connection, folder_id: str, name: str) -> None:
    """This folder answers to `name` from now on, and nothing else does.

    `INSERT OR REPLACE` on the name key is the taking-back: a name belongs to
    one folder, so a second folder called Admin takes `admin` off the one that
    used to be called it. The fold does the same thing in the same order.
    """
    key = normalize_tag(name)
    if not key:
        return
    conn.execute(
        "INSERT OR REPLACE INTO folder_names (name_key, folder_id) VALUES (?, ?)",
        (key, folder_id),
    )


def set_folder_state(conn: sqlite3.Connection, folder_id: str, state: str) -> None:
    with conn:
        conn.execute("UPDATE folders SET state = ? WHERE id = ?", (state, folder_id))


def set_folder_group(
    conn: sqlite3.Connection, folder_id: str, year: str, name: str
) -> None:
    """Mirror of the `set-group` branch of `fold`. Empty name un-groups.

    The `seq` a new group lands on is one past the highest in that year, which
    is what `fold` would give it too: the fold numbers by event position, and
    this event is the newest one there is.
    """
    with conn:
        if not name:
            conn.execute(
                "DELETE FROM folder_groups WHERE folder_id = ? AND year = ?",
                (folder_id, year),
            )
            return
        row = conn.execute(
            "SELECT seq FROM folder_groups WHERE year = ? AND name = ? LIMIT 1",
            (year, name),
        ).fetchone()
        if row is None:
            top = conn.execute(
                "SELECT coalesce(max(seq), -1) AS s FROM folder_groups"
            ).fetchone()
            seq = top["s"] + 1
        else:
            seq = row["seq"]
        conn.execute(
            "INSERT INTO folder_groups (folder_id, year, name, seq) "
            "VALUES (?, ?, ?, ?) ON CONFLICT (folder_id, year) "
            "DO UPDATE SET name = excluded.name, seq = excluded.seq",
            (folder_id, year, name, seq),
        )


def rename_group(conn: sqlite3.Connection, year: str, old: str, new: str) -> None:
    """Mirror of the `rename-group` branch of `fold`.

    The `seq` rule is the whole subtlety: a plain rename carries its own slot
    across untouched, and a rename *onto an existing group* adopts that group's
    slot, because the survivor is the older of the two and the shelf must not
    reorder itself because you renamed something into it.
    """
    with conn:
        row = conn.execute(
            "SELECT seq FROM folder_groups WHERE year = ? AND name = ? LIMIT 1",
            (year, new),
        ).fetchone()
        if row is None:
            conn.execute(
                "UPDATE folder_groups SET name = ? WHERE year = ? AND name = ?",
                (new, year, old),
            )
        else:
            conn.execute(
                "UPDATE folder_groups SET name = ?, seq = ? WHERE year = ? AND name = ?",
                (new, row["seq"], year, old),
            )


def order_groups(conn: sqlite3.Connection, year: str, order: list[str]) -> None:
    """Mirror of the `order-groups` branch of `fold`. Rewrites `seq` for every
    group standing on one year's shelf, by the one rule in `order_seqs`."""
    with conn:
        _, drawn = groups_for(conn, year)
        for name, slot in order_seqs(drawn, order).items():
            conn.execute(
                "UPDATE folder_groups SET seq = ? WHERE year = ? AND name = ?",
                (slot, year, name),
            )


def lift_tag(conn: sqlite3.Connection, tag: str, lifted: bool) -> None:
    """Mirror of the `lift-tag` / `unlift-tag` branches of `fold`."""
    with conn:
        if lifted:
            conn.execute("INSERT OR IGNORE INTO lifted_tags (tag) VALUES (?)", (tag,))
        else:
            conn.execute("DELETE FROM lifted_tags WHERE tag = ?", (tag,))


def delete_group(conn: sqlite3.Connection, year: str, name: str) -> None:
    """Mirror of the `delete-group` branch of `fold`. Un-groups its folders and
    nothing else — no folder and no entry is touched, and there is nothing else
    a group could have been holding."""
    with conn:
        conn.execute(
            "DELETE FROM folder_groups WHERE year = ? AND name = ?", (year, name)
        )


def drop_folder(conn: sqlite3.Connection, folder_id: str) -> None:
    with conn:
        conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        conn.execute("DELETE FROM folder_tags WHERE folder_id = ?", (folder_id,))
        conn.execute("DELETE FROM entry_folders WHERE folder_id = ?", (folder_id,))
        conn.execute("DELETE FROM folder_names WHERE folder_id = ?", (folder_id,))
        conn.execute("DELETE FROM folder_groups WHERE folder_id = ?", (folder_id,))


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
        "places": json.loads(row["places"]),
        "todo_lines": json.loads(row["todo_lines"]),
        "todo_done": json.loads(row["todo_done"]),
        "media": json.loads(row["media"]),
        # The folder this line named outright, or "". Beside `folders` rather
        # than in it: a tag is a word you chose and a directive is a folder you
        # named, and only the first belongs in the registry.
        "directive": row["directive"] if "directive" in row.keys() else "",
        # The thread, both ways. `reply_to` is what this line answers;
        # `replied_by` is what answered it. Only the first is stored.
        "reply_to": row["reply_to"] if "reply_to" in row.keys() else "",
        "replied_by": (
            row["replied_by"] if "replied_by" in row.keys() and row["replied_by"] else ""
        ),
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


def folders(conn: sqlite3.Connection, counts: bool = True) -> list[dict]:
    """Every folder, oldest first, each with the tags that point at it.

    `counts=False` drops `entry_count` to 0 and skips the query behind it.
    That query is the expensive half of this function — it resolves membership
    across every tagged entry in the log, so it grows with the log while the
    rest of this grows with the number of folders. Most callers want the
    figure and pay for it once; `vocab()` does not, and used to pay for it
    after every single capture and then throw the number away.

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

    # How much is in each folder, by the same union `folder_entries` uses —
    # tagged into it or filed into it by hand, counted once either way. It is
    # here rather than on the detail route because the log's filter chips need
    # every count at once, and a count is the one thing that makes a chip worth
    # reading before you tap it. Still derived: no row anywhere stores it.
    tallies: dict[str, int] = (
        {
            row["folder_id"]: row["n"]
            for row in conn.execute(
                f"SELECT folder_id, count(*) AS n FROM ({_ALL_MEMBERSHIP}) "
                "GROUP BY folder_id"
            ).fetchall()
        }
        if counts
        else {}
    )

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "color": row["color"],
            "created_ts": row["created_ts"],
            "state": row["state"],
            "entry_count": tallies.get(row["id"], 0),
            "tags": tags.get(row["id"], []),
            "overview": row["overview"],
            "overview_media": row["overview_media"],
        }
        for row in conn.execute(
            "SELECT id, name, color, created_ts, state, overview, overview_media "
            "FROM folders ORDER BY created_ts, rowid"
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

    `_MEMBERSHIP` is the whole rule and this used to spell its own copy of it,
    which is how it came to be the one read that had never heard of a
    directive. Nothing here is stored as membership — see the module docstring.
    """
    return [
        _as_entry(row)
        for row in conn.execute(
            f"{SELECT_ENTRIES} WHERE id IN ({_MEMBERSHIP}) ORDER BY ts DESC, id DESC",
            (folder_id, folder_id, folder_id),
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
        # A lifted tag has been told it is a word rather than a tag, and a word
        # does not need filing. Leaving it here would have this screen go on
        # asking about the one thing the user has already answered.
        "  AND tag NOT IN (SELECT tag FROM lifted_tags) "
        "GROUP BY tag"
    ).fetchall()
    return _counted({r["tag"]: r["n"] for r in rows}, "tag")


def tag_census(conn: sqlite3.Connection) -> list[dict]:
    """Every tag the user has actually written, commonest first, with where it
    lands and whether it has been lifted.

    Written, not merely mapped: a folder claims the tag of its own name the
    moment it is created, so the mapping knows tags nobody has typed yet — and
    lifting is about *appearances in a line*, which a tag with no lines does
    not have. A tag that has been lifted stays on the list whatever became of
    its entries, because otherwise there would be no way back.
    """
    counts = {
        row["tag"]: row["n"]
        for row in conn.execute(
            "SELECT tag, count(*) AS n FROM entry_tags GROUP BY tag"
        ).fetchall()
    }
    owner = {
        row["tag"]: row["folder_id"]
        for row in conn.execute("SELECT tag, folder_id FROM folder_tags").fetchall()
    }
    lifted = set(lifted_tags(conn))
    for tag in lifted:
        counts.setdefault(tag, 0)
    return [
        {**row, "folder": owner.get(row["tag"], ""), "lifted": row["tag"] in lifted}
        for row in _counted(counts, "tag")
    ]


def dates(conn: sqlite3.Connection) -> dict[str, int]:
    """Day key → entry count. Drives the timeline's density marks."""
    rows = conn.execute(
        "SELECT day, count(*) AS n FROM entries GROUP BY day"
    ).fetchall()
    return {r["day"]: r["n"] for r in rows}


# ── The shelf: albums, scoped to a year ───────────────────────────────────
#
# An album is a folder read one year at a time. That split is the whole reason
# the Log can promise a fixed-size instrument: whatever a project's age, its
# spine holds at most twelve bars, so "the top of the tree" never has to grow
# a scrollbar. Nothing below is stored — the year is a `LIKE 'YYYY-%'` on the
# day key, and every count is recomputed on the read, exactly like membership.
#
# `year=None` means "no year filter", which is what the setting turns the whole
# screen into when the user does not want the yearly restart.

# The membership rule, spelled once: tagged in, named by a directive, or filed
# in by hand. Every half is parameterised by the same folder id, so callers pass
# it three times.
#
# **The directive is the newest of the three and it replaced a stored thing.**
# A `--directive` used to travel as a tag — `derive()` appended it to the
# entry's tag list, and every folder claimed the tag of its own name at
# creation, so `--work` arrived through the ordinary mapping. It worked, and it
# put a word in the registry for every folder that nobody had ever typed. The
# registry is meant to hold the words the user chose — the non-obvious ones
# they want pointed somewhere — so the claim is gone and the directive resolves
# against the folder's name here instead, at read time, storing nothing.
#
# The two routes stay different on purpose. A tag is semantic and arbitrary and
# goes where you say it goes; a directive names the folder outright and needs
# no mapping to be understood. Both still resolve, neither is stored.
_BY_DIRECTIVE = (
    "SELECT id FROM entries WHERE directive <> '' AND directive IN "
    "  (SELECT name_key FROM folder_names WHERE folder_id = ?)"
)

_MEMBERSHIP = (
    "SELECT entry_id FROM entry_tags WHERE tag IN "
    "  (SELECT tag FROM folder_tags WHERE folder_id = ?) "
    "UNION "
    "SELECT entry_id FROM entry_folders WHERE folder_id = ? "
    "UNION "
    f"{_BY_DIRECTIVE}"
)

# The other side of it: an entry no folder claims. Not "has no tags" — a tag
# nothing has been mapped to leaves its entry unfiled, which is exactly the
# pile the shelf's dashed card is offering to sort out. A directive naming no
# folder leaves it there too, and the word is not lost: it is on the raw line
# and in the `directive` column, so the folder made for it next year collects
# every entry that has been waiting.
_UNFILED = (
    "SELECT id FROM entries WHERE id NOT IN ("
    "  SELECT entry_id FROM entry_tags WHERE tag IN (SELECT tag FROM folder_tags)"
    "  UNION SELECT entry_id FROM entry_folders"
    "  UNION SELECT id FROM entries WHERE directive <> '' "
    "    AND directive IN (SELECT name_key FROM folder_names)"
    ")"
)

# The same three routes as one table of (folder, entry) pairs, for the reads
# that want every folder's membership at once rather than one folder's.
_ALL_MEMBERSHIP = (
    "SELECT folder_id, entry_id FROM folder_tags JOIN entry_tags USING (tag)"
    " UNION "
    "SELECT folder_id, entry_id FROM entry_folders"
    " UNION "
    "SELECT fn.folder_id AS folder_id, e.id AS entry_id FROM folder_names fn"
    "  JOIN entries e ON e.directive = fn.name_key"
)


def _year_clause(year: str | None) -> tuple[str, list]:
    return (" AND day LIKE ?", [f"{year}-%"]) if year else ("", [])


def years(conn: sqlite3.Connection) -> list[str]:
    """Every year the log has anything in, newest first. The year rail."""
    rows = conn.execute(
        "SELECT DISTINCT substr(day, 1, 4) AS y FROM entries ORDER BY y DESC"
    ).fetchall()
    return [row["y"] for row in rows]


def _volumes(rows: list[sqlite3.Row]) -> list[int]:
    """Twelve entry counts, January first. The sparkline and the spine read
    the same list — one is it lying down, the other standing up."""
    out = [0] * 12
    for row in rows:
        out[int(row["day"][5:7]) - 1] += 1
    return out


def _month_range(volumes: list[int]) -> str:
    """`Feb–May`, or `Feb` for a single month. Empty when nothing is in."""
    live = [i for i, n in enumerate(volumes) if n]
    if not live:
        return ""
    first, last = calendar.month_abbr[live[0] + 1], calendar.month_abbr[live[-1] + 1]
    return first if first == last else f"{first}–{last}"


def _runs(volumes: list[int]) -> list[tuple[int, int]]:
    """Contiguous months with activity, as (first, last) zero-based indices."""
    out: list[tuple[int, int]] = []
    start: int | None = None
    for i, n in enumerate(volumes):
        if n and start is None:
            start = i
        elif not n and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, 11))
    return out


def set_chapter_name(
    conn: sqlite3.Connection, folder_id: str, year: str, month: int, name: str
) -> None:
    """Mirror one `name-chapter`. An empty name is a deletion, which is what
    hands the chapter back to the reader that names it from your own words."""
    with conn:
        conn.execute(
            "DELETE FROM chapter_names WHERE folder_id = ? AND year = ? AND month = ?",
            (folder_id, year, month),
        )
        if name:
            conn.execute(
                "INSERT INTO chapter_names (folder_id, year, month, name) "
                "VALUES (?, ?, ?, ?)",
                (folder_id, year, month, name),
            )


def chapter_names(
    conn: sqlite3.Connection, folder_id: str | None, year: str | None
) -> dict[int, str]:
    """Month → the name given to the chapter anchored there, for one album in
    one year. Empty for the all-years shelf: a chapter is a run of months
    *inside a year*, so there is no chapter to have named across all of them."""
    if year is None:
        return {}
    rows = conn.execute(
        "SELECT month, name FROM chapter_names WHERE folder_id = ? AND year = ?",
        (folder_id or UNFILED_ALBUM, year),
    ).fetchall()
    return {int(r["month"]): r["name"] for r in rows}


def _chapter_name(rows: list[sqlite3.Row], first: int, last: int, owned: set[str]) -> str:
    """What the app calls a run of months.

    Named from the user's own words, never invented: the commonest `\\pattern`
    or `<tag>` written inside the run, minus the tags that merely say which
    album this is — those are true of every entry here and so distinguish
    nothing. With no word to use, the month range is the name, which is honest
    rather than clever.
    """
    counts: dict[str, int] = {}
    for row in rows:
        month = int(row["day"][5:7]) - 1
        if not first <= month <= last:
            continue
        for word in json.loads(row["patterns"]) + json.loads(row["folders"]):
            if word in owned:
                continue
            counts[word] = counts.get(word, 0) + 1
    if not counts:
        return _month_range([1 if first <= i <= last else 0 for i in range(12)])
    # Commonest wins; ties break on the word so a reload cannot rename a
    # chapter the user is looking at.
    name = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return name.replace("-", " ").capitalize()


def chapters(
    rows: list[sqlite3.Row],
    owned: set[str] = frozenset(),
    named: dict[int, str] | None = None,
) -> list[dict]:
    """Month runs, newest first. Derived on every read — see `_chapter_name` —
    except where one has been named by hand, which is `named`.

    A run takes the name anchored to the earliest of its months that has one.
    Two named runs merge into one chapter when the month between them is
    written in, and this is the rule that says which of the two names it keeps:
    the one it began with. Renaming always anchors to the run's *first* month,
    so a rename cannot be shadowed by an older name further along.
    """
    volumes = _volumes(rows)
    named = named or {}
    out = []
    for first, last in reversed(_runs(volumes)):
        window = [1 if first <= i <= last else 0 for i in range(12)]
        # Months here are zero-based; the anchors, like the payload, are not.
        given = next((named[m] for m in range(first + 1, last + 2) if m in named), "")
        out.append(
            {
                "name": given or _chapter_name(rows, first, last, owned),
                # What the run is called with nothing said about it, so the
                # panel can offer to hand it back without asking the server.
                "derived": _chapter_name(rows, first, last, owned),
                "named": bool(given),
                "range": _month_range(window),
                "first_month": first + 1,
                "last_month": last + 1,
                "entries": sum(volumes[first : last + 1]),
            }
        )
    return out


def _album_rows(
    conn: sqlite3.Connection, folder_id: str | None, year: str | None
) -> list[sqlite3.Row]:
    """One album's entries in one year, as the handful of columns every
    figure on a shelf card is folded out of. `folder_id=None` is the unfiled
    pile.

    `ts` is here only so `shelf()` can say which album was written in last. Day
    would nearly do, and ties on the same day would then fall to whatever order
    the folders happen to come back in — which is the kind of arbitrary that
    reads as a broken setting rather than as a coin toss."""
    clause, args = _year_clause(year)
    columns = "ts, day, media, patterns, folders, todo_lines, todo_done"
    if folder_id is None:
        sql = f"SELECT {columns} FROM entries WHERE id IN ({_UNFILED})"
    else:
        sql = f"SELECT {columns} FROM entries WHERE id IN ({_MEMBERSHIP})"
        args = [folder_id, folder_id, folder_id] + args
    return conn.execute(sql + clause, args).fetchall()


def _shelf_buckets(
    conn: sqlite3.Connection, year: str | None
) -> dict[str | None, list[dict]]:
    """Every album's rows for one year, in one pass over the log.

    The shelf used to build this by calling `_album_rows` once per folder, and
    each of those re-resolved membership against the whole `entries` table —
    so drawing a shelf of twelve albums scanned the log thirteen times, plus
    another twelve for the mosaics. That is O(folders x entries) for a screen
    whose answer is O(entries), and it was by a wide margin the slowest thing
    in the app: 216ms at 150k entries against 25ms at 20k, on the screen the
    journal opens with.

    So: resolve membership once, walk the rows once, and drop each row into
    every album that claims it. `_volumes` still folds the twelve bars off the
    day keys exactly as it did — the shape of a shelf figure did not change,
    only the number of times the log is read to arrive at one.

    `None` is the unfiled pile, and it is derived here rather than by the
    `NOT IN` subquery it used to need: an entry no folder claimed is exactly
    an entry this loop found no bucket for.

    Ordered newest first, which `entries_by_ts` now serves without a sort. The
    order is load-bearing twice over — `shelf` reads the newest line off the
    front of a bucket instead of taking a `max`, and `_lead_from` walks the
    front of it for the card's mosaic.

    **The three JSON columns are counted by sqlite, not by Python.** Decoding
    `media`, `todo_lines` and `todo_done` per row was measurably the largest
    single cost of drawing a shelf — 385k `json.loads` calls at 150k entries,
    more than half the total — and `json_array_length` does the same work
    about three times faster without ever building a Python list. The raw
    `media` text still comes along because `_lead_from` needs the refs
    themselves, but it decodes at most a couple of rows per album before it
    has its three and stops.

    `done` is the one figure sqlite has to be *taught*, and it is written to
    mirror `todo_tally` line for line: iterate `todo_lines`, count the ones
    that appear in `todo_done`. That direction matters — a `check` event from
    a restored backup can name a line that is not a todo, and counting from
    `todo_done` instead would report more kept than were ever made. Being a
    second implementation of a figure this app draws in three places, it is
    pinned against the first one by a test; see
    `test_the_shelf_counts_todos_the_way_todo_tally_does`.
    """
    clause, args = _year_clause(year)

    # Which folders claim which entries: mapped tag, or filed by hand. The
    # same union `folders()` counts with, joined to `entries` so a year's
    # shelf does not carry every other year's memberships in memory.
    membership: dict[str, list[str]] = {}
    for row in conn.execute(
        "SELECT t.entry_id AS entry_id, ft.folder_id AS folder_id "
        "  FROM entry_tags t"
        "  JOIN folder_tags ft USING (tag)"
        "  JOIN entries e ON e.id = t.entry_id"
        f" WHERE 1=1{clause}"
        " UNION "
        "SELECT ef.entry_id AS entry_id, ef.folder_id AS folder_id"
        "  FROM entry_folders ef"
        "  JOIN entries e ON e.id = ef.entry_id"
        f" WHERE 1=1{clause}"
        # The third route, joined the same way: an entry whose directive names
        # this folder. See `_BY_DIRECTIVE`.
        " UNION "
        "SELECT e.id AS entry_id, fn.folder_id AS folder_id"
        "  FROM entries e"
        "  JOIN folder_names fn ON fn.name_key = e.directive"
        f" WHERE 1=1{clause}",
        args + args + args,
    ).fetchall():
        membership.setdefault(row["entry_id"], []).append(row["folder_id"])

    buckets: dict[str | None, list[dict]] = {}
    for row in conn.execute(
        "SELECT id, ts, day, media, "
        "       json_array_length(media) AS media_n, "
        "       json_array_length(todo_lines) AS made, "
        # The guard is not an optimisation of the answer, only of the work:
        # neither list having anything in it means the intersection is empty,
        # and that is the overwhelming majority of rows.
        "       CASE WHEN todo_lines = '[]' OR todo_done = '[]' THEN 0 ELSE ("
        "         SELECT count(*) FROM json_each(entries.todo_lines) l "
        "          WHERE l.value IN (SELECT value FROM json_each(entries.todo_done))"
        "       ) END AS done "
        f"  FROM entries WHERE 1=1{clause} ORDER BY ts DESC, id DESC",
        args,
    ):
        entry = {
            "ts": row["ts"],
            "day": row["day"],
            "media": row["media"],
            "media_n": row["media_n"],
            "made": row["made"],
            "done": row["done"],
        }
        for folder_id in membership.get(row["id"], (None,)):
            buckets.setdefault(folder_id, []).append(entry)
    return buckets


def _lead_from(rows: list[dict], limit: int = 3) -> list[str]:
    """The card's mosaic, off rows already in newest-first order. The query
    version of this was one more scan per folder; the rows are in hand."""
    out: list[str] = []
    for row in rows:
        if not row["media_n"]:
            continue
        out.extend(json.loads(row["media"]))
        if len(out) >= limit:
            break
    return out[:limit]


def album_entries(
    conn: sqlite3.Connection, folder_id: str | None, year: str | None
) -> list[dict]:
    """Everything in one album in one year, newest first."""
    clause, args = _year_clause(year)
    if folder_id is None:
        sql = f"{SELECT_ENTRIES} WHERE id IN ({_UNFILED})"
    else:
        sql = f"{SELECT_ENTRIES} WHERE id IN ({_MEMBERSHIP})"
        args = [folder_id, folder_id, folder_id] + args
    sql += clause + " ORDER BY ts DESC, id DESC"
    return [_as_entry(row) for row in conn.execute(sql, args).fetchall()]


def album(
    conn: sqlite3.Connection, folder_id: str | None, year: str | None
) -> dict | None:
    """One album, one year: its entries, its twelve bars, its chapters.

    The folder's own record comes back beside them unchanged — the album view
    still renames, ships and deletes the *folder*, because a year is a way of
    reading a project rather than a second kind of thing to own.
    """
    record = folder(conn, folder_id) if folder_id else None
    if folder_id and record is None:
        return None
    rows = _album_rows(conn, folder_id, year)
    owned = set(record["tags"]) if record else set()
    contents = album_entries(conn, folder_id, year)
    return {
        "folder": record,
        "year": year,
        "entries": contents,
        "volumes": _volumes(rows),
        "chapters": chapters(rows, owned, chapter_names(conn, folder_id, year)),
        "media_count": sum(len(json.loads(r["media"])) for r in rows),
        # Promises made in here and promises kept, off the same rows the twelve
        # bars are counted from. The unfiled pile gets one like any other album
        # — a todo nobody tagged is still a todo, and the pile is a real album
        # you can open.
        "todos": rows_tally(rows),
        "sentiments": folder_sentiments(conn, folder_id) if folder_id else [],
        # The group is a fact about this folder *in this year*, so it belongs
        # to the album rather than to the folder record beside it.
        "group": groups_for(conn, year)[0].get(folder_id or "", ""),
    }


def groups_for(conn: sqlite3.Connection, year: str | None) -> tuple[dict, list]:
    """`(folder id -> group name, group names in shelf order)` for one year.

    `year` of None is the all-years shelf, and it has no groups at all: a group
    is an arrangement *of a year*, so asking which group a folder is in across
    every year at once has no answer that is not a guess. The all view gets the
    plain grid, which is what it was before groups existed.
    """
    if year is None:
        return {}, []
    rows = conn.execute(
        "SELECT folder_id, name, seq FROM folder_groups WHERE year = ? "
        "ORDER BY seq, name",
        (year,),
    ).fetchall()
    names: list[str] = []
    for row in rows:
        if row["name"] not in names:
            names.append(row["name"])
    return {r["folder_id"]: r["name"] for r in rows}, names


def shelf(conn: sqlite3.Connection, year: str | None) -> dict:
    """The year shelf: which albums exist, how big each is, when each was busy.

    Every album in the year, whether or not it has a lifecycle, plus the
    unfiled pile and a one-line handover to the year below. Albums with nothing
    in them this year are dropped rather than shown empty — an album is a year
    of a project, and a year you did not touch it is not one of them.

    **An empty folder is not that.** A folder with nothing in it in any year has
    no year it belongs to, so dropping it drops it from everywhere; it stays on
    whatever shelf you are looking at until something lands in it. See the note
    on the filter below.
    """
    available = years(conn)
    in_group, group_names = groups_for(conn, year)
    # Every album's rows, resolved in one pass rather than one scan of the log
    # per folder. See `_shelf_buckets` for what that used to cost.
    buckets = _shelf_buckets(conn, year)
    albums = []
    # Where the most recent line in this year actually landed. Tracked here
    # rather than read off `albums[0]` by the caller, because the shelf is
    # sorted by size — which is the right order to *read* it in and the wrong
    # answer to "take me back to where I was". `Opens on: latest day` asked the
    # sorted list that question for a while and got the biggest album every
    # time, which is a setting that appears to do nothing.
    latest: dict | None = None

    def _mark(folder_id: str | None, rows: list[dict]) -> None:
        nonlocal latest
        if not rows:
            return
        # Front of the list, not a `max`: the buckets come back newest first.
        newest = rows[0]
        if latest is None or newest["ts"] > latest["ts"]:
            latest = {"folder": folder_id, "day": newest["day"], "ts": newest["ts"]}

    for record in folders(conn):
        rows = buckets.get(record["id"], [])
        # Nothing in it this year: drop it, but only if there is a *year* it
        # does belong to. A folder that has never held anything anywhere is not
        # a project you did not touch this year — it is a folder you just made,
        # and hiding it is indistinguishable from having eaten it. That is
        # exactly what happened: three empty folders were marked `open` and
        # `shipped` and vanished off every shelf at once, reachable only
        # through the mapping screen, because the only state that kept an empty
        # album on the shelf was `active`.
        if not rows and record["state"] != "active" and record["entry_count"] > 0:
            continue
        volumes = _volumes(rows)
        albums.append(
            {
                **record,
                # `entry_count` on the folder record is all-time; inside a year
                # the album's own count is the one that means anything.
                "entry_count": len(rows),
                "all_time_count": record["entry_count"],
                "media_count": sum(r["media_n"] for r in rows),
                # Promises made in this album this year, and how many were
                # kept. On the card rather than only on the folder's own screen
                # because it is the one figure here that is about how the
                # project is going rather than about how much of it there is.
                #
                # Summed rather than folded: `_shelf_buckets` had sqlite count
                # each row's promises on the way past, for the reason given
                # there. A test pins that arithmetic against `todo_tally`.
                "todos": {
                    "made": sum(r["made"] for r in rows),
                    "done": sum(r["done"] for r in rows),
                },
                "volumes": volumes,
                "months": _month_range(volumes),
                "chapters": len(_runs(volumes)),
                "lead": _lead_from(rows),
                # Empty for a folder in the loose grid above the groups, which
                # is where a folder starts and where most of them stay.
                "group": in_group.get(record["id"], ""),
            }
        )
        _mark(record["id"], rows)

    # Busiest first: the shelf is read to find what you were doing, and what
    # you were doing most is the best first guess.
    albums.sort(key=lambda a: (-a["entry_count"], a["name"].lower()))

    unfiled_rows = buckets.get(None, [])
    # The unfiled pile is a place you can be taken back to like any other. It
    # was not one before, so a shelf with nothing filed in it made the setting
    # do nothing at all rather than something imperfect.
    _mark(None, unfiled_rows)

    clause, args = _year_clause(year)
    total = conn.execute(
        f"SELECT count(*) AS n, "
        f"coalesce(sum(json_array_length(media)), 0) AS m FROM entries "
        f"WHERE 1=1{clause}",
        args,
    ).fetchone()

    previous = None
    if year and year in available:
        older = [y for y in available if y < year]
        if older:
            before = older[0]
            row = conn.execute(
                "SELECT count(*) AS n FROM entries WHERE day LIKE ?", (f"{before}-%",)
            ).fetchone()
            previous = {"year": before, "entries": row["n"]}

    return {
        "year": year,
        "years": available,
        "albums": albums,
        # In shelf order, so the client draws the sections without sorting.
        "groups": group_names,
        "unfiled": len(unfiled_rows),
        "entries": total["n"],
        "media": total["m"],
        "previous": previous,
        # `{folder, day, ts}` of the newest line in this year, or None for a
        # year with nothing in it. `folder` is None when that line is unfiled.
        "latest": latest,
    }


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
        "SELECT folders, times, patterns, places FROM entries "
        "ORDER BY ts DESC LIMIT ?",
        (recent,),
    ).fetchall()
    tags: set[str] = set()
    times: set[str] = set()
    patterns: set[str] = set()
    places: set[str] = set()
    for row in rows:
        tags.update(json.loads(row["folders"]))
        times.update(json.loads(row["times"]))
        patterns.update(json.loads(row["patterns"]))
        places.update(json.loads(row["places"]))

    mapping = {
        row["tag"]: row["folder_id"]
        for row in conn.execute("SELECT tag, folder_id FROM folder_tags").fetchall()
    }
    tags.update(mapping)
    # A lifted tag is still a tag: it files where it always did and the
    # autocomplete should still offer it. Only its brackets stop being drawn.
    lifted = lifted_tags(conn)
    tags.update(lifted)

    return {
        # `counts=False`: the capture bar needs a folder's id, name and colour
        # and nothing else, and this runs after every send. The count it used
        # to compute here was resolved across the whole log and then discarded
        # one line later.
        "folders": [
            {"id": f["id"], "name": f["name"], "color": f["color"]}
            for f in folders(conn, counts=False)
        ],
        "tag_to_folder": mapping,
        "tags": sorted(tags),
        "times": sorted(times),
        "patterns": sorted(patterns),
        "places": sorted(places),
        # Which tags the reader draws without their brackets. It rides along
        # with the vocabulary rather than on a request of its own because
        # every screen that renders a captured line needs it before it can
        # draw one, and the capture bar already asks for this on load.
        "lifted": lifted,
    }


def lifted_tags(conn: sqlite3.Connection) -> list[str]:
    """Every tag that has been lifted out of its brackets, sorted."""
    return [
        row["tag"]
        for row in conn.execute("SELECT tag FROM lifted_tags ORDER BY tag").fetchall()
    ]
