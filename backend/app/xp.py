"""Levels and experience.

READ THIS FIRST — this file breaks the rule the rest of the app is built on.
The README says there is no scoring and nothing adaptive, and XP is scoring. So
the crossing is contained by one hard constraint, which every function here
obeys:

    **XP NEVER CHANGES WHAT THE BOARD SHOWS YOU.**

Nothing in here feeds `_pick_active`, `_status`, seasons, cadence or due-ness.
It is a pure read-only fold over the event log, stored nowhere, derived fresh
every request. Delete this module and the app still decides what to work on in
exactly the same way. That keeps the recommendation engine deterministic and
unscored — which was the actual value of the original rule — while still
letting the bar go up.

The other consequence of deriving rather than storing: retuning any constant
below re-scores your whole history immediately and consistently. There is no
migration, because there is no state.

HOW ONE SESSION IS SCORED

    SESSION_XP  x  tier multiplier  x  streak multiplier  x  spread multiplier

Todos are flat: no tier, no streak, no spread. They are errands, not practice,
and should not be a way to farm a streak bonus.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from . import eventlog, index, todos
from .models import Domain
from .timeutil import day_key, days_between

# -- tunables ---------------------------------------------------------------
# All of it is here, in one block, because "you can predict the board by reading
# it" has to keep being true once a number is attached to the reading.

SESSION_XP = 10.0  # flat, per node checked off on a day
TODO_XP = 2.0  # flat, per checklist item ticked. Deliberately small.

# Higher tiers pay more: tier 1 is 1.0x, and each tier above adds this.
TIER_BONUS = 0.15

# Consecutive days with at least one session. Todos do not hold a streak.
STREAK_BONUS = 0.02  # +2% per day
STREAK_CAP = 0.50  # ...capped, or a year-long streak doubles everything

# The anti-breadth rule, and the reason this scoring is worth having at all.
# Acquiring in more than SPREAD_FREE domains on the same day cuts everything you
# earned that day. `low` and `off` domains are exempt — upkeep is not spreading,
# and the whole seasons argument is that holding is cheap.
SPREAD_FREE = 2
SPREAD_PENALTY = 0.15  # -15% per acquiring domain beyond the free ones
SPREAD_FLOOR = 0.40  # never cut a day below this

# Levels get more expensive geometrically, so the number stays small and legible
# rather than running to four digits.
LEVEL_BASE = 120.0  # cost of level 2
LEVEL_GROWTH = 1.18  # each level costs this much more than the last
MAX_LEVEL = 200  # a bound for the cumulative table, not a cap you will meet


def tier_multiplier(tier: int) -> float:
    return 1.0 + TIER_BONUS * max(0, tier - 1)


def streak_multiplier(streak: int) -> float:
    return 1.0 + min(STREAK_CAP, STREAK_BONUS * max(0, streak))


def spread_multiplier(acquiring_domains: int) -> float:
    """The penalty for learning in too many places at once.

    Counts only domains in a `high` season. Doing maintenance in five held
    domains is not what this is aimed at — acquiring in five is.
    """
    excess = max(0, acquiring_domains - SPREAD_FREE)
    return max(SPREAD_FLOOR, 1.0 - SPREAD_PENALTY * excess)


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
    todos: int = 0
    acquiring: set[str] = field(default_factory=set)
    streak: int = 0

    @property
    def spread(self) -> float:
        return spread_multiplier(len(self.acquiring))

    def total(self) -> float:
        return self.base * streak_multiplier(self.streak) * self.spread + self.todo


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


def build(
    conn: sqlite3.Connection, domains: list[Domain], today: str | None = None
) -> dict:
    """The whole XP state, folded from the log. Stores nothing."""
    today = today or day_key()

    tiers = {(d.id, n.id): n.tier for d in domains for n in d.nodes}
    acquiring_domains = {d.id for d in domains if d.season.acquiring}

    scores: dict[str, DayScore] = {}

    for (domain, node), days in _session_days(conn).items():
        tier = tiers.get((domain, node), 1)
        for day in days:
            score = scores.setdefault(day, DayScore(day))
            score.base += SESSION_XP * tier_multiplier(tier)
            score.sessions += 1
            # A node whose domain has since been parked still earned its XP;
            # only the *spread* question asks about seasons, and it asks about
            # the season now, because that is the only one we can know.
            if domain in acquiring_domains:
                score.acquiring.add(domain)

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

    level, into, span = level_at(total)
    _, into_before, _ = level_at(before_today)
    # The white section is only what carried in from yesterday *within the level
    # you are on now*. Levelling up today collapses it to zero, which is right:
    # none of the new level was there yesterday.
    carried = into_before if level_at(before_today)[0] == level else 0.0

    today_score = scores.get(today, DayScore(today))
    return {
        "total": round(total, 1),
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
            "todos": today_score.todos,
            "session_xp": round(today_score.base, 1),
            "todo_xp": round(today_score.todo, 1),
            "streak_mult": round(streak_multiplier(today_score.streak), 3),
            "spread_mult": round(today_score.spread, 3),
            "acquiring_domains": sorted(today_score.acquiring),
            "spread_penalised": len(today_score.acquiring) > SPREAD_FREE,
        },
        "tunables": {
            "session_xp": SESSION_XP,
            "todo_xp": TODO_XP,
            "tier_bonus": TIER_BONUS,
            "streak_bonus": STREAK_BONUS,
            "streak_cap": STREAK_CAP,
            "spread_free": SPREAD_FREE,
            "spread_penalty": SPREAD_PENALTY,
        },
    }
