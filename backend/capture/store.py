"""Holds capture's index connection and serialises access to it.

Deliberately a second Store rather than a member of the tech tree's: the two
apps share a data root and nothing else. `version` increments on every change
so the frontend can poll cheaply and know whether anything moved — the same
contract the tech tree's store offers, because the frontend already knows how
to consume it.
"""
from __future__ import annotations

import sqlite3
import threading

from . import eventlog, index
from .config import MAX_RAW_LEN


class CaptureError(Exception):
    """A refusal the user should read, not a bug."""


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.conn = index.connect()
        self.warnings: list[str] = []
        self.indexed = 0
        self.version = 0

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self.reindex()

    def reindex(self) -> None:
        """Throw the index away and replay the log.

        Reconnects first: if the sqlite file was deleted out from under us the
        old handle still points at an unlinked inode and writes into nothing.
        """
        with self._lock:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass
            self.conn = index.connect()
            self.indexed, self.warnings = index.rebuild(self.conn)
            self.version += 1

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    # -- reads -------------------------------------------------------------

    def entries(
        self, start: str | None = None, end: str | None = None, limit: int = 20
    ) -> list[dict]:
        with self._lock:
            return index.entries(self.conn, start, end, limit)

    def dates(self) -> dict[str, int]:
        with self._lock:
            return index.dates(self.conn)

    def vocab(self) -> dict[str, list[str]]:
        with self._lock:
            return index.vocab(self.conn)

    def cumulative(self, up_to: str) -> dict:
        with self._lock:
            return index.cumulative(self.conn, up_to)

    def entry(self, entry_id: str) -> dict | None:
        with self._lock:
            return index.get(self.conn, entry_id)

    # -- writes ------------------------------------------------------------

    def capture(self, raw_text: str) -> dict:
        """Append one captured line. Log first, then mirror into the index —
        if the process dies between the two, a reindex recovers the truth."""
        text = raw_text.strip()
        if not text:
            raise CaptureError("nothing to capture")
        if len(text) > MAX_RAW_LEN:
            raise CaptureError(f"too long (max {MAX_RAW_LEN} characters)")

        with self._lock:
            event = eventlog.append(eventlog.CAPTURE, eventlog.new_id(), text=text)
            index.add_capture(self.conn, event)
            self.version += 1
            return index.get(self.conn, event["id"])  # type: ignore[return-value]

    def toggle_line(self, entry_id: str, line: int) -> dict:
        """Tick or untick one `--todo` line.

        Reads the folded state and writes its inverse, both under one lock: the
        log has no notion of "the current value", so two toggles racing would
        otherwise both read unticked and both append `check`.
        """
        with self._lock:
            entry = index.get(self.conn, entry_id)
            if entry is None:
                raise CaptureError(f"no such entry: {entry_id}")
            if line not in entry["todo_lines"]:
                raise CaptureError(f"line {line} of that entry is not a todo")

            done = set(entry["todo_done"])
            if line in done:
                eventlog.append(eventlog.UNCHECK, entry_id, line=line)
                done.discard(line)
            else:
                eventlog.append(eventlog.CHECK, entry_id, line=line)
                done.add(line)

            index.set_done(self.conn, entry_id, sorted(done))
            self.version += 1
            return index.get(self.conn, entry_id)  # type: ignore[return-value]


store = Store()
