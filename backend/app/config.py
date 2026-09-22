"""Paths and tunables. Everything else imports locations from here."""
from __future__ import annotations

import os
from datetime import date, time
from pathlib import Path

# Repo root is two levels up from backend/app/.
ROOT = Path(__file__).resolve().parents[2]

# Set when the data lives somewhere other than the checkout — another disk, an
# encrypted volume, a drive shared with the machine's other operating system.
DATA_DIR_ENV = os.environ.get("PGS_DATA_DIR")

DATA_DIR = Path(DATA_DIR_ENV or ROOT / "data")
MEDIA_DIR = DATA_DIR / "media"
PORTAL_DIR = DATA_DIR / "portal"
# The sealed Records: one write-once JSON per Instance that committed.
RECORDS_DIR = PORTAL_DIR / "records"
# Their printable form, rendered from the JSON and reproducible from it.
PDF_DIR = PORTAL_DIR / "pdf"
# The day in progress. The only file in the Portal that is ever deleted.
TODAY_PATH = PORTAL_DIR / "today.json"

# The user's day boundary. Every date in this system is computed in this zone.
TZ_OFFSET_HOURS = int(os.environ.get("PGS_TZ_OFFSET_HOURS", "7"))

# The true birth: Instance 0. Chosen so that 2026-09-22 is Instance 8193, the
# day the Portal was first opened — the number is the premise, not a birthday.
BIRTH = date(2004, 4, 17)

# When a Record can be committed, in the zone above. Closing an hour before
# midnight is deliberate: the deadline is 23:00, and the hour after it is when
# the Instance finds out whether it made it.
WINDOW_OPEN = time(19, 0)
WINDOW_CLOSE = time(23, 0)

# How long a sitting may go unheard before it is over. Long enough for a phone
# to lock, or for the camera to take the tab away while a clip is recorded;
# short enough that walking off and coming back tomorrow is not a sitting.
SITTING_GRACE_SECONDS = int(os.environ.get("PGS_SITTING_GRACE", "300"))

# Media blocks on a Record, not counting the selfie.
MAX_MEDIA = 4


class DataDirMissing(RuntimeError):
    """`PGS_DATA_DIR` points at something that is not there."""


def check_data_dir() -> None:
    """Refuse to start on a data directory that has not been mounted.

    Only when `PGS_DATA_DIR` was set. The reasoning is the same as the one
    behind `backup.sh`'s device check, and the danger is worse: when the data
    lives on a removable disk and that disk is not mounted, its mount point is
    an ordinary empty directory. `ensure_dirs` would cheerfully create the tree
    inside it and the app would come up looking brand new — no trees, no log,
    no photographs — and then start writing a *second* history into the wrong
    filesystem. The two would have to be merged by hand afterwards, if anyone
    noticed at all.

    So: a configured data directory must already exist and already have
    something of ours in it. Nothing is created. The first run on a new disk
    is the one case that needs a directory made, and `pgs --data-dir` makes it
    explicitly, which is the difference between asking and assuming.
    """
    if DATA_DIR_ENV is None:
        return
    if not DATA_DIR.is_dir():
        raise DataDirMissing(
            f"PGS_DATA_DIR is {DATA_DIR} and there is no directory there. "
            "If it is on a removable disk, it is probably not mounted — "
            "nothing has been created and nothing has been written."
        )
    # An empty directory at a mount point is what an unmounted disk looks
    # like. A real data directory always has at least one of these.
    if not any(
        (DATA_DIR / name).exists()
        for name in ("portal", "media", "log", "domains", "capture")
    ):
        raise DataDirMissing(
            f"PGS_DATA_DIR is {DATA_DIR} but it holds no portal, no media and "
            "nothing from the apps before it. That is what an unmounted disk looks like, so "
            "this is a refusal rather than a fresh start. Use "
            "`pgs --data-dir` if you really mean to begin a new one here."
        )


def ensure_dirs() -> None:
    for directory in (MEDIA_DIR, RECORDS_DIR, PDF_DIR):
        directory.mkdir(parents=True, exist_ok=True)
