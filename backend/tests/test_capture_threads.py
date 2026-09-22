"""Threads: a deadline carried forward, and the chain of turns that carried it.

**What makes a thread is the hop**, and it is the whole of what these tests are
about. A `{}` nobody answered is a reminder and the banner already has it; a
reply carrying no `{}` of its own is an answer rather than a date being moved.
A thread is what you get when a prompt's reply sets the next prompt — which is
the shape "deadline management" actually has, and it is narrower than "any
reply chain" on purpose.

Nothing here is stored. `reply_to` is the link, `reminders` is the deadline,
and `capture` already dismisses the one a reply answers, so every assertion
below is a read over rows written for other reasons.
"""
from __future__ import annotations

import json

from backend.capture import eventlog, index


def append_raw(entry_id: str, text: str, ts: str, day: str) -> None:
    """Write a capture by hand — the only way to write one in the past, and the
    only way to have a prompt that has actually come due by the time a reply is
    typed. Same helper `test_capture_reminders.py` uses, for the same reason."""
    with eventlog.log_path_for(day).open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({"ts": ts, "day": day, "kind": "capture", "id": entry_id, "text": text})
            + "\n"
        )


def test_a_prompt_nobody_answered_is_not_a_thread(capture_store):
    """It is a reminder. The banner has it, and drawing it here as a thread of
    one turn would make this screen a second copy of that strip."""
    capture_store.capture("finish the intro {2d}")

    assert index.threads(capture_store.conn) == []


def test_a_reply_without_its_own_prompt_does_not_make_one(capture_store):
    """The reply answered it — the reminder is dismissed and nothing is being
    carried. That is a conversation, and the reading lens draws it."""
    root = capture_store.capture("finish the intro {2d}")
    capture_store.capture("done, finally", reply_to=root["id"])

    assert index.threads(capture_store.conn) == []


def test_the_hop_makes_a_thread(capture_store):
    root = capture_store.capture("finish the intro {2d}")
    moved = capture_store.capture("pushed it {3d}", reply_to=root["id"])

    threads = index.threads(capture_store.conn)
    assert len(threads) == 1
    assert [t["entry_id"] for t in threads[0]["turns"]] == [root["id"], moved["id"]]
    # Live: the newest turn carries a date that is still standing, and that is
    # the one the screen counts down to.
    assert threads[0]["closed"] is False
    assert threads[0]["due_at"] == threads[0]["turns"][-1]["due_at"]


def test_answering_a_prompt_that_came_due_puts_it_behind_you(capture_store):
    """The mechanic the whole screen leans on: `capture` dismisses the reminder
    a reply answers, so a turn that has been answered stops being pending and
    the newest one is the only date left standing. Written in the past, because
    a prompt typed a moment ago has not come due yet and so has nothing to
    dismiss."""
    append_raw("root-1", "finish the intro {2d}", "2026-01-01T09:00:00+00:00", "2026-01-01")
    capture_store.reindex()
    moved = capture_store.capture("pushed it {3d}", reply_to="root-1")

    turns = index.threads(capture_store.conn)[0]["turns"]
    assert [t["dismissed"] for t in turns] == [True, False]
    assert index.threads(capture_store.conn)[0]["due_at"] == turns[1]["due_at"]
    assert turns[1]["entry_id"] == moved["id"]


def test_a_chain_keeps_going_and_stays_in_order(capture_store):
    root = capture_store.capture("finish the intro {2d}")
    second = capture_store.capture("pushed it {3d}", reply_to=root["id"])
    third = capture_store.capture("pushed again {4d}", reply_to=second["id"])

    turns = index.threads(capture_store.conn)[0]["turns"]
    # Oldest first, root first: a spine is read forwards even though every
    # list in this app is read backwards.
    assert [t["entry_id"] for t in turns] == [
        root["id"],
        second["id"],
        third["id"],
    ]


def test_the_closing_turn_is_drawn(capture_store):
    """A reply with no new date ends the chain, and showing it is what lets a
    thread read as finished rather than as one you walked away from."""
    root = capture_store.capture("finish the intro {2d}")
    moved = capture_store.capture("pushed it {3d}", reply_to=root["id"])
    done = capture_store.capture("done, finally", reply_to=moved["id"])

    thread = index.threads(capture_store.conn)[0]
    assert thread["closed"] is True
    assert thread["due_at"] is None
    assert [t["entry_id"] for t in thread["turns"]][-1] == done["id"]
    assert thread["turns"][-1]["due_at"] is None


def test_dismissing_the_last_prompt_by_hand_closes_it_too(capture_store):
    """Closed is *nothing pending on the newest turn*, not "a reply with no
    date arrived". Telling the app to stop asking is the same answer."""
    root = capture_store.capture("finish the intro {2d}")
    moved = capture_store.capture("pushed it {3d}", reply_to=root["id"])
    capture_store.dismiss_reminder(moved["id"], 0)

    thread = index.threads(capture_store.conn)[0]
    assert thread["closed"] is True
    assert thread["due_at"] is None
    # The turn is still drawn, and still says it had a date.
    assert thread["turns"][-1]["due_at"] is not None
    assert thread["turns"][-1]["dismissed"] is True


def test_a_thread_is_not_cut_by_the_year(capture_store):
    """The one lens that is not. A thread routinely crosses a year — you answer
    in February something you asked in November — and half a conversation is
    not a smaller answer, it is a wrong one."""
    root = capture_store.capture("finish the intro {60d}")
    moved = capture_store.capture("pushed it {60d}", reply_to=root["id"])

    turns = index.threads(capture_store.conn)[0]["turns"]
    assert len(turns) == 2
    assert turns[1]["entry_id"] == moved["id"]


def test_the_folder_filter_matches_any_turn_not_only_the_root(capture_store):
    """A reply tagged into a different folder must not make a thread vanish
    from the folder you would look for it in."""
    film = capture_store.create_folder("film", ["film"])
    root = capture_store.capture("finish the intro {2d}")
    capture_store.capture("pushed it <film> {3d}", reply_to=root["id"])

    assert len(index.threads(capture_store.conn, index.InFolder(film["id"]))) == 1
    # And from the pile the root sits in, which is where it started.
    assert len(index.threads(capture_store.conn, index.UNFILED)) == 1


def test_a_thread_in_another_folder_is_filtered_out(capture_store):
    film = capture_store.create_folder("film", ["film"])
    capture_store.create_folder("garden", ["garden"])
    root = capture_store.capture("finish the intro <film> {2d}")
    capture_store.capture("pushed it <film> {3d}", reply_to=root["id"])

    assert len(index.threads(capture_store.conn, index.InFolder(film["id"]))) == 1
    assert index.threads(capture_store.conn, index.InFolder("garden")) == []


def test_a_turn_carries_its_promises(capture_store):
    """The user's rule — a todo with a `{}` in the same entry belongs here —
    falls out of the model rather than needing a section of its own: a turn is
    an entry, so its todo lines come with it."""
    root = capture_store.capture("finish the intro {2d}")
    capture_store.capture(
        "pushed it {3d}\n--todo restring first", reply_to=root["id"]
    )

    turns = index.threads(capture_store.conn)[0]["turns"]
    assert turns[1]["todo_lines"] == [1]
    assert turns[1]["todo_done"] == []


def test_threads_survive_the_index_being_deleted(capture_store):
    """Derived like everything else — the chain is `reply_to` and the dates are
    folded forward from the day each line was written."""
    root = capture_store.capture("finish the intro {2d}")
    capture_store.capture("pushed it {3d}", reply_to=root["id"])

    before = index.threads(capture_store.conn)
    capture_store.reindex()
    assert index.threads(capture_store.conn) == before
