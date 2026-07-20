"""A plain checklist, appended to its own log.

This is the one part of the app that is *not* a tech tree. Trees answer "what
should I be working on"; this answers "buy strings, email the studio, book the
HSK slot" — specific things with no tier, no gate and no accrual, which would
be nonsense as nodes.

It is a separate stream from `log/*.jsonl` because those events are keyed by
(domain, node) and a todo has neither.

**Completion deletes the item from the list, and nothing from the file.** The
live list is a fold over the ops, exactly as node state is: `done` stops an item
rendering, it does not rewrite history. So the checklist behaves the way the
user asked — tick it and it is gone — while the record of what you actually did
survives on disk like everything else here.

The list does **not** reset daily. An item stays until you tick it, which is the
honest behaviour: things you meant to do do not stop mattering at midnight.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from .config import DATA_DIR, ensure_dirs
from .timeutil import day_key, now

ADD = "add"
DONE = "done"
OPS = {ADD, DONE}

MAX_TEXT = 500


def path() -> Path:
    return DATA_DIR / "todos.jsonl"


def _append(op: str, item_id: str, text: str = "") -> dict:
    ensure_dirs()
    when = now()
    record = {
        "ts": when.isoformat(timespec="seconds"),
        "day": day_key(when),
        "id": item_id,
        "op": op,
    }
    if text:
        record["text"] = text
    with path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
    return record


def add(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("a todo needs some text")
    return _append(ADD, uuid.uuid4().hex[:12], text[:MAX_TEXT])


def complete(item_id: str) -> dict:
    return _append(DONE, item_id)


def read_all() -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    warnings: list[str] = []
    target = path()
    if not target.exists():
        return records, warnings

    with target.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                warnings.append(f"todos.jsonl:{lineno}: unparseable line, skipped")
                continue
            if not all(k in record for k in ("ts", "day", "id", "op")):
                warnings.append(f"todos.jsonl:{lineno}: missing fields, skipped")
                continue
            if record["op"] not in OPS:
                warnings.append(
                    f"todos.jsonl:{lineno}: unknown op {record['op']!r}, skipped"
                )
                continue
            records.append(record)

    # Same reasoning as the event log: order by timestamp so two machines agree
    # after a merge, stably so that ties keep file order. No dedupe needed —
    # every op is keyed by item id and applying one twice is idempotent.
    records.sort(key=lambda record: record["ts"])
    return records, warnings


def live() -> list[dict]:
    """The open items, oldest first.

    Oldest first on purpose: a list that never resets will otherwise bury the
    thing you have been avoiding for a fortnight under this morning's additions.
    """
    open_items: dict[str, dict] = {}
    for record in read_all()[0]:
        if record["op"] == ADD:
            open_items[record["id"]] = {
                "id": record["id"],
                "text": record.get("text", ""),
                "added": record["day"],
            }
        else:
            open_items.pop(record["id"], None)
    return list(open_items.values())
