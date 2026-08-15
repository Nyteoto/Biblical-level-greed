"""Refusing to start on a disk that is not mounted.

The data can live on a removable drive — a second disk, or one shared with the
machine's other operating system. When such a drive is not mounted its mount
point is an ordinary empty directory, and the app's own `ensure_dirs` would
happily build a tree inside it: no history, no trees, no photographs, and from
then on a second parallel history being written to the wrong filesystem.

That is the failure `backup.sh` already refuses for the copy. These pin the
same refusal for the original, which matters more.
"""
from __future__ import annotations

import importlib

import pytest


def _config_with(monkeypatch, path: str | None):
    """Re-import config with PGS_DATA_DIR set, since it reads it at import."""
    from backend.app import config as live

    if path is None:
        monkeypatch.delenv("PGS_DATA_DIR", raising=False)
    else:
        monkeypatch.setenv("PGS_DATA_DIR", path)
    return importlib.reload(live)


@pytest.fixture(autouse=True)
def _restore(monkeypatch):
    """Put the real module back, or every later test sees a stray data dir."""
    from backend.app import config as live

    original = live.DATA_DIR_ENV
    yield
    monkeypatch.setenv("PGS_DATA_DIR", original) if original else monkeypatch.delenv(
        "PGS_DATA_DIR", raising=False
    )
    importlib.reload(live)


def test_a_missing_directory_is_refused(monkeypatch, tmp_path):
    config = _config_with(monkeypatch, str(tmp_path / "not-mounted" / "pgs-data"))
    with pytest.raises(config.DataDirMissing) as caught:
        config.check_data_dir()
    assert "not mounted" in str(caught.value)


def test_an_empty_directory_is_refused(monkeypatch, tmp_path):
    """What an unmounted mount point looks like from the inside."""
    empty = tmp_path / "mountpoint"
    empty.mkdir()
    config = _config_with(monkeypatch, str(empty))
    with pytest.raises(config.DataDirMissing):
        config.check_data_dir()


def test_nothing_is_created_by_the_refusal(monkeypatch, tmp_path):
    """The whole point: a refusal that wrote a tree first would be no refusal."""
    target = tmp_path / "not-mounted" / "pgs-data"
    config = _config_with(monkeypatch, str(target))
    with pytest.raises(config.DataDirMissing):
        config.check_data_dir()
    assert not target.exists()


@pytest.mark.parametrize("marker", ["log", "domains", "capture"])
def test_a_real_data_directory_starts(monkeypatch, tmp_path, marker):
    real = tmp_path / "pgs-data"
    (real / marker).mkdir(parents=True)
    config = _config_with(monkeypatch, str(real))
    config.check_data_dir()  # does not raise


def test_the_checkout_default_is_never_refused(monkeypatch):
    """Only an explicitly configured directory is checked. A fresh clone has
    no data/ yet and must still be able to make one."""
    config = _config_with(monkeypatch, None)
    config.check_data_dir()  # does not raise
