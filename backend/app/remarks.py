"""What the Portal says when an Instance wakes.

Why it is shaped this way
-------------------------
**Written in advance, chosen by state.** The lines are pre-written in
`remarks.toml`, grouped into pools, and each pool has a condition read off the
Records — whether any exist, how many Instances failed since the last one,
what mood it was left in. The first pool whose condition holds is the one
spoken from. Adding a new kind of remark is a new condition here and a new
pool there; the lines themselves never touch code.

**Seeded by the instance number.** A remark drawn fresh on every request
would change under the Instance each time it reloaded, which reads as a
machine rolling dice rather than a machine that has an opinion. Seeded, 8193
hears one thing all day and 8194 hears something else.

**Derived from Records and nothing else.** A failed day leaves no file, so
"how many failed" is the gap between the last sealed number and this one.
The remark knows only what the Records can tell it — which is also all the
next Instance can know, and that is the premise.
"""
from __future__ import annotations

import random
import tomllib
from pathlib import Path

from . import records

_SOURCE = Path(__file__).with_name("remarks.toml")


def _pools() -> list[dict]:
    with _SOURCE.open("rb") as handle:
        return tomllib.load(handle)["pool"]


def context(instance: int) -> dict:
    """The facts a remark may be about, as seen from `instance`'s morning."""
    last = records.latest(before=instance)
    if last is None:
        return {"n": instance, "next": instance + 1, "first": True}
    return {
        "n": instance,
        "next": instance + 1,
        "prev": last["instance"],
        "gap": instance - last["instance"] - 1,
        "mood": last.get("mood"),
        "first": False,
    }


_CONDITIONS = {
    "first": lambda c: c["first"],
    "failed_many": lambda c: not c["first"] and c["gap"] >= 3,
    "failed": lambda c: not c["first"] and c["gap"] >= 1,
    "mood_low": lambda c: not c["first"] and (c["mood"] or 10) <= 3,
    "mood_high": lambda c: not c["first"] and (c["mood"] or 0) >= 8,
    "always": lambda c: True,
}


def pick(instance: int) -> str:
    facts = context(instance)
    for pool in _pools():
        test = _CONDITIONS.get(pool["when"])
        if test is None or not test(facts):
            continue
        line = random.Random(instance).choice(pool["lines"])
        # `format_map` over a dict that leaves unknown names alone, so a line
        # that mentions {prev} in a pool where there is no prev prints the
        # brace rather than taking the greeting down with a KeyError.
        return line.format_map(_Leave(facts))
    return ""


class _Leave(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
