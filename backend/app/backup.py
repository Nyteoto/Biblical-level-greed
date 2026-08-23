"""When the backup last worked, and a button that runs it.

The backup script already writes `.last-backup` into the destination on success,
and its own comment says why: "the only question that matters about a backup" is
when it last *actually* worked, and a silent timer never answers it. This module
is the reader of that stamp, plus a way to start a run from the Settings screen
when you are about to unplug the disk and do not want to wait for the timer.

There are two scripts — `backup.sh` and `backup.ps1`, one per operating system —
and this picks between them by platform. Everything below that line is written
once and knows nothing about which one it ran.

Three things this deliberately does not do:

- **It does not reimplement any of the script.** The device check and the
  missing delete are the two refusals that make a backup safe, and a third copy
  of that logic in Python would be a third place for it to rot. This shells out,
  and reports what the script said.
- **It does not report the destination's size.** Walking a backup disk on every
  Settings load costs seconds for a number the local total already implies.
- **It does not queue.** One run at a time; asking again while one is in flight
  gets the run already going, not a second copy over the same tree.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR

# One script per operating system, rather than one script with branches in it.
# `rsync`, `df --output=source` and `date -Iseconds` have no Windows equivalent
# worth shimming, and the two refusals that make a backup safe are easier to
# read stated twice than to find inside a platform conditional. This module
# stays the thin thing it always was: it picks the file and reports what it
# said.
ROOT = Path(__file__).resolve().parents[2]
_WINDOWS = sys.platform == "win32"
SCRIPT = ROOT / ("backup.ps1" if _WINDOWS else "backup.sh")

# The two operating systems back up to different disks, and must. The Linux
# destination is ext4, which Windows cannot read; the Windows one is on the
# internal NTFS disk, which is a different physical device from the shared
# exFAT drive the data lives on — so both satisfy the same "not the same
# device" refusal. Neither script ever deletes, and both read one shared data
# directory, so these are two complete copies of one source rather than two
# halves that need reconciling.
DEFAULT_DEST = "C:\\pgs-backup" if _WINDOWS else "/mnt/data/pgs-backup"

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


def _command(dest: Path) -> list[str]:
    """The argv that runs the script.

    A `.ps1` is not executable the way a `.sh` with a shebang is — Windows
    has no such concept — so it has to be handed to an interpreter, and with
    the execution policy waived, because the default on a desktop install
    refuses unsigned local scripts and does it with an error about publishers
    that explains nothing about backups.
    """
    if _WINDOWS:
        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            str(dest),
        ]
    return [str(SCRIPT), str(dest)]


def _run(dest: Path) -> None:
    global _running, _last
    try:
        done = subprocess.run(
            _command(dest),
            capture_output=True,
            text=True,
            # Long enough for a first copy of a media library over USB, short
            # enough that a wedged copy does not hold the flag forever.
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
