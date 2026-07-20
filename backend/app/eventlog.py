"""The append-only event log. This is the source of truth for everything the
user has done; the SQLite index is a disposable projection of it."""
from __future__ import annotations

import json
from pathlib import Path

from .config import LOG_DIR, ensure_dirs
from .timeutil import day_key, month_key, now

SESSION = "session"
UNDO = "undo"
COMPLETE = "complete"
REOPEN = "reopen"
JOURNAL = "journal"
PHASE = "phase"  # a project phase was ticked; `text` is the phase name
PHASE_UNDO = "phase_undo"

KINDS = {SESSION, UNDO, COMPLETE, REOPEN, JOURNAL, PHASE, PHASE_UNDO}


def log_path_for(day: str) -> Path:
    return LOG_DIR / f"{month_key(day)}.jsonl"


def append(
    domain: str,
    node: str,
    kind: str,
    day: str | None = None,
    text: str = "",
    value: float | None = None,
) -> dict:
    """Write one event. Never rewrites or deletes an existing line.

    `value` carries a measurable-gate reading taken on the day — the tempo you
    actually hit, say. It is a number the user typed, never one we inferred, and
    it is optional everywhere: older lines simply have no value.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown event kind: {kind}")

    ensure_dirs()
    when = now()
    event = {
        "ts": when.isoformat(timespec="seconds"),
        "day": day or day_key(when),
        "domain": domain,
        "node": node,
        "kind": kind,
    }
    if text:
        event["text"] = text
    if value is not None:
        event["value"] = value

    path = log_path_for(event["day"])
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        handle.flush()
    return event


def read_all() -> tuple[list[dict], list[str]]:
    """Every event, ordered by timestamp. Returns (events, warnings).

    Sorted by `ts` so a union-merged log resolves the same on any machine, and
    **stably with no content in the key**: `session, undo, session` inside one
    second is a real double-toggle and must keep file order. No dedupe — the
    fold is last-wins everywhere it matters.
    """
    events: list[dict] = []
    warnings: list[str] = []

    if not LOG_DIR.exists():
        return events, warnings

    for path in sorted(LOG_DIR.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    warnings.append(f"{path.name}:{lineno}: unparseable line, skipped")
                    continue
                if not all(k in event for k in ("ts", "day", "domain", "node", "kind")):
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
