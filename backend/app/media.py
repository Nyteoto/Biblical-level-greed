"""Images attached to nodes.

The first thing this app stores that is not a line of text, which is why it is
kept deliberately dumb: files on disk, named by content-independent ids, with
no database and no metadata beyond what the filesystem already knows.

**Not tracked by git.** `data/media/` is gitignored, so the repo stops being a
complete backup the moment a photo lands here. That was a deliberate call — the
alternative was a repo that grows by hundreds of megabytes a year — but it
means these files have exactly one copy unless something else backs them up.

Images are re-encoded on the way in rather than stored as received:

  * downscaled to fit MAX_EDGE, which keeps a phone photo readable on a Retina
    iPad while turning 5 MB into a few hundred KB
  * EXIF rotation applied and then dropped, because a sideways photo in the
    journal is worse than a slightly larger file, and the rest of EXIF is
    location and device data nobody asked to keep
  * re-encoded as JPEG, so an HEIC from an iPhone becomes something every
    browser can draw
"""
from __future__ import annotations

import io
import uuid
from pathlib import Path

from .config import DATA_DIR, ensure_dirs

MAX_EDGE = 2048  # long edge, in pixels: sharp on a Retina iPad, ~200-400 KB
JPEG_QUALITY = 82
MAX_UPLOAD = 40 * 1024 * 1024  # refuse anything absurd before decoding it


class MediaError(Exception):
    """The upload was not a usable image. Message is shown to the caller."""


def media_dir() -> Path:
    return DATA_DIR / "media"


def _month_dir(day: str) -> Path:
    # Same YYYY-MM grouping the event log uses, so a directory listing stays
    # navigable by hand after a few thousand photos.
    return media_dir() / day[:7]


def save(data: bytes, day: str) -> str:
    """Store one image. Returns its path relative to `data/media`."""
    if not data:
        raise MediaError("empty upload")
    if len(data) > MAX_UPLOAD:
        raise MediaError(f"upload is larger than {MAX_UPLOAD // (1024 * 1024)} MB")

    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise MediaError("Pillow is not installed") from exc

    try:
        image = Image.open(io.BytesIO(data))
        # Applies the EXIF orientation and strips the tag, so what is stored is
        # what you saw. Everything else in EXIF goes with it.
        image = ImageOps.exif_transpose(image)
        image.thumbnail((MAX_EDGE, MAX_EDGE))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
    except MediaError:
        raise
    except Exception as exc:
        raise MediaError(f"not a readable image: {exc}") from exc

    ensure_dirs()
    target_dir = _month_dir(day)
    target_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:16]}.jpg"
    target = target_dir / name

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    target.write_bytes(buffer.getvalue())

    return f"{day[:7]}/{name}"


def path_for(relative: str) -> Path | None:
    """Resolve a stored path, refusing anything that escapes the media root."""
    root = media_dir().resolve()
    try:
        target = (media_dir() / relative).resolve()
    except (OSError, ValueError):
        return None
    if not target.is_relative_to(root) or not target.is_file():
        return None
    return target
