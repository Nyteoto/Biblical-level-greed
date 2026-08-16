"""When the backup last worked, and a button that runs it.

`backup.sh` already writes `.last-backup` into the destination on success, and
its own comment says why: "the only question that matters about a backup" is
when it last *actually* worked, and a silent timer never answers it. This module
is the reader of that stamp, plus a way to start a run from the Settings screen
when you are about to unplug the disk and do not want to wait for the timer.

Three things this deliberately does not do:

- **It does not reimplement any of the script.** The device check and the
  missing `--delete` are the two refusals that make the script safe, and a
  second copy of that logic in Python would be a second place for it to rot.
  This shells out to the one file, and reports what it said.
- **It does not report the destination's size.** Walking a backup disk on every
  Settings load costs seconds for a number the local total already implies.
- **It does not queue.** One run at a time; asking again while one is in flight
  gets the run already going, not a second rsync over the same tree.
"""
from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR

SCRIPT = Path(__file__).resolve().parents[2] / "backup.sh"
DEFAULT_DEST = "/mnt/data/pgs-backup"

_lock = threading.Lock()
_running = False
# What the last run this process started had to say. `None` until one has been
# asked for — a backup made by the timer leaves its trace in the stamp file
# instead, which is the same fact from the other direction.
_last: dict | None = None


def destination() -> Path:
    return Path(os.environ.get("PGS_BACKUP_DIR", DEFAULT_DEST))


def _stamp(dest: Path) -> str | None:
    """The ISO timestamp `backup.sh` writes on success, or None if it has never
    finished here. Unreadable is the same as absent: a stamp you cannot read
    tells you nothing, and guessing would be worse than saying so."""
    try:
        return (dest / ".last-backup").read_text().strip() or None
    except OSError:
        return None


def status() -> dict:
    dest = destination()
    last = _stamp(dest)
    ago = None
    if last:
        try:
            delta = datetime.now(timezone.utc) - datetime.fromisoformat(last).astimezone(
                timezone.utc
            )
            ago = int(delta.total_seconds())
        except ValueError:
            last = None
    return {
        "destination": str(dest),
        "source": str(DATA_DIR),
        "last": last,
        "seconds_ago": ago,
        "running": _running,
        "result": _last,
    }


def _run(dest: Path) -> None:
    global _running, _last
    try:
        done = subprocess.run(
            [str(SCRIPT), str(dest)],
            capture_output=True,
            text=True,
            # Long enough for a first copy of a media library over USB, short
            # enough that a wedged rsync does not hold the flag forever.
            timeout=60 * 60 * 6,
        )
        # The script's own refusals go to stderr and are the whole message when
        # it declines — passed through verbatim, because they explain
        # themselves better than any status code this could invent.
        said = (done.stderr.strip() or done.stdout.strip()).splitlines()
        _last = {
            "ok": done.returncode == 0,
            "message": said[-1] if said else "",
        }
    except (OSError, subprocess.SubprocessError) as exc:
        _last = {"ok": False, "message": str(exc)}
    finally:
        with _lock:
            _running = False


def start() -> dict:
    """Kick off a run in the background and return immediately.

    Backing up a media library takes minutes; a request that waited for it
    would time out and tell the user nothing. The screen polls `status()`.
    """
    global _running, _last
    with _lock:
        if _running:
            return status()
        if not SCRIPT.is_file():
            return {**status(), "result": {"ok": False, "message": f"no {SCRIPT}"}}
        _running = True
        _last = None
    threading.Thread(target=_run, args=(destination(),), daemon=True).start()
    return status()
