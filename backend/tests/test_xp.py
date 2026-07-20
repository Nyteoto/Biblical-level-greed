"""Levels and experience.

This is the one scoring system in the app, so the tests care as much about what
it must *not* touch as about the arithmetic.
"""
from __future__ import annotations

import pytest

from backend.app import eventlog, index, loader, state, xp

TWO_DOMAINS = """
id = "{id}"
title = "{id}"
priority = 1
shape = "strands"
strands = ["a"]

[season]
state = "{season}"

[[node]]
id = "low-tier"
title = "Low"
tier = 1
strand = "a"
estimate = 50

[[node]]
id = "high-tier"
title = "High"
tier = 5
strand = "a"
estimate = 50
requires = ["low-tier"]
"""


@pytest.fixture
def setup(write_domain, data_dir):
    def _setup(*specs):
        for domain_id, season in specs:
            write_domain(domain_id, TWO_DOMAINS.format(id=domain_id, season=season))
        domains, errors = loader.load_all()
        assert not errors, errors
        return domains

    return _setup


@pytest.fixture
def score(conn):
    def _score(domains, today="2026-07-20"):
        index.rebuild(conn)
        return xp.build(conn, domains, today=today)

    return _score


# -- the containment rule ---------------------------------------------------


def test_the_board_does_not_import_xp():
    """The hard constraint: XP may never change what you are told to work on.
    If `state` ever needs xp, that guarantee is gone and this test should be
    the thing that stops it, not a code review."""
    # Checked against the module namespace rather than its source, because the
    # substring "xp" also appears in words like "expired".
    assert not hasattr(state, "xp")


def test_xp_is_derived_and_stores_nothing(conn, setup, score, log):
    """Delete the index, replay the log, get the same number."""
    domains = setup(("d", "high"))
    log("d", "low-tier", eventlog.SESSION, "2026-07-20")
    first = score(domains)["total"]
    index.rebuild(conn)
    assert score(domains)["total"] == first


# -- the arithmetic ---------------------------------------------------------


def test_a_session_is_worth_the_flat_rate(setup, score, log):
    domains = setup(("d", "high"))
    log("d", "low-tier", eventlog.SESSION, "2026-07-20")
    # Tier 1, first day of a streak, one acquiring domain: no multipliers bite
    # except the day-1 streak, which is +2%.
    assert score(domains)["total"] == pytest.approx(
        xp.SESSION_XP * xp.streak_multiplier(1), abs=0.05
    )


def test_higher_tiers_pay_more(setup, score, log):
    domains = setup(("d", "high"))
    log("d", "low-tier", eventlog.SESSION, "2026-07-20")
    low = score(domains)["total"]
    log("d", "high-tier", eventlog.SESSION, "2026-07-20")
    both = score(domains)["total"]
    high = both - low
    assert high == pytest.approx(low * xp.tier_multiplier(5), abs=0.05)


def test_an_undone_session_scores_nothing(setup, score, log):
    domains = setup(("d", "high"))
    log("d", "low-tier", eventlog.SESSION, "2026-07-20")
    log("d", "low-tier", eventlog.UNDO, "2026-07-20")
    assert score(domains)["total"] == 0


# -- streaks ----------------------------------------------------------------


def test_consecutive_days_build_a_streak(setup, score, log):
    domains = setup(("d", "high"))
    for day in ("2026-07-18", "2026-07-19", "2026-07-20"):
        log("d", "low-tier", eventlog.SESSION, day)
    assert score(domains)["streak"] == 3


def test_a_gap_breaks_the_streak(setup, score, log):
    domains = setup(("d", "high"))
    for day in ("2026-07-14", "2026-07-15", "2026-07-18"):
        log("d", "low-tier", eventlog.SESSION, day)
    # The 18th starts a new streak of 1, and by the 20th it is two days stale.
    assert score(domains)["streak"] == 0


def test_yesterday_still_counts_as_a_live_streak(setup, score, log):
    """A streak is not dead until you miss a whole day."""
    domains = setup(("d", "high"))
    for day in ("2026-07-18", "2026-07-19"):
        log("d", "low-tier", eventlog.SESSION, day)
    assert score(domains)["streak"] == 2


def test_the_streak_bonus_is_capped(setup, score):
    assert xp.streak_multiplier(10_000) == 1.0 + xp.STREAK_CAP


# -- the spread penalty -----------------------------------------------------


def test_two_acquiring_domains_are_free(setup, score, log):
    domains = setup(("d1", "high"), ("d2", "high"))
    for d in ("d1", "d2"):
        log(d, "low-tier", eventlog.SESSION, "2026-07-20")
    assert score(domains)["today_breakdown"]["spread_mult"] == 1.0
    assert score(domains)["today_breakdown"]["spread_penalised"] is False


def test_a_third_acquiring_domain_cuts_the_day(setup, score, log):
    domains = setup(("d1", "high"), ("d2", "high"), ("d3", "high"))
    for d in ("d1", "d2", "d3"):
        log(d, "low-tier", eventlog.SESSION, "2026-07-20")
    breakdown = score(domains)["today_breakdown"]
    assert breakdown["spread_mult"] == pytest.approx(1 - xp.SPREAD_PENALTY)
    assert breakdown["spread_penalised"] is True


def test_held_domains_do_not_count_towards_the_spread(setup, score, log):
    """Upkeep in five held domains is not what the penalty is aimed at. The
    seasons argument is that holding is cheap; the scoring has to agree, or the
    two systems would push in opposite directions."""
    domains = setup(("d1", "high"), ("d2", "high"), ("d3", "low"), ("d4", "low"))
    for d in ("d1", "d2", "d3", "d4"):
        log(d, "low-tier", eventlog.SESSION, "2026-07-20")
    breakdown = score(domains)["today_breakdown"]
    assert breakdown["acquiring_domains"] == ["d1", "d2"]
    assert breakdown["spread_mult"] == 1.0


def test_the_penalty_has_a_floor(setup):
    assert xp.spread_multiplier(50) == xp.SPREAD_FLOOR


# -- todos ------------------------------------------------------------------


def test_a_ticked_todo_is_worth_a_flat_amount(setup, score):
    from backend.app import todos

    domains = setup(("d", "high"))
    item = todos.add("buy strings")
    todos.complete(item["id"])
    assert score(domains)["total"] == pytest.approx(xp.TODO_XP)


def test_todos_take_no_streak_or_spread_bonus(setup, score, log):
    """Errands must not be a way to farm the practice multipliers."""
    from backend.app import todos

    domains = setup(("d1", "high"), ("d2", "high"), ("d3", "high"))
    for day in ("2026-07-18", "2026-07-19", "2026-07-20"):
        log("d1", "low-tier", eventlog.SESSION, day)
    before = score(domains)["total"]
    item = todos.add("errand")
    todos.complete(item["id"])
    # Exactly TODO_XP more, with no multiplier applied to it.
    assert score(domains)["total"] == pytest.approx(before + xp.TODO_XP)


def test_a_todo_only_day_does_not_hold_a_streak(setup, score, log):
    from backend.app import todos

    domains = setup(("d", "high"))
    log("d", "low-tier", eventlog.SESSION, "2026-07-18")
    item = todos.add("errand")  # added and ticked today, 2 days later
    todos.complete(item["id"])
    assert score(domains, today="2026-07-20")["streak"] == 0


# -- levels and the two-tone bar --------------------------------------------


def test_levels_get_geometrically_more_expensive():
    table = xp.level_table()
    first = table[2] - table[1]
    later = table[11] - table[10]
    assert later > first * 3


def test_the_bar_splits_yesterday_from_today(setup, score, log):
    domains = setup(("d", "high"))
    log("d", "low-tier", eventlog.SESSION, "2026-07-19")
    log("d", "low-tier", eventlog.SESSION, "2026-07-20")
    result = score(domains)
    assert result["carried_pct"] > 0  # white: what yesterday left you with
    assert result["today_pct"] > 0  # yellow: what today added
    assert result["carried_pct"] + result["today_pct"] == pytest.approx(
        100 * result["into_level"] / result["level_span"], abs=0.05
    )


def test_levelling_up_today_clears_the_carried_section(setup, score, log):
    """None of the new level was there yesterday, so the white bar is zero."""
    domains = setup(("d", "high"))
    day = 1
    while day <= 28:
        log("d", "high-tier", eventlog.SESSION, f"2026-06-{day:02d}")
        day += 1
    for d in range(1, 21):
        log("d", "high-tier", eventlog.SESSION, f"2026-07-{d:02d}")

    result = score(domains, today="2026-07-20")
    assert result["level"] > 1
    before = xp.level_at(result["total"] - result["earned_today"])[0]
    if before < result["level"]:
        assert result["carried_pct"] == 0


def test_nothing_logged_is_level_one(setup, score):
    domains = setup(("d", "high"))
    result = score(domains)
    assert result["level"] == 1
    assert result["total"] == 0
    assert result["carried_pct"] == 0
    assert result["today_pct"] == 0
