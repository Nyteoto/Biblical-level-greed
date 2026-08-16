"""What the app is costing you on disk, broken down by what it is.

Media dwarfs everything else and is the only part not in git, so the split that
matters is "things a backup already covers" against "the one copy of my photos".

Capture's log and index are named separately from the tech tree's because they
are the ones the Settings screen is actually about now: capture is the app, and
"delete this and it rebuilds" is a different promise from "delete this and your
history is gone". The tech tree's three parts are folded into one line for the
same reason — it is support, and its size is a footnote rather than a subject.
"""
from __future__ import annotations

from pathlib import Path

from ..capture.config import INDEX_PATH as CAPTURE_INDEX_PATH
from ..capture.config import LOG_DIR as CAPTURE_LOG_DIR
from .config import DATA_DIR, DOMAINS_DIR, INDEX_PATH, LOG_DIR


def _walk(root: Path) -> tuple[int, int]:
    """Bytes and file count under `root`. Missing directories read as empty."""
    if not root.exists():
        return 0, 0
    total = 0
    count = 0
    for path in root.rglob("*"):
        # Symlinks are not followed: a link into a photo library elsewhere would
        # otherwise be counted as if it lived here.
        if path.is_file() and not path.is_symlink():
            total += path.stat().st_size
            count += 1
    return total, count


def _one(path: Path) -> tuple[int, int]:
    if not path.is_file():
        return 0, 0
    return path.stat().st_size, 1


def _sum(*pairs: tuple[int, int]) -> tuple[int, int]:
    return sum(p[0] for p in pairs), sum(p[1] for p in pairs)


def report() -> dict:
    parts = []

    for key, label, hint, (size, files), recoverable in (
        (
            "media",
            "media",
            "photos and clips at full quality, plus a display copy each. "
            "This is the only copy unless something else backs it up.",
            _walk(DATA_DIR / "media"),
            False,
        ),
        (
            "capture-log",
            "capture log",
            "append-only truth. Everything else here is derived from it.",
            _walk(CAPTURE_LOG_DIR),
            False,
        ),
        (
            "capture-index",
            "index",
            "delete it any time; the log rebuilds it on the next read",
            _one(CAPTURE_INDEX_PATH),
            True,
        ),
        (
            "tree",
            "tech tree",
            "its own log, its trees and its index — the support half of the app",
            _sum(_walk(LOG_DIR), _walk(DOMAINS_DIR), _one(INDEX_PATH)),
            False,
        ),
    ):
        parts.append(
            {
                "key": key,
                "label": label,
                "hint": hint,
                "bytes": size,
                "files": files,
                "recoverable": recoverable,
            }
        )

    counted = sum(p["bytes"] for p in parts)
    total, total_files = _walk(DATA_DIR)
    # Anything in data/ that none of the buckets above claimed — todos, stray
    # files. Reported rather than hidden, so the parts always sum to the total.
    other = total - counted
    if other > 0:
        parts.append(
            {
                "key": "other",
                "label": "other",
                "hint": "everything else under data/",
                "bytes": other,
                "files": max(total_files - sum(p["files"] for p in parts), 0),
                "recoverable": False,
            }
        )

    return {
        "path": str(DATA_DIR),
        "total_bytes": total,
        "total_files": total_files,
        "parts": sorted(parts, key=lambda p: p["bytes"], reverse=True),
    }
