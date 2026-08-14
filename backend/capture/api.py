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

from .store import CaptureError, store

router = APIRouter(prefix="/api/capture", tags=["capture"])

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CaptureIn(BaseModel):
    raw_text: str


class EntryPatch(BaseModel):
    toggle_line: int


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
        return {"entry": store.capture(body.raw_text), "version": store.version}
    except CaptureError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/entries/{entry_id}")
def patch_entry(entry_id: str, body: EntryPatch) -> dict:
    """The only mutation an entry has. It is not an edit: it appends a
    `check` or an `uncheck` and returns the re-folded entry."""
    try:
        return {
            "entry": store.toggle_line(entry_id, body.toggle_line),
            "version": store.version,
        }
    except CaptureError as exc:
        raise HTTPException(404 if "no such entry" in str(exc) else 400, str(exc)) from exc


@router.get("/dates")
def list_dates() -> dict:
    return {"dates": store.dates(), "version": store.version}


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
    """Autocomplete's raw material. `folders` is always empty for now: folders
    are entities in the source (name, colour, tag mappings) and that screen is
    not ported yet. The key is present so the client's shape does not change
    when it arrives."""
    return {"folders": [], "tag_to_folder": {}, **store.vocab()}


@router.get("/health")
def health() -> dict:
    return {
        "entries": len(store.entries(limit=5000)),
        "indexed_events": store.indexed,
        "warnings": store.warnings,
        "version": store.version,
    }
