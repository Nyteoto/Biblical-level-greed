"""One day, from the selfie to the seal — or to nothing.

    unborn ──selfie──▶ awake ──begin (19:00–23:00)──▶ sitting ──commit──▶ sealed
                         │                              │
                         └───────── 23:00 ──────────────┴──left / silent──▶ terminated

Why it is shaped this way
-------------------------
**The day in progress is the one thing in the Portal that is meant to be
lost.** It lives in `today.json` and nowhere else, and it is deleted the moment
it resolves either way: on a seal because the Record now holds it, on a
termination because the premise says the day did not happen. So there is no
log here, and nothing append-only — this module's whole job is to be able to
forget.

**A terminated day leaves one tombstone, until midnight.** Everything it held —
the selfie, every clip, the file itself — is deleted, and a bare
`{"terminated": true}` is written in its place so that the same Instance
cannot simply open the app again, take a new selfie and sit a second time. At
the next day's first request even that goes. Nothing about a failed day
survives into the next one except the gap in the numbering, which `records`
already explains.

**One sitting means the text never reaches the server until it is sealed.**
The draft lives in the page. The server holds only a token, a start time and
the last heartbeat, so there is no copy to resume from — a reload is a lost
sitting *by construction*, rather than by a rule somebody could find a way
around. The page reports its own departure (`leave`) and the heartbeat catches
the departures a page cannot report: a crash, a closed laptop, a phone that
died in a pocket.

**Settling is lazy, and it is the only way a day ends without a commit.** No
timer thread watches the clock. Every request settles first — has the date
rolled over, has 23:00 passed, has the sitting gone quiet for longer than the
grace — and the answer is the same whenever it is asked, which is what lets
the same code run unattended on both halves of a dual-boot machine. A laptop
closed at 21:00 and opened at 08:00 finds a terminated yesterday, not a sitting
that is somehow still open.

**Every decision takes `now` as an argument.** The routes pass the clock in;
the tests pass the instant they mean. No function here reads the time itself.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path

from . import media, records, timeutil
from .config import MAX_MEDIA, SITTING_GRACE_SECONDS, TODAY_PATH

# Which version of the template a Record was written against. Stored on every
# Record so a later template can add a field without making the old ones look
# as if they had left it blank.
TEMPLATE = 1

# What counts as "filled": at least one letter or digit, in any script.
_FILLED = re.compile(r"\w")

# The fields a Record's text is made of, in the order the template draws them,
# and what a refusal calls each one.
TEXT_FIELDS = {
    "body": "the record",
    "wish": "what the next Instance should do",
    "signature": "the signature",
}

_lock = threading.RLock()


class DayError(Exception):
    """The day refused what was asked of it. `status` is the HTTP answer."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


# ── The file ──────────────────────────────────────────────────────────────


def _load() -> dict | None:
    try:
        return json.loads(TODAY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except ValueError:
        # A torn write is a day that did not happen cleanly, and a day that did
        # not happen cleanly is terminated rather than guessed at.
        return {"terminated": True, "reason": "corrupt"}


def _save(state: dict) -> None:
    TODAY_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=TODAY_PATH.parent, suffix=".part")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(state, out, ensure_ascii=False, indent=2)
        os.replace(temp, TODAY_PATH)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _forget_media(refs: list[str]) -> None:
    for ref in refs:
        for path in (media.path_for(ref), media.path_for(media.view_ref(ref))):
            if path is not None:
                path.unlink(missing_ok=True)


def _owned(state: dict) -> list[str]:
    refs = [m["ref"] for m in state.get("media", [])]
    if state.get("selfie"):
        refs.append(state["selfie"])
    return refs


def _terminate(state: dict, reason: str) -> dict:
    _forget_media(_owned(state))
    tomb = {
        "day": state.get("day"),
        "instance": state.get("instance"),
        "terminated": True,
        "reason": reason,
    }
    _save(tomb)
    return tomb


# ── Settling ──────────────────────────────────────────────────────────────


def _silent(state: dict, now: datetime) -> bool:
    sitting = state.get("sitting")
    if not sitting:
        return False
    last = datetime.fromisoformat(sitting["beat"])
    return now - last > timedelta(seconds=SITTING_GRACE_SECONDS)


def settle(now: datetime) -> dict | None:
    """Resolve whatever the clock has already decided. Returns today's state.

    Idempotent: asking twice at the same instant changes nothing the second
    time, which is what lets every route call it without thinking.
    """
    with _lock:
        state = _load()
        if state is None:
            return None
        today = timeutil.day_key(now)

        if state.get("day") != today:
            # Yesterday never sealed (a seal deletes this file). Whatever it
            # held goes, and so does its tombstone: today starts clean.
            if not state.get("terminated"):
                _forget_media(_owned(state))
            TODAY_PATH.unlink(missing_ok=True)
            return None

        if state.get("terminated"):
            return state
        if timeutil.past_window(now):
            return _terminate(state, "deadline")
        if _silent(state, now):
            return _terminate(state, "silent")
        return state


# ── What the page asks ────────────────────────────────────────────────────


def phase(state: dict | None, now: datetime) -> str:
    instance = timeutil.instance_of(timeutil.day_key(now))
    if records.exists(instance):
        return "sealed"
    if state is None:
        # Nobody woke today. After the deadline that is a termination with
        # nothing to delete; before it, the Instance simply has not arrived.
        return "terminated" if timeutil.past_window(now) else "unborn"
    if state.get("terminated"):
        return "terminated"
    if state.get("sitting"):
        return "sitting"
    return "awake" if state.get("selfie") else "unborn"


def _fresh(now: datetime) -> dict:
    day = timeutil.day_key(now)
    return {"day": day, "instance": timeutil.instance_of(day), "media": []}


def take_selfie(ref: str, kind: str, now: datetime) -> dict:
    """Wake the Instance. A retake is allowed until the sitting begins."""
    if kind != "image":
        _forget_media([ref])
        raise DayError("a mugshot is a photograph", 400)
    with _lock:
        state = settle(now)
        current = phase(state, now)
        if current not in ("unborn", "awake"):
            _forget_media([ref])
            raise DayError(f"the selfie cannot change now: today is {current}")
        state = state or _fresh(now)
        if state.get("selfie") and state["selfie"] != ref:
            _forget_media([state["selfie"]])
        state["selfie"] = ref
        _save(state)
        return state


def begin_sitting(now: datetime) -> str:
    """Open the one sitting this day gets. Returns its token."""
    with _lock:
        state = settle(now)
        current = phase(state, now)
        if current == "sitting":
            raise DayError("a sitting is already under way on another screen")
        if current != "awake":
            raise DayError(f"a sitting cannot begin: today is {current}")
        if not timeutil.in_window(now):
            raise DayError("the commit window is closed")
        token = secrets.token_urlsafe(24)
        stamp = now.isoformat()
        state["sitting"] = {"token": token, "began": stamp, "beat": stamp}
        _save(state)
        return token


def _sitting(token: str, now: datetime) -> dict:
    state = settle(now)
    if phase(state, now) != "sitting":
        raise DayError("there is no sitting: the day has ended", 410)
    if not secrets.compare_digest(state["sitting"]["token"], token or ""):
        raise DayError("this is not the sitting that began", 403)
    return state


def beat(token: str, now: datetime) -> None:
    with _lock:
        state = _sitting(token, now)
        state["sitting"]["beat"] = now.isoformat()
        _save(state)


def leave(token: str, now: datetime) -> None:
    """The page is going. So is the day."""
    with _lock:
        state = _sitting(token, now)
        _terminate(state, "left")


def attach(token: str, ref: str, kind: str, now: datetime) -> dict:
    with _lock:
        try:
            state = _sitting(token, now)
        except DayError:
            _forget_media([ref])
            raise
        if kind not in ("image", "video") or media.path_for(ref) is None:
            raise DayError("no such media", 404)
        if len(state["media"]) >= MAX_MEDIA:
            _forget_media([ref])
            raise DayError(f"a Record holds {MAX_MEDIA} media and no more")
        state["media"].append({"ref": ref, "kind": kind})
        state["sitting"]["beat"] = now.isoformat()
        _save(state)
        return state


def detach(token: str, ref: str, now: datetime) -> dict:
    with _lock:
        state = _sitting(token, now)
        kept = [m for m in state["media"] if m["ref"] != ref]
        if len(kept) == len(state["media"]):
            raise DayError("that media is not on this Record", 404)
        _forget_media([ref])
        state["media"] = kept
        _save(state)
        return state


def owns(ref: str, now: datetime) -> bool:
    """Whether today's unsealed day holds this media — for the poster route."""
    state = settle(now)
    return bool(state and not state.get("terminated") and ref in _owned(state))


# ── Committing ────────────────────────────────────────────────────────────


def missing(state: dict, fields: dict) -> list[str]:
    """What still stands between this draft and a Record. Empty means ready."""
    gaps = [
        label
        for key, label in TEXT_FIELDS.items()
        if not _FILLED.search(str(fields.get(key) or ""))
    ]
    mood = fields.get("mood")
    if not isinstance(mood, int) or isinstance(mood, bool) or not 1 <= mood <= 10:
        gaps.append("how you feel, from 1 to 10")
    pictures = (1 if state.get("selfie") else 0) + sum(
        1 for m in state.get("media", []) if m["kind"] == "image"
    )
    if pictures < 1:
        gaps.append("at least one picture")
    return gaps


def commit(token: str, fields: dict, now: datetime) -> dict:
    """Seal today's Record. Returns it. After this nothing can change it."""
    with _lock:
        state = _sitting(token, now)
        if not timeutil.in_window(now):
            raise DayError("the commit window is closed")
        gaps = missing(state, fields)
        if gaps:
            raise DayError("not yet committable: " + "; ".join(gaps), 422)

        captions = fields.get("captions") or {}
        record = {
            "template": TEMPLATE,
            "instance": state["instance"],
            "day": state["day"],
            "selfie": state["selfie"],
            "media": [
                {
                    "ref": m["ref"],
                    "kind": m["kind"],
                    "caption": str(captions.get(m["ref"]) or "").strip(),
                }
                for m in state["media"]
            ],
            "body": str(fields["body"]).strip(),
            "wish": str(fields["wish"]).strip(),
            "signature": str(fields["signature"]).strip(),
            "mood": fields["mood"],
            "sitting": {"began": state["sitting"]["began"], "sealed": now.isoformat()},
        }
        try:
            records.write(record)
        except records.SealedError as exc:
            raise DayError(str(exc)) from exc
        # The Record owns the media now. Deleting the day must not take it.
        TODAY_PATH.unlink(missing_ok=True)
        return record
