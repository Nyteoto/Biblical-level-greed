"""SQLite index. Delete the file at any time — `rebuild()` replays the log and
reproduces it exactly. Nothing is ever stored here that isn't derived."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import eventlog
from .config import INDEX_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     TEXT NOT NULL,
    day    TEXT NOT NULL,
    domain TEXT NOT NULL,
    node   TEXT NOT NULL,
    kind   TEXT NOT NULL,
    text   TEXT NOT NULL DEFAULT '',
    value  REAL
);
CREATE INDEX IF NOT EXISTS events_by_node ON events (domain, node, seq);
CREATE INDEX IF NOT EXISTS events_by_day  ON events (day);
"""


def _open(target: Path) -> sqlite3.Connection | None:
    """Connect and prove the file is actually a database.

    `sqlite3.connect` opens anything — it does not read the file until the
    first statement, so a corrupt index surfaces later as an error from
    whatever query happened to run first. Probe it here instead.
    """
    # Handlers run in FastAPI's threadpool; Store serialises access with a lock.
    conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except sqlite3.DatabaseError:
        conn.close()
        return None
    return conn


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open the index, discarding it if it is unreadable.

    Deleting is always the right answer here and never costs anything: this
    file holds nothing that is not derived from the log, and `rebuild()`
    reproduces it exactly. Refusing to start because a disposable cache went
    bad would strand the user outside an app whose data is fine — and outside
    the very UI that would let them fix it.
    """
    ensure_dirs()
    target = Path(path or INDEX_PATH)
    conn = _open(target)
    if conn is None:
        target.unlink(missing_ok=True)
        conn = _open(target)
        if conn is None:  # a fresh file that still will not open: not our bug
            raise sqlite3.DatabaseError(f"cannot create an index at {target}")
    return conn


def rebuild(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    """Drop and replay. Returns (events indexed, log warnings)."""
    events, warnings = eventlog.read_all()

    with conn:
        conn.execute("DROP TABLE IF EXISTS events")
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO events (ts, day, domain, node, kind, text, value) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    e["ts"],
                    e["day"],
                    e["domain"],
                    e["node"],
                    e["kind"],
                    e.get("text", ""),
                    e.get("value"),
                )
                for e in events
            ],
        )

    return len(events), warnings


def add(conn: sqlite3.Connection, event: dict) -> None:
    """Mirror a freshly appended log line into the index."""
    with conn:
        conn.execute(
            "INSERT INTO events (ts, day, domain, node, kind, text, value) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event["ts"],
                event["day"],
                event["domain"],
                event["node"],
                event["kind"],
                event.get("text", ""),
                event.get("value"),
            ),
        )


def session_events(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every session/undo event, across all domains, in order.

    XP is a fold over this and nothing else — there is no xp table, because
    there is nothing to store that the log does not already say.
    """
    return conn.execute(
        "SELECT day, domain, node, kind FROM events "
        "WHERE kind IN ('session', 'undo') ORDER BY seq"
    ).fetchall()


def completion_events(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every complete/reopen event, across all domains, in order.

    XP needs these to tell acquisition from upkeep: a session logged after the
    gate was called is maintenance, and maintenance is paid on the decay
    cadence rather than per repetition.
    """
    return conn.execute(
        "SELECT day, domain, node, kind FROM events "
        "WHERE kind IN ('complete', 'reopen') ORDER BY seq"
    ).fetchall()


def unlock_events(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every unlock, with the price paid at the time.

    The price is read off the event rather than recomputed, so retuning the
    economy cannot retroactively change what something cost.
    """
    return conn.execute(
        "SELECT day, domain, node, value FROM events "
        "WHERE kind = 'unlock' ORDER BY seq"
    ).fetchall()


def events_for_domain(conn: sqlite3.Connection, domain: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT ts, day, node, kind, text, value FROM events WHERE domain = ? "
        "ORDER BY seq",
        (domain,),
    ).fetchall()
