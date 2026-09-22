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

from . import index
from .config import YEAR_RE
from .store import store

router = APIRouter(prefix="/api/capture", tags=["capture"])

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: How many entries a read hands back when the caller named no limit. Small
#: for an open-ended read and large once a day or a span has been named,
#: because the caller has already bounded it — the source's own three numbers.
ENTRY_LIMITS = {"open": 20, "day": 500, "span": 2000}

#: The ceiling, whatever was asked for.
ENTRY_LIMIT_CAP = 5000


def entry_limit(asked: int | None, asked_for: str) -> int:
    """How many entries to read, given what the caller asked for and what
    kind of read it is.

    A named function rather than four lines inside the route: it is a real
    policy — three defaults and a cap — and while it lived in the route body
    the only way to exercise it was over HTTP.
    """
    return min(asked or ENTRY_LIMITS[asked_for], ENTRY_LIMIT_CAP)


class CaptureIn(BaseModel):
    raw_text: str = ""
    # Paths under data/media, uploaded before this call. A capture may be
    # nothing but a clip, so the text is allowed to be empty when these are not.
    media: list[str] = []
    # The entry this line answers, when it was sent with `--reply`. The client
    # strips the command off the text before sending — the same as the source —
    # so what is stored is the thought and this is what it is a thought about.
    reply_to: str | None = None


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
    asked_for = "open"
    if from_ and to:
        start, end = _day(from_, "from"), _day(to, "to")
        asked_for = "span"
    elif date:
        start = end = _day(date, "date")
        asked_for = "day"

    return {
        "entries": store.entries(start, end, entry_limit(limit, asked_for)),
        "version": store.version,
    }


@router.get("/search")
def search_entries(
    q: str,
    folder: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    limit: int | None = None,
) -> dict:
    """Every entry whose text contains `q`, newest first. `folder` scopes it
    to one album; `from`/`to` to a day span. The one route in this API that
    reads by content rather than by when or where something was filed."""
    start = end = None
    if from_ and to:
        start, end = _day(from_, "from"), _day(to, "to")
    return {
        "entries": store.search(
            q,
            index.scope_of(folder, index.EVERYTHING),
            start,
            end,
            min(limit or 50, 500),
        ),
        "version": store.version,
    }


@router.post("/entries", status_code=201)
def create_entry(body: CaptureIn) -> dict:
    return {
        "entry": store.capture(body.raw_text, body.media, body.reply_to),
        "version": store.version,
    }


@router.patch("/entries/{entry_id}")
def patch_entry(entry_id: str, body: EntryPatch) -> dict:
    """Tick a box, or file the entry into a folder by hand. Neither is an
    edit: each appends an event and returns the re-folded entry."""
    if body.toggle_line is not None:
        entry = store.toggle_line(entry_id, body.toggle_line)
    elif body.attach_media:
        entry = store.attach_media(entry_id, body.attach_media)
    elif "assign_folder" in body.model_fields_set:
        entry = store.assign_entry(entry_id, body.assign_folder)
    else:
        raise HTTPException(400, "nothing to change")
    return {"entry": entry, "version": store.version}


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

    A list where the source returns a single row. The capture screen shows one
    prompt either way — see the strip in `(capture)/+page.svelte` — but it also
    says how many are behind it, and a second single-row route would be two
    ways to ask one question.
    """
    return {"reminders": store.due_reminders(), "version": store.version}


@router.post("/reminders/dismiss")
def dismiss_reminder(body: DismissIn) -> dict:
    store.dismiss_reminder(body.entry_id, body.line)
    return {"reminders": store.due_reminders(), "version": store.version}


# ── Folders ───────────────────────────────────────────────────────────────


@router.get("/folders")
def list_folders() -> dict:
    return {"folders": store.folders(), "version": store.version}


@router.post("/folders", status_code=201)
def create_folder(body: FolderIn) -> dict:
    return {
        "folder": store.create_folder(body.name, body.tags),
        "version": store.version,
    }


@router.get("/folders/{folder_id}")
def folder_detail(folder_id: str) -> dict:
    """The folder, everything in it, and its sentiment counts.

    Membership is resolved here rather than stored, so this is also the answer
    to "what would happen if I mapped that tag" — map it and the entries are
    already inside.
    """
    return {**store.folder_detail(folder_id), "version": store.version}


@router.patch("/folders/{folder_id}")
def patch_folder(folder_id: str, body: FolderPatch) -> dict:
    """Rename it, move it along its life, and add or drop tag mappings. One
    request can do all of them, which is what Record's held panel needs when
    it points a loose tag at a folder it is also renaming.

    One call, because the gesture is one thing: `amend_folder` validates the
    whole patch before it appends any of it. This route used to make the six
    calls itself, in order, which is how a rename could commit and a bad state
    then answer 400 with the rename already in the log.
    """
    folder = store.amend_folder(
        folder_id,
        name=body.name,
        state=body.state,
        add_tags=body.add_tags,
        remove_tags=body.remove_tags,
        overview=body.overview,
        overview_media=body.overview_media,
    )
    return {"folder": folder, "version": store.version}


@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: str) -> dict:
    """Deletes the folder, not what was written into it. The entries stay and
    their tags return to the unassigned pool."""
    store.delete_folder(folder_id)
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


def _chapter_subject(folder: str | None) -> str | None:
    """Which album a chapter is being cut in, as the *write* side spells it:
    `None` for the pile, an id otherwise.

    Reads do not come through here — they take an `index.Scope`, built once by
    `index.scope_of`. This is the other half of that seam and the only
    translation left at the wire: a cut names the subject an event will carry,
    which is a different question from which entries a read is about.
    """
    return None if folder in (None, "", "unfiled") else folder


class ChapterIn(BaseModel):
    """`month` is `YYYY-MM`, where the chapter begins — the cut, which is the
    chapter's whole identity. An empty `name` is one cut and not yet named."""

    month: str
    name: str = ""


@router.put("/folders/{folder_id}/chapter")
def split_chapter(folder_id: str, body: ChapterIn) -> dict:
    """Cut a chapter here, or rename the one already cut here.

    One route for both because they are one event — see `split-chapter` in
    eventlog.py. Answers with the whole album, because a cut changes more than
    the row that asked for it: every chapter after it now ends a month earlier.
    """
    album = store.split_chapter(_chapter_subject(folder_id), body.month, body.name)
    return {**album, "version": store.version}


@router.delete("/folders/{folder_id}/chapter")
def unsplit_chapter(folder_id: str, month: str) -> dict:
    """Take a cut back. Nothing written moves: the entries join the chapter
    before them, and the album comes back saying so."""
    album = store.unsplit_chapter(_chapter_subject(folder_id), month)
    return {**album, "version": store.version}


@router.put("/folders/{folder_id}/group")
def set_folder_group(folder_id: str, body: GroupIn) -> dict:
    """Put a folder under a named heading on one year's shelf.

    Returns the whole shelf rather than the folder: the caller is looking at
    the shelf, one move can create a heading or empty one out of existence, and
    a folder-shaped answer would not say either.
    """
    return {**store.set_folder_group(folder_id, body.year, body.name), "version": store.version}


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
    return {**store.rename_group(body.year, body.name, body.to), "version": store.version}


@router.post("/groups/delete")
def delete_group(body: GroupEdit) -> dict:
    """Take a group off one year's shelf. Its folders return to the loose grid;
    no folder and no entry is touched."""
    return {**store.delete_group(body.year, body.name), "version": store.version}


class GroupOrder(BaseModel):
    """The whole arrangement of one year's shelf, not a move. See
    `order-groups` in eventlog.py: an order replayed twice is the same shelf,
    and a move replayed twice is not."""

    year: str
    order: list[str] = []


@router.post("/groups/order")
def order_groups(body: GroupOrder) -> dict:
    """Arrange one year's group headings. Answers with the whole shelf."""
    return {**store.order_groups(body.year, body.order), "version": store.version}


class TagLift(BaseModel):
    tag: str
    lifted: bool = True


@router.post("/tags/lift")
def lift_tag(body: TagLift) -> dict:
    """Stop drawing a tag's brackets, or draw them again.

    Presentation only: nothing about where the line files changes, and the raw
    line is untouchable in any case. Answers with the whole lifted set, because
    that is what every screen rendering a captured line holds.
    """
    return {"lifted": store.lift_tag(body.tag, body.lifted), "version": store.version}


@router.get("/tags")
def list_tags() -> dict:
    """Every tag written, commonest first, with where it lands and whether it
    has been lifted. The Settings screen's list."""
    return {"tags": store.tags(), "version": store.version}


@router.get("/shelf")
def shelf(year: str | None = None) -> dict:
    """The year shelf: every album with anything in it this year, its twelve
    month volumes, its lead media and its chapter count.

    All of it derived on the read. An album is a folder seen through one year,
    and no row anywhere records that pairing — see `index.shelf`.
    """
    return {**store.shelf(_year(year)), "version": store.version}


@router.get("/heat")
def heat(year: str | None = None, folder: str | None = None) -> dict:
    """Days and what each was worth, for the year lens.

    `folder` absent is **everything** — every entry the year holds, filed or
    not — which is what Map draws before a folder is chosen. `unfiled` is the
    pile, and an id is that folder. Its own route rather than a key on
    `/shelf`: the reading lens asks for the shelf every time the album
    changes and has no use for three hundred rows.
    """
    return {
        "days": store.heat(_year(year), index.scope_of(folder, index.EVERYTHING)),
        "version": store.version,
    }


@router.get("/threads")
def threads(folder: str | None = None) -> dict:
    """Every deadline that has been carried forward — a `{}` whose reply set
    the next one — live ones first.

    `folder` absent is every thread there is; `unfiled` is the pile; an id is
    that folder, matched against *any* turn so a reply tagged elsewhere cannot
    make a thread vanish from the folder you would look in.

    **No year.** A thread routinely crosses one, and cutting it at December
    would show half a conversation. Its own route rather than a key on
    `/banner`: the banner is read on every screen and has no use for a walk.
    """
    return {
        "threads": store.threads(index.scope_of(folder, index.EVERYTHING)),
        "version": store.version,
    }


@router.get("/album")
def album(folder: str | None = None, year: str | None = None) -> dict:
    """One album, one year. `folder` absent (or `unfiled`) is the pile nothing
    has claimed, which the shelf offers as an album of its own."""
    return {
        **store.album(index.album_scope_of(folder), _year(year)),
        "version": store.version,
    }


class TimeIn(BaseModel):
    """`seconds` and nothing else. The client measured it; the server records
    it and stamps it with now."""

    seconds: int


@router.post("/folders/{folder_id}/time", status_code=201)
def log_time(folder_id: str, body: TimeIn) -> dict:
    """Record a finished timer session against this folder.

    On the folder rather than on an entry: a session is time spent on the
    project, not a thing that was written. Nothing in the journal changes.
    """
    return {"session": store.log_time(folder_id, body.seconds), "version": store.version}


@router.delete("/time/{session_id}")
def unlog_time(session_id: str) -> dict:
    """Take back a session. Appends the inverse; deletes nothing."""
    store.unlog_time(session_id)
    return {"ok": True, "version": store.version}


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
