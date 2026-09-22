"""What the app is costing you on disk, broken down by what it is.

Media dwarfs everything else and is the only part not in git, so the split that
matters is "things a backup already covers" against "the one copy of my photos".

Records and their prints are named apart because they make opposite promises:
a Record is the only copy of a day and cannot be made again, while every PDF
can be reprinted from its Record by `python -m backend.app.pdf --all`. What the
apps before the Portal left behind — capture's log, the tech tree — is still on
the disk and still counted, as one line, because nothing reads it any more and
nothing is allowed to delete it.
"""
from __future__ import annotations

from pathlib import Path

from .config import DATA_DIR, MEDIA_DIR, PDF_DIR, RECORDS_DIR


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
            "selfies, photos and clips at full quality, plus a display copy "
            "each. This is the only copy unless something else backs it up.",
            _walk(MEDIA_DIR),
            False,
        ),
        (
            "records",
            "records",
            "one sealed Record per Instance that committed. The only copy of "
            "each day, and never rewritten.",
            _walk(RECORDS_DIR),
            False,
        ),
        (
            "prints",
            "prints",
            "a PDF per Record, rendered from it. Reprintable at any time.",
            _walk(PDF_DIR),
            True,
        ),
        (
            "before",
            "before the Portal",
            "capture's log and the tech tree, kept on the disk and read by "
            "nothing",
            _sum(
                _walk(DATA_DIR / "capture"),
                _walk(DATA_DIR / "log"),
                _walk(DATA_DIR / "domains"),
                _one(DATA_DIR / "index.sqlite"),
                _one(DATA_DIR / "todos.jsonl"),
            ),
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
    # Anything in data/ that none of the buckets above claimed — the day in
    # progress, stray files. Reported rather than hidden, so the parts always sum to the total.
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
