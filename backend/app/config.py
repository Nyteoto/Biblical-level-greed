"""Paths and tunables. Everything else imports locations from here."""
from __future__ import annotations

import os
from pathlib import Path

# Repo root is two levels up from backend/app/.
ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("PGS_DATA_DIR", ROOT / "data"))
DOMAINS_DIR = DATA_DIR / "domains"
LOG_DIR = DATA_DIR / "log"
INDEX_PATH = Path(os.environ.get("PGS_INDEX_PATH", DATA_DIR / "index.sqlite"))

# The user's day boundary. Every date in this system is computed in this zone.
TZ_OFFSET_HOURS = int(os.environ.get("PGS_TZ_OFFSET_HOURS", "7"))


def ensure_dirs() -> None:
    DOMAINS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
