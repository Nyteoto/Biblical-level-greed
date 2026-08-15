"""Reading a CSV of somebody else's thoughts into this one.

A port of `trophic/reference/logic/import-csv.ts`: a small CSV reader and a
very generous date parser, pinned by 48 golden fixtures across two corpus
files. Both are pure.

What the port added
-------------------
**`compose_line` puts the syntax back into the text.** The source's importer
writes `folders` and `patterns` into columns beside `rawText`, because that is
where its reader looks. Here those columns do not exist — they are derived by
running the parser over the raw line — so a tag that arrives in its own CSV
column has to be written *into* the line or it is lost on the next rebuild.
Composing `<tag>` and `\\pattern` back onto the end of the text is the only
lossless answer, and it has a pleasant side effect: an imported entry is
indistinguishable from a typed one, and editing history is not a special case.

Why the date parser is shaped this way
--------------------------------------
`flexParseTime` opens with `new Date(s)`, which is the JavaScript engine's own
date parsing — an enormous, half-specified surface that no Python port can
reproduce in general. It does not have to. Of the strings the corpus feeds it,
only the ISO-shaped ones actually need that branch: every numeric and
named-month form the engine accepts is also matched by one of the regexes
below, and produces the same instant either way. So `_engine_date` implements
ISO 8601 and nothing else, and everything else falls through to the regexes.
A string V8 would accept and this rejects will take the slower path to the
same answer, or to `None` — the corpus is silent on which, and it is the only
authority there is.

Three JavaScript behaviours are deliberate here:

 - **A bare ISO date is UTC; everything else is local.** `new Date("2026-01-01")`
   is midnight UTC, while `new Date(2026, 0, 1)` is midnight where you are
   standing. That inconsistency is real, it is in the source, and importing a
   date-only CSV in a non-UTC zone therefore lands it at an offset. Preserved:
   changing it would silently move every imported row by a few hours relative
   to what the source did with the same file.
 - **Numeric dates disambiguate by magnitude, not by locale.** If the first
   number is over 12 it is the day. `reminder.py` does the opposite and asks
   the locale. Both are intentional; the note in the corpus says so.
 - **Out-of-range parts overflow rather than fail.** `32/1/2026` is the 1st of
   February, because `new Date(2026, 0, 32)` is.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo

from .parser import js_trim

# `[0-9]`, never `\d`: Python's is Unicode and JavaScript's is not.
_NUM_DATE_RE = re.compile(
    r"^([0-9]{1,2})[/\-.]([0-9]{1,2})[/\-.]([0-9]{2,4})(?:\s+(.+))?$"
)
_NAMED_A_RE = re.compile(r"^([a-zA-Z]+)\s+([0-9]{1,2}),?\s*([0-9]{2,4})(?:\s+(.+))?$")
_NAMED_B_RE = re.compile(r"^([0-9]{1,2})\s+([a-zA-Z]+),?\s*([0-9]{2,4})(?:\s+(.+))?$")
_TIME_24_RE = re.compile(r"^([0-9]{1,2}):([0-9]{2})$")
_TIME_12_RE = re.compile(r"^([0-9]{1,2}):([0-9]{2})\s*(am|pm)$")
_TIME_BARE_RE = re.compile(r"^([0-9]{1,2})\s*(am|pm)$")
_ISO_RE = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})"
    r"(?:[T ]([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.([0-9]{1,3}))?)?"
    r"(Z|[+-][0-9]{2}:?[0-9]{2})?)?$"
)

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12,
    "december": 12,
}


@dataclass(frozen=True)
class CsvRow:
    time: str
    text: str
    tags: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedCsv:
    rows: list[CsvRow]
    has_header: str  # "full" | "basic" | "none"


# ── The CSV half ──────────────────────────────────────────────────────────


def _split_line(line: str) -> list[str]:
    """One line into fields. Doubled quotes inside a quoted field are one."""
    fields: list[str] = []
    current: list[str] = []
    in_quotes = False
    i = 0
    while i < len(line):
        char = line[i]
        if in_quotes:
            if char == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    current.append('"')
                    i += 1
                else:
                    in_quotes = False
            else:
                current.append(char)
        elif char == '"':
            in_quotes = True
        elif char == ",":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
        i += 1
    fields.append("".join(current))
    return fields


def _split_list(cell: str | None) -> list[str]:
    if not cell:
        return []
    return [t for t in (js_trim(s).lower() for s in cell.split(",")) if t]


def parse_import_csv(csv: str) -> ParsedCsv:
    """Rows, and whether the file led with one of our own headers.

    Header detection is case-insensitive and does not care about column order:
    `time` and `text` both present means a header, and `tags` or `patterns`
    alongside them means the file carries the full shape. Anything less and
    the tag columns are ignored even if they are there — the source refuses to
    guess at a file it did not write.

    Note that each line is trimmed *before* it is split, so a quoted field at
    the very start or end of a line loses its outer whitespace. That is the
    source's order of operations and one of the corpus's notes.
    """
    all_rows = [_split_line(t) for t in (js_trim(l) for l in csv.split("\n")) if t]
    if not all_rows:
        return ParsedCsv(rows=[], has_header="none")

    first = [js_trim(cell).lower() for cell in all_rows[0]]
    has_header = "none"
    if "time" in first and "text" in first:
        has_header = "full" if ("tags" in first or "patterns" in first) else "basic"

    data = all_rows[1:] if has_header != "none" else all_rows
    is_full = has_header == "full"

    rows: list[CsvRow] = []
    for cells in data:
        text = js_trim(cells[1]) if len(cells) > 1 else ""
        if not text:  # a row with no words is not an entry
            continue
        rows.append(
            CsvRow(
                time=js_trim(cells[0]) if cells else "",
                text=text,
                tags=_split_list(cells[2] if len(cells) > 2 else None) if is_full else [],
                patterns=(
                    _split_list(cells[3] if len(cells) > 3 else None) if is_full else []
                ),
            )
        )

    return ParsedCsv(rows=rows, has_header=has_header)


# ── The date half ─────────────────────────────────────────────────────────


def _local(
    year: int, month: int, day: int, zone: tzinfo, hour: int = 0, minute: int = 0
) -> datetime:
    """`new Date(y, m, d)`: a wall-clock date in `zone`, with both the month
    and the day allowed to run off the end and carry."""
    if 0 <= year <= 99:
        year += 1900  # the JavaScript rule, not a typo
    year += (month - 1) // 12
    month = (month - 1) % 12 + 1
    landed = date(year, month, 1) + timedelta(days=day - 1)
    return datetime(
        landed.year, landed.month, landed.day, hour, minute, tzinfo=zone
    )


def _engine_date(text: str, zone: tzinfo) -> datetime | None:
    """The ISO slice of `new Date(str)`. See the module docstring."""
    match = _ISO_RE.match(text)
    if match is None:
        return None
    year, month, day = (int(match.group(i)) for i in (1, 2, 3))
    hour, minute = (int(g) if g else 0 for g in (match.group(4), match.group(5)))
    second = int(match.group(6)) if match.group(6) else 0
    micro = int(match.group(7).ljust(3, "0")) * 1000 if match.group(7) else 0
    offset = match.group(8)

    if match.group(4) is None:
        # Date only. UTC, by the standard and by V8 — unlike every other form.
        where: tzinfo = timezone.utc
    elif offset in (None, ""):
        where = zone
    elif offset == "Z":
        where = timezone.utc
    else:
        sign = 1 if offset[0] == "+" else -1
        digits = offset[1:].replace(":", "")
        where = timezone(
            sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
        )

    try:
        return datetime(
            year, month, day, hour, minute, second, micro, tzinfo=where
        ).astimezone(zone)
    except ValueError:
        return None


def _parse_time_part(text: str) -> tuple[int, int] | None:
    """`14:30`, `2:30 pm`, `2pm`. Anything else is not a time."""
    s = js_trim(text).lower()

    match = _TIME_24_RE.match(s)
    if match:
        return (int(match.group(1)), int(match.group(2)))

    match = _TIME_12_RE.match(s)
    if match:
        hour = int(match.group(1))
        if match.group(3) == "pm" and hour != 12:
            hour += 12
        if match.group(3) == "am" and hour == 12:
            hour = 0
        return (hour, int(match.group(2)))

    match = _TIME_BARE_RE.match(s)
    if match:
        hour = int(match.group(1))
        if match.group(2) == "pm" and hour != 12:
            hour += 12
        if match.group(2) == "am" and hour == 12:
            hour = 0
        return (hour, 0)

    return None


def _year_of(digits: str) -> int:
    return 2000 + int(digits) if len(digits) == 2 else int(digits)


def flex_parse_time(
    raw: str | None, now: datetime, zone: tzinfo | None = None
) -> datetime | None:
    """A timestamp out of whatever the spreadsheet had in that column.

    Returns None when nothing parses; the caller decides whether that is a row
    to skip or a row to stamp with the time of import.
    """
    zone = zone or now.tzinfo or timezone.utc
    if not raw:
        return None
    s = js_trim(raw)
    if not s:
        return None

    # Anything before 1971 is treated as a failed parse rather than a date.
    # It is how the source rejects the epoch, which is what a spreadsheet
    # produces from an empty cell.
    native = _engine_date(s, zone)
    if native is not None and native.year > 1970:
        return native

    numeric = _NUM_DATE_RE.match(s)
    if numeric:
        first, second = int(numeric.group(1)), int(numeric.group(2))
        year = _year_of(numeric.group(3))
        # Magnitude, not locale: over 12 can only be a day.
        month, day = (second, first) if first > 12 else (first, second)
        base = _local(year, month, day, zone)
        part = _parse_time_part(numeric.group(4)) if numeric.group(4) else None
        return base.replace(hour=part[0], minute=part[1]) if part else base

    for match, name_group, day_group in (
        (_NAMED_A_RE.match(s), 1, 2),
        (_NAMED_B_RE.match(s), 2, 1),
    ):
        if match is None:
            continue
        month = MONTHS.get(match.group(name_group).lower())
        if month is None:
            continue
        base = _local(
            _year_of(match.group(3)), month, int(match.group(day_group)), zone
        )
        part = _parse_time_part(match.group(4)) if match.group(4) else None
        return base.replace(hour=part[0], minute=part[1]) if part else base

    # A bare time means today, wherever the caller's clock is.
    part = _parse_time_part(s)
    if part:
        return now.astimezone(zone).replace(
            hour=part[0], minute=part[1], second=0, microsecond=0
        )

    return None


# ── Putting a row back into a line ────────────────────────────────────────


def compose_line(row: CsvRow) -> str:
    """The raw line an imported row becomes.

    Tags and patterns already written into the text are not repeated — a file
    exported from this app round-trips to itself rather than growing a second
    copy of its own syntax on every pass.
    """
    from .parser import parse_entry

    parsed = parse_entry(row.text)
    extra = [f"<{t}>" for t in row.tags if t not in parsed.folders]
    extra += [f"\\{p}" for p in row.patterns if p not in parsed.patterns]
    return " ".join([row.text, *extra]) if extra else row.text
