"""Capture: the log is the truth, the index is a projection of it.

These test the seams that the port introduced and the source did not have —
storing the raw line instead of the parsed one, deriving on replay, and
turning row mutations into events. The parser itself is covered by the golden
corpus (`python3 trophic/golden/verify_golden.py parser`, 1185 cases), not by
anything here.
"""
from __future__ import annotations

import json
import re

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


def test_the_directive_is_kept_beside_the_tags_not_among_them(capture_store):
    """`--work-log` is stripped from the text but must not vanish silently.

    It is not a tag, though, and that is the whole distinction: a tag is a word
    you chose and pointed somewhere, a directive names a folder outright. The
    word survives in its own field — and on the raw line, as everything does —
    so a folder called Work log picks this entry up whenever it is made, which
    is what the source loses by resolving the directive at write time."""
    entry = capture_store.capture("--work-log shipped the parser")

    assert entry["clean_text"] == "shipped the parser"
    assert entry["folders"] == []
    assert entry["directive"] == "work-log"


def test_deleting_the_index_loses_nothing(capture_store):
    """The claim the whole architecture rests on."""
    first = capture_store.capture("<job> a \\win --todo one")
    capture_store.capture("<home> b")
    capture_store.toggle_line(first["id"], 0)

    before = capture_store.entries(limit=100)

    from backend.capture.config import INDEX_PATH

    rebuilt = Store(INDEX_PATH.with_name("index-replay.sqlite"))
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


def test_the_shelf_counts_todos_the_way_todo_tally_does(capture_store):
    """`_shelf_buckets` has sqlite count each entry's promises, which makes it
    a second implementation of `todo_tally` — the thing this codebase says not
    to have. It is allowed to exist because it is three times faster over the
    whole log and because of this test, which is what stops the two drifting.

    The case that separates a careless translation from a correct one is a
    `check` naming a line that is not a todo, on an entry that has todos of
    its own. A restored backup or an interrupted write produces exactly that,
    and `todo_tally` ignores the stray one. The obvious sqlite spelling —
    `json_array_length(todo_done)` — does not, and reports more promises kept
    than were ever made. The intersection has to be real.

    Note what this does *not* separate: which of the two lists the count
    iterates. Both directions measure the same intersection, and both are
    correct as long as neither list repeats a value. That was worth finding
    out rather than asserting — the first version of this test claimed the
    direction mattered and passed against a translation that reversed it.
    """
    folder = capture_store.create_folder("Bench", ["bench"])
    tag = folder["tags"][0]

    for text in (
        f"--todo sand the top <{tag}>",
        f"--todo oil it <{tag}>\n--todo wax it <{tag}>",
        f"nothing promised here <{tag}>",
    ):
        capture_store.capture(text)

    entries = capture_store.entries(limit=10)
    for entry in entries:
        for line in entry["todo_lines"][:1]:
            capture_store.toggle_line(entry["id"], line)

    # A stray check, straight into the log: a line index that is not a todo,
    # on an entry that *does* carry todos. On an entry with none, the cheap
    # `todo_lines = '[]'` guard answers 0 whatever the intersection says, and
    # the case proves nothing.
    promising = next(e for e in entries if len(e["todo_lines"]) > 1)
    eventlog.append(eventlog.CHECK, promising["id"], line=99)
    capture_store.reindex()

    conn = capture_store.conn
    truth = index.todo_tally(
        [
            {"todo_lines": e["todo_lines"], "todo_done": e["todo_done"]}
            for e in capture_store.entries(limit=100)
        ]
    )
    assert truth["made"] == 3 and truth["done"] == 2, truth

    buckets = index._shelf_buckets(conn, None)
    every = [row for rows in buckets.values() for row in rows]
    assert {
        "made": sum(r["made"] for r in every),
        "done": sum(r["done"] for r in every),
    } == truth

    # And through the shelf itself, where the figure is actually read.
    card = next(a for a in index.shelf(conn, None)["albums"] if a["id"] == folder["id"])
    assert card["todos"] == truth


def test_the_newest_first_reads_do_not_scan_the_whole_log(capture_store):
    """`entries()` and `vocab()` both ask for the newest handful of a table
    that only grows, and both are on hot paths — the log opens with one and
    the capture bar re-reads the other after every send. Without an index on
    `ts` sqlite serves them by scanning every row and sorting the lot in a
    temp b-tree, which is invisible until there is a lot of history and then
    is the slowest thing in the app.

    Pinned as a query *plan* rather than a duration: a timing test on a
    hundred rows would pass whatever the plan was, and the plan is the actual
    claim.
    """
    capture_store.capture("a line <garden>")
    conn = capture_store.conn

    plan = " ".join(
        row["detail"]
        for row in conn.execute(
            "EXPLAIN QUERY PLAN "
            + index.SELECT_ENTRIES
            + " ORDER BY ts DESC, id DESC LIMIT 20"
        )
    )
    assert "entries_by_ts" in plan, plan
    assert "TEMP B-TREE" not in plan, plan


def test_the_frontend_mirrors_the_capture_cap():
    """The bar refuses a too-long draft before it sends, which is the only
    reason the draft survives being refused — the server's answer arrives after
    the box has begun emptying. That only works while the two numbers agree,
    and they are declared in two files in two languages, so nothing but this
    notices when one of them moves.
    """
    from pathlib import Path

    from backend.capture.config import MAX_RAW_LEN

    source = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "lib"
        / "trophic"
        / "validation.ts"
    ).read_text(encoding="utf-8")

    match = re.search(r"export const MAX_RAW_LEN = (\d+);", source)
    assert match, "validation.ts no longer declares MAX_RAW_LEN"
    assert int(match.group(1)) == MAX_RAW_LEN


def test_dates_and_vocab_come_off_the_index(capture_store):
    capture_store.capture("<job> \\win {tmr} @helsinki")
    capture_store.capture("<home> \\win")

    day = capture_store.entries(limit=1)[0]["day"]
    assert capture_store.dates() == {day: 2}
    assert capture_store.vocab() == {
        "folders": [],
        "tag_to_folder": {},
        "tags": ["home", "job"],
        "times": ["tmr"],
        "patterns": ["win"],
        "places": ["helsinki"],
        "lifted": [],
    }


def test_a_place_is_a_tag_that_points_nowhere(capture_store):
    """`@place` captures like `\\pattern` and files like neither.

    The two halves that matter: a place reaches the index as its own list, and
    it does *not* reach `folders`. Only `<tag>` and `--directive` can put an
    entry anywhere, and a second route into folder membership is the one thing
    the folder model cannot survive — see TROPHIC.md.
    """
    capture_store.capture("coffee @helsinki with <work>")
    entry = capture_store.entries(limit=1)[0]

    assert entry["places"] == ["helsinki"]
    assert entry["folders"] == ["work"]  # the place is not in here
    assert entry["raw_text"] == "coffee @helsinki with <work>"


def test_an_email_address_is_not_a_place(capture_store):
    """The boundary rule, which forty parser fixtures pin from the other side."""
    capture_store.capture("email a@b.com about @oslo")
    assert capture_store.entries(limit=1)[0]["places"] == ["oslo"]


def test_the_log_keeps_to_its_own_subtree(capture_store):
    """The log lives under `data/capture/`, not loose in the data root.

    This used to assert that capture wrote nowhere near the tech tree's log,
    back when both shared a data root. The tree is gone and the subtree stayed,
    which is the right way round: `data/` is the disk, and what the user wrote
    is one directory inside it — alongside `media/`, which is the other thing
    that is theirs and has one copy.
    """
    from backend.capture import config as capture_config

    capture_store.capture("<job> a line")

    written = list(capture_config.LOG_DIR.glob("*.jsonl"))
    assert written
    for path in written:
        assert path.parent == capture_config.LOG_DIR
    assert not list(capture_config.DATA_DIR.glob("*.jsonl"))


def test_the_index_derives_the_same_thing_the_parser_does(capture_store):
    """`derive` is the only place the parser's output is reshaped; keep it a
    pure function of the raw text so a rebuild is deterministic."""
    assert index.derive("<a> <a> \\x --b") == index.derive("<a> <a> \\x --b")
    # The directive is beside the tags, never among them.
    assert index.derive("<a> --b")["folders"] == ["a"]
    assert index.derive("<a> --b")["directive"] == "b"


# ── The todo cap ──────────────────────────────────────────────────────────
#
# Ten open todos, enforced on the write. The rule is arithmetic rather than a
# special case: what stands open plus what this line adds must not exceed the
# cap, which refuses an eleventh added to ten and eleven in one line with the
# same sum. The log is append-only, so the refusal has to happen before the
# append — a capture that broke the rule could not be taken back.


def _fill(store, n: int) -> None:
    for i in range(n):
        store.capture(f"--todo item {i}")


def test_ten_todos_are_allowed(capture_store):
    _fill(capture_store, 10)
    assert capture_store.banner()["open"] == 10


def test_the_eleventh_todo_is_refused(capture_store):
    _fill(capture_store, 10)
    with pytest.raises(CaptureError):
        capture_store.capture("--todo one too many")


def test_a_refused_capture_never_reaches_the_log(capture_store):
    """The point of checking before the append. There is no way to unwrite a
    line, so a capture that breaks the rule must not be written at all."""
    _fill(capture_store, 10)
    before = len(log_lines())
    with pytest.raises(CaptureError):
        capture_store.capture("--todo one too many")

    assert len(log_lines()) == before
    assert capture_store.banner()["open"] == 10


def test_eleven_todos_in_one_entry_are_refused_whole(capture_store):
    """Typing faster is not a way past the limit. The whole entry is turned
    away — not trimmed to ten, which would silently lose what you wrote."""
    lines = "\n".join(f"--todo item {i}" for i in range(11))
    with pytest.raises(CaptureError):
        capture_store.capture(lines)

    assert log_lines() == []
    assert capture_store.banner()["open"] == 0


def test_an_entry_that_exactly_fills_the_cap_is_allowed(capture_store):
    capture_store.capture("\n".join(f"--todo item {i}" for i in range(10)))
    assert capture_store.banner()["open"] == 10


def test_an_entry_is_refused_by_its_total_not_its_first_line(capture_store):
    """Eight open and a three-todo entry is eleven, so it goes — even though
    each of its lines would have been fine on its own."""
    _fill(capture_store, 8)
    with pytest.raises(CaptureError):
        capture_store.capture("--todo a\n--todo b\n--todo c")

    assert capture_store.banner()["open"] == 8
    capture_store.capture("--todo a\n--todo b")
    assert capture_store.banner()["open"] == 10


def test_checking_one_off_makes_room_for_another(capture_store):
    entries = [capture_store.capture(f"--todo item {i}") for i in range(10)]
    with pytest.raises(CaptureError):
        capture_store.capture("--todo blocked")

    capture_store.toggle_line(entries[0]["id"], 0)

    assert capture_store.banner()["open"] == 9
    capture_store.capture("--todo now there is room")
    assert capture_store.banner()["open"] == 10


def test_unchecking_can_put_you_back_at_the_cap(capture_store):
    """It cannot push you over it — you can only get to eleven by writing one,
    and that is the path that is guarded."""
    entries = [capture_store.capture(f"--todo item {i}") for i in range(10)]
    capture_store.toggle_line(entries[0]["id"], 0)
    capture_store.capture("--todo the replacement")
    capture_store.toggle_line(entries[0]["id"], 0)  # back on

    assert capture_store.banner()["open"] == 11
    with pytest.raises(CaptureError):
        capture_store.capture("--todo definitely not")


def test_a_capture_with_no_todo_is_never_gated(capture_store):
    """The cap is about promises, not about writing. A full list must not stop
    you capturing a thought."""
    _fill(capture_store, 10)
    entry = capture_store.capture("just a thought <somewhere>")
    assert entry["raw_text"] == "just a thought <somewhere>"


def test_open_todos_are_oldest_first_and_carry_their_line(capture_store):
    first = capture_store.capture("--todo call the roofer")
    capture_store.capture("nothing here")
    second = capture_store.capture("a line\n--todo second thing")

    todos = capture_store.banner()["todos"]
    assert [t["entry_id"] for t in todos] == [first["id"], second["id"]]
    assert [t["text"] for t in todos] == ["--todo call the roofer", "--todo second thing"]
    assert [t["line"] for t in todos] == [0, 1]


def test_a_checked_todo_leaves_the_open_list(capture_store):
    entry = capture_store.capture("--todo a\n--todo b")
    capture_store.toggle_line(entry["id"], 0)

    todos = capture_store.banner()["todos"]
    assert [t["line"] for t in todos] == [1]


def test_the_cap_survives_the_index_being_deleted(capture_store):
    _fill(capture_store, 10)
    fresh = Store()
    fresh.start()
    try:
        assert fresh.banner()["open"] == 10
        with pytest.raises(CaptureError):
            fresh.capture("--todo one too many")
    finally:
        fresh.close()


# ── The standing tally ────────────────────────────────────────────────────
#
# Promises made against promises kept, all of history. The cap above governs
# what is *open*, which is the difference between these two — so the tally has
# to be folded from the same fields or the two numbers on screen disagree.


def test_the_banner_carries_the_all_time_tally(capture_store):
    entry = capture_store.capture("--todo a\n--todo b")
    capture_store.capture("--todo c")
    capture_store.toggle_line(entry["id"], 0)

    banner = capture_store.banner()
    assert (banner["made"], banner["done"]) == (3, 1)


def test_open_is_exactly_what_was_made_less_what_was_kept(capture_store):
    """The invariant the badge and the banner share. Ticking moves one across;
    unticking moves it back. Neither ever changes what was made."""
    entries = [capture_store.capture(f"--todo item {i}") for i in range(4)]
    for state in (True, False, True):
        for entry in entries[:2]:
            capture_store.toggle_line(entry["id"], 0)
        banner = capture_store.banner()
        assert banner["made"] == 4
        assert banner["done"] == (2 if state else 0)
        assert banner["open"] == banner["made"] - banner["done"]


def test_a_kept_promise_is_never_unmade(capture_store):
    """What makes this worth showing: `made` only ever climbs. Checking one
    off frees room under the cap and takes nothing off the total, which is the
    difference between a tally and a queue length."""
    entry = capture_store.capture("--todo the only one")
    capture_store.toggle_line(entry["id"], 0)

    banner = capture_store.banner()
    assert (banner["made"], banner["done"], banner["open"]) == (1, 1, 0)


def test_the_tally_counts_todos_no_folder_claims(capture_store):
    """A todo written with no tag is in no folder, and is still a promise. The
    total is read off the entries rather than summed over the folders for
    exactly this line."""
    capture_store.create_folder("work", ["work"])
    capture_store.capture("--todo filed <work>")
    capture_store.capture("--todo loose")

    assert capture_store.banner()["made"] == 2


def test_a_check_on_a_line_that_is_not_a_todo_is_not_kept(capture_store):
    """The fold does not ask whether a checked line is a todo — a restored
    backup can leave one behind. `open_todos` ignores it, and so must the
    tally, or the badge reads as more kept than were ever made."""
    entry = capture_store.capture("plain line\n--todo the real one")
    eventlog.append(eventlog.CHECK, entry["id"], line=0)
    capture_store.reindex()

    banner = capture_store.banner()
    assert (banner["made"], banner["done"]) == (1, 0)
    assert banner["open"] == 1


def test_the_tally_survives_the_index_being_deleted(capture_store):
    """Derived like everything else: nothing anywhere records it."""
    entry = capture_store.capture("--todo a\n--todo b")
    capture_store.toggle_line(entry["id"], 1)

    fresh = Store()
    fresh.start()
    try:
        assert fresh.banner()["made"] == 2
        assert fresh.banner()["done"] == 1
    finally:
        fresh.close()
