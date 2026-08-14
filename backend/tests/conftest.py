"""Point the app at a throwaway data directory before it is imported."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="pgs-test-"))
os.environ["PGS_DATA_DIR"] = str(_TMP)
os.environ["PGS_INDEX_PATH"] = str(_TMP / "index.sqlite")

import pytest  # noqa: E402

from backend.app import config, eventlog, index, loader, state, xp  # noqa: E402


@pytest.fixture
def data_dir() -> Path:
    """A clean data directory for each test."""
    for path in list(config.DOMAINS_DIR.glob("*.toml")) + list(
        config.LOG_DIR.glob("*.jsonl")
    ):
        path.unlink()
    config.INDEX_PATH.unlink(missing_ok=True)
    # Everything that lives beside the log rather than inside it has to be
    # cleared explicitly, or state leaks between tests: ticked todos leaked XP
    # once, and a note written by one test was appended to by the next.
    (config.DATA_DIR / "todos.jsonl").unlink(missing_ok=True)
    for tree in ("notes", "media", "tools"):
        shutil.rmtree(config.DATA_DIR / tree, ignore_errors=True)
    config.ensure_dirs()
    return _TMP


@pytest.fixture
def capture_store():
    """A clean capture app: its own log and index, thrown away between tests.

    Separate from `data_dir` because capture is a separate app — it shares the
    data root and nothing else, and a test of one must not have to know what
    the other keeps on disk.
    """
    from backend.capture import config as capture_config
    from backend.capture.store import Store

    shutil.rmtree(capture_config.CAPTURE_DIR, ignore_errors=True)
    capture_config.ensure_dirs()
    store = Store()
    store.start()
    yield store
    store.close()


@pytest.fixture
def write_domain(data_dir: Path):
    def _write(name: str, body: str) -> None:
        (config.DOMAINS_DIR / f"{name}.toml").write_text(body, encoding="utf-8")

    return _write


@pytest.fixture
def conn(data_dir: Path):
    connection = index.connect()
    index.rebuild(connection)
    yield connection
    connection.close()


@pytest.fixture
def view(conn):
    """Reindex the log and derive the current view of one domain."""

    def _view(domain_id: str, today: str = "2026-07-20"):
        index.rebuild(conn)
        domains, errors = loader.load_all()
        assert not errors, errors
        domain = next(d for d in domains if d.id == domain_id)
        return state.build_domain_view(conn, domain, today=today)

    return _view


@pytest.fixture
def log():
    def _log(
        domain: str,
        node: str,
        kind: str,
        day: str,
        text: str = "",
        value: float | None = None,
    ) -> None:
        eventlog.append(domain, node, kind, day=day, text=text, value=value)

    return _log


@pytest.fixture
def unlock(log):
    """Buy a node's unlock, at whatever its tier costs.

    Tier II and above are sealed until paid for, so any test that walks a tree
    upward has to spend — which is the point of the mechanic, and the reason
    this is a fixture rather than something the board does for you.
    """

    def _unlock(domain: str, node: str, tier: int, day: str = "2026-07-01") -> None:
        eventlog.append(
            domain, node, eventlog.UNLOCK, day=day, value=xp.unlock_price(tier)
        )

    return _unlock


@pytest.fixture
def node_of(view):
    """One node's derived view, by id."""

    def _node(domain_id: str, node_id: str, today: str = "2026-07-20"):
        return next(
            n for n in view(domain_id, today=today)["nodes"] if n["id"] == node_id
        )

    return _node
