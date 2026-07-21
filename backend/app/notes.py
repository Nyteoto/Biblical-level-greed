"""Titled markdown documents, one folder per domain.

These used to be one note per node, with a separate append-only journal of
events beside them. That split is gone: in practice a thing you write while
working is both — knowledge you will revise *and* a record of the day — and
having to decide which one you were writing was friction with nothing on the
other side of it.

So a domain now owns a folder of freely titled documents. Markdown, on disk,
hand-editable and git-mergeable, same as before. The old per-node files carry
over untouched: `chinese/pinyin-tones.md` simply reads as a note titled
"pinyin-tones".
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .config import DATA_DIR, ensure_dirs
from .writer import SLUG_OK

MAX_BYTES = 2 * 1024 * 1024  # a note, not a novel


class NoteError(Exception):
    """Bad domain or note id, or a note that is implausibly large."""


def notes_dir() -> Path:
    return DATA_DIR / "notes"


def path_for(domain_id: str, node_id: str) -> Path:
    """`data/notes/<domain>/<slug>.md`. Ids come off the URL, so they are
    validated rather than trusted — `../` would escape the directory."""
    for value, what in ((domain_id, "domain"), (node_id, "note")):
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


def slugify(title: str, taken: set[str]) -> str:
    """A filename from a human title. The title is recoverable from it, which is
    why the file stays readable in a directory listing years later."""
    import re

    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "note"
    if base[0].isdigit():
        base = f"n-{base}"
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def titleize(slug: str) -> str:
    return slug.replace("-", " ").strip().capitalize() or slug


def listing(domain_id: str) -> list[dict]:
    """Every document in a domain's folder, newest first.

    Sorted by modification time rather than name: what you touched last is
    almost always what you want next.
    """
    if not SLUG_OK.match(domain_id or ""):
        raise NoteError(f"invalid domain id `{domain_id}`")
    folder = notes_dir() / domain_id
    if not folder.is_dir():
        return []

    out = []
    for path in folder.glob("*.md"):
        if not path.is_file():
            continue
        stat = path.stat()
        text = path.read_text(encoding="utf-8", errors="replace")
        out.append(
            {
                "slug": path.stem,
                "title": heading(text) or titleize(path.stem),
                "bytes": stat.st_size,
                "updated": stat.st_mtime,
                # Enough to tell two notes apart in a list without opening them.
                "preview": preview(text),
            }
        )
    return sorted(out, key=lambda n: n["updated"], reverse=True)


def heading(text: str) -> str:
    """The document's own `# Title`, if it opens with one. A note that names
    itself should not also be named by its filename."""
    first = text.lstrip().split("\n", 1)[0].strip()
    return first[1:].strip() if first.startswith("# ") else ""


def preview(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("!["):
            return stripped[:120]
    return ""


def create(domain_id: str, title: str) -> str:
    """Start a document. Returns its slug."""
    clean = title.strip()
    if not clean:
        raise NoteError("a note needs a title")
    existing = {n["slug"] for n in listing(domain_id)}
    slug = slugify(clean, existing)
    write(domain_id, slug, f"# {clean}\n\n")
    return slug


def delete(domain_id: str, node_id: str) -> None:
    path_for(domain_id, node_id).unlink(missing_ok=True)
