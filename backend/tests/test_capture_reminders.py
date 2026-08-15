"""Reminders: a `{time}` and the moment it was typed, folded forward.

The resolver itself has 104 golden fixtures — none of that is retested here.
What is tested is the seam the port invented: the source writes a Reminder row
at submit time, and this derives the same rows on every rebuild from the two
things the log already holds. The property that buys is the one asserted
below: throw the index away and the reminders come back with the same dates,
because "two days" was two days from the day it was written and not from now.
"""
from __future__ import annotations

import json

from backend.capture import eventlog
from backend.capture.store import CaptureError, Store

import pytest


def append_raw(event: dict) -> None:
    """Write a log line by hand — the only way to write in the past."""
    with eventlog.log_path_for(event["day"]).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


def old_capture(entry_id: str, text: str, ts: str, day: str) -> dict:
    return {"ts": ts, "day": day, "kind": "capture", "id": entry_id, "text": text}


def test_a_time_token_becomes_a_reminder_dated_from_when_it_was_written(
    capture_store,
):
    append_raw(
        old_capture("aaa", "chase the invoice {2d}", "2026-01-01T09:00:00+00:00", "2026-01-01")
    )
    capture_store.reindex()

    due = capture_store.due_reminders()
    assert len(due) == 1
    assert due[0]["line_text"] == "chase the invoice {2d}"
    # Two days after the 1st, not two days after today.
    assert due[0]["due_at"].startswith("2026-01-03T09:00")


def test_a_reminder_that_has_not_come_due_is_not_shown(capture_store):
    capture_store.capture("far off {5y}")

    assert capture_store.due_reminders() == []


def test_a_line_with_no_future_time_makes_nothing(capture_store):
    capture_store.capture("<work> just a thought")
    capture_store.capture("a date already gone {01/01/2024}")

    assert capture_store.due_reminders() == []


def test_dismissing_appends_and_stops_it_coming_back(capture_store):
    append_raw(old_capture("aaa", "ring them {tmr}", "2026-01-01T09:00:00+00:00", "2026-01-01"))
    capture_store.reindex()

    capture_store.dismiss_reminder("aaa", 0)

    assert capture_store.due_reminders() == []
    kinds = [json.loads(line)["kind"] for line in _log_lines()]
    assert kinds[-1] == "dismiss"


def test_a_dismissal_survives_the_index_being_deleted(capture_store):
    append_raw(old_capture("aaa", "ring them {tmr}", "2026-01-01T09:00:00+00:00", "2026-01-01"))
    append_raw(old_capture("bbb", "and them {2d}", "2026-01-01T09:00:00+00:00", "2026-01-01"))
    capture_store.reindex()
    capture_store.dismiss_reminder("aaa", 0)
    before = capture_store.due_reminders()

    from backend.capture.config import INDEX_PATH

    INDEX_PATH.unlink()
    fresh = Store()
    fresh.start()
    try:
        assert fresh.due_reminders() == before
        assert len(before) == 1 and before[0]["entry_id"] == "bbb"
    finally:
        fresh.close()


def test_each_line_carries_its_own_reminder(capture_store):
    append_raw(
        old_capture(
            "aaa",
            "first thing {1d}\nnothing here\nthird thing {3d}",
            "2026-01-01T09:00:00+00:00",
            "2026-01-01",
        )
    )
    capture_store.reindex()

    due = capture_store.due_reminders()
    assert [r["line"] for r in due] == [0, 2]
    assert [r["line_text"] for r in due] == ["first thing {1d}", "third thing {3d}"]


def test_dismissing_something_that_was_never_captured_is_refused(capture_store):
    with pytest.raises(CaptureError):
        capture_store.dismiss_reminder("ghost", 0)


def test_reminders_are_stored_in_utc_so_the_due_test_is_a_string_compare(
    capture_store,
):
    """A duration inherits the writer's offset and an absolute date is UTC
    midnight. Left alone, the column would hold both and `due_at <= now`
    would compare `+07:00` against `+00:00` as text."""
    append_raw(
        old_capture(
            "aaa", "relative {2d}", "2026-01-01T09:00:00+07:00", "2026-01-01"
        )
    )
    append_raw(
        old_capture(
            "bbb", "absolute {02/01/2026}", "2026-01-01T09:00:00+07:00", "2026-01-01"
        )
    )
    capture_store.reindex()

    stored = capture_store.conn.execute("SELECT due_at FROM reminders").fetchall()
    assert all(row["due_at"].endswith("+00:00") for row in stored)


def _log_lines() -> list[str]:
    from backend.capture.config import LOG_DIR

    out: list[str] = []
    for path in sorted(LOG_DIR.glob("*.jsonl")):
        out += [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return out
