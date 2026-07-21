"""Levels and experience.

This is the one scoring system in the app, so the tests care as much about what
it must *not* touch as about the arithmetic.
"""
from __future__ import annotations

import pytest

import inspect
import re

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
kind = "drill"
decay_days = 30

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


def test_the_board_never_reads_your_balance():
    """The containment rule, narrowed rather than abandoned.

    XP now gates the board — a tier II node is sealed until bought — so `state`
    does import `xp`. What must stay true is that it reads *prices* and never
    *earnings*: the board is decided by what the log says you bought, not by
    what you happen to be able to afford right now.

    If that slipped, retuning SESSION_XP would silently relock nodes you had
    already paid for, and a good day's practice could change what is startable.
    Checked against the source, because the point is which attribute is reached
    for.
    """
    source = inspect.getsource(state)
    used = set(re.findall(r"\bxp\.(\w+)", source))
    assert used == {"unlock_price"}, f"state reached into xp for {used}"


def test_prices_do_not_move_when_the_economy_is_retuned(conn, setup, log, monkeypatch):
    """A purchase is a fact, not a derivation. Retuning must not un-buy it."""
    domains = setup(("d", "high"))
    eventlog.append("d", "high-tier", eventlog.UNLOCK, day="2026-07-19", value=1000.0)
    index.rebuild(conn)

    before = xp.build(conn, domains, today="2026-07-20")
    monkeypatch.setattr(xp, "SESSION_XP", 1.0)
    after = xp.build(conn, domains, today="2026-07-20")

    # Earnings re-score; the price paid does not.
    assert after["spent"] == before["spent"] == 1000.0


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
    # Tier 1, first day of a streak, one acquiring domain: the focus bonus is
    # full and the day-1 streak adds 2%.
    assert score(domains)["total"] == pytest.approx(
        xp.SESSION_XP * xp.streak_multiplier(1) * xp.focus_multiplier(1), abs=0.05
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


# -- the focus bonus --------------------------------------------------------


def test_two_acquiring_domains_still_earn_the_full_bonus(setup, score, log):
    domains = setup(("d1", "high"), ("d2", "high"))
    for d in ("d1", "d2"):
        log(d, "low-tier", eventlog.SESSION, "2026-07-20")
    assert score(domains)["today_breakdown"]["focus_mult"] == 1.25
    assert score(domains)["today_breakdown"]["focused"] is True


def test_a_third_acquiring_domain_erodes_the_bonus(setup, score, log):
    domains = setup(("d1", "high"), ("d2", "high"), ("d3", "high"))
    for d in ("d1", "d2", "d3"):
        log(d, "low-tier", eventlog.SESSION, "2026-07-20")
    breakdown = score(domains)["today_breakdown"]
    # The payload rounds for display, so compare against the rounded value.
    assert breakdown["focus_mult"] == pytest.approx(
        round((1 + xp.FOCUS_BONUS) - xp.FOCUS_FALLOFF, 3)
    )
    assert breakdown["focused"] is False


def test_held_domains_do_not_count_towards_focus(setup, score, log):
    """Upkeep in five held domains is not what the bonus is aimed at. The
    seasons argument is that holding is cheap; the scoring has to agree, or the
    two systems would push in opposite directions."""
    domains = setup(("d1", "high"), ("d2", "high"), ("d3", "low"), ("d4", "low"))
    for d in ("d1", "d2", "d3", "d4"):
        log(d, "low-tier", eventlog.SESSION, "2026-07-20")
    breakdown = score(domains)["today_breakdown"]
    assert breakdown["acquiring_domains"] == ["d1", "d2"]
    assert breakdown["focus_mult"] == 1.25


def test_the_penalty_has_a_floor(setup):
    assert xp.focus_multiplier(50) == xp.FOCUS_FLOOR


# -- todos ------------------------------------------------------------------


def test_a_ticked_todo_is_worth_a_flat_amount(setup, score):
    from backend.app import todos

    domains = setup(("d", "high"))
    item = todos.add("buy strings")
    todos.complete(item["id"])
    assert score(domains)["total"] == pytest.approx(xp.TODO_XP)


def test_todos_take_no_streak_or_focus_bonus(setup, score, log):
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


# -- the price of starting --------------------------------------------------


def test_tier_one_is_free_everywhere():
    """Every tree has to be enterable. Seasons cap how many, not whether."""
    assert xp.unlock_price(1) == 0.0
    assert xp.unlock_price(0) == 0.0


def test_prices_rise_with_tier():
    prices = [xp.unlock_price(t) for t in range(2, 13)]
    assert prices == sorted(prices)
    assert len(set(prices)) == len(prices)


def test_no_node_can_fund_the_tier_above_it():
    """The load-bearing claim of the whole economy.

    Doing one node perfectly — every session on an unbroken streak, fully
    focused — must leave you short of the next tier's price. Being a hair short
    is the mechanism: it forces upkeep drilling elsewhere, or a break, and both
    are the intended answer.

    Checked against the shipped trees, so adding a node big enough to break it
    fails here rather than quietly turning the tree into a staircase.
    """
    import tomllib
    from pathlib import Path

    peak: dict[int, tuple[float, str]] = {}
    for path in sorted(Path("data/domains").glob("*.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        for node in data.get("node", []):
            tier = node.get("tier", 1)
            best = xp.best_case_earnings(tier, node.get("estimate", 0))
            if best > peak.get(tier, (0.0, ""))[0]:
                peak[tier] = (best, f"{data['id']}/{node['id']}")

    for tier, (best, who) in sorted(peak.items()):
        price = xp.unlock_price(tier + 1)
        if price <= 0:
            continue
        assert best < price, (
            f"{who} can earn {best:.0f}, which pays for tier {tier + 1} "
            f"at {price:.0f} — the tree has become a staircase"
        )


def test_the_shortfall_is_a_hair_not_a_chasm():
    """The other half of the claim: short, but within reach of some upkeep.

    If the best node at a tier left you 90% short, the gate would not be a
    pacing mechanism, it would be a wall.
    """
    import tomllib
    from pathlib import Path

    peak: dict[int, float] = {}
    for path in sorted(Path("data/domains").glob("*.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        for node in data.get("node", []):
            tier = node.get("tier", 1)
            best = xp.best_case_earnings(tier, node.get("estimate", 0))
            peak[tier] = max(peak.get(tier, 0.0), best)

    # Tier I is the exception: it is free to enter and its nodes are small, so
    # the first purchase is meant to take a while.
    # Only tiers that something actually sits above: the top of a tree has no
    # next rung to be short of.
    for tier, best in sorted(peak.items()):
        price = xp.unlock_price(tier + 1)
        if price <= 0 or tier < 2 or (tier + 1) not in peak:
            continue
        assert best / price > 0.55, (
            f"tier {tier} peaks at {best:.0f} against a {price:.0f} gate — "
            "that is a wall, not a pacing mechanism"
        )


# -- upkeep -----------------------------------------------------------------


def test_upkeep_pays_nothing_inside_the_decay_window():
    """Checking off a finished drill daily is over-commitment, not optimisation."""
    assert xp.upkeep_multiplier(1, 30) == 0.0
    assert xp.upkeep_multiplier(29, 30) == 0.0


def test_upkeep_pays_full_rate_exactly_when_it_goes_stale():
    assert xp.upkeep_multiplier(30, 30) == 1.0


def test_upkeep_pays_less_the_longer_it_was_neglected():
    """Coming back after a year should not pay like maintenance."""
    on_time = xp.upkeep_multiplier(30, 30)
    late = xp.upkeep_multiplier(45, 30)
    very_late = xp.upkeep_multiplier(400, 30)
    assert on_time > late > xp.UPKEEP_STALE_FLOOR
    assert very_late == xp.UPKEEP_STALE_FLOOR


def test_a_drill_kept_up_on_cadence_feeds_the_pool(conn, setup, score, log):
    """The relief valve: a held domain is worth something, so the only way to
    fund a new node is not always to start another one."""
    domains = setup(("d", "high"))
    log("d", "low-tier", eventlog.SESSION, "2026-07-01")
    log("d", "low-tier", eventlog.COMPLETE, "2026-07-01")
    before = score(domains, today="2026-07-02")["total"]

    # One repetition, a full decay window later.
    log("d", "low-tier", eventlog.SESSION, "2026-08-01")
    after = score(domains, today="2026-08-02")["total"]
    assert after > before


def test_hammering_a_finished_drill_earns_nothing(conn, setup, score, log):
    domains = setup(("d", "high"))
    log("d", "low-tier", eventlog.SESSION, "2026-07-01")
    log("d", "low-tier", eventlog.COMPLETE, "2026-07-01")
    baseline = score(domains, today="2026-07-10")["total"]

    for day in ("2026-07-02", "2026-07-03", "2026-07-04", "2026-07-05"):
        log("d", "low-tier", eventlog.SESSION, day)
    assert score(domains, today="2026-07-10")["total"] == baseline


# -- the two pools ----------------------------------------------------------


def test_spending_takes_from_the_bank_and_not_the_level(conn, setup, score, log):
    """Levelling is a record of what you did; nothing can take it away."""
    domains = setup(("d", "high"))
    for day in ("2026-07-01", "2026-07-02", "2026-07-03"):
        log("d", "low-tier", eventlog.SESSION, day)
    before = score(domains, today="2026-07-04")

    eventlog.append("d", "high-tier", eventlog.UNLOCK, day="2026-07-04", value=25.0)
    after = score(domains, today="2026-07-04")

    assert after["total"] == before["total"]
    assert after["level"] == before["level"]
    assert after["spent"] == 25.0
    assert after["bank"] == pytest.approx(before["bank"] - 25.0)


def test_the_bank_starts_equal_to_what_you_have_earned(conn, setup, score, log):
    domains = setup(("d", "high"))
    log("d", "low-tier", eventlog.SESSION, "2026-07-01")
    result = score(domains, today="2026-07-02")
    assert result["bank"] == result["total"]
    assert result["spent"] == 0.0


def test_the_focus_reframe_changed_no_numbers():
    """The penalty became a bonus and the arithmetic stayed put.

    Good design rewards the right behaviour rather than punishing the wrong
    one, so the multiplier now reads above 1.00 on a focused day instead of
    exactly 1.00 with a deduction waiting. That was a labelling decision, not a
    rebalance: SESSION_XP came down by exactly the factor the bonus goes up, so
    every day in the log is worth what it was worth before.

    These are the per-session values the old `spread` curve produced.
    """
    was = {1: 10.0, 2: 10.0, 3: 8.5, 4: 7.0, 5: 5.5, 6: 4.0, 7: 4.0}
    for acquiring, before in was.items():
        now = xp.SESSION_XP * xp.focus_multiplier(acquiring)
        assert now == pytest.approx(before), (
            f"{acquiring} acquiring domains used to pay {before}, now pays {now} — "
            "the reframe was meant to change the label, not the economy"
        )


# -- the substrate ----------------------------------------------------------


def test_sleep_and_movement_carry_the_best_streak_in_the_system():
    """Nothing else in this app compounds the way sleeping properly does, so
    nothing else is paid like it."""
    for day in (1, 7, 30, 100):
        assert xp.substrate_streak_multiplier(day) >= xp.streak_multiplier(day)
    assert xp.SUBSTRATE_STREAK_CAP > xp.STREAK_CAP
    assert xp.SUBSTRATE_STREAK_BONUS > xp.STREAK_BONUS


def test_the_substrate_buff_needs_a_fortnight():
    assert xp.substrate_buff(0) == 1.0
    assert xp.substrate_buff(1) == pytest.approx(1 + xp.SUBSTRATE_BUFF)
    assert xp.substrate_buff(2) == pytest.approx(1 + 2 * xp.SUBSTRATE_BUFF)


def _foundation_domains():
    from backend.app import loader

    domains, _ = loader.load_all()
    return domains


def test_a_held_substrate_streak_buffs_everything_else(conn, setup, log):
    """The whole argument for paying these two so heavily: sleeping properly
    does not make sleeping more valuable, it makes every other hour worth
    more."""
    setup(("d", "high"))
    domains = _foundation_domains()

    import datetime

    start = datetime.date(2026, 6, 1)
    for i in range(40):
        day = (start + datetime.timedelta(days=i)).isoformat()
        log("mementomori", "sleep", eventlog.SESSION, day)
        log("mementomori", "movement", eventlog.SESSION, day)

    on_day = (start + datetime.timedelta(days=39)).isoformat()
    log("d", "low-tier", eventlog.SESSION, on_day)
    index.rebuild(conn)
    result = xp.build(conn, domains, today=on_day)

    breakdown = result["today_breakdown"]
    assert breakdown["substrate_held"] == 2
    assert breakdown["substrate_mult"] == pytest.approx(1.30)


def test_the_substrate_never_buffs_itself(conn, setup, log):
    """Two streaks buffing each other would compound into the only strategy
    worth having."""
    setup(("d", "high"))
    domains = _foundation_domains()

    import datetime

    start = datetime.date(2026, 6, 1)
    for i in range(40):
        day = (start + datetime.timedelta(days=i)).isoformat()
        log("mementomori", "sleep", eventlog.SESSION, day)
        log("mementomori", "movement", eventlog.SESSION, day)

    on_day = (start + datetime.timedelta(days=39)).isoformat()
    index.rebuild(conn)
    day_score = xp.build(conn, domains, today=on_day)["today_breakdown"]

    # Their own XP is reported separately and is not multiplied by the buff
    # they generate: at the streak cap it is exactly 2x the flat rate each.
    expected = 2 * xp.SESSION_XP * (1 + xp.SUBSTRATE_STREAK_CAP)
    assert day_score["substrate_xp"] == pytest.approx(expected, abs=0.05)


def test_the_foundation_is_not_acquiring(conn, log):
    """Holding your own substrate must never read as spreading yourself thin."""
    domains = _foundation_domains()
    log("mementomori", "sleep", eventlog.SESSION, "2026-07-20")
    index.rebuild(conn)
    breakdown = xp.build(conn, domains, today="2026-07-20")["today_breakdown"]
    assert breakdown["acquiring_domains"] == []
    assert breakdown["focused"] is True
