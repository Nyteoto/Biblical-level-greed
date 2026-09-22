"""The only place in the codebase that does timezone math.

Everything the Portal decides is a question about the clock — which Instance
you are, whether the window is open, whether today is still today — so every
one of those questions is answered here, in one zone, and the rest of the
system compares plain `YYYY-MM-DD` strings and plain instance numbers.

**The clock can be set, and only through the environment.** `PGS_FAKE_NOW`
pins `now()` to an ISO instant in the user's zone. It exists because the one
screen worth testing by hand only opens between 19:00 and 23:00, and a flow
that can only be walked at night against real data is a flow that gets tested
against real data. Point it at a scratch `PGS_DATA_DIR` and walk it at noon.
Tests need neither: every decision in `day.py` takes the instant as an
argument.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

from .config import BIRTH, TZ_OFFSET_HOURS, WINDOW_CLOSE, WINDOW_OPEN

TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))

DAY_FMT = "%Y-%m-%d"

_FAKE = os.environ.get("PGS_FAKE_NOW")


def now() -> datetime:
    if _FAKE:
        pinned = datetime.fromisoformat(_FAKE)
        return pinned if pinned.tzinfo else pinned.replace(tzinfo=TZ)
    return datetime.now(TZ)


def day_key(when: datetime | None = None) -> str:
    """The YYYY-MM-DD the given instant falls on, in the user's zone."""
    return (when or now()).astimezone(TZ).strftime(DAY_FMT)


def parse_day(key: str) -> date:
    return datetime.strptime(key, DAY_FMT).date()


def instance_of(day: str) -> int:
    """Which Instance lives on `day`: whole days since the true birth."""
    return (parse_day(day) - BIRTH).days


def day_of(instance: int) -> str:
    """The day an Instance lived. The inverse of `instance_of`."""
    return (BIRTH + timedelta(days=instance)).strftime(DAY_FMT)


def window_for(day: str) -> tuple[datetime, datetime]:
    """When `day`'s Record may be committed: [open, close)."""
    d = parse_day(day)
    return (
        datetime.combine(d, WINDOW_OPEN, tzinfo=TZ),
        datetime.combine(d, WINDOW_CLOSE, tzinfo=TZ),
    )


def in_window(when: datetime | None = None) -> bool:
    current = (when or now()).astimezone(TZ)
    opens, closes = window_for(day_key(current))
    return opens <= current < closes


def past_window(when: datetime | None = None) -> bool:
    """True once today's window has closed — the deadline has passed."""
    current = (when or now()).astimezone(TZ)
    return current >= window_for(day_key(current))[1]
