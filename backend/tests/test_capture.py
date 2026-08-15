"""Capture: the log is the truth, the index is a projection of it.

These test the seams that the port introduced and the source did not have —
storing the raw line instead of the parsed one, deriving on replay, and
turning row mutations into events. The parser itself is covered by the golden
corpus (`python3 trophic/golden/verify_golden.py parser`, 1185 cases), not by
anything here.
"""
from __future__ import annotations

import json

from backend.capture import eventlog, index
from backend.capture.store import CaptureError, Store

import pytest


def log_lines() -> list[dict]:
    from backend.capture.config import LOG_DIR

    out = []
    for path in sorted(LOG_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def test_the_log_holds_the_raw_line_and_the_index_holds_the_parse(capture_store):
    entry = capture_store.capture("<job> shipped it \\win --todo tell them")

    assert log_lines()[0]["text"] == "<job> shipped it \\win --todo tell them"
    assert entry["clean_text"] == "<job> shipped it \\win tell them"
    assert entry["folders"] == ["job"]
    assert entry["patterns"] == ["win"]
    assert entry["todo_lines"] == [0]


def test_nothing_derived_is_written_to_the_log(capture_store):
    """The whole point of storing `raw_text`: a log line carries no parse.

    If folders or todo indices leaked into the log they would freeze at the
    parser version that wrote them, and a parser fix could never reach them.
    """
    capture_store.capture("<job> {tmr} \\win --todo x")

    assert set(log_lines()[0]) == {"ts", "day", "kind", "id", "text"}


def test_the_directive_files_the_entry_under_its_own_name(capture_store):
    """`--work-log` is stripped from the text but must not vanish silently —
    it files the entry exactly where `<work-log>` would have."""
    entry = capture_store.capture("--work-log shipped the parser")

    assert entry["clean_text"] == "shipped the parser"
    assert entry["folders"] == ["work-log"]


def test_deleting_the_index_loses_nothing(capture_store):
    """The claim the whole architecture rests on."""
    first = capture_store.capture("<job> a \\win --todo one")
    capture_store.capture("<home> b")
    capture_store.toggle_line(first["id"], 0)

    before = capture_store.entries(limit=100)

    from backend.capture.config import INDEX_PATH

    INDEX_PATH.unlink()
    rebuilt = Store()
    rebuilt.start()
    try:
        assert rebuilt.entries(limit=100) == before
        assert rebuilt.entry(first["id"])["todo_done"] == [0]
    finally:
        rebuilt.close()


def test_ticking_a_box_appends_and_never_edits(capture_store):
    entry = capture_store.capture("--todo write the notes")

    capture_store.toggle_line(entry["id"], 0)
    assert capture_store.entry(entry["id"])["todo_done"] == [0]

    capture_store.toggle_line(entry["id"], 0)
    assert capture_store.entry(entry["id"])["todo_done"] == []

    kinds = [line["kind"] for line in log_lines()]
    assert kinds == ["capture", "check", "uncheck"]


def test_a_line_that_is_not_a_todo_cannot_be_ticked(capture_store):
    entry = capture_store.capture("just a thought")

    with pytest.raises(CaptureError):
        capture_store.toggle_line(entry["id"], 0)
    assert [line["kind"] for line in log_lines()] == ["capture"]


def test_out_of_order_and_duplicated_lines_fold_the_same(capture_store):
    """A restored backup or an interrupted write produces both shapes. The
    fold is last-wins and sorts by `ts`, so neither changes the result."""
    entry = capture_store.capture("--todo x")
    entry_id = entry["id"]
    day = entry["day"]

    path = eventlog.log_path_for(day)
    with path.open("a", encoding="utf-8") as handle:
        # The same capture again (duplicate), and a check that sorts *before*
        # an uncheck already on disk.
        handle.write(json.dumps({**log_lines()[0]}) + "\n")
        handle.write(
            json.dumps(
                {
                    "ts": "2000-01-01T00:00:00+07:00",
                    "day": "2000-01-01",
                    "kind": "check",
                    "id": entry_id,
                    "line": 0,
                }
            )
            + "\n"
        )

    capture_store.reindex()
    entries = capture_store.entries(limit=100)
    assert len(entries) == 1  # the duplicate collapsed
    assert entries[0]["todo_done"] == [0]


def test_an_unreadable_line_costs_that_line_and_nothing_else(capture_store):
    entry = capture_store.capture("<job> good line")
    path = eventlog.log_path_for(entry["day"])
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json at all\n")

    capture_store.reindex()
    assert len(capture_store.entries(limit=10)) == 1
    assert capture_store.warnings and "unparseable" in capture_store.warnings[0]


def test_empty_and_oversized_captures_are_refused(capture_store):
    from backend.capture.config import MAX_RAW_LEN

    with pytest.raises(CaptureError):
        capture_store.capture("   \n  ")
    with pytest.raises(CaptureError):
        capture_store.capture("x" * (MAX_RAW_LEN + 1))
    assert log_lines() == []


def test_dates_and_vocab_come_off_the_index(capture_store):
    capture_store.capture("<job> \\win {tmr}")
    capture_store.capture("<home> \\win")

    day = capture_store.entries(limit=1)[0]["day"]
    assert capture_store.dates() == {day: 2}
    assert capture_store.vocab() == {
        "folders": [],
        "tag_to_folder": {},
        "tags": ["home", "job"],
        "times": ["tmr"],
        "patterns": ["win"],
    }


def test_capture_writes_nowhere_near_the_tech_tree(capture_store):
    """Sibling app, own subtree. If this ever fails, the two logs have started
    sharing a directory and one app's reindex can drop the other's events."""
    from backend.app import config as tree_config
    from backend.capture import config as capture_config

    capture_store.capture("<job> a line")

    assert capture_config.LOG_DIR != tree_config.LOG_DIR
    assert not list(tree_config.LOG_DIR.glob("*.jsonl"))


def test_the_index_derives_the_same_thing_the_parser_does(capture_store):
    """`derive` is the only place the parser's output is reshaped; keep it a
    pure function of the raw text so a rebuild is deterministic."""
    assert index.derive("<a> <a> \\x --b") == index.derive("<a> <a> \\x --b")
    assert index.derive("<a> --b")["folders"] == ["a", "b"]
