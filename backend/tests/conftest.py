"""Point the app at a throwaway data directory before it is imported."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="pgs-test-"))
os.environ["PGS_DATA_DIR"] = str(_TMP)
(_TMP / "portal").mkdir()

import pytest  # noqa: E402

from backend.app import config  # noqa: E402


@pytest.fixture
def data_dir() -> Path:
    """A clean data directory for each test.

    Everything the Portal and the blob store keep is under these two trees, so
    clearing them is the whole of a fresh start — nothing leaks between tests,
    least of all a sealed Record, which no code path is allowed to remove.
    """
    for tree in ("media", "portal"):
        shutil.rmtree(config.DATA_DIR / tree, ignore_errors=True)
    config.ensure_dirs()
    return _TMP
