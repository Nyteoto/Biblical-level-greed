"""Levels and experience, and the price of starting things.

XP used to be decoration, under a rule this module no longer obeys: it now gates
the board, because starting a node above tier I costs XP. What survives of that
rule is the part worth keeping — **earning is still a read-only fold over the
log, stored nowhere**, so retuning a constant re-scores everything at once with
no migration. Spending is not derived: the price paid is written into the unlock
event, so retuning tomorrow cannot make yesterday's purchase unaffordable.

    SESSION_XP x tier x streak x focus

Todos are flat: errands should not farm a practice bonus.

Two pools come out of this, and only one of them is a currency:

    earned  — lifetime. Drives the level. Never goes down.
    bank    — earned minus everything spent on unlocks. This is what you buy with.

Levelling is a record of what you have done and nothing can take it away.
Spending is the cost of deciding to do more.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from . import eventlog, foundation, index, todos
from .models import DRILL, Domain
from .timeutil import day_key, days_between

# -- tunables ---------------------------------------------------------------
# All of it is here, in one block, because "you can predict the board by reading
# it" has to keep being true once a number is attached to the reading.

SESSION_XP = 8.0  # flat, per node checked off on a day, before multipliers
TODO_XP = 2.0  # flat, per checklist item ticked. Deliberately small.

# Higher tiers pay more: tier 1 is 1.0x, and each tier above adds this.
TIER_BONUS = 0.15

# Consecutive days with at least one session. Todos do not hold a streak.
STREAK_BONUS = 0.02  # +2% per day
STREAK_CAP = 0.50  # ...capped, or a year-long streak doubles everything

# -- the substrate -----------------------------------------------------------
# Sleep and the daily walk, out of the compiled-in foundation domain. They are
# paid unlike anything else in this app, deliberately and heavily.
#
# Two separate rewards, and the split matters:
#
#   1. Their own streak pays at double the normal rate, to twice the cap. This
#      is the best streak in the system and nothing else comes close.
#   2. Past SUBSTRATE_BUFF_DAYS, each one buffs *everything else you earn*.
#      Not itself — a substrate node never buffs its own sessions, or the two
#      of them would compound into the only strategy worth having.
#
# Reason for the second one: sleeping properly does not make sleeping properly
# more valuable, it makes every other hour you spend more valuable. The scoring
# says the same thing. Keep both streaks and the whole board pays 30% more.
SUBSTRATE_STREAK_BONUS = 0.04  # +4%/day on their own sessions — double normal
SUBSTRATE_STREAK_CAP = 1.00  # ...to +100%, double the normal cap
SUBSTRATE_BUFF_DAYS = 14  # a fortnight unbroken before the buff starts
SUBSTRATE_BUFF = 0.15  # +15% to all *other* earnings, per substrate node held

# The focus rule, and the reason this scoring is worth having at all.
#
# Written as a bonus for concentrating rather than a fine for spreading, which
# is the same curve seen from the other side: acquiring in FOCUS_DOMAINS or
# fewer pays FOCUS_BONUS on everything, and the bonus falls away as you add
# more. The arithmetic is identical to the penalty it replaces — SESSION_XP came
# down by the same factor the bonus goes up — but a multiplier you read on a
# good day now sits above 1.00 instead of at it.
#
# That matters more than it sounds. Nobody is told off for a day of practice.
# You are told what your focus is currently earning you, and watch it shrink if
# you take on a fourth thing.
#
# `low` and `off` domains are exempt: upkeep is not spreading, and the whole
# seasons argument is that holding is cheap.
FOCUS_DOMAINS = 2  # acquire in this many or fewer for the full bonus
FOCUS_BONUS = 0.25  # +25% while focused
FOCUS_FALLOFF = 0.1875  # ...shrinking by this per extra acquiring domain
FOCUS_FLOOR = 0.50  # never below this, however scattered the day

# -- the price of starting -------------------------------------------------
# Tier I is free in every tree: a tree has to be enterable, and the season
# system already caps how many you may enter at once.
#
# Above that the price is set so that finishing one node can never pay for the
# next tier up. Best case for a single node is
#
#     estimate x SESSION_XP x tier_multiplier x streak cap
#
# and UNLOCK_BASE/UNLOCK_GROWTH are tuned to sit just above the biggest such
# number at every tier in the shipped trees — tightest margin is about 2%.
# `best_case_earnings` assumes both substrate streaks are held, because that is
# genuinely the best case; the prices carry the same factor, so holding them
# does not change how far short you are, it just gets you there sooner.
# `test_no_node_can_fund_the_tier_above_it` asserts exactly that, so adding a
# large enough node fails the suite rather than quietly breaking the economy.
#
# Being a hair short is the whole mechanism: it forces you to drill something
# already held, or to stop for a while. Both are the intended answer.
UNLOCK_BASE = 1300.0  # tier II
UNLOCK_GROWTH = 1.25  # each tier above costs this much more
UNLOCK_ROUNDING = 25  # prices are legible numbers, not 1562.5


def unlock_price(tier: int) -> float:
    """What it costs to start a node at this tier. Tier I is free."""
    if tier <= 1:
        return 0.0
    raw = UNLOCK_BASE * (UNLOCK_GROWTH ** (tier - 2))
    return float(round(raw / UNLOCK_ROUNDING) * UNLOCK_ROUNDING)


def best_case_earnings(tier: int, estimate: int) -> float:
    """The most XP one node can yield: every session on an unbroken streak, no
    spread penalty. The number the unlock prices are checked against."""
    return (
        estimate
        * SESSION_XP
        * tier_multiplier(tier)
        * streak_multiplier(int(STREAK_CAP / STREAK_BONUS))
        # Best case is a focused one, with the substrate held: the prices are
        # set against someone doing this properly, not against someone
        # scattered across five domains on four hours of sleep.
        * focus_multiplier(FOCUS_DOMAINS)
        * max_substrate_buff()
    )


# -- upkeep ------------------------------------------------------------------
# A drill past its estimate still pays, or a held domain would be worth nothing
# and the only way to fund anything would be to start something new — which is
# the opposite of what this system argues for.
#
# It pays on the node's own decay cadence, not on demand. Checking off a drill
# every day once it is done is over-commitment, not optimisation, so repetitions
# inside the decay window are worth nothing at all. Returning exactly when it
# goes stale pays full rate; leaving it longer pays progressively less, because
# neglect is its own failure and coming back after a year should not pay like
# maintenance.
UPKEEP_STALE_FLOOR = 0.35  # never worth less than this, or why bother returning


def upkeep_multiplier(idle_days: int, decay_days: int) -> float:
    """What a maintenance repetition is worth, given the gap before it."""
    if decay_days <= 0 or idle_days < decay_days:
        return 0.0
    # Full value at the decay line, sliding to the floor one window later.
    overdue = (idle_days - decay_days) / decay_days
    return max(UPKEEP_STALE_FLOOR, 1.0 - overdue)


# Levels get more expensive geometrically, so the number stays small and legible
# rather than running to four digits.
LEVEL_BASE = 120.0  # cost of level 2
LEVEL_GROWTH = 1.18  # each level costs this much more than the last
MAX_LEVEL = 200  # a bound for the cumulative table, not a cap you will meet


def tier_multiplier(tier: int) -> float:
    return 1.0 + TIER_BONUS * max(0, tier - 1)


def streak_multiplier(streak: int) -> float:
    return 1.0 + min(STREAK_CAP, STREAK_BONUS * max(0, streak))


def substrate_streak_multiplier(streak: int) -> float:
    """What a night of proper sleep is worth on day N of a run."""
    return 1.0 + min(SUBSTRATE_STREAK_CAP, SUBSTRATE_STREAK_BONUS * max(0, streak))


def substrate_buff(held: int) -> float:
    """The multiplier on everything else, given how many substrate streaks are
    standing past the threshold today."""
    return 1.0 + SUBSTRATE_BUFF * max(0, held)


def max_substrate_buff() -> float:
    return substrate_buff(len(foundation.SUBSTRATE_NODES))


def focus_multiplier(acquiring_domains: int) -> float:
    """What concentrating is worth today.

    Counts only domains in a `high` season. Doing maintenance in five held
    domains is not what this is aimed at — acquiring in five is.
    """
    excess = max(0, acquiring_domains - FOCUS_DOMAINS)
    return max(FOCUS_FLOOR, (1.0 + FOCUS_BONUS) - FOCUS_FALLOFF * excess)


def level_table() -> list[float]:
    """Cumulative XP required to *reach* each level. Index 0 is level 1 at 0."""
    table = [0.0]
    cost = LEVEL_BASE
    for _ in range(MAX_LEVEL):
        table.append(table[-1] + cost)
        cost *= LEVEL_GROWTH
    return table


_TABLE = level_table()


def level_at(total: float) -> tuple[int, float, float]:
    """(level, xp into this level, xp this level costs)."""
    level = 1
    for i in range(1, len(_TABLE)):
        if total < _TABLE[i]:
            break
        level = i + 1
    floor = _TABLE[level - 1]
    ceiling = _TABLE[level] if level < len(_TABLE) else floor + LEVEL_BASE
    return level, total - floor, ceiling - floor


@dataclass
class DayScore:
    day: str
    base: float = 0.0  # session XP before the day's multipliers
    todo: float = 0.0  # flat, unmultiplied
    sessions: int = 0
    upkeep: int = 0  # of those sessions, how many were maintenance
    todos: int = 0
    # Scored on their own streak, and excluded from the buff they generate.
    substrate_base: float = 0.0
    substrate_held: int = 0  # substrate streaks standing past the threshold
    acquiring: set[str] = field(default_factory=set)
    streak: int = 0

    @property
    def focus(self) -> float:
        return focus_multiplier(len(self.acquiring))

    @property
    def buff(self) -> float:
        return substrate_buff(self.substrate_held)

    def total(self) -> float:
        earned = self.base * streak_multiplier(self.streak) * self.focus * self.buff
        # Substrate sessions take their own streak and never their own buff.
        return earned + self.substrate_base + self.todo


def _session_days(conn: sqlite3.Connection) -> dict[tuple[str, str], set[str]]:
    """(domain, node) -> the days it is currently checked off.

    Same toggle semantics as everywhere else: within a day, the last
    session/undo wins, so an undone day scores nothing.
    """
    per_day: dict[tuple[str, str, str], str] = {}
    for row in index.session_events(conn):
        per_day[(row["domain"], row["node"], row["day"])] = row["kind"]

    days: dict[tuple[str, str], set[str]] = {}
    for (domain, node, day), kind in per_day.items():
        if kind == eventlog.SESSION:
            days.setdefault((domain, node), set()).add(day)
    return days


def _completion_days(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    """(domain, node) -> the day its gate was last called, if it is called now.

    Reopening clears it, because a reopened node is being acquired again and its
    sessions are worth full rate for the same reason they were the first time.
    """
    done: dict[tuple[str, str], str] = {}
    for row in index.completion_events(conn):
        key = (row["domain"], row["node"])
        if row["kind"] == eventlog.COMPLETE:
            done[key] = row["day"]
        else:
            done.pop(key, None)
    return done


def build(
    conn: sqlite3.Connection, domains: list[Domain], today: str | None = None
) -> dict:
    """The whole XP state, folded from the log. Stores nothing."""
    today = today or day_key()

    nodes_by_key = {(d.id, n.id): n for d in domains for n in d.nodes}
    # The foundation is never "acquiring": holding your own substrate must not
    # read as spreading yourself thin.
    acquiring_domains = {
        d.id for d in domains if d.season.acquiring and not d.foundation
    }
    substrate_keys = {
        (d.id, n.id)
        for d in domains
        if d.foundation
        for n in d.nodes
        if n.id in foundation.SUBSTRATE_NODES
    }
    completed_on = _completion_days(conn)

    session_days = _session_days(conn)

    # Pass one: the substrate. Their per-node streaks decide both what they are
    # worth themselves and how much everything else is buffed that day, so they
    # have to be scored before anything can be multiplied by them.
    scores: dict[str, DayScore] = {}

    for key in substrate_keys:
        model = nodes_by_key.get(key)
        if model is None:
            continue
        run = 0
        previous: str | None = None
        for day in sorted(session_days.get(key, ())):
            run = run + 1 if previous and days_between(previous, day) == 1 else 1
            previous = day
            score = scores.setdefault(day, DayScore(day))
            score.substrate_base += (
                SESSION_XP
                * tier_multiplier(model.tier)
                * substrate_streak_multiplier(run)
            )
            score.sessions += 1
            if run >= SUBSTRATE_BUFF_DAYS:
                score.substrate_held += 1

    upkeep_total = 0.0

    for (domain, node), days in session_days.items():
        if (domain, node) in substrate_keys:
            continue  # already scored, on its own terms
        model = nodes_by_key.get((domain, node))
        tier = model.tier if model else 1
        finished_on = completed_on.get((domain, node))

        previous: str | None = None
        for day in sorted(days):
            # Acquisition until the gate was called; maintenance after it.
            is_upkeep = bool(finished_on) and day > finished_on
            weight = 1.0
            if is_upkeep:
                # Only a drill decays, so only a drill has upkeep worth paying
                # for. Everything else is simply held.
                if not model or model.kind != DRILL:
                    previous = day
                    continue
                idle = days_between(previous, day) if previous else model.decay_days
                weight = upkeep_multiplier(idle, model.decay_days)
                if weight <= 0:
                    previous = day
                    continue

            score = scores.setdefault(day, DayScore(day))
            gained = SESSION_XP * tier_multiplier(tier) * weight
            score.base += gained
            score.sessions += 1
            if is_upkeep:
                score.upkeep += 1
                upkeep_total += gained
            # A node whose domain has since been parked still earned its XP;
            # only the *spread* question asks about seasons, and it asks about
            # the season now, because that is the only one we can know.
            if domain in acquiring_domains:
                score.acquiring.add(domain)
            previous = day

    for record in todos.read_all()[0]:
        if record["op"] == todos.DONE:
            score = scores.setdefault(record["day"], DayScore(record["day"]))
            score.todo += TODO_XP
            score.todos += 1

    # Streaks run over days that contain *sessions*. A day of nothing but
    # ticked errands does not keep a practice streak alive.
    practice_days = sorted(d for d, s in scores.items() if s.sessions)
    streak = 0
    previous: str | None = None
    for day in practice_days:
        streak = streak + 1 if previous and days_between(previous, day) == 1 else 1
        scores[day].streak = streak
        previous = day

    # A streak that did not reach today (or yesterday, which is still alive
    # until midnight) is over.
    current_streak = 0
    if practice_days:
        last = practice_days[-1]
        gap = days_between(last, today)
        if gap <= 1:
            current_streak = scores[last].streak

    ordered = sorted(scores.values(), key=lambda s: s.day)
    total = sum(s.total() for s in ordered)
    earned_today = sum(s.total() for s in ordered if s.day == today)
    before_today = total - earned_today

    spent = 0.0
    unlocks = []
    for row in index.unlock_events(conn):
        # The price as it was on the day, not as the constants say today.
        paid = float(row["value"] or 0.0)
        spent += paid
        unlocks.append(
            {"day": row["day"], "domain": row["domain"], "node": row["node"], "paid": paid}
        )

    level, into, span = level_at(total)
    _, into_before, _ = level_at(before_today)
    # The white section is only what carried in from yesterday *within the level
    # you are on now*. Levelling up today collapses it to zero, which is right:
    # none of the new level was there yesterday.
    carried = into_before if level_at(before_today)[0] == level else 0.0

    today_score = scores.get(today, DayScore(today))
    return {
        "total": round(total, 1),
        # The two pools. `total` is the record and only ever grows; `bank` is
        # the currency and is what unlocking spends.
        "spent": round(spent, 1),
        "bank": round(total - spent, 1),
        "unlocks": unlocks,
        "level": level,
        "into_level": round(into, 1),
        "level_span": round(span, 1),
        # The two bar sections, as fractions of the current level.
        "carried_pct": round(100 * carried / span, 2) if span else 0.0,
        "today_pct": round(100 * min(earned_today, span - carried) / span, 2)
        if span
        else 0.0,
        "earned_today": round(earned_today, 1),
        "streak": current_streak,
        # The arithmetic, spelled out, so the number stays predictable.
        "today_breakdown": {
            "sessions": today_score.sessions,
            "upkeep_sessions": today_score.upkeep,
            "todos": today_score.todos,
            "session_xp": round(today_score.base, 1),
            "todo_xp": round(today_score.todo, 1),
            "streak_mult": round(streak_multiplier(today_score.streak), 3),
            "focus_mult": round(today_score.focus, 3),
            "acquiring_domains": sorted(today_score.acquiring),
            "focused": len(today_score.acquiring) <= FOCUS_DOMAINS,
            "substrate_mult": round(today_score.buff, 3),
            "substrate_held": today_score.substrate_held,
            "substrate_xp": round(today_score.substrate_base, 1),
        },
        "tunables": {
            "session_xp": SESSION_XP,
            "todo_xp": TODO_XP,
            "tier_bonus": TIER_BONUS,
            "streak_bonus": STREAK_BONUS,
            "streak_cap": STREAK_CAP,
            "focus_domains": FOCUS_DOMAINS,
            "focus_bonus": FOCUS_BONUS,
            "substrate_buff": SUBSTRATE_BUFF,
            "substrate_buff_days": SUBSTRATE_BUFF_DAYS,
            "unlock_base": UNLOCK_BASE,
            "unlock_growth": UNLOCK_GROWTH,
            "upkeep_stale_floor": UPKEEP_STALE_FLOOR,
        },
        "upkeep_total": round(upkeep_total, 1),
    }
