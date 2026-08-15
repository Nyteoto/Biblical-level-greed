"""Capture's append-only event log. The source of truth; the index is a
projection of it.

Why it is shaped this way
-------------------------
**The log holds the raw line, not the parsed line.** The Postgres original
stores `parsed.cleanText` in `rawText` and keeps `folders`/`times`/`patterns`
as columns beside it. Doing that here would be lossy in a way it is not there:
`cleanText` has the `--directive` and `--todo` stripped out, so once the
columns are dropped the directive can never be recovered. Store what was
typed, derive the rest — then `clean_text`, the three capture lists and the
todo line indices are all a pure function of one immutable string, and
retuning the parser re-derives every entry ever written.

**Mutations are events.** Three fields are mutable in the source: checkbox
state, manual folder assignment, and tag→folder mappings. Rows cannot be
edited here, so those become `check`/`uncheck`, `assign`/`unassign` and
`map-tag`/`unmap-tag`, folded last-wins at read time. `Folder` is a table
there and a fold here too: `create-folder`/`rename-folder`/`delete-folder`.

**`id` is the subject, whatever kind of thing that is.** Entry events carry
the entry's id, folder events carry the folder's. It is one field rather than
two because every event has exactly one subject, and a second nullable id
column would only ever be half-populated. Where an event needs to name a
*second* thing — `assign` names a folder, `map-tag` names a tag — that goes in
its own field, and the fold is the only thing that has to know which pairing
each kind uses.

Out-of-order and duplicate lines are handled on read, exactly as the tech
tree's log does: sort by `ts` stably, fold last-wins. A restored backup or an
interrupted write produces those shapes whether or not anything merges files.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from backend.app.timeutil import day_key, month_key, now

from .config import LOG_DIR, ensure_dirs

# ── Entry events. `id` is the entry's. ────────────────────────────────────
# A new entry. `text` is the raw line as typed; `media`, when present, is the
# list of files attached to it, as paths under data/media.
CAPTURE = "capture"
# One `--todo` line ticked / unticked. `line` is its index into the entry.
CHECK = "check"
UNCHECK = "uncheck"
# Post-hoc filing: this entry belongs in `folder`, whatever its tags say.
# `assign` replaces any previous manual filing, matching the source, where
# `assignFolderId` overwrites the whole `manualFolderIds` array.
ASSIGN = "assign"
UNASSIGN = "unassign"
# Files that finished uploading after the entry was already written. Sending a
# thought must never wait on a 2 GB video, so the entry goes in immediately and
# its media catches up — one of these per upload that lands.
ATTACH_MEDIA = "attach-media"
# A reminder has been seen and does not need showing again. `line` is the
# line that carried the `{time}`. There is no `undismiss`: the source has no
# way back either, and the line itself is still in the log to be re-read.
DISMISS = "dismiss"

# ── Folder events. `id` is the folder's. ──────────────────────────────────
# A new folder. `text` is its name, `color` the palette entry it was given.
CREATE_FOLDER = "create-folder"
# `text` is the new name. The colour never changes; the source has no UI for
# it either, and a folder's colour is how you recognise it in a list.
RENAME_FOLDER = "rename-folder"
# The folder is gone, and with it its tag mappings and manual filings. The
# entries themselves are untouched — deleting a folder is not deleting what
# was written into it, and nothing in this log can delete that.
DELETE_FOLDER = "delete-folder"
# `tag` now points at this folder / no longer does. A tag belongs to at most
# one folder, so `map-tag` moves it rather than adding a second owner — the
# fold is last-wins, which is this log's spelling of the source's
# `@@unique([userId, tagName])`.
MAP_TAG = "map-tag"
UNMAP_TAG = "unmap-tag"

KINDS = {
    CAPTURE,
    CHECK,
    UNCHECK,
    ASSIGN,
    UNASSIGN,
    ATTACH_MEDIA,
    DISMISS,
    CREATE_FOLDER,
    RENAME_FOLDER,
    DELETE_FOLDER,
    MAP_TAG,
    UNMAP_TAG,
}


def new_id() -> str:
    """An id for an entry or a folder. Random rather than sequential: ids are
    referenced by later events (`check`, `assign`, `map-tag`), so they have to
    survive a replay unchanged, which rules out anything derived from
    position."""
    return uuid.uuid4().hex[:12]


def log_path_for(day: str) -> Path:
    return LOG_DIR / f"{month_key(day)}.jsonl"


def append(
    kind: str,
    subject_id: str,
    text: str = "",
    line: int | None = None,
    day: str | None = None,
    tag: str | None = None,
    color: str | None = None,
    folder: str | None = None,
    ts: str | None = None,
    media: list[str] | None = None,
) -> dict:
    """Write one event. Never rewrites or deletes an existing line.

    Every optional field is omitted when unset rather than written as null, so
    a log line only ever carries what its kind actually means. That keeps the
    file readable by eye, which is the format's other job.

    `ts` overrides the clock, and exactly one caller passes it: the CSV
    importer, where the whole point is that the entries happened before today.
    It is not a general-purpose backdating hook — everything else must be
    stamped with when it actually happened.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown event kind: {kind}")

    ensure_dirs()
    when = now()
    event = {
        "ts": ts or when.isoformat(timespec="seconds"),
        "day": day or day_key(when),
        "kind": kind,
        "id": subject_id,
    }
    if text:
        event["text"] = text
    if line is not None:
        event["line"] = line
    if tag is not None:
        event["tag"] = tag
    if color is not None:
        event["color"] = color
    if folder is not None:
        event["folder"] = folder
    if media:
        # Paths under data/media, not the files. A reference is a fact about
        # the entry in the same way the raw line is — it cannot be derived
        # from anything, so it lives on the event rather than in the index.
        event["media"] = list(media)

    path = log_path_for(event["day"])
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        handle.flush()
        # Synced for the same reason the tech tree's log is: this file is the
        # only copy of what the user wrote. The index rebuilds from it on every
        # launch, so an event lost here is lost outright.
        os.fsync(handle.fileno())
    return event


def read_all() -> tuple[list[dict], list[str]]:
    """Every event, ordered by timestamp. Returns (events, warnings).

    Stable sort with no content in the key: `check, uncheck, check` inside one
    second is a real triple-toggle and must keep file order.
    """
    events: list[dict] = []
    warnings: list[str] = []

    if not LOG_DIR.exists():
        return events, warnings

    for path in sorted(LOG_DIR.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for lineno, raw in enumerate(handle, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    warnings.append(f"{path.name}:{lineno}: unparseable line, skipped")
                    continue
                if not all(k in event for k in ("ts", "day", "kind", "id")):
                    warnings.append(f"{path.name}:{lineno}: missing fields, skipped")
                    continue
                if event["kind"] not in KINDS:
                    warnings.append(
                        f"{path.name}:{lineno}: unknown kind "
                        f"{event['kind']!r}, skipped"
                    )
                    continue
                events.append(event)

    events.sort(key=lambda event: event["ts"])  # stable: ties keep file order
    return events, warnings
