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
from datetime import timedelta, timezone

from backend.app.timeutil import now
from backend.capture import eventlog, index
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


@pytest.fixture
def client(capture_store):
    """The same wiring `test_capture_folders.py` uses: the app's own global
    store, reindexed onto this test's throwaway data dir."""
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.capture.store import store as global_store

    global_store.reindex()
    with TestClient(app) as test_client:
        yield test_client


# ── Replying to a reminder ────────────────────────────────────────────────
#
# The source's mechanic, ported: a `{time}` that has come due surfaces one
# prompt above the capture box, and `--reply` answers it. The command is
# stripped by the client — what is stored is the thought — and the link between
# the two entries rides on the capture event, because the line said "reply" and
# did not say to what.


def due_yesterday(store, days_ago: int = 3):
    """An entry whose reminder has already come due. `days_ago` sets how long
    ago it was written, which is what decides the order two of them queue in —
    two written in the same second would come due in the same second, and the
    tiebreak after that is an id nobody can predict."""
    from backend.capture import eventlog
    from backend.app.timeutil import now

    when = now() - timedelta(days=days_ago)
    event = eventlog.append(
        eventlog.CAPTURE,
        eventlog.new_id(),
        text="ring the shop about the enlarger {2d}",
        ts=when.isoformat(timespec="seconds"),
        day=when.date().isoformat(),
    )
    store.reindex()
    return event["id"]


def test_one_reminder_is_awaiting_an_answer_at_a_time(capture_store):
    """One prompt, oldest first. A list would invite a queue on screen, and a
    queue of prompts above the capture box is the opposite of a capture bar."""
    first = due_yesterday(capture_store, days_ago=9)
    second = due_yesterday(capture_store, days_ago=3)

    due = capture_store.due_reminders()
    assert [r["entry_id"] for r in due] == [first, second]
    assert due[0]["line"] == 0

    # Dealing with the first surfaces the second, and nothing else.
    capture_store.dismiss_reminder(first, 0)
    assert [r["entry_id"] for r in capture_store.due_reminders()] == [second]
    capture_store.dismiss_reminder(second, 0)
    assert capture_store.due_reminders() == []


def test_a_reply_links_to_the_entry_and_dismisses_its_reminder(capture_store):
    original = due_yesterday(capture_store)

    reply = capture_store.capture("they have one in on Thursday", reply_to=original)

    assert reply["reply_to"] == original
    # Answering a prompt is the most complete way of having dealt with it.
    assert capture_store.due_reminders() == []
    # And the thread reads from both ends.
    assert capture_store.entry(original)["replied_by"] == reply["id"]
    assert capture_store.entry(reply["id"])["reply_to"] == original


def test_the_reply_stores_the_thought_and_not_the_command(capture_store):
    """`--reply` is addressed to the app, not to the journal. The client strips
    it, exactly as the source does, and what lands in the log is what the reply
    said — so a rebuild has nothing to strip and the parser never sees it."""
    original = due_yesterday(capture_store)

    reply = capture_store.capture("they have one in on Thursday", reply_to=original)

    assert reply["raw_text"] == "they have one in on Thursday"
    assert "--reply" not in reply["raw_text"]


def test_a_reply_can_carry_its_own_reminder(capture_store):
    """The source resolves `{time}` on the stripped text, so a reply is an
    entry like any other and can start the next round of the conversation."""
    original = due_yesterday(capture_store)

    reply = capture_store.capture("ask again {2d}", reply_to=original)

    assert capture_store.entry(reply["id"])["times"] == ["2d"]
    assert [r["entry_id"] for r in capture_store.due_reminders()] == []
    reminders = index.upcoming_reminders(
        capture_store.conn, now().astimezone(timezone.utc).isoformat()
    )
    assert [r["entry_id"] for r in reminders] == [reply["id"]]


def test_replying_to_nothing_is_refused(capture_store):
    with pytest.raises(CaptureError, match="no such entry to reply to"):
        capture_store.capture("into the void", reply_to="deadbeef1234")
    assert capture_store.entries(limit=10) == []


def test_the_thread_survives_the_index_being_deleted(capture_store):
    """The link is on the event, so a replay rebuilds both directions of it."""
    original = due_yesterday(capture_store)
    reply = capture_store.capture("they have one in on Thursday", reply_to=original)

    from backend.capture.config import INDEX_PATH

    INDEX_PATH.unlink()
    fresh = Store()
    fresh.start()
    try:
        assert fresh.entry(reply["id"])["reply_to"] == original
        assert fresh.entry(original)["replied_by"] == reply["id"]
        # The dismissal replays too: the prompt does not come back.
        assert fresh.due_reminders() == []
    finally:
        fresh.close()


def test_the_reply_travels_over_the_wire(client):
    from backend.capture import eventlog
    from backend.app.timeutil import now as clock

    when = clock() - timedelta(days=3)
    original = eventlog.append(
        eventlog.CAPTURE,
        eventlog.new_id(),
        text="ring the shop {2d}",
        ts=when.isoformat(timespec="seconds"),
        day=when.date().isoformat(),
    )["id"]
    client.post("/api/capture/reindex")

    due = client.get("/api/capture/reminders").json()["reminders"]
    assert [r["entry_id"] for r in due] == [original]

    posted = client.post(
        "/api/capture/entries",
        json={"raw_text": "Thursday", "reply_to": original},
    )
    assert posted.status_code == 201, posted.text
    assert posted.json()["entry"]["reply_to"] == original
    assert client.get("/api/capture/reminders").json()["reminders"] == []
