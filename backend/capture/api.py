"""Capture's HTTP surface. Thin: parse, call the store, return derived state.

A router rather than its own FastAPI app, so both apps are one process, one
port and one `run.sh`. Everything lives under `/api/capture/` — the prefix is
the seam, and the day the two products need to talk it is the only thing that
has to change.

Nothing here is user-scoped. The source's every route opens with an auth check
and every query filters by `userId`; there is one user here, sitting at the
machine, so all of that is gone rather than stubbed.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .config import YEAR_RE
from .store import CaptureError, store

router = APIRouter(prefix="/api/capture", tags=["capture"])

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CaptureIn(BaseModel):
    raw_text: str = ""
    # Paths under data/media, uploaded before this call. A capture may be
    # nothing but a clip, so the text is allowed to be empty when these are not.
    media: list[str] = []


class EntryPatch(BaseModel):
    """The two things that can happen to an entry after it is written. Both
    are events; neither edits the line. `assign_folder` is tri-state on
    purpose — absent means "leave the filing alone", `null` means "unfile it",
    which is the distinction the source draws with `"assignFolderId" in body`.
    """

    toggle_line: int | None = None
    assign_folder: str | None = None
    # Files that finished uploading after the entry was written.
    attach_media: list[str] = []


class ImportIn(BaseModel):
    csv: str


class FolderIn(BaseModel):
    name: str
    tags: list[str] = []


class FolderPatch(BaseModel):
    name: str | None = None
    # "", "active" or "shipped". Absent leaves it alone; the empty string is a
    # real value meaning "no lifecycle", so this cannot collapse into a falsy
    # check the way the others can.
    state: str | None = None
    add_tags: list[str] = []
    remove_tags: list[str] = []
    # The overview's two halves. Absent leaves each alone; empty is a real
    # value for both — a cleared description, or a removed picture.
    overview: str | None = None
    overview_media: str | None = None


def _status(exc: CaptureError) -> int:
    """A refusal that names something missing is a 404; everything else the
    store refuses is a bad request."""
    return 404 if str(exc).startswith("no such ") else 400


def _day(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    if not DAY_RE.match(value):
        raise HTTPException(400, f"{field} must be YYYY-MM-DD")
    return value


@router.get("/entries")
def list_entries(
    date: str | None = None,
    # `from` is a keyword, so the wire name has to be spelled out by hand.
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    limit: int | None = None,
) -> dict:
    """Newest first. `date` for one day, `from`/`to` for a span, neither for
    the most recent handful.

    The default limit follows the source: small for an open-ended read, large
    when a day or a span was named, because the caller has already bounded it.
    """
    start = end = None
    default = 20
    if from_ and to:
        start, end = _day(from_, "from"), _day(to, "to")
        default = 2000
    elif date:
        start = end = _day(date, "date")
        default = 500

    capped = min(limit or default, 5000)
    return {
        "entries": store.entries(start, end, capped),
        "version": store.version,
    }


@router.post("/entries", status_code=201)
def create_entry(body: CaptureIn) -> dict:
    try:
        return {
            "entry": store.capture(body.raw_text, body.media),
            "version": store.version,
        }
    except CaptureError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/entries/{entry_id}")
def patch_entry(entry_id: str, body: EntryPatch) -> dict:
    """Tick a box, or file the entry into a folder by hand. Neither is an
    edit: each appends an event and returns the re-folded entry."""
    try:
        if body.toggle_line is not None:
            entry = store.toggle_line(entry_id, body.toggle_line)
        elif body.attach_media:
            entry = store.attach_media(entry_id, body.attach_media)
        elif "assign_folder" in body.model_fields_set:
            entry = store.assign_entry(entry_id, body.assign_folder)
        else:
            raise HTTPException(400, "nothing to change")
        return {"entry": entry, "version": store.version}
    except CaptureError as exc:
        raise HTTPException(_status(exc), str(exc)) from exc


# ── Reminders ─────────────────────────────────────────────────────────────


class DismissIn(BaseModel):
    entry_id: str
    line: int


@router.get("/banner")
def banner() -> dict:
    """The persistent banner: the open todos, the cap, and the reminders on
    both sides of now. One read, so its halves cannot disagree about when."""
    return {**store.banner(), "version": store.version}


@router.get("/reminders")
def list_reminders() -> dict:
    """What has come due and not been dismissed, soonest first.

    Derived, not stored: a reminder is a `{time}` on a line plus the moment
    that line was written. Nothing was written when the reminder was made,
    because the reminder was never made — it was always implied by the entry.
    """
    return {"reminders": store.due_reminders(), "version": store.version}


@router.post("/reminders/dismiss")
def dismiss_reminder(body: DismissIn) -> dict:
    try:
        store.dismiss_reminder(body.entry_id, body.line)
    except CaptureError as exc:
        raise HTTPException(_status(exc), str(exc)) from exc
    return {"reminders": store.due_reminders(), "version": store.version}


# ── Folders ───────────────────────────────────────────────────────────────


@router.get("/folders")
def list_folders() -> dict:
    return {"folders": store.folders(), "version": store.version}


@router.post("/folders", status_code=201)
def create_folder(body: FolderIn) -> dict:
    try:
        return {
            "folder": store.create_folder(body.name, body.tags),
            "version": store.version,
        }
    except CaptureError as exc:
        raise HTTPException(_status(exc), str(exc)) from exc


@router.get("/folders/{folder_id}")
def folder_detail(folder_id: str) -> dict:
    """The folder, everything in it, and its sentiment counts.

    Membership is resolved here rather than stored, so this is also the answer
    to "what would happen if I mapped that tag" — map it and the entries are
    already inside.
    """
    try:
        return {**store.folder_detail(folder_id), "version": store.version}
    except CaptureError as exc:
        raise HTTPException(_status(exc), str(exc)) from exc


@router.patch("/folders/{folder_id}")
def patch_folder(folder_id: str, body: FolderPatch) -> dict:
    """Rename it, move it along its life, and add or drop tag mappings. One
    request can do all of them, which is what the mapping screen's drag needs
    when it also creates."""
    try:
        folder = None
        if body.name is not None:
            folder = store.rename_folder(folder_id, body.name)
        if body.state is not None:
            folder = store.set_folder_state(folder_id, body.state)
        for tag in body.add_tags:
            folder = store.map_tag(folder_id, tag)
        for tag in body.remove_tags:
            folder = store.unmap_tag(folder_id, tag)
        if body.overview is not None:
            folder = store.set_overview(folder_id, body.overview)
        if body.overview_media is not None:
            folder = store.set_overview_media(folder_id, body.overview_media)
        if folder is None:
            raise HTTPException(400, "nothing to change")
        return {"folder": folder, "version": store.version}
    except CaptureError as exc:
        raise HTTPException(_status(exc), str(exc)) from exc


@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: str) -> dict:
    """Deletes the folder, not what was written into it. The entries stay and
    their tags return to the unassigned pool."""
    try:
        store.delete_folder(folder_id)
    except CaptureError as exc:
        raise HTTPException(_status(exc), str(exc)) from exc
    return {"ok": True, "version": store.version}


@router.post("/import")
def import_csv(body: ImportIn) -> dict:
    """Read a CSV into the log. Parsed here rather than in the browser: the
    source parses client-side because it may have to encrypt before the server
    sees anything, and that reason does not exist on one machine."""
    return {**store.import_csv(body.csv), "version": store.version}


@router.get("/tags/unassigned")
def unassigned_tags() -> dict:
    """Every tag written that no folder has claimed. The mapping screen is
    this list and nothing else."""
    tags = store.unassigned_tags()
    return {"tags": tags, "total": len(tags), "version": store.version}


@router.get("/dates")
def list_dates() -> dict:
    return {"dates": store.dates(), "version": store.version}




def _year(value: str | None) -> str | None:
    """`all` and an absent parameter both mean "do not scope by year" — the
    first is the setting turned off, the second a caller that never had one."""
    if value is None or value == "all":
        return None
    if not YEAR_RE.match(value):
        raise HTTPException(400, "year must be YYYY or 'all'")
    return value


class GroupIn(BaseModel):
    """`year` is required and `name` may be empty — an empty name is the way
    out of a group, and there is no other one."""

    year: str
    name: str = ""


@router.put("/folders/{folder_id}/group")
def set_folder_group(folder_id: str, body: GroupIn) -> dict:
    """Put a folder under a named heading on one year's shelf.

    Returns the whole shelf rather than the folder: the caller is looking at
    the shelf, one move can create a heading or empty one out of existence, and
    a folder-shaped answer would not say either.
    """
    try:
        return {**store.set_folder_group(folder_id, body.year, body.name), "version": store.version}
    except CaptureError as exc:
        raise HTTPException(_status(exc), str(exc)) from exc


class GroupEdit(BaseModel):
    """`to` is only read by the rename route. Both routes are POSTs on a name
    rather than verbs on a path, because a group's name is its identity and a
    name with a slash or a space in it does not belong in a URL path — the same
    reason `/reminders/dismiss` is shaped this way."""

    year: str
    name: str
    to: str = ""


@router.post("/groups/rename")
def rename_group(body: GroupEdit) -> dict:
    """Rename one year's group. Renaming onto a name the year already has
    merges the two; see `store.rename_group`."""
    try:
        return {**store.rename_group(body.year, body.name, body.to), "version": store.version}
    except CaptureError as exc:
        raise HTTPException(_status(exc), str(exc)) from exc


@router.post("/groups/delete")
def delete_group(body: GroupEdit) -> dict:
    """Take a group off one year's shelf. Its folders return to the loose grid;
    no folder and no entry is touched."""
    try:
        return {**store.delete_group(body.year, body.name), "version": store.version}
    except CaptureError as exc:
        raise HTTPException(_status(exc), str(exc)) from exc


@router.get("/shelf")
def shelf(year: str | None = None) -> dict:
    """The year shelf: every album with anything in it this year, its twelve
    month volumes, its lead media and its chapter count.

    All of it derived on the read. An album is a folder seen through one year,
    and no row anywhere records that pairing — see `index.shelf`.
    """
    return {**store.shelf(_year(year)), "version": store.version}


@router.get("/album")
def album(folder: str | None = None, year: str | None = None) -> dict:
    """One album, one year. `folder` absent (or `unfiled`) is the pile nothing
    has claimed, which the shelf offers as an album of its own."""
    target = None if folder in (None, "", "unfiled") else folder
    try:
        return {**store.album(target, _year(year)), "version": store.version}
    except CaptureError as exc:
        raise HTTPException(_status(exc), str(exc)) from exc


@router.post("/reindex")
def reindex() -> dict:
    """Throw the index away and replay the log.

    Safe by construction — the index is a projection and nothing else — which
    is why this can be a button rather than a maintenance procedure.
    """
    store.reindex()
    return {
        "indexed": store.indexed,
        "warnings": store.warnings,
        "version": store.version,
    }


@router.get("/cumulative")
def cumulative(up_to: str) -> dict:
    """Word count, tag bars and the sentiment weekday chart, as of a day.

    Readings, drawn and never interpreted — the same rule the tech tree's
    metrics live under. Nothing here tells the user what any of it means.
    """
    day = _day(up_to, "up_to")
    assert day is not None  # _day only returns None for a None input
    return {**store.cumulative(day), "version": store.version}


@router.get("/vocab")
def get_vocab() -> dict:
    """Autocomplete's raw material, plus the folder registry the live
    validation checks a draft against. One request because the capture bar
    needs all of it before the first keystroke."""
    return {**store.vocab(), "version": store.version}


@router.get("/health")
def health() -> dict:
    return {
        "entries": len(store.entries(limit=5000)),
        "indexed_events": store.indexed,
        "warnings": store.warnings,
        "version": store.version,
    }
