"""The invariants that make the board predictable. If one of these breaks, the
user can no longer guess what the app will show, which is the whole product."""
from __future__ import annotations

import pytest

from backend.app import eventlog, index, loader, state
from backend.app.models import DomainError

BRANCHING = """
id = "korean"
title = "Korean"
priority = 10
cadence = "daily"

[[node]]
id = "hangul"
title = "Hangul"
tier = 1
sessions = 3

# Declared before `listening` on purpose: it must win the tier-3 tie.
[[node]]
id = "grammar"
title = "Grammar"
tier = 2
requires = ["hangul"]
sessions = 2

[[node]]
id = "listening"
title = "Listening"
tier = 2
requires = ["hangul"]
sessions = 2

[[node]]
id = "exam"
title = "Exam"
tier = 3
requires = ["grammar", "listening"]
sessions = 1
"""


def node_of(view: dict, node_id: str) -> dict:
    return next(n for n in view["nodes"] if n["id"] == node_id)


def test_active_is_lowest_tier_then_file_order(write_domain, view, log):
    write_domain("korean", BRANCHING)
    assert view("korean")["active_node_id"] == "hangul"

    log("korean", "hangul", eventlog.COMPLETE, "2026-07-19")
    v = view("korean")
    # Both tier-2 nodes unlock at once; the earlier declaration is active.
    assert v["active_node_id"] == "grammar"
    assert node_of(v, "listening")["status"] == "available"
    assert node_of(v, "exam")["status"] == "locked"
    assert node_of(v, "exam")["blocked_by"] == ["grammar", "listening"]


def test_a_node_unlocks_only_when_every_prerequisite_is_done(write_domain, view, log):
    write_domain("korean", BRANCHING)
    log("korean", "hangul", eventlog.COMPLETE, "2026-07-19")
    log("korean", "grammar", eventlog.COMPLETE, "2026-07-19")
    assert node_of(view("korean"), "exam")["status"] == "locked"

    log("korean", "listening", eventlog.COMPLETE, "2026-07-19")
    assert view("korean")["active_node_id"] == "exam"


def test_reopen_walks_the_tree_back(write_domain, view, log):
    write_domain("korean", BRANCHING)
    log("korean", "hangul", eventlog.COMPLETE, "2026-07-19")
    assert view("korean")["active_node_id"] == "grammar"

    log("korean", "hangul", eventlog.REOPEN, "2026-07-20")
    v = view("korean")
    assert v["active_node_id"] == "hangul"
    assert node_of(v, "grammar")["status"] == "locked"


def test_sessions_count_distinct_days_not_clicks(write_domain, view, log):
    write_domain("korean", BRANCHING)
    for _ in range(5):
        log("korean", "hangul", eventlog.SESSION, "2026-07-20")
    assert node_of(view("korean"), "hangul")["sessions_done"] == 1

    # A second day adds one, however many times it was clicked.
    log("korean", "hangul", eventlog.SESSION, "2026-07-21")
    log("korean", "hangul", eventlog.SESSION, "2026-07-21")
    assert node_of(view("korean", today="2026-07-21"), "hangul")["sessions_done"] == 2


def test_undo_reverses_the_day_and_is_replayable(write_domain, view, log):
    write_domain("korean", BRANCHING)
    log("korean", "hangul", eventlog.SESSION, "2026-07-20")
    assert node_of(view("korean"), "hangul")["checked_today"] is True

    log("korean", "hangul", eventlog.UNDO, "2026-07-20")
    v = node_of(view("korean"), "hangul")
    assert v["checked_today"] is False
    assert v["sessions_done"] == 0

    log("korean", "hangul", eventlog.SESSION, "2026-07-20")
    assert node_of(view("korean"), "hangul")["sessions_done"] == 1


def test_hitting_the_target_never_auto_completes(write_domain, view, log):
    """Accrual is the machine's job; completion is always a human click."""
    write_domain("korean", BRANCHING)
    for day in ("2026-07-18", "2026-07-19", "2026-07-20"):
        log("korean", "hangul", eventlog.SESSION, day)

    node = node_of(view("korean"), "hangul")
    assert node["sessions_done"] == node["estimate"] == 3
    assert node["ready_to_complete"] is True
    assert node["status"] == "active"  # still not done


@pytest.mark.parametrize(
    "cadence,today,expected",
    [
        ('cadence = "daily"', "2026-07-19", True),  # a Sunday
        ('cadence = "weekdays"', "2026-07-19", False),
        ('cadence = "weekdays"', "2026-07-20", True),  # a Monday
    ],
)
def test_cadence_decides_whether_a_domain_is_due(
    write_domain, view, cadence, today, expected
):
    write_domain("korean", BRANCHING.replace('cadence = "daily"', cadence))
    assert view("korean", today=today)["due_today"] is expected


def test_every_n_days_domain_stays_on_todays_board_once_checked(
    write_domain, view, log
):
    """Regression: checking off an every_n_days domain used to make it drop out
    of 'due today', so the row vanished and the day's denominator shrank."""
    write_domain("korean", BRANCHING.replace('cadence = "daily"', "cadence = { every_n_days = 2 }"))

    assert view("korean", today="2026-07-20")["due_today"] is True
    log("korean", "hangul", eventlog.SESSION, "2026-07-20")

    v = view("korean", today="2026-07-20")
    assert v["due_today"] is True, "the row must not disappear when you check it"
    assert v["checked_today"] is True

    assert view("korean", today="2026-07-21")["due_today"] is False  # resting
    assert view("korean", today="2026-07-22")["due_today"] is True  # due again


def test_index_is_disposable(write_domain, conn, log):
    """Delete the index, replay the log, get the same answer. The log is truth."""
    write_domain("korean", BRANCHING)
    log("korean", "hangul", eventlog.SESSION, "2026-07-19")
    log("korean", "hangul", eventlog.COMPLETE, "2026-07-19")
    log("korean", "grammar", eventlog.SESSION, "2026-07-20")

    domains, _ = loader.load_all()
    domain = domains[0]

    index.rebuild(conn)
    before = state.build_domain_view(conn, domain, today="2026-07-20")

    count, warnings = index.rebuild(conn)
    after = state.build_domain_view(conn, domain, today="2026-07-20")

    assert (count, warnings) == (3, [])
    assert before == after


def test_domains_sort_by_priority_and_a_broken_file_is_isolated(write_domain):
    write_domain("korean", BRANCHING)
    write_domain("later", BRANCHING.replace('id = "korean"', 'id = "later"').replace(
        "priority = 10", "priority = 99"
    ))
    write_domain(
        "broken",
        'id = "broken"\ntitle = "B"\n[[node]]\nid = "x"\ntitle = "X"\n'
        'tier = 2\nrequires = ["ghost"]\n',
    )

    domains, errors = loader.load_all()
    assert [d.id for d in domains] == ["korean", "later"]
    assert len(errors) == 1 and "ghost" in errors[0]


@pytest.mark.parametrize(
    "body,fragment",
    [
        ('id="c"\n[[node]]\nid="a"\ntitle="A"\ntier=1\nrequires=["b"]\n'
         '[[node]]\nid="b"\ntitle="B"\ntier=2\nrequires=["a"]\n', "cycle"),
        ('id="c"\n[[node]]\nid="a"\ntitle="A"\ntier=1\n'
         '[[node]]\nid="a"\ntitle="A2"\ntier=2\n', "duplicate"),
        ('id="c"\n[[node]]\nid="a"\ntitle="A"\ntier=2\n'
         '[[node]]\nid="b"\ntitle="B"\ntier=1\nrequires=["a"]\n', "earlier tier"),
    ],
)
def test_malformed_trees_are_rejected_with_a_readable_message(
    write_domain, body, fragment
):
    write_domain("c", body)
    from backend.app.config import DOMAINS_DIR

    with pytest.raises(DomainError, match=fragment):
        loader.load_domain_file(DOMAINS_DIR / "c.toml")
