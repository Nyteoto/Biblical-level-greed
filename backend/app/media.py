"""The blob store: photos and video, kept exactly as they arrived.

Not tracked by git — a year of video is a repo nobody wants to clone — so these
have one copy unless something else backs them up.

Why it is shaped this way
-------------------------
**The original is never touched.** This module used to decode every upload,
downscale it to 2048px, re-encode it to JPEG q82 and strip the EXIF, so the
file on disk was never the file you took. That was right when the app stored
illustrations for a tech tree and wrong now that it is a journal: the point of
recording something is to still have it. What arrives is what is written.

**So there are two files, not one.** A browser that cannot decode HEIC still
has to show you the photo, and a log scrolling past thirty clips must not pull
thirty full-resolution files to do it. Every upload may therefore have a
derivative beside it:

    data/media/YYYY-MM/<hex16>.<ext>       the upload, byte for byte
    data/media/YYYY-MM/<hex16>.view.jpg    a display copy, if one could be made

For an image the derivative is the old pipeline, demoted from *the* file to *a*
copy. For a video it is a poster frame, and it is produced by the browser
rather than here: a server-side frame grab means ffmpeg, and ffmpeg would have
to be installed on both of a dual-boot machine's operating systems to keep the
app working on either. A missing derivative is never an error — the caller
falls back to the original.

**Nothing is read into memory.** `write_stream` consumes an async iterator
chunk by chunk into a temporary file in the destination directory, then
`os.replace`s it into place: atomic, same filesystem, and flat in memory
whether the upload is 40 KB or 4 GB. The old code did `await request.body()`
and held three copies of a decoded image at once, which put a hard ceiling on
the size of thing you could keep.

**The extension is part of the contract.** `FileResponse` picks the response's
content type from the file suffix, so a video saved as `.jpg` would be served
as an image and refuse to play. The suffix comes from the uploaded filename,
lowercased and checked against an allowlist — guessing from content sniffing
would be worse, because the failure is silent and only shows up in a player.
"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import time
import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from .config import DATA_DIR, ensure_dirs

# What a derivative is downscaled to. Only the display copy is resized; the
# original keeps whatever resolution it was shot at.
VIEW_EDGE = 2048  # long edge, in pixels: sharp on a Retina iPad, ~200-400 KB
VIEW_QUALITY = 82

# Suffix → kind. An upload whose extension is not here is refused rather than
# stored under a guess. HEIC and AVIF are here because an iPhone shoots them;
# the browser may not render them, which is what the derivative is for.
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".avif"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}

# Refuse a write that would leave the disk under this. Not a cap on the upload
# — a cap is what this module just stopped having — but a full disk mid-write
# leaves a truncated file, and a clear refusal beforehand is kinder than that.
FREE_SPACE_MARGIN = 512 * 1024 * 1024

CHUNK = 1024 * 1024


class MediaError(Exception):
    """The upload cannot be stored. Message is shown to the caller."""


def media_dir() -> Path:
    return DATA_DIR / "media"


def _month_dir(day: str) -> Path:
    # Same YYYY-MM grouping the event log uses, so a directory listing stays
    # navigable by hand after a few thousand files.
    return media_dir() / day[:7]


def kind_of(relative: str) -> str:
    """"image", "video", or "" for something this store would not have taken."""
    suffix = Path(relative).suffix.lower()
    if suffix in IMAGE_EXT:
        return "image"
    if suffix in VIDEO_EXT:
        return "video"
    return ""


def extension_for(filename: str) -> str:
    """The suffix an upload will be stored under, or raise."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in IMAGE_EXT and suffix not in VIDEO_EXT:
        allowed = ", ".join(sorted(IMAGE_EXT | VIDEO_EXT))
        raise MediaError(f"cannot store {suffix or 'a file with no extension'} — {allowed}")
    return suffix


def _slug(label: str) -> str:
    """A folder name as a filename fragment: lowercase, ASCII-ish, hyphenated.

    Unicode folder names are normal here — the corpus has `<仕事>` and
    `<công-việc>` — and a filename is the one place in this app that has to
    survive being copied onto another filesystem, a backup disk, a phone. What
    does not survive gets dropped rather than transliterated: a name that is
    entirely non-ASCII becomes empty and the caller falls back to `unfiled`,
    which is honest, where a mangled transliteration would not be.
    """
    kept = [c if c.isascii() and (c.isalnum()) else "-" for c in label.lower()]
    return re.sub(r"-{2,}", "-", "".join(kept)).strip("-")[:32]


def _umask() -> int:
    """Read the process umask without leaving it changed. There is no getter."""
    current = os.umask(0o022)
    os.umask(current)
    return current


def _check_space(target_dir: Path, expected: int | None) -> None:
    if not expected:
        return
    try:
        free = shutil.disk_usage(target_dir).free
    except OSError:  # pragma: no cover - the mkdir above would have failed first
        return
    if free < expected + FREE_SPACE_MARGIN:
        raise MediaError(
            f"not enough room: {expected // (1024 * 1024)} MB incoming, "
            f"{free // (1024 * 1024)} MB free"
        )


async def write_stream(
    chunks: AsyncIterator[bytes],
    day: str,
    filename: str,
    expected: int | None = None,
    folder: str = "",
) -> tuple[str, int]:
    """Stream one upload to disk. Returns (path relative to media/, bytes).

    Written to a temporary file in the destination directory and moved into
    place, so a connection that dies halfway leaves nothing behind that looks
    like a real file.

    The name says what the file is: `2026-08-18-garden-a1b2c3d4.jpg` — the day
    it was uploaded, where it was filed as it arrived, and enough random hex to
    never collide. It is readable in a file manager, sorts by date inside its
    month directory, and answers "what is this" without opening the app.

    **The folder is a snapshot, and cannot be anything else.** Membership in
    this app is resolved from tags at read time, not stored, so a photograph's
    folder can change tomorrow when a tag is mapped — and this name will not
    change with it. It could not: the relative path is written into the
    append-only log as the entry's `media` ref, and renaming the file would mean
    rewriting history to match. So read the folder in a name as *where this was
    filed when it landed*, which is a fact about the upload, and never as a
    claim about where it lives now. The app never reads it back; only a human
    browsing the directory does.
    """
    suffix = extension_for(filename)

    ensure_dirs()
    target_dir = _month_dir(day)
    target_dir.mkdir(parents=True, exist_ok=True)
    _check_space(target_dir, expected)

    name = f"{day}-{_slug(folder) or 'unfiled'}-{uuid.uuid4().hex[:8]}{suffix}"
    target = target_dir / name

    handle, temp_path = tempfile.mkstemp(dir=target_dir, suffix=".part")
    written = 0
    try:
        with os.fdopen(handle, "wb") as out:
            async for chunk in chunks:
                if not chunk:
                    continue
                out.write(chunk)
                written += len(chunk)
            out.flush()
            # The same durability the event log takes: this is the only copy.
            os.fsync(out.fileno())
        if written == 0:
            raise MediaError("empty upload")
        # mkstemp creates 0600. Everything else under data/ is written by
        # ordinary means and lands at the umask default, and an original that
        # is readable by fewer people than its own thumbnail is a surprise
        # waiting for whoever next runs a backup as another user.
        os.chmod(temp_path, 0o666 & ~_umask())
        os.replace(temp_path, target)
    except MediaError:
        Path(temp_path).unlink(missing_ok=True)
        raise
    except OSError as exc:
        Path(temp_path).unlink(missing_ok=True)
        raise MediaError(f"could not write the upload: {exc}") from exc
    except BaseException:
        # Everything else, and the one that matters is `ClientDisconnect`: the
        # phone went out of range or the tab was closed halfway through two
        # gigabytes. Neither an OSError nor ours, so it used to escape both
        # handlers above and leave the part file on disk forever — invisible
        # to the app, counted by the storage page, and growing one dead clip
        # at a time. `BaseException` because a cancelled task is one too.
        Path(temp_path).unlink(missing_ok=True)
        raise

    return f"{day[:7]}/{name}", written


# ── The display copy ──────────────────────────────────────────────────────

_heif_ready = False


def _register_heif() -> None:
    """Teach Pillow to read HEIC, which it cannot do on its own.

    An iPhone shoots HEIC by default, so without this every photo from one
    fails at `Image.open` with "cannot identify image file" and gets no
    display copy — which is exactly the case the display copy exists for,
    since no browser but Safari renders HEIC either. Registering is idempotent
    but not free, hence the flag.
    """
    global _heif_ready
    if _heif_ready:
        return
    try:
        from pillow_heif import register_heif_opener
    except ImportError:  # pragma: no cover - dependency is declared
        # Everything else still imports; only HEIC is lost.
        _heif_ready = True
        return
    register_heif_opener()
    _heif_ready = True


def view_ref(relative: str) -> str:
    """The display copy's path for a stored file. `a/b.mov` → `a/b.view.jpg`."""
    return str(Path(relative).with_suffix(".view.jpg"))


def derive_view(relative: str) -> str | None:
    """Make the display copy for a stored image. Returns its ref, or None.

    Never raises: a file Pillow cannot open simply has no derivative, and the
    caller shows the original instead. Video gets no derivative here — its
    poster is captured in the browser and arrives through `save_poster`.
    """
    if kind_of(relative) != "image":
        return None

    original = path_for(relative)
    if original is None:
        return None

    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover - dependency is declared
        return None

    _register_heif()
    target = media_dir() / view_ref(relative)

    try:
        with Image.open(original) as image:
            # Applies the EXIF orientation and drops the tag, so the copy is
            # oriented the way you saw it. The original keeps its EXIF intact.
            image = ImageOps.exif_transpose(image)
            image.thumbnail((VIEW_EDGE, VIEW_EDGE))
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=VIEW_QUALITY, optimize=True)
        target.write_bytes(buffer.getvalue())
    except Exception:
        # Includes the case where the "image" is something Pillow will not
        # decode. Not fatal, and not worth a log line the user cannot act on.
        target.unlink(missing_ok=True)
        return None

    return view_ref(relative)


def save_poster(relative: str, data: bytes) -> str | None:
    """Store a poster frame the browser captured for a video.

    Same slot as an image's display copy, so everything downstream asks one
    question — "is there a view for this?" — rather than branching on kind.
    """
    if not data or path_for(relative) is None:
        return None
    target = media_dir() / view_ref(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return view_ref(relative)


def sweep_parts(older_than_seconds: int = 3600) -> int:
    """Delete abandoned part files. Returns how many went.

    Called at startup. A part file is a live upload's temporary name, so the
    age check is what separates one of those from the wreckage of a connection
    that dropped — at boot there is nothing in flight, but a second process
    sharing the data directory (a scratch server, say) might have one.
    """
    root = media_dir()
    if not root.exists():
        return 0
    cutoff = time.time() - older_than_seconds
    gone = 0
    for stale in root.rglob("*.part"):
        try:
            if stale.stat().st_mtime < cutoff:
                stale.unlink()
                gone += 1
        except OSError:  # pragma: no cover - raced with something else
            continue
    return gone


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
