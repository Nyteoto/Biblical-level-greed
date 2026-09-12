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
from datetime import date, datetime, timedelta, timezone
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
    "time_sessions",
)

# Dropped and recreated by `rebuild` alongside the tables. A view holds no
# rows, so this is not about the data — it is so that changing the membership
# rule takes effect on an index file that predates the change. `CREATE VIEW IF
# NOT EXISTS` over a stale definition is a silent no-op, and the stale
# definition is exactly the thing a reindex is being run to get rid of.
VIEWS = ("membership",)

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
    -- them belongs in the registry. See the `membership` view.
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

-- Measured stretches of work on a folder. One row per timer session.
--
-- Keyed on the session rather than the folder, which is what keeps this
-- summable *and* idempotent: totals are `sum(seconds)` over these rows, and a
-- log line applied twice replaces its own row instead of adding to it. See
-- `log-time` in eventlog.py for the argument.
--
-- `day` is stored rather than derived from `ts` because every other read here
-- compares date strings and exactly one module is allowed to do timezone
-- math. It is what lets a total be cut by year for an album and by month for
-- the spine, off the same key shape the entries use.
--
-- Nothing here is a fact the log does not carry: drop the table, replay, and
-- every row comes back identical.
CREATE TABLE IF NOT EXISTS time_sessions (
    id        TEXT PRIMARY KEY,
    folder_id TEXT NOT NULL,
    seconds   INTEGER NOT NULL,
    day       TEXT NOT NULL,
    ts        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS time_sessions_by_folder ON time_sessions (folder_id, day);

-- ── The membership rule, and the only place it is written ─────────────────
--
-- An entry is in a folder when one of its tags is mapped to that folder, when
-- it was filed there by hand, or when its `--directive` names the folder. All
-- three are resolved here, at read time, and none of them is stored — see the
-- module docstring for why a junction table would be wrong in between mapping
-- changes.
--
-- A view rather than four SQL strings. The rule used to be spelled once per
-- query *shape* — one for a folder's entries, one for the complement, one for
-- every pair at once, one inline in the shelf, and three separate queries in
-- `home_folder` — and they had to agree by hand. They did not: the docstring
-- on `folder_entries` records the read that had never heard of a directive,
-- and the comment above `_shelf_buckets`'s union records the one that was
-- taught about it afterwards. A view is still resolved, still stored nowhere,
-- and is now the one edit a fourth route would need.
--
-- `route` ranks the ways in, most deliberate first: filed by hand, then a
-- mapped tag, then a directive. `key` is the tag a tag-route came in by and
-- empty otherwise, which is what lets `home_folder` break its tie the way it
-- always did — on the tag's name. Consumers that want *pairs* rather than
-- routes ask for them: an entry reachable two ways is two rows here, and
-- `DISTINCT` is how a caller says it does not care which way.
CREATE VIEW IF NOT EXISTS membership AS
    SELECT ef.entry_id AS entry_id, ef.folder_id AS folder_id,
           0 AS route, '' AS key
      FROM entry_folders ef
    UNION ALL
    SELECT et.entry_id, ft.folder_id, 1 AS route, et.tag
      FROM entry_tags et JOIN folder_tags ft USING (tag)
    UNION ALL
    SELECT e.id, fn.folder_id, 2 AS route, ''
      FROM entries e JOIN folder_names fn ON fn.name_key = e.directive
     WHERE e.directive <> '';
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
    name at read time instead, and stores nothing. See the `membership` view.

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


# Everything below replaces `fold()` and the nineteen targeted mirrors.

# The columns of `entries` that hold a JSON array. Named once because both the
# upsert and the placeholder below have to agree with the schema about which
# ones cannot be an empty string.
_JSON_COLUMNS = frozenset(
    ("folders", "times", "patterns", "places", "todo_lines", "todo_done", "media")
)

# Every column of an `entries` row is derived from the capture event except
# `todo_done`, which is the fold of the check events that landed on it. So a
# capture line arriving twice — a restored backup, an interrupted write —
# rewrites the derived half and leaves the ticks alone. Spelled off `COLUMNS`
# rather than by hand so a new column cannot be forgotten here.
_ENTRY_UPSERT = (
    f"INSERT INTO entries ({COLUMNS}) VALUES ({PLACEHOLDERS}) "
    "ON CONFLICT (id) DO UPDATE SET "
    + ", ".join(
        f"{name} = excluded.{name}"
        for name in (c.strip() for c in COLUMNS.split(","))
        if name not in ("id", "todo_done")
    )
)


# An `entries` row with nothing in it but an id, for the events that reach the
# index before the capture they belong to. `ts = ''` is what marks one: every
# real capture has one, and no read wants a row without it.
_ENTRY_PLACEHOLDER = (
    f"INSERT OR IGNORE INTO entries ({COLUMNS}) VALUES ("
    + ", ".join(
        "?"
        if name == "id"
        else ("'[]'" if name in _JSON_COLUMNS else "''")
        for name in (c.strip() for c in COLUMNS.split(","))
    )
    + ")"
)


def _folder_exists(conn: sqlite3.Connection, folder_id: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM folders WHERE id = ? LIMIT 1", (folder_id,)
        ).fetchone()
        is not None
    )


def _claim_name(conn: sqlite3.Connection, folder_id: str, name: str) -> None:
    """This folder answers to `name` from now on, and nothing else does.

    `INSERT OR REPLACE` on the name key is the taking-back: a name belongs to
    one folder, so a second folder called Admin takes `admin` off the one that
    used to be called it.
    """
    key = normalize_tag(name)
    if not key:
        return
    conn.execute(
        "INSERT OR REPLACE INTO folder_names (name_key, folder_id) VALUES (?, ?)",
        (key, folder_id),
    )


def apply(conn: sqlite3.Connection, event: dict) -> None:
    """Put one event into the tables. **The transition table, and the only
    copy of it.**

    Why it is shaped this way
    -------------------------
    This used to be two functions. `fold()` replayed the whole log into
    dictionaries and `rebuild()` bulk-loaded them; beside it sat nineteen
    "targeted mirrors" — `add_folder`, `rename_group`, `set_manual_folder` and
    the rest — which `store.py` called after appending, so that the index did
    not have to be rebuilt on every keystroke. Twenty-two event kinds, each
    implemented twice, in two files, with nothing but a hand-kept checklist in
    the tests to notice when the two disagreed.

    They did disagree. `delete-folder` dropped the folder's chapter names in
    the fold and left them behind in the mirror, so a folder deleted and an
    index rebuilt were two different databases — latent, because nothing reads
    a chapter name for a folder that is gone, and exactly the shape of thing
    that is found the hard way. There is one implementation now, so there is
    nothing left to keep in step: `rebuild()` is this function over every
    event, and a write is this function over one.

    **It does not open a transaction.** The caller owns that — `rebuild` wraps
    the whole replay in one, `Store._commit` wraps one event — because the
    unit of atomicity is the caller's, not the event's.

    **It is tolerant, the way the fold was.** An event naming a folder that
    does not exist — deleted, or a line restored out of order from a backup —
    is dropped rather than resurrecting it. Most of that falls out of `UPDATE
    … WHERE id = ?` touching no rows; where it does not, the guard is written
    out.
    """
    kind = event["kind"]
    subject = event["id"]

    # ── Entries ───────────────────────────────────────────────────────────
    if kind == eventlog.CAPTURE:
        # Whether anything is already filed under this id decides how much
        # work the rest of this branch is. On a replay it almost never is —
        # each capture line is seen once — and the two DELETEs below are then
        # provably no-ops on an empty index. One primary-key lookup is cheaper
        # than two b-tree deletes, and a replay does this fifty thousand times.
        prior = conn.execute(
            "SELECT 1 FROM entries WHERE id = ? LIMIT 1", (subject,)
        ).fetchone()

        row, tags = _row(event, [])
        conn.execute(_ENTRY_UPSERT, row)

        if prior is not None:
            conn.execute("DELETE FROM entry_tags WHERE entry_id = ?", (subject,))
        conn.executemany(
            "INSERT INTO entry_tags (entry_id, tag) VALUES (?, ?)",
            [(subject, tag) for tag in tags],
        )

        # Reminders are derived from the line and the moment it was written,
        # so a replayed capture produces the rows it produced the first time.
        # Upserted rather than deleted and rewritten, because `dismissed` is
        # *not* derived — it is the fold of the dismiss events, and throwing
        # the row away would throw that away with it.
        reminders = derive_reminders(event)
        conn.executemany(
            "INSERT INTO reminders (entry_id, line, line_text, due_at, dismissed) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (entry_id, line) DO UPDATE SET "
            "line_text = excluded.line_text, due_at = excluded.due_at",
            reminders,
        )
        if prior is not None:
            # Lines this text no longer names a time on — a capture rewritten
            # by a replayed duplicate, or a dismissal that was holding a line
            # that turned out not to be a reminder at all.
            lines = [r[1] for r in reminders]
            if lines:
                marks = ", ".join("?" * len(lines))
                conn.execute(
                    f"DELETE FROM reminders WHERE entry_id = ? AND line NOT IN ({marks})",
                    [subject, *lines],
                )
            else:
                conn.execute("DELETE FROM reminders WHERE entry_id = ?", (subject,))

    elif kind in (eventlog.CHECK, eventlog.UNCHECK):
        # Read-modify-write on the JSON list rather than a `todo_done` table.
        # The column is what every read wants — one row, one entry — and a
        # tick is rare enough that the extra select does not show.
        #
        # The placeholder is the out-of-order case, and it is a real one: a
        # restored backup can put a `check` on disk with a `ts` that sorts
        # ahead of the capture it belongs to, and the tick must still land.
        # A row with nothing in it holds the ticks until the capture arrives
        # and fills the rest in around them — the upsert above leaves
        # `todo_done` alone precisely so it can. A placeholder whose capture
        # never arrives is swept at the end of the replay; see `_sweep_lost`.
        conn.execute(_ENTRY_PLACEHOLDER, (subject,))
        row = conn.execute(
            "SELECT todo_done FROM entries WHERE id = ?", (subject,)
        ).fetchone()
        done = set(json.loads(row["todo_done"]))
        line = int(event.get("line", 0))
        done.add(line) if kind == eventlog.CHECK else done.discard(line)
        conn.execute(
            "UPDATE entries SET todo_done = ? WHERE id = ?",
            (json.dumps(sorted(done)), subject),
        )

    elif kind == eventlog.ATTACH_MEDIA:
        row = conn.execute(
            "SELECT media FROM entries WHERE id = ?", (subject,)
        ).fetchone()
        if row is not None:
            attached = json.loads(row["media"])
            for ref in event.get("media", []):
                if ref not in attached:  # a replayed line must not duplicate
                    attached.append(ref)
            conn.execute(
                "UPDATE entries SET media = ? WHERE id = ?",
                (json.dumps(attached, ensure_ascii=False), subject),
            )

    elif kind == eventlog.DISMISS:
        # Same placeholder trick, for the same reason: `dismissed` is the one
        # column of a reminder row that is *not* derived from the line, so a
        # dismissal that arrives ahead of its capture has to wait somewhere.
        # The capture's upsert fills in `line_text` and `due_at` around it, and
        # drops the row again if that line turned out not to be a reminder.
        line = int(event.get("line", 0))
        conn.execute(
            "INSERT OR IGNORE INTO reminders "
            "(entry_id, line, line_text, due_at, dismissed) VALUES (?, ?, '', '', 1)",
            (subject, line),
        )
        conn.execute(
            "UPDATE reminders SET dismissed = 1 WHERE entry_id = ? AND line = ?",
            (subject, line),
        )

    # ── Folders ───────────────────────────────────────────────────────────
    elif kind == eventlog.CREATE_FOLDER:
        conn.execute(
            "INSERT OR REPLACE INTO folders "
            "(id, name, color, created_ts, state, overview, overview_media) "
            "VALUES (?, ?, ?, ?, '', '', '')",
            (subject, event.get("text", ""), event.get("color", ""), event["ts"]),
        )
        _claim_name(conn, subject, event.get("text", ""))

    elif kind == eventlog.RENAME_FOLDER:
        if _folder_exists(conn, subject):
            conn.execute(
                "UPDATE folders SET name = ? WHERE id = ?",
                (event.get("text", ""), subject),
            )
            # The old name is not dropped: entries written `--oldname` reach
            # this folder by it, and a rename must not un-file them.
            _claim_name(conn, subject, event.get("text", ""))

    elif kind == eventlog.SET_STATE:
        conn.execute(
            "UPDATE folders SET state = ? WHERE id = ?",
            (event.get("text", ""), subject),
        )

    elif kind == eventlog.SET_OVERVIEW:
        conn.execute(
            "UPDATE folders SET overview = ? WHERE id = ?",
            (event.get("text", ""), subject),
        )

    elif kind == eventlog.SET_OVERVIEW_MEDIA:
        # A list, because that is the field the log already has for a media
        # ref. One entry, or none to clear it.
        refs = event.get("media") or []
        conn.execute(
            "UPDATE folders SET overview_media = ? WHERE id = ?",
            (refs[0] if refs else "", subject),
        )

    # ── Time ──────────────────────────────────────────────────────────────
    elif kind == eventlog.LOG_TIME:
        folder_id = event.get("folder") or ""
        # A session on a folder that has since been deleted is dropped, the
        # same way `set-group` checks. The folder is the only thing that makes
        # the number mean anything — an hour attributed to nothing is not a
        # figure anyone can read, and the event stays in the log either way.
        if folder_id and _folder_exists(conn, folder_id):
            conn.execute(
                "INSERT OR REPLACE INTO time_sessions (id, folder_id, seconds, day, ts) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    subject,
                    folder_id,
                    max(0, int(event.get("seconds") or 0)),
                    event.get("day", ""),
                    event.get("ts", ""),
                ),
            )

    elif kind == eventlog.UNLOG_TIME:
        conn.execute("DELETE FROM time_sessions WHERE id = ?", (subject,))

    elif kind == eventlog.DELETE_FOLDER:
        conn.execute("DELETE FROM folders WHERE id = ?", (subject,))
        # Cascade, the same one Prisma declares on FolderTag and the same one
        # the source gets from `onDelete: Cascade`. A mapping to a folder that
        # no longer exists would make its tag look claimed.
        conn.execute("DELETE FROM folder_tags WHERE folder_id = ?", (subject,))
        conn.execute("DELETE FROM entry_folders WHERE folder_id = ?", (subject,))
        conn.execute("DELETE FROM folder_names WHERE folder_id = ?", (subject,))
        conn.execute("DELETE FROM folder_groups WHERE folder_id = ?", (subject,))
        # The half the targeted mirror used to miss.
        conn.execute("DELETE FROM chapter_names WHERE folder_id = ?", (subject,))
        # Time goes with the folder, unlike the entries. An entry is only
        # *resolved* into a folder and survives it being deleted intact; a
        # session is a measurement *of* that folder and cannot be re-resolved
        # onto anything. Leaving the rows would make `sum(seconds)` count time
        # against a folder nothing can open.
        conn.execute("DELETE FROM time_sessions WHERE folder_id = ?", (subject,))

    # ── The shelf ─────────────────────────────────────────────────────────
    elif kind == eventlog.SET_GROUP:
        year = event.get("year") or ""
        name = event.get("text", "")
        if year and _folder_exists(conn, subject):
            if not name:
                conn.execute(
                    "DELETE FROM folder_groups WHERE folder_id = ? AND year = ?",
                    (subject, year),
                )
            else:
                # First naming wins the ordering slot. Moving another folder
                # into an existing group must not jump that group to the end
                # of the shelf; a group nobody has named before goes one past
                # the highest slot there is, which is where this event stands.
                row = conn.execute(
                    "SELECT seq FROM folder_groups WHERE year = ? AND name = ? LIMIT 1",
                    (year, name),
                ).fetchone()
                if row is None:
                    top = conn.execute(
                        "SELECT coalesce(max(seq), -1) AS s FROM folder_groups"
                    ).fetchone()
                    slot = top["s"] + 1
                else:
                    slot = row["seq"]
                conn.execute(
                    "INSERT INTO folder_groups (folder_id, year, name, seq) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT (folder_id, year) "
                    "DO UPDATE SET name = excluded.name, seq = excluded.seq",
                    (subject, year, name, slot),
                )

    elif kind == eventlog.RENAME_GROUP:
        year = event.get("year") or ""
        new = event.get("text", "")
        if year and new and new != subject:
            # A plain rename carries its own slot across untouched; a rename
            # *onto an existing group* adopts that group's slot, because the
            # survivor is the older of the two and the shelf must not reorder
            # itself because you renamed something into it.
            row = conn.execute(
                "SELECT seq FROM folder_groups WHERE year = ? AND name = ? LIMIT 1",
                (year, new),
            ).fetchone()
            if row is None:
                conn.execute(
                    "UPDATE folder_groups SET name = ? WHERE year = ? AND name = ?",
                    (new, year, subject),
                )
            else:
                conn.execute(
                    "UPDATE folder_groups SET name = ?, seq = ? "
                    "WHERE year = ? AND name = ?",
                    (new, row["seq"], year, subject),
                )

    elif kind == eventlog.ORDER_GROUPS:
        # `id` is the year: what is being arranged is the shelf, not any one
        # of the groups standing on it.
        _, drawn = groups_for(conn, subject)
        for name, slot in order_seqs(drawn, event.get("order") or []).items():
            conn.execute(
                "UPDATE folder_groups SET seq = ? WHERE year = ? AND name = ?",
                (slot, subject, name),
            )

    elif kind == eventlog.DELETE_GROUP:
        year = event.get("year") or ""
        if year:
            # Un-groups its folders and nothing else — no folder and no entry
            # is touched, and there is nothing else a group could be holding.
            conn.execute(
                "DELETE FROM folder_groups WHERE year = ? AND name = ?",
                (year, subject),
            )

    elif kind == eventlog.NAME_CHAPTER:
        year = event.get("year") or ""
        month = int(event.get("month") or 0)
        # `unfiled` is a real album to name a chapter in and is the one
        # subject here that is not a folder id.
        known = subject == UNFILED_ALBUM or _folder_exists(conn, subject)
        if known and year and 1 <= month <= 12:
            conn.execute(
                "DELETE FROM chapter_names "
                "WHERE folder_id = ? AND year = ? AND month = ?",
                (subject, year, month),
            )
            # An empty name is a deletion, which is what hands the chapter
            # back to the reader that names it from your own words.
            if event.get("text", ""):
                conn.execute(
                    "INSERT INTO chapter_names (folder_id, year, month, name) "
                    "VALUES (?, ?, ?, ?)",
                    (subject, year, month, event.get("text", "")),
                )

    # ── Tags ──────────────────────────────────────────────────────────────
    elif kind == eventlog.LIFT_TAG:
        # No folder guard, and deliberately: a tag is not a folder's property.
        # Most tags worth lifting are ones nothing ever claimed, and a tag
        # lifted today must stay lifted through the folder that later claims
        # it being created, renamed and deleted.
        if subject:
            conn.execute(
                "INSERT OR IGNORE INTO lifted_tags (tag) VALUES (?)", (subject,)
            )

    elif kind == eventlog.UNLIFT_TAG:
        conn.execute("DELETE FROM lifted_tags WHERE tag = ?", (subject,))

    elif kind == eventlog.MAP_TAG:
        tag = event.get("tag")
        if tag and _folder_exists(conn, subject):
            # Moves the tag off whatever held it before: one tag, one folder.
            conn.execute(
                "INSERT OR REPLACE INTO folder_tags (tag, folder_id) VALUES (?, ?)",
                (tag, subject),
            )

    elif kind == eventlog.UNMAP_TAG:
        tag = event.get("tag")
        if tag:
            # Only unmap what this folder actually holds: an `unmap-tag` that
            # arrives after the tag moved elsewhere must not steal it back.
            conn.execute(
                "DELETE FROM folder_tags WHERE tag = ? AND folder_id = ?",
                (tag, subject),
            )

    # ── Filing by hand ────────────────────────────────────────────────────
    elif kind == eventlog.ASSIGN:
        folder_id = event.get("folder")
        if folder_id and _folder_exists(conn, folder_id):
            # Replaces, never adds — `assignFolderId` overwrites the whole
            # array in the source, and the assign menu is a radio group.
            conn.execute("DELETE FROM entry_folders WHERE entry_id = ?", (subject,))
            conn.execute(
                "INSERT INTO entry_folders (entry_id, folder_id) VALUES (?, ?)",
                (subject, folder_id),
            )

    elif kind == eventlog.UNASSIGN:
        folder_id = event.get("folder")
        if folder_id:
            conn.execute(
                "DELETE FROM entry_folders WHERE entry_id = ? AND folder_id = ?",
                (subject, folder_id),
            )


def _sweep_lost(conn: sqlite3.Connection) -> None:
    """Throw away what is left over an entry the log never captured.

    The replay's one extra step, and the only thing `rebuild` does that
    `apply` does not. A live write cannot produce any of this — the store
    refuses to tick, dismiss or file an entry that is not there — but a log
    can: a `check` whose capture line was lost, or a filing restored from a
    backup whose other half was not. `apply` holds those in a placeholder
    rather than dropping them, because the capture usually *is* still coming,
    a few lines further down. This is what happens when it is not.

    It is garbage collection, not a transition, which is why it is here rather
    than folded into a twenty-third branch of `apply`.
    """
    conn.execute(
        "DELETE FROM reminders WHERE entry_id IN "
        "(SELECT id FROM entries WHERE ts = '')"
    )
    conn.execute("DELETE FROM entries WHERE ts = ''")
    # An entry filed by hand that was never captured. It has to go rather than
    # be left invisible: the membership view reaches `entry_folders` without
    # touching `entries`, so an orphan would show up in a folder's count and
    # nowhere else — a figure with nothing behind it.
    conn.execute(
        "DELETE FROM entry_folders WHERE entry_id NOT IN (SELECT id FROM entries)"
    )
    conn.execute(
        "DELETE FROM entry_tags WHERE entry_id NOT IN (SELECT id FROM entries)"
    )


def rebuild(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    """Drop and replay. Returns (events indexed, log warnings).

    One `apply` per event, in `ts` order, inside one transaction. There is no
    separate bulk-load path any more: a rebuild and a write are the same code
    reaching the same tables, which is what makes "delete the index file at any
    moment" a promise rather than a hope.
    """
    events, warnings = eventlog.read_all()

    with conn:
        for view in VIEWS:
            conn.execute(f"DROP VIEW IF EXISTS {view}")
        for table in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.executescript(SCHEMA)
        for event in events:
            apply(conn, event)
        _sweep_lost(conn)

    return len(events), warnings


def home_folder(conn: sqlite3.Connection, entry_id: str) -> str | None:
    """Which album to open in order to be looking at this entry.

    Resolved, never stored — the same rule as membership itself. An entry's
    `folders` are *tags*; a tag points at a folder or at nothing, and an entry
    can also have been filed by hand. Either route counts, and a hand filing
    wins because it is the one somebody chose deliberately.

    `None` means the unfiled pile, which is a real album you can open rather
    than an absence. An entry in two folders has two right answers and gets the
    first — this is a place to be taken to, not a claim about where it lives.

    The priority is `route` on the `membership` view, which exists so that this
    ordering is a fact about the rule rather than about this function: hand
    filed, then a mapped tag, then a directive — the directive last only
    because a mapped tag is the more specific statement when an entry carries
    both. Ties within the tag route break on the tag's name, which is what
    `key` carries and what the three separate queries this replaced did.
    """
    row = conn.execute(
        "SELECT folder_id FROM membership WHERE entry_id = ? "
        "ORDER BY route, key LIMIT 1",
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
                "SELECT folder_id, count(DISTINCT entry_id) AS n FROM membership "
                "GROUP BY folder_id"
            ).fetchall()
        }
        if counts
        else {}
    )

    # All-time, like `entry_count` beside it, and skipped with it: `vocab()`
    # wants neither and is called after every keystroke.
    clocked: dict[str, int] = folder_seconds(conn) if counts else {}

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "color": row["color"],
            "created_ts": row["created_ts"],
            "state": row["state"],
            "entry_count": tallies.get(row["id"], 0),
            "seconds": clocked.get(row["id"], 0),
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


def folder_seconds(
    conn: sqlite3.Connection, year: str | None = None
) -> dict[str, int]:
    """`folder id -> seconds logged`, for one year or for all of them.

    A sum over rows, computed on every read and stored nowhere — the same
    contract as `entry_count` beside it. Retuning nothing can make yesterday's
    hour disagree with the log, because the log is where the hour is.

    Folders with no sessions are absent rather than zero. Every caller is
    filling in a figure for a folder it already has, so a `.get(id, 0)` is the
    honest shape and a row of zeroes would just be a longer way to say it.
    """
    clause, args = _year_clause(year)
    # `day LIKE '2026-%'` rather than a range: the same predicate the rest of
    # this module cuts years with, off the same precomputed day key.
    rows = conn.execute(
        "SELECT folder_id, sum(seconds) AS n FROM time_sessions "
        f"WHERE 1 {clause} GROUP BY folder_id",
        args,
    ).fetchall()
    return {row["folder_id"]: int(row["n"] or 0) for row in rows}


def folder_time_volumes(
    conn: sqlite3.Connection, folder_id: str | None, year: str | None
) -> list[int]:
    """Twelve seconds-per-month totals, January first — the time-shaped twin of
    `_volumes`, and drawn on the same twelve bars.

    `folder_id=None` is the unfiled pile, which can never have any: a session
    is logged *against a folder* from that folder's own screen, so there is no
    gesture that produces an unfiled one.
    """
    out = [0] * 12
    if folder_id is None:
        return out
    clause, args = _year_clause(year)
    rows = conn.execute(
        "SELECT day, seconds FROM time_sessions WHERE folder_id = ?" + clause,
        [folder_id] + args,
    ).fetchall()
    for row in rows:
        out[int(row["day"][5:7]) - 1] += int(row["seconds"])
    return out


def time_sessions(
    conn: sqlite3.Connection, folder_id: str, year: str | None = None
) -> list[dict]:
    """One folder's sessions, newest first. What the album lists so a session
    logged by mistake can be found and taken back."""
    clause, args = _year_clause(year)
    rows = conn.execute(
        "SELECT id, seconds, day, ts FROM time_sessions WHERE folder_id = ?"
        + clause
        + " ORDER BY ts DESC, id DESC",
        [folder_id] + args,
    ).fetchall()
    return [
        {
            "id": row["id"],
            "seconds": int(row["seconds"]),
            "day": row["day"],
            "ts": row["ts"],
        }
        for row in rows
    ]


# ── Points: the one figure that counts a day ──────────────────────────────
#
# A day in a folder is worth **one point per entry, plus one per twenty
# minutes clocked**. Both halves are deliberate and neither is a measure of
# quality: an entry counts the same whether it is a word or a paragraph,
# because the app has never had an opinion about how much you wrote, and
# twenty minutes is a coarse enough grain that the clock cannot out-shout the
# writing — an eight-hour day is worth 24, which is a lot and is not infinite.
#
# Integer division, and it truncates. Nineteen minutes is worth nothing, and
# that is the honest reading of "every twenty minutes" rather than a rounding
# bug. It also keeps the sum idempotent in the same way `folder_seconds` is:
# these are folds over rows, computed on every read and stored nowhere.
#
# **Nothing here interprets.** The cap that keeps a very loud day from
# out-glowing a merely good one is a drawing decision and lives in the
# component that draws it; the numbers that leave this module are the counts
# themselves, uncapped, because the order of the shelf is a sum over them.
SECONDS_PER_POINT = 20 * 60

#: How far back the shelf looks when it asks what you are working on *now*.
#: A month, so a project you put down three weeks ago is still visibly warm
#: and one you finished in spring is not.
MOMENTUM_DAYS = 30


def points(entries: int, seconds: int) -> int:
    """A day's score. The one place the rule above is spelled."""
    return entries + seconds // SECONDS_PER_POINT


def folder_heat(
    conn: sqlite3.Connection, folder_id: str | None, year: str | None
) -> list[dict]:
    """A folder's days, oldest first — `{day, entries, seconds, points}`.

    Only days with something on them. A year is 365 cells and at most a
    couple of hundred of them are ever non-empty, so sending the empty ones
    would be sending the calendar, which the client can work out for itself.

    A day where a five-minute session was logged and nothing was written comes
    back with `points` of 0 rather than being dropped. It is a day you worked,
    the row is what the readout says when the cell is pressed, and a fold that
    silently forgot short sessions would be the same class of mistake as
    rounding them up.

    The unfiled pile has no clock and no overview to draw this on, so it is
    empty rather than an error — the same shape `folder_time_volumes` takes.
    """
    if folder_id is None:
        return []
    clause, args = _year_clause(year)
    made: dict[str, int] = {}
    for row in conn.execute(
        f"SELECT day, count(*) AS n FROM entries WHERE id IN ({_MEMBERSHIP})"
        + clause
        + " GROUP BY day",
        [folder_id] + args,
    ).fetchall():
        made[row["day"]] = int(row["n"])
    clocked: dict[str, int] = {}
    for row in conn.execute(
        "SELECT day, sum(seconds) AS n FROM time_sessions WHERE folder_id = ?"
        + clause
        + " GROUP BY day",
        [folder_id] + args,
    ).fetchall():
        clocked[row["day"]] = int(row["n"] or 0)
    return [
        {
            "day": day,
            "entries": made.get(day, 0),
            "seconds": clocked.get(day, 0),
            "points": points(made.get(day, 0), clocked.get(day, 0)),
        }
        for day in sorted(made.keys() | clocked.keys())
    ]


def momentum_window(today: str) -> tuple[str, str]:
    """The span the shelf is ordered by: `MOMENTUM_DAYS` ending today,
    inclusive of both ends. Given a day rather than read off a clock, because
    exactly one module in this codebase is allowed to know what time it is."""
    since = date.fromisoformat(today) - timedelta(days=MOMENTUM_DAYS - 1)
    return since.isoformat(), today


def momentum(
    conn: sqlite3.Connection, since: str, until: str
) -> dict[str, int]:
    """`folder id -> points` over one span of days, both ends inclusive.

    The shelf's sort key, and the reason it is computed here rather than
    folded out of `folder_heat` once per folder: that would be one membership
    resolution per card, which is precisely the O(folders x entries) read that
    `_shelf_buckets` exists to have stopped doing. Two queries, whatever the
    shelf holds.

    The span is not cut by the shelf's year. It is a rolling month and it
    crosses New Year the way the work does — asking on the 3rd of January
    what you have been doing lately and being told "nothing, the year is new"
    would be an answer about the calendar rather than about the work.

    Folders with nothing in the span are absent rather than zero, like
    `folder_seconds`; every caller is filling in a figure for a folder it
    already has.
    """
    made: dict[str, int] = {}
    for row in conn.execute(
        "SELECT m.folder_id AS folder_id, count(DISTINCT m.entry_id) AS n"
        "  FROM membership m"
        "  JOIN entries e ON e.id = m.entry_id"
        " WHERE e.day BETWEEN ? AND ?"
        " GROUP BY m.folder_id",
        (since, until),
    ).fetchall():
        made[row["folder_id"]] = int(row["n"])
    clocked: dict[str, int] = {}
    for row in conn.execute(
        "SELECT folder_id, sum(seconds) AS n FROM time_sessions "
        "WHERE day BETWEEN ? AND ? GROUP BY folder_id",
        (since, until),
    ).fetchall():
        clocked[row["folder_id"]] = int(row["n"] or 0)
    return {
        folder_id: points(made.get(folder_id, 0), clocked.get(folder_id, 0))
        for folder_id in made.keys() | clocked.keys()
    }


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

    This used to spell its own copy of the rule, which is how it came to be the
    one read that had never heard of a directive. It selects from the
    `membership` view now, so there is no copy to fall behind. Nothing here is
    stored as membership — see the module docstring.
    """
    return [
        _as_entry(row)
        for row in conn.execute(
            f"{SELECT_ENTRIES} WHERE id IN ({_MEMBERSHIP}) ORDER BY ts DESC, id DESC",
            (folder_id,),
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

# Membership, asked three ways. The rule itself is the `membership` view in
# SCHEMA and is not restated here — these are the shapes the reads want it in,
# and each is a plain select over the view rather than its own copy of the
# union. One folder id, once, where there used to be three.
#
# **The directive is the newest of the three routes and it replaced a stored
# thing.** A `--directive` used to travel as a tag — `derive()` appended it to
# the entry's tag list, and every folder claimed the tag of its own name at
# creation, so `--work` arrived through the ordinary mapping. It worked, and it
# put a word in the registry for every folder that nobody had ever typed. The
# registry is meant to hold the words the user chose — the non-obvious ones
# they want pointed somewhere — so the claim is gone and the directive resolves
# against the folder's name, at read time, storing nothing.
#
# The routes stay different on purpose. A tag is semantic and arbitrary and
# goes where you say it goes; a directive names the folder outright and needs
# no mapping to be understood. Both still resolve, neither is stored.
_MEMBERSHIP = "SELECT DISTINCT entry_id FROM membership WHERE folder_id = ?"

# The other side of it: an entry no folder claims. Not "has no tags" — a tag
# nothing has been mapped to leaves its entry unfiled, which is exactly the
# pile the shelf's dashed card is offering to sort out. A directive naming no
# folder leaves it there too, and the word is not lost: it is on the raw line
# and in the `directive` column, so the folder made for it next year collects
# every entry that has been waiting.
_UNFILED = "SELECT id FROM entries WHERE id NOT IN (SELECT entry_id FROM membership)"


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
        args = [folder_id] + args
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

    # Which folders claim which entries. This used to spell the three routes
    # out again, joined to `entries` three times with the year clause repeated
    # for each — the fourth copy of the rule, and the one that had to be taught
    # about directives separately. It reads the `membership` view now and joins
    # `entries` once, which is what keeps a year's shelf from carrying every
    # other year's memberships in memory.
    #
    # `DISTINCT` because the view is per *route*: an entry that carries a
    # mapped tag and was also filed by hand is two rows there and one member
    # here.
    membership: dict[str, list[str]] = {}
    for row in conn.execute(
        "SELECT DISTINCT m.entry_id AS entry_id, m.folder_id AS folder_id"
        "  FROM membership m"
        "  JOIN entries e ON e.id = m.entry_id"
        f" WHERE 1=1{clause}",
        args,
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
        args = [folder_id] + args
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
        # The album's clock: the total for this year, the twelve monthly
        # totals that draw beside `volumes`, and the sessions themselves so
        # one logged by mistake can be found and taken back. All three are
        # sums over `time_sessions` and none of them is stored.
        "seconds": folder_seconds(conn, year).get(folder_id or "", 0),
        "time_volumes": folder_time_volumes(conn, folder_id, year),
        "sessions": time_sessions(conn, folder_id, year) if folder_id else [],
        # Promises made in here and promises kept, off the same rows the twelve
        # bars are counted from. The unfiled pile gets one like any other album
        # — a todo nobody tagged is still a todo, and the pile is a real album
        # you can open.
        "todos": rows_tally(rows),
        "sentiments": folder_sentiments(conn, folder_id) if folder_id else [],
        # The heatmap: every day of this year that has anything on it, and
        # what it is worth. A reading like the sentiments beside it — the
        # counts are drawn, the brightness is the count, and nothing here says
        # whether a dim week was a bad one.
        "heat": folder_heat(conn, folder_id, year),
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


def shelf(conn: sqlite3.Connection, year: str | None, today: str | None = None) -> dict:
    """The year shelf: which albums exist, how big each is, when each was busy.

    Every album in the year, whether or not it has a lifecycle, plus the
    unfiled pile and a one-line handover to the year below. Albums with nothing
    in them this year are dropped rather than shown empty — an album is a year
    of a project, and a year you did not touch it is not one of them.

    **An empty folder is not that.** A folder with nothing in it in any year has
    no year it belongs to, so dropping it drops it from everywhere; it stays on
    whatever shelf you are looking at until something lands in it. See the note
    on the filter below.

    `today` is the caller's day — the clock is read in `store`, never here —
    and it is what makes the order mean anything. See the sort below.
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

    # One query for the whole shelf rather than one per card: this is the same
    # shape as `_shelf_buckets` above it, and for the same reason — a figure
    # every card carries should cost one read, not one per album.
    clocked = folder_seconds(conn, year)
    # What each project is worth over the last month, in the same points the
    # heatmap draws. Two queries for the whole shelf, and it is asked for once
    # here rather than per card — see `momentum`.
    warm = momentum(conn, *momentum_window(today)) if today else {}

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
                # Time logged into this album this year. `entry_count` above is
                # scoped to the year and `all_time_count` is not; this follows
                # `entry_count`, because the card is a card *about a year*.
                "seconds": clocked.get(record["id"], 0),
                "volumes": volumes,
                "months": _month_range(volumes),
                "chapters": len(_runs(volumes)),
                "lead": _lead_from(rows),
                # Empty for a folder in the loose grid above the groups, which
                # is where a folder starts and where most of them stay.
                "group": in_group.get(record["id"], ""),
                # The sort key, carried so the order has a stated cause rather
                # than being a rule you have to read the server to know. It is
                # **not a figure to draw**: a number per project that goes up
                # when you work and down when you stop is a score, and a score
                # is the thing the clock was allowed in here without becoming.
                "momentum": warm.get(record["id"], 0),
            }
        )
        _mark(record["id"], rows)

    # **Warmest first: the shelf is ordered by what you are doing now.**
    #
    # It used to be by the year's entry count, which is a fact about how big a
    # project got rather than about whether it is alive — a finished thing you
    # poured a spring into sat at the front of the shelf for the rest of the
    # year, above the one you actually opened this morning. Sorting on the last
    # month's points puts the shelf in the order you would put it in yourself
    # if you had to rewrite the list every Monday.
    #
    # Size is the tiebreak rather than the key, and it is what a shelf of a
    # past year falls back to entirely: momentum is about now, so every album
    # of 2024 has none of it and that shelf reads exactly as it always did.
    # Name last, so a reload can never reorder a list you are reading.
    albums.sort(key=lambda a: (-a["momentum"], -a["entry_count"], a["name"].lower()))

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
