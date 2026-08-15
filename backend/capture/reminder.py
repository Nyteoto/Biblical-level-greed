"""`{time}` in, a due date out. Pure: the clock is a parameter.

A line-by-line port of `trophic/reference/logic/reminder.ts`, pinned by 104
golden fixtures. The rules it implements:

 - One reminder per line at most. The **first** duration token and the
   **first** absolute token on a line win, and an absolute date beats a
   duration. Anything after a newline is a separate scope.
 - `{2d}` `{3w}` `{6m}` `{1y}`, the composite `{1y2m3d}` (y→m→w→d, at most
   three units), `{tmr}`/`{tomorrow}`, and `{DD/MM/YY}` or `{MM/DD/YY}`
   depending on locale.
 - A reminder resolving to now or earlier is dropped in silence. A duration
   cannot underflow; an explicit `{01/01/24}` written in 2026 can.

Why it is shaped this way
-------------------------
Everything awkward below is a place where Python's obvious spelling produces a
*nearly* correct port — the failure mode `golden/README.md` warns about:

 - **`\\d` is ASCII in JavaScript and Unicode in Python.** `{٢d}` (Arabic-Indic
   two) matches Python's `\\d+` and then `int()` happily returns 2, inventing a
   reminder the source never makes. Every digit class here is `[0-9]`.
 - **`parseInt("3y", 10)` is 3; `int("3y")` raises.** The composite groups
   carry their unit letter, so they are sliced before conversion.
 - **Month and year arithmetic overflows, it does not clamp.** `setUTCMonth`
   keeps the day number and lets it spill: Jan 31 + 1 month is March 3 (or
   the 2nd, in a leap year), and Feb 29 + 1 year is March 1.
   `dateutil.relativedelta` would clamp to the end of the target month, which
   is the more reasonable behaviour and the wrong one. `_shift` reproduces the
   spill by counting days from the first of the target month.
 - **`Date.UTC` reads years 0–99 as 1900–1999.** The source builds a date and
   then checks that reading it back gives what went in, which is how it
   rejects `{31/02/26}`; the same check silently rejects any four-digit year
   below 100, because 26 goes in and 1926 comes out. Python would accept year
   26, so the guard is spelled out.

The result is deliberately not idiomatic Python. It is the JavaScript, in
Python, and the corpus is the reason.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

Locale = str  # "us" | "row"

# `[0-9]`, never `\d` — see the module docstring.
_COMPOSITE_RE = re.compile(r"^([0-9]+y)?([0-9]+m)?([0-9]+w)?([0-9]+d)?$")
_SIMPLE_RE = re.compile(r"^([0-9]+)([dwmy])$")
_DATE_RE = re.compile(r"^([0-9]{1,2})/([0-9]{1,2})/([0-9]{2}|[0-9]{4})$")
_TOKEN_RE = re.compile(r"\{([^{}]+)\}")


@dataclass(frozen=True)
class ResolvedReminder:
    line_index: int  # 0-based, within the raw text
    line_text: str  # the whole line, trimmed — this is the prompt
    due_at: datetime


@dataclass(frozen=True)
class _Duration:
    years: int = 0
    months: int = 0
    weeks: int = 0
    days: int = 0


def _shift(base: datetime, years: int, month0: int, day: int) -> datetime:
    """Rebuild `base` at a given year, zero-based month and day-of-month,
    letting both the month and the day spill over rather than clamping.

    Counting `day - 1` days from the first of the target month is exactly what
    a JavaScript Date does when its day number exceeds the month it lands in.
    """
    years += month0 // 12
    month0 %= 12
    first = date(years, month0 + 1, 1)
    landed = first + timedelta(days=day - 1)
    return base.replace(year=landed.year, month=landed.month, day=landed.day)


def _add(base: datetime, duration: _Duration) -> datetime:
    """`addDuration`, in its original order: years, months, weeks, days.

    The order is load-bearing, not stylistic — shifting the year first and the
    month second can spill twice, and doing it the other way round would not.
    """
    out = base
    if duration.years:
        out = _shift(out, out.year + duration.years, out.month - 1, out.day)
    if duration.months:
        out = _shift(out, out.year, out.month - 1 + duration.months, out.day)
    if duration.weeks:
        out = out + timedelta(days=duration.weeks * 7)
    if duration.days:
        out = out + timedelta(days=duration.days)
    return out


def _build_date(year: int, month: int, day: int) -> datetime | None:
    """A UTC midnight, or None if those numbers are not a real date.

    The `year < 100` refusal is not arbitrary: see the module docstring.
    """
    if month < 1 or month > 12 or day < 1 or day > 31 or year < 100:
        return None
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:  # Feb 30, Apr 31, and the rest
        return None


def _parse_token(raw: str, locale: Locale) -> tuple[str, object]:
    """One `{…}`'s inner text → ("duration"|"absolute"|"other", payload)."""
    from .parser import js_trim

    token = js_trim(raw).lower()
    if not token:
        return ("other", None)
    if token == "remind":
        # Accepted and cosmetic. Any `{…}` that resolves to a future time is
        # already the signal; this only ever said so out loud.
        return ("other", None)
    if token in ("tmr", "tomorrow"):
        return ("duration", _Duration(days=1))

    simple = _SIMPLE_RE.match(token)
    if simple:
        count = int(simple.group(1))
        if count <= 0:
            return ("other", None)
        unit = simple.group(2)
        return (
            "duration",
            {
                "d": _Duration(days=count),
                "w": _Duration(weeks=count),
                "m": _Duration(months=count),
                "y": _Duration(years=count),
            }[unit],
        )

    composite = _COMPOSITE_RE.match(token)
    if composite and token and any(composite.groups()):
        parts = [g for g in composite.groups() if g]
        # At least one unit, at most three. `{1y2m3w4d}` is not a duration.
        if 1 <= len(parts) <= 3:
            years, months, weeks, days = (
                int(g[:-1]) if g else 0 for g in composite.groups()
            )
            return ("duration", _Duration(years, months, weeks, days))

    dated = _DATE_RE.match(token)
    if dated:
        first, second = int(dated.group(1)), int(dated.group(2))
        raw_year = int(dated.group(3))
        year = 2000 + raw_year if len(dated.group(3)) == 2 else raw_year
        # The locale's reading first; the other one only if that is not a real
        # date. A US user who writes 25/12/26 still means Christmas.
        orders = ((second, first), (first, second))
        if locale != "us":
            orders = ((first, second), (second, first))
        for day, month in orders:
            built = _build_date(year, month, day)
            if built is not None:
                return ("absolute", built)

    return ("other", None)


def resolve_reminders(
    raw_text: str, now: datetime, locale: Locale = "row"
) -> list[ResolvedReminder]:
    """Every line of `raw_text` that names a future time, as a due date."""
    from .parser import js_trim

    out: list[ResolvedReminder] = []

    for index, line in enumerate(raw_text.split("\n")):
        duration: _Duration | None = None
        absolute: datetime | None = None

        for match in _TOKEN_RE.finditer(line):
            kind, value = _parse_token(match.group(1), locale)
            if kind == "duration" and duration is None:
                duration = value  # type: ignore[assignment]
            elif kind == "absolute" and absolute is None:
                absolute = value  # type: ignore[assignment]

        if duration is None and absolute is None:
            continue

        due_at = absolute if absolute is not None else _add(now, duration)
        if due_at <= now:
            continue

        out.append(
            ResolvedReminder(line_index=index, line_text=js_trim(line), due_at=due_at)
        )

    return out
