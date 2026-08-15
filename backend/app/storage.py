"""What the app is costing you on disk, broken down by what it is.

Media dwarfs everything else and is the only part not in git, so the split that
matters is "things a backup already covers" against "the one copy of my photos".
"""
from __future__ import annotations

from pathlib import Path

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


def report() -> dict:
    parts = []

    for key, label, hint, (size, files), recoverable in (
        (
            "media",
            "Photos and video",
            "Not in git. This is the only copy unless something else backs it up.",
            _walk(DATA_DIR / "media"),
            False,
        ),
        (
            "log",
            "Event log",
            "Append-only. Every session, completion and edit you have made.",
            _walk(LOG_DIR),
            False,
        ),
        (
            "domains",
            "Trees",
            "The .toml files your board is read from.",
            _walk(DOMAINS_DIR),
            False,
        ),
        (
            "index",
            "Index",
            "Derived from the log. Safe to delete; it rebuilds on the next start.",
            _one(INDEX_PATH),
            True,
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
                "label": "Other",
                "hint": "Everything else under data/.",
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
