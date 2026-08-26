"""Point the app at a throwaway data directory before it is imported."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="pgs-test-"))
os.environ["PGS_DATA_DIR"] = str(_TMP)

import pytest  # noqa: E402

from backend.app import config  # noqa: E402


@pytest.fixture
def data_dir() -> Path:
    """A clean data directory for each test.

    Everything that lives beside the log rather than inside it has to be
    cleared explicitly, or state leaks between tests — a photograph written by
    one test was counted by the next one's storage report.
    """
    shutil.rmtree(config.MEDIA_DIR, ignore_errors=True)
    config.ensure_dirs()
    return _TMP


@pytest.fixture
def capture_store():
    """A clean capture app: its own log and index, thrown away between tests."""
    from backend.capture import config as capture_config
    from backend.capture.store import Store

    shutil.rmtree(capture_config.CAPTURE_DIR, ignore_errors=True)
    capture_config.ensure_dirs()
    store = Store()
    store.start()
    yield store
    store.close()
