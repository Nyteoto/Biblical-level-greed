"""The sealed Records: one JSON file per Instance that made it.

Why it is shaped this way
-------------------------
**A Record is written once and never again.** That is the whole promise the
Portal makes to the next Instance: what 8193 wrote is what 8194 reads, and no
later hand can soften it. So there is a `write` that refuses to replace an
existing file and no update, no delete, no route to either. A mistake in a
sealed Record stays in it, the same way a mistake in a diary does.

**JSON is the truth; the PDF is a print of it.** `pdf.py` renders from these
files and can render them all again, so the layout, the page size and the
image quality of the printed archive can change without touching a single
Record. Keeping only the PDF was weighed and lost on exactly that: a print
cannot be re-printed at a better scale, and the remarks need yesterday's mood
as a number rather than as ink.

**The latest Record is simply the highest number.** Nothing is marked current
and nothing is replaced. A terminated day leaves a gap in the numbering, and
the gap is the only trace it leaves — which is how the Portal can say how many
Instances failed without having kept anything about them.

**The filename is the number, and the number is the day.** `8193.json` and the
day it was lived are one fact (`timeutil.day_of`), so the name answers "which
day is this" in a file manager without opening it.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .config import RECORDS_DIR


def _umask() -> int:
    """Read the process umask without leaving it changed. There is no getter."""
    current = os.umask(0o022)
    os.umask(current)
    return current


class SealedError(Exception):
    """A Record with this number already exists. It is not replaced."""


def path_of(instance: int) -> Path:
    return RECORDS_DIR / f"{instance}.json"


def numbers() -> list[int]:
    """Every sealed instance number, ascending."""
    if not RECORDS_DIR.exists():
        return []
    found = []
    for path in RECORDS_DIR.glob("*.json"):
        if path.stem.isdigit():
            found.append(int(path.stem))
    return sorted(found)


def exists(instance: int) -> bool:
    return path_of(instance).is_file()


def read(instance: int) -> dict | None:
    path = path_of(instance)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def latest(before: int | None = None) -> dict | None:
    """The newest sealed Record, or the newest one strictly before `before`."""
    candidates = [n for n in numbers() if before is None or n < before]
    return read(candidates[-1]) if candidates else None


def write(record: dict) -> Path:
    """Seal a Record. Raises `SealedError` if that number is already sealed.

    Written to a temporary file beside the target and moved into place, so a
    crash halfway leaves no half-Record for the next Instance to read. The
    existence check and the move are not one atomic step — exFAT, where this
    lives on a dual-boot machine, has no hard links to make them one — and the
    caller holds the day's lock across both, which in a single-user app with
    one process is the whole of the race.
    """
    target = path_of(int(record["instance"]))
    if target.exists():
        raise SealedError(f"Record {record['instance']} is already sealed")
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=target.parent, suffix=".part")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(record, out, ensure_ascii=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        # mkstemp creates 0600; a Record readable by fewer people than its own
        # photographs is a surprise for whoever next runs a backup as another
        # user. The umask default, as everything else under data/ gets.
        os.chmod(temp, 0o666 & ~_umask())
        os.replace(temp, target)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return target
