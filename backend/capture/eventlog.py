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
#
# `reply_to`, when present, is the id of the entry this one answers — a
# `--reply` to a reminder that had come due. It is a field rather than
# something derived from the text for the same reason `media` is: the line says
# "reply", it does not say *to what*, and the answer is not recoverable from
# any number of re-reads. The `--reply ` prefix itself is stripped before the
# line is written, exactly as the source strips it: what you typed the command
# *for* is stored, and the command was addressed to the app rather than to the
# journal.
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
# Where a folder is in its life, in `text`: "active" while you are working on
# it, "shipped" when it is done, and empty — the default — for one that has no
# life to speak of, which is what an ongoing interest looks like. Three states
# and no taxonomy: nothing has to be classified before it can be captured into,
# and a hobby that turns into a project is one event rather than a migration.
SET_STATE = "set-state"

# The folder's overview: a standing description of the project, and one picture
# to stand for it. Two events rather than one because they are set from
# different places — the card's editor, and a hold on any photograph in the log
# — and an event that carried both would have to invent a value for whichever
# half was not being changed.
SET_OVERVIEW = "set-overview"
SET_OVERVIEW_MEDIA = "set-overview-media"

# Which named group a folder sits in on the year shelf, in `text`, for the year
# in `year`. Empty `text` puts it back in the loose grid above the groups.
#
# The `year` field is the whole point and the reason this is not part of
# `set-state`: a folder's group is a *per-year* fact. A thing that was Field
# work in 2025 and Archive in 2026 is one folder with two groupings, not a
# folder that changed its mind, and there is no year in which the pairing is
# wrong. Nothing else in this log is keyed by year, so nothing else could carry
# it.
#
# There is no `create-group`. A group exists exactly while some folder in that
# year names it, which means it cannot be created empty and cannot be left
# behind empty — the two states a separate group object would have to be taught
# to handle. `delete-group` below is not a counter-example: it un-groups the
# folders that named one, which is the state in which the group stops existing,
# rather than destroying an object that was holding them.
SET_GROUP = "set-group"

# A whole group at once, for the two edits `set-group` cannot express one folder
# at a time. `id` is the *group's name* — a group has no id because a group is
# its name, in one year, and nothing else. `year` says which shelf.
#
# `rename-group` carries the new name in `text`. Renaming onto a name the year
# already uses merges the two, and the survivor keeps the older of the two
# ordering slots so the shelf does not reshuffle under a rename.
#
# `delete-group` un-groups every folder that named it, which returns them to
# the loose grid. It deletes no folder and no entry — there is nothing else it
# could mean, because a group has never held anything. It exists as its own
# event rather than as N `set-group` lines so the log says what you did once,
# the way `rename-folder` does instead of a delete and a create.
RENAME_GROUP = "rename-group"
DELETE_GROUP = "delete-group"

# The order the groups are drawn in on one year's shelf. `id` is the **year**,
# because the subject of a reordering is the shelf rather than any one group,
# and `order` is the names in the order they should be read.
#
# The whole order rather than "this one moved to third": a move is only
# meaningful against the arrangement it started from, so a replayed or
# duplicated move line would land somewhere different the second time. A whole
# order is idempotent — the same line applied twice is the same shelf — which is
# the property every other fold in this log has and the one a restored backup
# depends on.
#
# Groups the event does not name keep their relative order and follow the ones
# it does. That is what makes a reorder written before a group existed still
# mean something afterwards, and it is why this can be one event rather than a
# migration whenever a folder joins a new heading.
ORDER_GROUPS = "order-groups"

# A tag lifted out of its brackets, and put back. `id` is the tag — a tag has no
# id because a tag *is* its name, the same reason `rename-group` is keyed on a
# name.
#
# Lifting is about how a word reads, not about where a line goes: `<garden>`
# still files into whatever folder has claimed `garden`, and the raw line is
# untouched, as every line in this log is. What changes is that the app stops
# drawing the delimiters around that one word, so a tag you have stopped
# thinking of as a tag reads as the prose it has become.
#
# Only `<tags>` can be lifted. A `\pattern`, an `@place` and a `{time}` are one
# character of syntax and a word; a tag is the only kind whose sigil wraps the
# word on both sides, and so the only one whose removal leaves the sentence
# reading exactly as it was written.
LIFT_TAG = "lift-tag"
UNLIFT_TAG = "unlift-tag"

# A chapter given a name by hand. `id` is the folder — or the literal `unfiled`,
# which is an album you can open like any other and so is one you can name a
# chapter in. `year` and `month` say which chapter; `text` is the name, and an
# empty one hands the chapter back to the reader that names it from your own
# words.
#
# **A chapter has no id of its own because a chapter is a run of months, and a
# run is derived.** So the name is anchored to a month instead: the run's first
# month at the moment you named it. That works because of a property of this
# log — entries are only ever appended, so a month never loses its last entry,
# so a run can extend or merge but can never split or shrink. The anchor is
# therefore inside the same run forever, whatever else lands around it.
#
# When two named runs merge, the chapter has two names and takes the one
# anchored earliest. That is a rule rather than a guess: the chapter began
# there, and it is the same answer on every replay.
NAME_CHAPTER = "name-chapter"

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
    SET_STATE,
    SET_OVERVIEW,
    SET_OVERVIEW_MEDIA,
    SET_GROUP,
    RENAME_GROUP,
    DELETE_GROUP,
    ORDER_GROUPS,
    LIFT_TAG,
    UNLIFT_TAG,
    NAME_CHAPTER,
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
    reply_to: str | None = None,
    year: str | None = None,
    month: int | None = None,
    order: list[str] | None = None,
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
    if year is not None:
        event["year"] = year
    if month is not None:
        event["month"] = month
    if reply_to:
        event["reply_to"] = reply_to
    if order is not None:
        # Written even when empty, unlike `media`: an empty order is a real
        # statement — the shelf has nothing arranged on it — and dropping the
        # field would make that line indistinguishable from one that forgot to
        # carry it.
        event["order"] = list(order)
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
