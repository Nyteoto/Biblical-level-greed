"""What the Portal says when an Instance wakes.

Why it is shaped this way
-------------------------
**Written in advance, chosen by state.** The lines are pre-written in
`remarks.toml`, grouped into pools, and each pool has a condition read off the
Records and the clock — whether any Records exist, how many Instances failed
since the last one, what the last one wished for, what it signed. Adding a new
kind of remark is a condition here and a pool there; the lines themselves
never touch code.

**Some situations must be addressed; everything else is flavour.** A pool
marked `exclusive` is a situation the Portal cannot talk past — the first
Instance ever, Instances that failed, a waking after the window has opened —
and the first exclusive pool that holds is the only one spoken from. When none
does, every other pool that holds is pooled together and one line is drawn
from the lot, so an ordinary day does not hear the same four lines forever.

**Seeded by the instance number.** A remark drawn fresh on every request would
change under the Instance each time it reloaded, which reads as a machine
rolling dice rather than a machine that has an opinion. Seeded, 8193 hears one
thing all day and 8194 hears something else. The one exception is `late`,
which depends on the hour: an Instance that wakes at noon and reloads at 19:30
is told the window is already open, because by then it is.

**Derived from Records and nothing else.** A failed day leaves no file, so
"how many failed" is the gap between the last sealed number and this one. The
remark may quote the last Record — its mood, its wish, its signature — but it
never keeps score across Records: no averages, no trends, no streaks.
"""
from __future__ import annotations

import random
import re
import tomllib
from datetime import datetime
from pathlib import Path

from . import records, timeutil

_SOURCE = Path(__file__).with_name("remarks.toml")


def _pools() -> list[dict]:
    with _SOURCE.open("rb") as handle:
        return tomllib.load(handle)["pool"]


def _words(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def context(instance: int, now: datetime | None = None) -> dict:
    """The facts a remark may be about, as seen from `instance`'s day."""
    day = timeutil.day_of(instance)
    facts: dict = {
        "n": instance,
        "next": instance + 1,
        "weekday": timeutil.parse_day(day).strftime("%A"),
        "late": now is not None and timeutil.in_window(now),
        "first": True,
    }
    last = records.latest(before=instance)
    if last is None:
        return facts
    signature = str(last.get("signature") or "").strip()
    facts.update(
        first=False,
        prev=last["instance"],
        gap=instance - last["instance"] - 1,
        mood=last.get("mood"),
        wish=str(last.get("wish") or "").strip(),
        signature=signature,
        words=_words(last.get("body", "")),
        media=len(last.get("media") or []),
        signed_otherwise=bool(signature) and signature != str(last["instance"]),
    )
    return facts


_CONDITIONS = {
    "first": lambda c: c["first"],
    "failed_many": lambda c: not c["first"] and c["gap"] >= 3,
    "failed": lambda c: not c["first"] and c["gap"] >= 1,
    "milestone": lambda c: c["n"] % 100 == 0,
    "late": lambda c: c["late"],
    "mood_low": lambda c: not c["first"] and (c["mood"] or 10) <= 3,
    "mood_high": lambda c: not c["first"] and (c["mood"] or 0) >= 8,
    "wish": lambda c: not c["first"] and bool(c["wish"]),
    "signed_otherwise": lambda c: not c["first"] and c["signed_otherwise"],
    "terse": lambda c: not c["first"] and c["words"] < 15,
    "verbose": lambda c: not c["first"] and c["words"] > 400,
    "no_media": lambda c: not c["first"] and c["media"] == 0,
    "weekend": lambda c: c["weekday"] in ("Saturday", "Sunday"),
    "always": lambda c: True,
}


def pick(instance: int, now: datetime | None = None) -> str:
    facts = context(instance, now)
    held = [
        pool
        for pool in _pools()
        if (test := _CONDITIONS.get(pool["when"])) is not None and test(facts)
    ]
    exclusive = next((pool for pool in held if pool.get("exclusive")), None)
    lines = (
        exclusive["lines"]
        if exclusive
        else [line for pool in held for line in pool["lines"]]
    )
    if not lines:
        return ""
    line = random.Random(instance).choice(lines)
    # `format_map` over a dict that leaves unknown names alone, so a line that
    # mentions {prev} where there is no prev prints the brace rather than
    # taking the greeting down with a KeyError.
    return line.format_map(_Leave(facts))


class _Leave(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
