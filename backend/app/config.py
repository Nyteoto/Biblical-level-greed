"""Paths and tunables. Everything else imports locations from here."""
from __future__ import annotations

import os
from pathlib import Path

# Repo root is two levels up from backend/app/.
ROOT = Path(__file__).resolve().parents[2]

# Set when the data lives somewhere other than the checkout — another disk, an
# encrypted volume, a drive shared with the machine's other operating system.
DATA_DIR_ENV = os.environ.get("PGS_DATA_DIR")

DATA_DIR = Path(DATA_DIR_ENV or ROOT / "data")
DOMAINS_DIR = DATA_DIR / "domains"
LOG_DIR = DATA_DIR / "log"
INDEX_PATH = Path(os.environ.get("PGS_INDEX_PATH", DATA_DIR / "index.sqlite"))

# The user's day boundary. Every date in this system is computed in this zone.
TZ_OFFSET_HOURS = int(os.environ.get("PGS_TZ_OFFSET_HOURS", "7"))


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
    if not any((DATA_DIR / name).exists() for name in ("log", "domains", "capture")):
        raise DataDirMissing(
            f"PGS_DATA_DIR is {DATA_DIR} but it holds no log, no trees and no "
            "capture directory. That is what an unmounted disk looks like, so "
            "this is a refusal rather than a fresh start. Use "
            "`pgs --data-dir` if you really mean to begin a new one here."
        )


def ensure_dirs() -> None:
    DOMAINS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
