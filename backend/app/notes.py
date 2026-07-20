"""One mutable markdown document per node.

Not the journal, which stays append-only events in the log. A note is knowledge
and gets revised; markdown keeps it hand-editable and git-mergeable.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .config import DATA_DIR, ensure_dirs
from .writer import SLUG_OK

MAX_BYTES = 2 * 1024 * 1024  # a note, not a novel


class NoteError(Exception):
    """Bad domain/node id, or a note that is implausibly large."""


def notes_dir() -> Path:
    return DATA_DIR / "notes"


def path_for(domain_id: str, node_id: str) -> Path:
    """`data/notes/<domain>/<node>.md`. Ids come off the URL, so they are
    validated rather than trusted — `../` would escape the directory."""
    for value, what in ((domain_id, "domain"), (node_id, "node")):
        if not SLUG_OK.match(value or ""):
            raise NoteError(f"invalid {what} id `{value}`")
    return notes_dir() / domain_id / f"{node_id}.md"


def read(domain_id: str, node_id: str) -> str:
    target = path_for(domain_id, node_id)
    if not target.is_file():
        return ""
    return target.read_text(encoding="utf-8")


def write(domain_id: str, node_id: str, text: str) -> Path:
    """Replace the note. Atomic, so a crash cannot leave half a document."""
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise NoteError(f"note is larger than {MAX_BYTES // (1024 * 1024)} MB")

    target = path_for(domain_id, node_id)
    ensure_dirs()
    target.parent.mkdir(parents=True, exist_ok=True)

    handle, tmp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return target


def append(domain_id: str, node_id: str, text: str) -> Path:
    """Append, keeping a blank line between blocks. Used by the photo import."""
    existing = read(domain_id, node_id)
    joined = f"{existing.rstrip()}\n\n{text}\n" if existing.strip() else f"{text}\n"
    return write(domain_id, node_id, joined)
