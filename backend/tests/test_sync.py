"""Two machines, one log.

The app is single-machine now, but the same `data/` can still be written from
more than one checkout and reconciled by `git merge=union`, which concatenates
both sides of a conflict and preserves neither order nor uniqueness.

So the fold has to survive lines arriving **out of order** and **more than
once**. It already nearly did — sessions, completions and phases are all
last-wins, and todos are keyed by id — and these tests pin the two places it
didn't.
"""
from __future__ import annotations

import json

from backend.app import config, eventlog, index, state, todos

DOMAIN = """
id = "d"
title = "D"
priority = 1

[[node]]
id = "n"
title = "N"
tier = 1
estimate = 10
"""


def _log_path():
    return config.LOG_DIR / "2026-07.jsonl"


def _write_lines(lines):
    _log_path().write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def _event(ts, kind, day="2026-07-20", text=""):
    return {
        "ts": f"2026-07-20T{ts}+07:00",
        "day": day,
        "domain": "d",
        "node": "n",
        "kind": kind,
        **({"text": text} if text else {}),
    }


def test_events_are_ordered_by_timestamp_not_file_order(write_domain, view):
    """A merge can put a later event above an earlier one. The outcome must not
    depend on which machine's lines git happened to write first."""
    write_domain("d", DOMAIN)
    _write_lines(
        [
            _event("11:00:00", eventlog.UNDO),  # later event, written first
            _event("10:00:00", eventlog.SESSION),
        ]
    )
    node = view("d")["nodes"][0]
    assert node["checked_today"] is False  # the 11:00 undo still wins


def test_a_same_second_double_toggle_keeps_file_order(write_domain, view):
    """`session, undo, session` inside one second is a real double-click, and
    its correct outcome is *checked*. Nothing may reorder or collapse it."""
    write_domain("d", DOMAIN)
    _write_lines(
        [
            _event("10:00:00", eventlog.SESSION),
            _event("10:00:00", eventlog.UNDO),
            _event("10:00:00", eventlog.SESSION),
        ]
    )
    assert view("d")["nodes"][0]["checked_today"] is True


def test_duplicated_session_lines_are_harmless(write_domain, view):
    """Union merge repeats lines. Sessions are last-wins, so this is a no-op."""
    write_domain("d", DOMAIN)
    _write_lines([_event("10:00:00", eventlog.SESSION)] * 4)
    node = view("d")["nodes"][0]
    assert node["sessions_done"] == 1
    assert node["progress_done"] == 1


def test_backdated_events_sharing_a_timestamp_all_survive(write_domain, view):
    """Importing history writes many events in one second with different days.
    Nothing may treat those as the same event."""
    write_domain("d", DOMAIN)
    _write_lines(
        [
            _event("10:00:00", eventlog.SESSION, day=f"2026-07-{d:02d}")
            for d in (17, 18, 19, 20)
        ]
    )
    assert view("d")["nodes"][0]["sessions_done"] == 4


def test_a_merged_log_reindexes_to_the_same_state(write_domain, view, conn):
    """The index is disposable; the merged log is the truth."""
    write_domain("d", DOMAIN)
    _write_lines(
        [
            _event("10:00:00", eventlog.SESSION, day="2026-07-19"),
            _event("11:00:00", eventlog.SESSION, day="2026-07-20"),
        ]
    )
    before = view("d")["nodes"][0]["sessions_done"]
    index.rebuild(conn)
    assert view("d")["nodes"][0]["sessions_done"] == before == 2


# -- the checklist stream ---------------------------------------------------


def test_duplicated_todo_ops_are_idempotent(data_dir):
    """Keyed by item id, so applying an op twice changes nothing."""
    path = config.DATA_DIR / "todos.jsonl"
    add = {"ts": "2026-07-20T10:00:00+07:00", "day": "2026-07-20", "id": "x", "op": "add", "text": "a"}
    done = {"ts": "2026-07-20T11:00:00+07:00", "day": "2026-07-20", "id": "x", "op": "done"}
    path.write_text("\n".join(json.dumps(r) for r in [add, add, done, done]) + "\n")
    assert todos.live() == []


def test_todo_ops_out_of_order_still_resolve(data_dir):
    """`done` written above `add` by a merge must still remove the item."""
    path = config.DATA_DIR / "todos.jsonl"
    done = {"ts": "2026-07-20T11:00:00+07:00", "day": "2026-07-20", "id": "x", "op": "done"}
    add = {"ts": "2026-07-20T10:00:00+07:00", "day": "2026-07-20", "id": "x", "op": "add", "text": "a"}
    path.write_text("\n".join(json.dumps(r) for r in [done, add]) + "\n")
    assert todos.live() == []


def test_todos_added_in_the_same_second_keep_their_order(data_dir):
    """Stable sort: the checklist is oldest-first and a merge must not shuffle
    items that share a timestamp."""
    path = config.DATA_DIR / "todos.jsonl"
    rows = [
        {"ts": "2026-07-20T10:00:00+07:00", "day": "2026-07-20", "id": i, "op": "add", "text": i}
        for i in ("first", "second", "third")
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert [t["text"] for t in todos.live()] == ["first", "second", "third"]


def test_journal_events_survive_in_the_log_but_surface_nowhere(write_domain, view):
    """Journals merged into domain notes. The events are history and the log is
    append-only, so nothing is deleted — but the board stopped reading them, and
    a node no longer carries a journal at all."""
    write_domain("d", DOMAIN)
    _write_lines([_event("10:00:00", eventlog.JOURNAL, text="tried the new fingering")])
    node = view("d")["nodes"][0]
    assert "journal" not in node


def test_a_corrupt_index_is_discarded_rather_than_fatal(data_dir):
    """The index is disposable by design — SYNC.md tells the user to delete it
    whenever anything looks wrong. A corrupt one used to make that impossible:
    the app died on the first query with `file is not a database`, before the
    UI that would have let them fix it ever came up.

    A truncated write, a half-finished copy or a sync collision all produce
    this file, and none of them touch the log, so the data is fine. Discard and
    replay.
    """
    from backend.app import config, index

    config.INDEX_PATH.write_bytes(b"not a database, not even a little")

    conn = index.connect()
    try:
        indexed, _ = index.rebuild(conn)
        assert indexed == 0  # empty log in this fixture, but it opened at all
        assert config.INDEX_PATH.stat().st_size > 0
    finally:
        conn.close()
