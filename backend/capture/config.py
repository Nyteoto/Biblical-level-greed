"""Paths and tunables for capture. Everything else imports locations from here.

Reads `PGS_DATA_DIR` — the same variable the tech tree reads — and then claims
its own subtree under it. That is the whole of the "sibling app" arrangement:
one data root on one disk, backed up by one `backup.sh`, but two independent
logs that never have to agree about anything. Tests get isolation for free,
because `conftest.py` sets that variable before either app is imported.
"""
from __future__ import annotations

import os
from pathlib import Path

# Repo root is two levels up from backend/capture/.
ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("PGS_DATA_DIR", ROOT / "data"))
CAPTURE_DIR = DATA_DIR / "capture"
LOG_DIR = CAPTURE_DIR / "log"
INDEX_PATH = Path(
    os.environ.get("PGS_CAPTURE_INDEX_PATH", CAPTURE_DIR / "index.sqlite")
)

# The source app caps a capture at 2000 characters. Kept, not because storage
# is short here, but because the capture bar is for a thought you can hold in
# your head — anything longer is a note, and notes have their own home.
MAX_RAW_LEN = 2000


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
