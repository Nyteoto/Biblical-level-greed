"""The instruments a domain is practised with, one file per domain.

Not nodes and not resources. A tool is a physical object you own — a pad and
sticks, an iCE40 board, a meter, a camera — and the reason it is worth recording
is that a domain's real cost and its real history live in this list, and nothing
else in the app can see them.

Deliberately mutable JSON rather than log events: a tool is a *record you
correct* (the model was wrong, the date was wrong, it broke last March), not an
event that happened. The event log stays for things that happened.

Retirement is a date, never a delete. What a domain used to be practised on is
the interesting part of the list.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

from .config import DATA_DIR, ensure_dirs
from .writer import SLUG_OK

MAX_TOOLS = 200  # a shelf, not an inventory system

# Everything a profile carries. Free text throughout — `type` and `model` are
# whatever the domain calls them, and pretending otherwise would mean inventing
# a taxonomy per domain.
FIELDS = ("name", "image", "price_kind", "price", "acquired", "retired", "type", "model")
PRICE_KINDS = ("diy", "paid")


class ToolError(Exception):
    """Bad domain id, malformed profile, or a shelf that is implausibly full."""


def tools_dir() -> Path:
    return DATA_DIR / "tools"


def path_for(domain_id: str) -> Path:
    if not SLUG_OK.match(domain_id or ""):
        raise ToolError(f"invalid domain id `{domain_id}`")
    return tools_dir() / f"{domain_id}.json"


def read(domain_id: str) -> list[dict]:
    target = path_for(domain_id)
    if not target.is_file():
        return []
    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError(f"`{domain_id}` tool shelf is unreadable: {exc}") from exc
    return loaded if isinstance(loaded, list) else []


def _save(domain_id: str, shelf: list[dict]) -> None:
    """Atomic, so a crash cannot leave half a shelf."""
    ensure_dirs()
    target = path_for(domain_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(shelf, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _clean(raw: dict) -> dict:
    out = {key: str(raw.get(key, "") or "").strip() for key in FIELDS}
    if out["price_kind"] not in PRICE_KINDS:
        out["price_kind"] = "paid"
    return out


def add(domain_id: str, fields: dict) -> dict:
    shelf = read(domain_id)
    if len(shelf) >= MAX_TOOLS:
        raise ToolError(f"`{domain_id}` already holds {MAX_TOOLS} tools")
    entry = _clean(fields)
    if not entry["name"]:
        raise ToolError("a tool needs a name")
    entry["id"] = uuid.uuid4().hex[:12]
    shelf.append(entry)
    _save(domain_id, shelf)
    return entry


def update(domain_id: str, tool_id: str, fields: dict) -> dict:
    shelf = read(domain_id)
    for i, entry in enumerate(shelf):
        if entry.get("id") != tool_id:
            continue
        merged = {**entry, **_clean({**entry, **fields})}
        merged["id"] = tool_id
        if not merged["name"]:
            raise ToolError("a tool needs a name")
        shelf[i] = merged
        _save(domain_id, shelf)
        return merged
    raise ToolError(f"unknown tool `{tool_id}`")


def remove(domain_id: str, tool_id: str) -> None:
    """Only for a profile created by mistake. Retiring is a date, not a delete —
    see the module docstring."""
    shelf = read(domain_id)
    kept = [e for e in shelf if e.get("id") != tool_id]
    if len(kept) == len(shelf):
        raise ToolError(f"unknown tool `{tool_id}`")
    _save(domain_id, kept)
