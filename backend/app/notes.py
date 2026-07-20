"""One markdown document per node.

Deliberately NOT the journal. Those are two different things that were being
conflated, and separating them is what lets a full editor exist without
breaking anything:

    journal   what happened today        append-only events in the log
    note      what I have worked out     one mutable markdown file

The journal is evidence: immutable, timestamped, deduplicated on `(ts, text)`,
union-merged across machines. Making *that* editable would have cost the
append-only property the sync design, the XP fold and the calibration all rely
on.

A note is knowledge, and knowledge gets revised. A plain markdown file is the
right shape for it: hand-editable, greppable, diffable, mergeable by git like
any other text, and readable without this app existing. Images embed as
ordinary markdown pointing at `/media/...`.

That last property is the reason this is markdown rather than a block editor's
JSON. Storage decisions are permanent; which editor renders them is not.
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
    """`data/notes/<domain>/<node>.md`, with both ids validated as slugs.

    Both come off the URL, so they are checked against the same pattern the
    writer enforces rather than trusted — otherwise `../` walks out of the
    notes directory and writes wherever it likes.
    """
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
    """Add to the end of a note, keeping a blank line between blocks.

    Used by the photo import: a Shortcut has nowhere to show an editor, so it
    appends and gets out of the way.
    """
    existing = read(domain_id, node_id)
    joined = f"{existing.rstrip()}\n\n{text}\n" if existing.strip() else f"{text}\n"
    return write(domain_id, node_id, joined)
