"""The only place in the codebase that does timezone math.

Every event carries a precomputed `day` string in the user's zone, so the rest
of the system compares dates as plain strings and never touches a tzinfo.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .config import TZ_OFFSET_HOURS

TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))

DAY_FMT = "%Y-%m-%d"


def now() -> datetime:
    return datetime.now(TZ)


def day_key(when: datetime | None = None) -> str:
    """The YYYY-MM-DD the given instant falls on, in the user's zone."""
    return (when or now()).astimezone(TZ).strftime(DAY_FMT)


def parse_day(key: str) -> date:
    return datetime.strptime(key, DAY_FMT).date()


def days_between(earlier: str, later: str) -> int:
    return (parse_day(later) - parse_day(earlier)).days


def month_key(day: str) -> str:
    """Log files are sharded by month: 2026-07.jsonl"""
    return day[:7]


def next_midnight_iso(when: datetime | None = None) -> str:
    """When the dashboard next rolls over. Surfaced to the UI so it can refresh."""
    current = (when or now()).astimezone(TZ)
    tomorrow = (current + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return tomorrow.isoformat()
