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


def connect(path: Path | None = None) -> sqlite3.Connection:
    ensure_dirs()
    # Handlers run in FastAPI's threadpool; Store serialises access with a lock.
    conn = sqlite3.connect(path or INDEX_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
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


def events_for_domain(conn: sqlite3.Connection, domain: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT ts, day, node, kind, text, value FROM events WHERE domain = ? "
        "ORDER BY seq",
        (domain,),
    ).fetchall()
