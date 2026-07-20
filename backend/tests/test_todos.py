"""The checklist.

The only part of the app that is not a tech tree, and the only place where the
user asked for something to be *deleted*. It isn't: `done` is appended and the
live list is a fold, exactly like node completion. The item goes away, the
record does not.
"""
from __future__ import annotations

import pytest

from backend.app import todos


@pytest.fixture
def clean(data_dir):
    todos.path().unlink(missing_ok=True)
    return data_dir


def test_an_added_item_is_live(clean):
    todos.add("buy strings")
    assert [t["text"] for t in todos.live()] == ["buy strings"]


def test_ticking_removes_it_from_the_list(clean):
    item = todos.add("email the studio")
    todos.complete(item["id"])
    assert todos.live() == []


def test_ticking_removes_nothing_from_the_file(clean):
    """The user asked for completion to delete the item. It deletes it from the
    list; the log stays append-only like everything else here."""
    item = todos.add("book the HSK slot")
    todos.complete(item["id"])
    records, warnings = todos.read_all()
    assert not warnings
    assert [r["op"] for r in records] == ["add", "done"]
    assert records[0]["text"] == "book the HSK slot"


def test_the_list_does_not_reset_daily(clean):
    """No day filtering anywhere: an item stays until it is ticked. Things you
    meant to do do not stop mattering at midnight."""
    todos.add("restring the guitar")
    live = todos.live()
    assert len(live) == 1
    assert live[0]["added"]  # the day is recorded, and never used to expire it


def test_items_come_back_oldest_first(clean):
    """A list that never resets would otherwise bury the thing you have been
    avoiding under this morning's additions."""
    for text in ("first", "second", "third"):
        todos.add(text)
    assert [t["text"] for t in todos.live()] == ["first", "second", "third"]


def test_ticking_one_item_leaves_the_others(clean):
    a = todos.add("a")
    todos.add("b")
    todos.complete(a["id"])
    assert [t["text"] for t in todos.live()] == ["b"]


def test_empty_text_is_refused(clean):
    with pytest.raises(ValueError):
        todos.add("   ")


def test_ticking_an_unknown_id_is_harmless(clean):
    """The UI can double-fire on a slow connection; that must not corrupt
    anything or raise."""
    todos.add("still here")
    todos.complete("nope")
    assert [t["text"] for t in todos.live()] == ["still here"]


def test_ticking_twice_is_idempotent(clean):
    item = todos.add("once")
    todos.complete(item["id"])
    todos.complete(item["id"])
    assert todos.live() == []


def test_a_corrupt_line_is_skipped_and_reported(clean):
    todos.add("good")
    with todos.path().open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    records, warnings = todos.read_all()
    assert len(records) == 1
    assert warnings and "unparseable" in warnings[0]
    assert [t["text"] for t in todos.live()] == ["good"]


def test_no_file_yet_is_an_empty_list_not_an_error(clean):
    todos.path().unlink(missing_ok=True)
    assert todos.live() == []
    assert todos.read_all() == ([], [])
