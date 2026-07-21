"""The invariants that make the board predictable. If one of these breaks, the
user can no longer guess what the app will show, which is the whole product."""
from __future__ import annotations

import pytest

from backend.app import eventlog, index, loader, state, xp
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


def test_active_is_lowest_tier_then_file_order(write_domain, view, log, unlock):
    write_domain("korean", BRANCHING)
    assert view("korean")["active_node_id"] == "hangul"

    # Tier II costs XP; this test is about ordering once bought.
    unlock("korean", "grammar", 2)
    unlock("korean", "listening", 2)
    log("korean", "hangul", eventlog.COMPLETE, "2026-07-19")
    v = view("korean")
    # Both tier-2 nodes unlock at once; the earlier declaration is active.
    assert v["active_node_id"] == "grammar"
    assert node_of(v, "listening")["status"] == "available"
    assert node_of(v, "exam")["status"] == "locked"
    assert node_of(v, "exam")["blocked_by"] == ["grammar", "listening"]


def test_a_node_unlocks_only_when_every_prerequisite_is_done(
    write_domain, view, log, unlock
):
    write_domain("korean", BRANCHING)
    for node, tier in (("grammar", 2), ("listening", 2), ("exam", 3)):
        unlock("korean", node, tier)
    log("korean", "hangul", eventlog.COMPLETE, "2026-07-19")
    log("korean", "grammar", eventlog.COMPLETE, "2026-07-19")
    assert node_of(view("korean"), "exam")["status"] == "locked"

    log("korean", "listening", eventlog.COMPLETE, "2026-07-19")
    assert view("korean")["active_node_id"] == "exam"


def test_reopen_walks_the_tree_back(write_domain, view, log, unlock):
    write_domain("korean", BRANCHING)
    unlock("korean", "grammar", 2)
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
    domain = next(d for d in domains if d.id != "mementomori")

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
    # The compiled-in foundation always leads; it is priority 0 by design.
    assert [d.id for d in domains] == ["mementomori", "korean", "later"]
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


# -- unlocking --------------------------------------------------------------


def test_a_tier_two_node_is_sealed_until_bought(write_domain, node_of, log):
    """Prerequisites met is no longer the same as startable."""
    write_domain("korean", BRANCHING)
    log("korean", "hangul", eventlog.COMPLETE, "2026-07-19")
    grammar = node_of("korean", "grammar")
    assert grammar["status"] == "sealed"
    assert grammar["unlock_price"] == xp.unlock_price(2)
    assert grammar["unlocked"] is False


def test_a_sealed_node_is_never_todays_work(write_domain, view, log):
    """Sealed is not startable, so the board must not offer it."""
    write_domain("korean", BRANCHING)
    log("korean", "hangul", eventlog.COMPLETE, "2026-07-19")
    assert "grammar" not in view("korean")["active_node_ids"]


def test_tier_one_needs_no_unlocking(write_domain, node_of):
    write_domain("korean", BRANCHING)
    hangul = node_of("korean", "hangul")
    assert hangul["unlock_price"] == 0.0
    assert hangul["unlocked"] is True
    assert hangul["status"] in ("available", "active")


def test_locked_outranks_sealed(write_domain, node_of, unlock):
    """A node you have paid for but cannot reach still reads as locked: the
    price is not the thing standing in your way, and the card should say so."""
    write_domain("korean", BRANCHING)
    unlock("korean", "grammar", 2)
    assert node_of("korean", "grammar")["status"] == "locked"


def test_buying_the_unlock_makes_it_startable(write_domain, node_of, log, unlock):
    write_domain("korean", BRANCHING)
    log("korean", "hangul", eventlog.COMPLETE, "2026-07-19")
    unlock("korean", "grammar", 2)
    assert node_of("korean", "grammar")["status"] in ("available", "active")


def test_conditions_are_reported_for_the_ui(write_domain, node_of, log):
    """The panel and the card render whatever comes back, so a new gate shows
    up in both without either learning about it."""
    write_domain("korean", BRANCHING)
    log("korean", "hangul", eventlog.COMPLETE, "2026-07-19")
    keys = {c["key"]: c for c in node_of("korean", "grammar")["conditions"]}
    assert keys["prerequisites"]["met"] is True
    assert keys["unlock_price"]["met"] is False
    assert keys["unlock_price"]["cost"] == xp.unlock_price(2)


# -- the foundation ---------------------------------------------------------


def test_the_foundation_exists_without_any_file(data_dir):
    """It is compiled in, so a fresh install has it before any tree is written."""
    domains, errors = loader.load_all()
    assert not errors
    assert any(d.id == "mementomori" for d in domains)


def test_the_foundation_cannot_be_edited_or_deleted(data_dir):
    from backend.app.models import DomainError
    from backend.app.store import store

    store.reload_domains()
    with pytest.raises(DomainError, match="built into the app"):
        store.mutate("mementomori", lambda d: d)
    with pytest.raises(DomainError, match="built into the app"):
        store.delete_domain("mementomori")


def test_reminders_are_standing_and_never_startable(conn):
    from backend.app import foundation

    view = state.build_domain_view(conn, foundation.build(), today="2026-07-21")
    reminders = [n for n in view["nodes"] if n["kind"] == "reminder"]
    assert reminders
    assert all(n["status"] == "standing" for n in reminders)
    assert not any(n["id"] in view["active_node_ids"] for n in reminders)


def test_only_sleep_and_movement_are_todays_work(conn):
    from backend.app import foundation

    view = state.build_domain_view(conn, foundation.build(), today="2026-07-21")
    assert view["active_node_ids"] == ["sleep", "movement"]


def test_nothing_in_the_foundation_has_a_price(conn):
    from backend.app import foundation

    view = state.build_domain_view(conn, foundation.build(), today="2026-07-21")
    assert all(n["unlock_price"] == 0.0 for n in view["nodes"])
    assert all(n["unlocked"] for n in view["nodes"])
    assert all(not n["conditions"] for n in view["nodes"])


def test_the_foundation_drills_never_finish(conn, log):
    """There is no day you are done with sleeping."""
    from backend.app import foundation

    for day in ("2026-07-19", "2026-07-20", "2026-07-21"):
        log("mementomori", "sleep", eventlog.SESSION, day)
    index.rebuild(conn)
    view = state.build_domain_view(conn, foundation.build(), today="2026-07-21")
    sleep = next(n for n in view["nodes"] if n["id"] == "sleep")
    assert sleep["sessions_done"] == 3
    assert sleep["ready_to_complete"] is False
