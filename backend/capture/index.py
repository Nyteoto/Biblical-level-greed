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
"""
from __future__ import annotations

import calendar
import json
import sqlite3
from datetime import date
from pathlib import Path

from . import eventlog
from .config import INDEX_PATH, ensure_dirs
from .parser import parse_entry

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
    todo_done  TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS entries_by_day ON entries (day, ts);
"""

COLUMNS = (
    "id, ts, day, raw_text, clean_text, folders, times, patterns, "
    "todo_lines, todo_done"
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

    The `--directive` joins `folders` rather than living in a field of its own.
    That matches what the source does once a folder exists with no explicit tag
    mappings: it upserts the folder's own lowercased name as a tag and merges
    it into the entry's folder list. With no folder registry here yet, that
    fallback *is* the behaviour — `--work` files the entry under `work`, the
    same place `<work>` would have put it.
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


def _row(event: dict, done: list[int]) -> tuple:
    d = derive(event.get("text", ""))
    return (
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
    )


def rebuild(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    """Drop and replay. Returns (events indexed, log warnings)."""
    events, warnings = eventlog.read_all()

    captures: dict[str, dict] = {}
    done: dict[str, set[int]] = {}
    for event in events:
        kind = event["kind"]
        if kind == eventlog.CAPTURE:
            # Last-wins on a duplicated id, which only happens if a log file
            # was restored twice. Re-applying the same line is then a no-op.
            captures[event["id"]] = event
            done.setdefault(event["id"], set())
        elif kind == eventlog.CHECK:
            done.setdefault(event["id"], set()).add(int(event.get("line", 0)))
        elif kind == eventlog.UNCHECK:
            done.setdefault(event["id"], set()).discard(int(event.get("line", 0)))

    with conn:
        conn.execute("DROP TABLE IF EXISTS entries")
        conn.executescript(SCHEMA)
        conn.executemany(
            f"INSERT INTO entries ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                _row(event, sorted(done.get(entry_id, set())))
                for entry_id, event in captures.items()
            ],
        )

    return len(events), warnings


def add_capture(conn: sqlite3.Connection, event: dict) -> None:
    """Mirror a freshly appended capture into the index."""
    with conn:
        conn.execute(
            f"INSERT OR REPLACE INTO entries ({COLUMNS}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _row(event, []),
        )


def set_done(conn: sqlite3.Connection, entry_id: str, done: list[int]) -> None:
    """Mirror a check/uncheck. The list is the folded result, not a delta."""
    with conn:
        conn.execute(
            "UPDATE entries SET todo_done = ? WHERE id = ?",
            (json.dumps(sorted(set(done))), entry_id),
        )


# ── Reads ─────────────────────────────────────────────────────────────────


def _as_entry(row: sqlite3.Row) -> dict:
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
    }


def get(conn: sqlite3.Connection, entry_id: str) -> dict | None:
    row = conn.execute(
        f"SELECT {COLUMNS} FROM entries WHERE id = ?", (entry_id,)
    ).fetchone()
    return _as_entry(row) if row else None


def entries(
    conn: sqlite3.Connection,
    start: str | None = None,
    end: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Newest first, as the log reads. `start`/`end` are inclusive day keys."""
    sql = f"SELECT {COLUMNS} FROM entries"
    args: list = []
    if start and end:
        sql += " WHERE day >= ? AND day <= ?"
        args += [start, end]
    sql += " ORDER BY ts DESC, id DESC LIMIT ?"
    args.append(limit)
    return [_as_entry(r) for r in conn.execute(sql, args).fetchall()]


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


def vocab(conn: sqlite3.Connection, recent: int = 500) -> dict[str, list[str]]:
    """What the autocomplete offers: every tag, time and pattern the user has
    actually written, most recent entries first (the source caps at 500 too).
    Sorted, because the trie's own ordering is insertion order and a stable
    input is what makes its suggestions stable."""
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
    return {
        "tags": sorted(tags),
        "times": sorted(times),
        "patterns": sorted(patterns),
    }
