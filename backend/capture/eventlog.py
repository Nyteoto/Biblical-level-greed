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
`map-tag`/`unmap-tag`, folded last-wins at read time. Only the checkbox pair
is implemented so far — the other four are named here so the vocabulary is
decided once rather than reinvented per feature.

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

# A new entry. `id` is the entry's, `text` is the raw line as typed.
CAPTURE = "capture"
# One `--todo` line ticked / unticked. `line` is its index into the entry.
CHECK = "check"
UNCHECK = "uncheck"

KINDS = {CAPTURE, CHECK, UNCHECK}

# Reserved, not yet written by anything: post-hoc filing into a folder
# (`assign`/`unassign`, carrying a folder id) and tag→folder mapping
# (`map-tag`/`unmap-tag`). Listed so the names are settled before the features
# arrive; `read_all` will skip them until they join KINDS.


def new_id() -> str:
    """An entry id. Random rather than sequential: ids are referenced by later
    events (`check`, and eventually `reply-to`), so they have to survive a
    replay unchanged, which rules out anything derived from position."""
    return uuid.uuid4().hex[:12]


def log_path_for(day: str) -> Path:
    return LOG_DIR / f"{month_key(day)}.jsonl"


def append(
    kind: str,
    entry_id: str,
    text: str = "",
    line: int | None = None,
    day: str | None = None,
) -> dict:
    """Write one event. Never rewrites or deletes an existing line."""
    if kind not in KINDS:
        raise ValueError(f"unknown event kind: {kind}")

    ensure_dirs()
    when = now()
    event = {
        "ts": when.isoformat(timespec="seconds"),
        "day": day or day_key(when),
        "kind": kind,
        "id": entry_id,
    }
    if text:
        event["text"] = text
    if line is not None:
        event["line"] = line

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
