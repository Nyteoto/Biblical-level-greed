"""Holds capture's index connection and serialises access to it.

Deliberately a second Store rather than a member of the tech tree's: the two
apps share a data root and nothing else. `version` increments on every change
so the frontend can poll cheaply and know whether anything moved — the same
contract the tech tree's store offers, because the frontend already knows how
to consume it.

It imports `app.media` for the same reason `eventlog` imports `app.timeutil`:
the blob store is a property of the *disk*, not of either app, and two of them
would mean two directories of the user's photographs. That is the second and
last deliberate coupling between the siblings.
"""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from datetime import timezone
from pathlib import Path

from backend.app import media as blobs
from backend.app.timeutil import day_key, now

from . import colors, eventlog, index, parser
from .config import (
    FOLDER_STATES,
    MAX_OPEN_TODOS,
    GROUP_NAME_MAX,
    MAX_NAME_LEN,
    MAX_RAW_LEN,
    MAX_SESSION_SECONDS,
    YEAR_RE,
)
from .import_csv import compose_line, flex_parse_time, parse_import_csv


class CaptureError(Exception):
    """A refusal the user should read, not a bug.

    `status` is the HTTP code the refusal deserves, and it is here rather than
    in `api.py` because the raise site is the only place that knows which it
    is. It used to be decided at the wire by reading the message —
    `str(exc).startswith("no such ")` — which made the *wording* of every
    refusal load-bearing: rewording one to "that folder is gone" would have
    turned a 404 into a 400 with nothing anywhere to notice. The prose is
    prose again.

    400 is the default because most refusals here are about what was asked
    for rather than about what is missing: a name too long, a state that is
    not a state, an eleventh open todo.
    """

    status = 400


class NotFound(CaptureError):
    """The thing this call names does not exist.

    Not every "no such …" is one of these, which is the whole reason the code
    is chosen at the raise rather than derived from the sentence. A capture
    naming a blob that is not there is a bad *request* — the collection it
    posts to exists — so `capture()` raises the base class for that and this
    subclass is for the subject the caller addressed: the folder in the path,
    the entry being ticked, the group being renamed.
    """

    status = 404


class Store:
    """The capture app's loaded state, and the one connection into its index.

    `index_path` names the index to open, and exists for the tests that prove
    the index is disposable: they build a second store by replaying the log and
    compare it against the first, which needs the two to hold separate files.
    They used to get that by unlinking the shared one — the first store kept
    reading the deleted inode, which is a POSIX behaviour and an error on
    Windows, where an open file cannot be unlinked at all. Asking for a path is
    the same test without the trick in it. The app never passes one.
    """

    def __init__(self, index_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._index_path = index_path
        self.conn = index.connect(index_path)
        self.warnings: list[str] = []
        self.indexed = 0
        self.version = 0

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self.reindex()

    def reindex(self) -> None:
        """Throw the index away and replay the log.

        Reconnects first: if the sqlite file was deleted out from under us the
        old handle still points at an unlinked inode and writes into nothing.
        """
        with self._lock:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass
            self.conn = index.connect(self._index_path)
            self.indexed, self.warnings = index.rebuild(self.conn)
            self.version += 1

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    # -- reads -------------------------------------------------------------

    def entries(
        self, start: str | None = None, end: str | None = None, limit: int = 20
    ) -> list[dict]:
        with self._lock:
            return index.entries(self.conn, start, end, limit)

    def dates(self) -> dict[str, int]:
        with self._lock:
            return index.dates(self.conn)

    def vocab(self) -> dict[str, list[str]]:
        with self._lock:
            return index.vocab(self.conn)

    def cumulative(self, up_to: str) -> dict:
        with self._lock:
            return index.cumulative(self.conn, up_to)

    def entry(self, entry_id: str) -> dict | None:
        with self._lock:
            return index.get(self.conn, entry_id)

    def folders(self) -> list[dict]:
        with self._lock:
            return index.folders(self.conn)

    def folder_detail(self, folder_id: str) -> dict:
        with self._lock:
            found = index.folder(self.conn, folder_id)
            if found is None:
                raise NotFound(f"no such folder: {folder_id}")
            return {
                "folder": found,
                "entries": index.folder_entries(self.conn, folder_id),
                "sentiments": index.folder_sentiments(self.conn, folder_id),
            }

    def shelf(self, year: str | None) -> dict:
        with self._lock:
            return index.shelf(self.conn, year)

    def album(self, folder_id: str | None, year: str | None) -> dict:
        with self._lock:
            found = index.album(self.conn, folder_id, year)
            if found is None:
                raise NotFound(f"no such folder: {folder_id}")
            return found

    def unassigned_tags(self) -> list[dict]:
        with self._lock:
            return index.unassigned_tags(self.conn)

    def due_reminders(self) -> list[dict]:
        """What has come due. The clock is read here and nowhere below."""
        as_of = now().astimezone(timezone.utc).isoformat()
        with self._lock:
            return index.due_reminders(self.conn, as_of)

    def banner(self) -> dict:
        """Everything the persistent banner draws, in one read.

        One endpoint rather than three, because the banner is one strip on
        every screen and three requests for it would let its halves disagree
        about the moment they describe — a todo checked off and a count that
        still says otherwise, half a second apart.

        The clock is read here, once, and handed down. Nothing below reads one.
        """
        as_of = now().astimezone(timezone.utc).isoformat()
        with self._lock:
            todos = index.open_todos(self.conn)

            def _placed(item: dict) -> dict:
                """Where to go to be looking at this line. Resolved here so the
                banner is one round trip — the client would otherwise have to
                ask per item, on every screen, forever."""
                entry = index.get(self.conn, item["entry_id"])
                return {
                    **item,
                    "folder": index.home_folder(self.conn, item["entry_id"]),
                    # The day the line was *written*, which is the year whose
                    # album holds it. Not the due date: `{14/09}` written in
                    # August is read in August's album, and a reminder that
                    # crosses a new year would otherwise open an album the
                    # entry is not in.
                    "day": entry["day"] if entry else "",
                }

            due = [_placed(r) for r in index.due_reminders(self.conn, as_of)]
            upcoming = [_placed(r) for r in index.upcoming_reminders(self.conn, as_of)]
            return {
                # All of them, not just the first: the banner shows one at a
                # time but the client picks *which* — a queued todo is a
                # device-local choice and the server has no business knowing it.
                "todos": [_placed(t) for t in todos],
                "open": len(todos),
                "cap": MAX_OPEN_TODOS,
                # The standing pair, all of history and every folder including
                # none: how many promises have been written here and how many
                # were kept. It rides on this read rather than getting an
                # endpoint of its own because everything that changes it — a
                # capture, a tick — already refreshes the banner, and a second
                # channel for the same two numbers is a second thing to be out
                # of date. `open` is `made - done`, by construction.
                **index.todo_totals(self.conn),
                # Overdue first, then the countdown. Both are the same shape,
                # and which of them a reminder is is a fact about the clock
                # rather than about the reminder.
                "due": due,
                "upcoming": upcoming,
                "as_of": as_of,
            }

    # -- writes ------------------------------------------------------------

    def _commit(self, kind: str, subject: str, **fields) -> dict:
        """Append one event and put it into the index. Every write goes here.

        **Log first, always.** If the process dies between the append and the
        apply, a reindex recovers the truth; the other order would lose it.
        That ordering used to be restated at twenty-three call sites, each
        naming the event kind twice — once for the log and once again to pick
        which of `index.py`'s nineteen targeted mirrors to call afterwards.
        The mirrors are gone: `index.apply` is the one transition table, and
        the only thing a caller has to get right now is the event.

        `version` moves on every commit rather than once per method. It is a
        change counter the frontend polls, so more of them is never wrong —
        and a method that appends twice (a reply, which also dismisses what it
        answers) genuinely did change two things.
        """
        event = eventlog.append(kind, subject, **fields)
        with self.conn:
            index.apply(self.conn, event)
        self.version += 1
        return event

    def capture(
        self, raw_text: str, media: Iterable[str] = (), reply_to: str | None = None
    ) -> dict:
        """Append one captured line. Log first, then mirror into the index —
        if the process dies between the two, a reindex recovers the truth.

        `media` is a list of paths already uploaded to the blob store. They are
        checked here rather than trusted, because a reference that resolves to
        nothing would be written into an append-only log and stay wrong. An
        entry may carry media and no text — a clip is a capture on its own —
        but it may not be empty of both.

        `reply_to` is the entry this one answers — a `--reply` to a reminder
        that had come due. Two things follow from it, and the second is the
        reason it belongs here rather than in two calls: the link is written on
        the event, and **the reminder being answered is dismissed**, because
        answering a prompt is the most complete way of having dealt with it and
        being asked again would be the app not listening. One append for the
        capture, one for the dismissal, both inside the lock.
        """
        text = raw_text.strip()
        attached = [ref for ref in media if ref]
        if not text and not attached:
            raise CaptureError("nothing to capture")
        if len(text) > MAX_RAW_LEN:
            raise CaptureError(f"too long (max {MAX_RAW_LEN} characters)")
        for ref in attached:
            if blobs.path_for(ref) is None:
                raise CaptureError(f"no such media: {ref}")

        with self._lock:
            # The todo cap, checked against the log as it stands plus what this
            # line would add. Both halves matter: eleven todos in one entry is
            # refused by the same arithmetic that refuses an eleventh added to
            # ten, and neither is a special case.
            #
            # Refused *before* the append, because the log is append-only —
            # there is no way to take a line back, so a capture that breaks the
            # rule must never reach the file. This is the only place a capture
            # is turned away for what it says rather than how big it is.
            adding = len(index.derive(text)["todo_lines"])
            if adding:
                standing = index.count_open_todos(self.conn)
                if standing + adding > MAX_OPEN_TODOS:
                    raise CaptureError(
                        f"{standing} of {MAX_OPEN_TODOS} todos are already open"
                        + (
                            f" — this line adds {adding}"
                            if adding > 1
                            else " — check one off first"
                        )
                    )

            answering = None
            if reply_to:
                if index.get(self.conn, reply_to) is None:
                    raise CaptureError(f"no such entry to reply to: {reply_to}")
                # Which of that entry's reminders is being answered: the oldest
                # one that has come due and not been dismissed — the same one
                # the capture screen was showing when the reply was typed. It
                # is resolved here rather than sent by the client so the two
                # cannot disagree about which prompt this answers.
                answering = self._due_on(reply_to)

            event = self._commit(
                eventlog.CAPTURE,
                eventlog.new_id(),
                text=text,
                media=attached,
                reply_to=reply_to or None,
            )
            if answering is not None:
                self._commit(eventlog.DISMISS, reply_to, line=answering["line"])
            return index.get(self.conn, event["id"])  # type: ignore[return-value]

    def _due_on(self, entry_id: str) -> dict | None:
        """The oldest undismissed reminder that has come due on one entry."""
        as_of = now().astimezone(timezone.utc).isoformat()
        for reminder in index.due_reminders(self.conn, as_of):
            if reminder["entry_id"] == entry_id:
                return reminder
        return None

    def toggle_line(self, entry_id: str, line: int) -> dict:
        """Tick or untick one `--todo` line.

        Reads the folded state and writes its inverse, both under one lock: the
        log has no notion of "the current value", so two toggles racing would
        otherwise both read unticked and both append `check`.
        """
        with self._lock:
            entry = index.get(self.conn, entry_id)
            if entry is None:
                raise NotFound(f"no such entry: {entry_id}")
            if line not in entry["todo_lines"]:
                raise CaptureError(f"line {line} of that entry is not a todo")

            ticking = line not in set(entry["todo_done"])
            self._commit(
                eventlog.CHECK if ticking else eventlog.UNCHECK, entry_id, line=line
            )
            return index.get(self.conn, entry_id)  # type: ignore[return-value]

    def import_csv(self, text: str) -> dict:
        """Read a CSV of entries into the log, stamped with their own dates.

        Every row becomes an ordinary capture event: `compose_line` folds the
        tag and pattern columns back into the text, so an imported entry is a
        line like any other and the parser derives its metadata on the next
        rebuild exactly as it would for something typed. A row whose time
        column does not parse is stamped with the moment of import rather than
        dropped — the words are the part worth keeping.

        One reindex at the end rather than a mirror per row: an import is the
        one bulk write this app has, and replaying is cheaper than a thousand
        round trips through the index.
        """
        parsed = parse_import_csv(text)
        stamp = now()

        written = skipped = 0
        with self._lock:
            for row in parsed.rows:
                line = compose_line(row)
                if len(line) > MAX_RAW_LEN:
                    skipped += 1
                    continue
                when = flex_parse_time(row.time, now=stamp) or stamp
                eventlog.append(
                    eventlog.CAPTURE,
                    eventlog.new_id(),
                    text=line,
                    ts=when.isoformat(timespec="seconds"),
                    day=day_key(when),
                )
                written += 1

        # Outside the loop and outside nothing else: reindex takes the lock.
        self.reindex()
        return {"imported": written, "skipped": skipped, "header": parsed.has_header}

    def attach_media(self, entry_id: str, media: Iterable[str]) -> dict:
        """Hang files on an entry that is already written.

        This is what keeps the capture bar honest about its own promise. A
        thought is sent the moment you press enter; a two-gigabyte clip takes
        minutes, and making the line wait for it would turn the fastest screen
        in the app into the slowest. So the entry goes in with whatever has
        finished, and each upload that lands afterwards appends one of these.

        Appending rather than replacing, and de-duplicated on the way in: a
        retried attach must not double the list.
        """
        refs = [ref for ref in media if ref]
        if not refs:
            raise CaptureError("nothing to attach")

        with self._lock:
            entry = index.get(self.conn, entry_id)
            if entry is None:
                raise NotFound(f"no such entry: {entry_id}")
            for ref in refs:
                if blobs.path_for(ref) is None:
                    raise NotFound(f"no such media: {ref}")

            fresh = [ref for ref in refs if ref not in entry["media"]]
            if not fresh:
                return entry

            self._commit(eventlog.ATTACH_MEDIA, entry_id, media=fresh)
            return index.get(self.conn, entry_id)  # type: ignore[return-value]

    def dismiss_reminder(self, entry_id: str, line: int) -> None:
        """Stop showing one reminder. Appends; the line it came from stays."""
        with self._lock:
            entry = index.get(self.conn, entry_id)
            if entry is None:
                raise NotFound(f"no such entry: {entry_id}")
            self._commit(eventlog.DISMISS, entry_id, line=line)

    # -- folders -----------------------------------------------------------
    #
    # Every one of these is log-first, mirror-second, under the lock — the
    # same shape as `capture`. A folder is not a row that gets edited; it is
    # the last word in a conversation the log has been having about it.

    def _checked_name(self, name: str, except_id: str | None = None) -> str:
        clean = name.strip()
        if not clean:
            raise CaptureError("a folder needs a name")
        if len(clean) > MAX_NAME_LEN:
            raise CaptureError(f"name too long (max {MAX_NAME_LEN} characters)")
        if index.folder_name_taken(self.conn, clean, except_id):
            raise CaptureError(f"there is already a folder called {clean!r}")
        return clean

    def _map_tag(self, folder_id: str, raw_tag: str, *, steal: bool) -> None:
        """Point one tag at one folder, if it is allowed to move.

        `steal` is the difference between the two ways a mapping happens. A
        tag the user drags onto a folder moves there whatever held it before —
        that is the whole gesture, and it is what the source's upsert does. A
        folder's own name, claimed implicitly on create and rename, does not:
        naming a folder `work` must never silently pull `<work>` out of the
        folder it was already filed under.
        """
        tag = parser.normalize_tag(raw_tag)
        if not tag:
            return
        owner = index.folder(self.conn, folder_id)
        if owner is None:
            raise NotFound(f"no such folder: {folder_id}")
        current = index.tag_owner(self.conn, tag)
        if current == folder_id or (current is not None and not steal):
            return
        self._commit(eventlog.MAP_TAG, folder_id, tag=tag)

    def create_folder(self, name: str, tags: Iterable[str] = ()) -> dict:
        with self._lock:
            clean = self._checked_name(name)
            existing = index.folders(self.conn)
            colour = colors.next_color([f["color"] for f in existing])

            folder_id = eventlog.new_id()
            self._commit(
                eventlog.CREATE_FOLDER, folder_id, text=clean, color=colour
            )

            # **A folder claims no tag of its own.** It used to claim the tag of
            # its own name here, so that `--work` reached the folder Work
            # through the ordinary mapping and needed no special case anywhere.
            # The special case is cheaper than what that cost: a word per folder
            # in the registry that nobody had ever typed, in the one list that
            # is supposed to hold the words you chose to point somewhere. A
            # directive resolves against the folder's *name* now, at read time —
            # see `_BY_DIRECTIVE` in index.py — so nothing downstream lost
            # anything and the registry starts empty.
            for tag in tags:
                self._map_tag(folder_id, tag, steal=True)

            self.version += 1
            return index.folder(self.conn, folder_id)  # type: ignore[return-value]

    def rename_folder(self, folder_id: str, name: str) -> dict:
        with self._lock:
            before = index.folder(self.conn, folder_id)
            if before is None:
                raise NotFound(f"no such folder: {folder_id}")
            clean = self._checked_name(name, except_id=folder_id)

            # The old name keeps answering, and nothing here has to arrange
            # that: a folder's names accumulate in `folder_names`, so entries
            # written `--oldname` reach it exactly as they did. That is the one
            # thing a rename must not change, and it costs no tag and no
            # registry entry — see `folder_names` in index.py.
            self._commit(eventlog.RENAME_FOLDER, folder_id, text=clean)
            return index.folder(self.conn, folder_id)  # type: ignore[return-value]

    def set_overview(self, folder_id: str, text: str) -> dict:
        """The folder's standing description. Last write wins, like a rename.

        Empty is a real value: clearing an overview is an edit, not a deletion,
        and the card stays because the folder still has one — it is just blank.
        """
        with self._lock:
            if index.folder(self.conn, folder_id) is None:
                raise NotFound(f"no such folder: {folder_id}")
            self._commit(eventlog.SET_OVERVIEW, folder_id, text=text)
            return index.folder(self.conn, folder_id)  # type: ignore[return-value]

    def set_overview_media(self, folder_id: str, ref: str) -> dict:
        """The one picture that stands for the folder.

        Setting this on a folder with no overview yet *creates* one, empty —
        a picture is a statement that the project is worth describing, and the
        card has to exist for the picture to sit in.
        """
        with self._lock:
            if index.folder(self.conn, folder_id) is None:
                raise NotFound(f"no such folder: {folder_id}")
            self._commit(
                eventlog.SET_OVERVIEW_MEDIA, folder_id, media=[ref] if ref else []
            )
            return index.folder(self.conn, folder_id)  # type: ignore[return-value]

    def set_folder_state(self, folder_id: str, state: str) -> dict:
        """Move a folder along its life: active, shipped, or neither.

        Neither is the default and the commonest: a folder you never mark is
        an ongoing interest rather than a project, and that distinction is
        allowed to emerge instead of being declared. Nothing has to be
        classified before it can be captured into, which is why this is three
        states on one list rather than two kinds of thing.
        """
        if state not in FOLDER_STATES:
            allowed = ", ".join(sorted(s or "none" for s in FOLDER_STATES))
            raise CaptureError(f"unknown state {state!r} — {allowed}")

        with self._lock:
            folder = index.folder(self.conn, folder_id)
            if folder is None:
                raise NotFound(f"no such folder: {folder_id}")
            if folder["state"] == state:
                return folder
            self._commit(eventlog.SET_STATE, folder_id, text=state)
            return index.folder(self.conn, folder_id)  # type: ignore[return-value]

    def set_folder_group(self, folder_id: str, year: str, name: str) -> dict:
        """Put a folder in a named group on one year's shelf, or take it out.

        The group is purely an arrangement of the shelf: it files nothing,
        gates nothing, and is not a second kind of membership. A folder's
        entries are found through its tags in every year, whether or not the
        card sits under a heading — which is what makes it safe for the same
        folder to be grouped one way in 2025 and another way in 2026.

        An empty `name` returns it to the loose grid. Naming a group nothing
        else uses is how a group is created; there is no separate object to
        make first, and none left behind when the last folder leaves.
        """
        name = self._group_name(name)
        if not YEAR_RE.match(year):
            raise CaptureError(f"not a year: {year!r}")

        with self._lock:
            folder = index.folder(self.conn, folder_id)
            if folder is None:
                raise NotFound(f"no such folder: {folder_id}")
            self._commit(eventlog.SET_GROUP, folder_id, text=name, year=year)
            return index.shelf(self.conn, year)

    def name_chapter(
        self, folder_id: str | None, year: str, month: int, name: str
    ) -> dict:
        """Give a chapter a name of your own, or hand it back.

        A chapter is the one thing on the album screen that had no way to be
        wrong: it is a run of months named from the commonest word written
        inside it, which is right often enough to be worth doing and wrong often
        enough to need overruling. An empty `name` deletes the override and the
        reader names it again.

        The month is the run's first, and the caller is the only one that knows
        it — `index.chapters` hands `first_month` out with every chapter for
        exactly this. See `name-chapter` in eventlog.py for why a month is a
        durable anchor for something derived.
        """
        name = self._group_name(name)
        if not YEAR_RE.match(year):
            raise CaptureError(f"not a year: {year!r}")
        if not 1 <= month <= 12:
            raise CaptureError(f"not a month: {month!r}")

        subject = folder_id or index.UNFILED_ALBUM
        with self._lock:
            if subject != index.UNFILED_ALBUM and index.folder(self.conn, subject) is None:
                raise NotFound(f"no such folder: {folder_id}")
            self._commit(
                eventlog.NAME_CHAPTER, subject, text=name, year=year, month=month
            )
            found = index.album(self.conn, folder_id, year)
            if found is None:
                raise NotFound(f"no such folder: {folder_id}")
            return found

    def _group_name(self, name: str) -> str:
        """One tidy-and-cap, so a name typed in the panel and one arriving from
        anywhere else cannot end up as two different groups."""
        name = " ".join(name.split())
        if len(name) > GROUP_NAME_MAX:
            raise CaptureError(f"group name is longer than {GROUP_NAME_MAX} characters")
        return name

    def rename_group(self, year: str, name: str, new_name: str) -> dict:
        """Rename one year's group, carrying every folder under it along.

        Renaming onto a name the year already uses **merges** rather than
        refusing. It is the obvious reading of the gesture, it is what the fold
        does anyway, and refusing would leave you renaming a group to something
        it is already next to with no way to say "these are the same thing".
        """
        if not YEAR_RE.match(year):
            raise CaptureError(f"not a year: {year!r}")
        new_name = self._group_name(new_name)
        if not new_name:
            raise CaptureError("a group needs a name — delete it instead")

        with self._lock:
            _, names = index.groups_for(self.conn, year)
            if name not in names:
                raise NotFound(f"no such group in {year}: {name!r}")
            if name == new_name:
                return index.shelf(self.conn, year)
            self._commit(eventlog.RENAME_GROUP, name, text=new_name, year=year)
            return index.shelf(self.conn, year)

    def order_groups(self, year: str, order: list[str]) -> dict:
        """Arrange one year's group headings.

        The whole order arrives at once rather than "this one moved to third",
        for the reason written beside `order-groups` in eventlog.py: an order
        is idempotent and a move is not. Names the shelf does not have are
        refused rather than ignored — a reorder naming a group that is not
        there means the caller is looking at a shelf that has since changed,
        and silently arranging the rest of it would be the wrong half of what
        they asked for.

        Groups the caller *omits* are not an error. They keep their relative
        order behind the ones named, which is what a partial arrangement means
        and what makes this survive a group appearing between the read and the
        write.
        """
        if not YEAR_RE.match(year):
            raise CaptureError(f"not a year: {year!r}")
        order = [self._group_name(name) for name in order]

        with self._lock:
            _, names = index.groups_for(self.conn, year)
            missing = [name for name in order if name not in names]
            if missing:
                raise NotFound(f"no such group in {year}: {missing[0]!r}")
            self._commit(eventlog.ORDER_GROUPS, year, order=order)
            return index.shelf(self.conn, year)

    def lift_tag(self, tag: str, lifted: bool) -> list[str]:
        """Stop drawing a tag's brackets, or draw them again.

        Presentation, and only presentation. The raw line is untouched — it is
        untouchable — and so is where it files: `<garden>` lifted still lands
        in whatever folder has claimed `garden`. What changes is that the app
        reads that word back as the prose it has become, which is the whole of
        what a tag you have stopped thinking of as a tag needs.

        Only `<tags>` can be lifted; see `lift-tag` in eventlog.py for why a
        `\\pattern`, an `@place` and a `{time}` cannot be.
        """
        tag = parser.normalize_tag(tag)
        if not tag:
            raise CaptureError("a tag to lift needs a name")

        with self._lock:
            already = tag in index.lifted_tags(self.conn)
            if already != lifted:
                self._commit(
                    eventlog.LIFT_TAG if lifted else eventlog.UNLIFT_TAG, tag
                )
            return index.lifted_tags(self.conn)

    def tags(self) -> list[dict]:
        """Every tag written, where it lands, and whether it is lifted."""
        with self._lock:
            return index.tag_census(self.conn)

    def delete_group(self, year: str, name: str) -> dict:
        """Take a group off one year's shelf, returning its folders to the
        loose grid above.

        Nothing is deleted in any sense that costs anything: a group has never
        held a folder, let alone an entry, and this is the same un-grouping you
        could do one card at a time written as one event.
        """
        if not YEAR_RE.match(year):
            raise CaptureError(f"not a year: {year!r}")

        with self._lock:
            _, names = index.groups_for(self.conn, year)
            if name not in names:
                raise NotFound(f"no such group in {year}: {name!r}")
            self._commit(eventlog.DELETE_GROUP, name, year=year)
            return index.shelf(self.conn, year)

    def delete_folder(self, folder_id: str) -> None:
        """Forget a folder, its tag mappings and its manual filings.

        Nothing written is deleted: the entries stay, their tags stay, and the
        tags land back in the unassigned pool. Deleting a folder is undoing a
        piece of filing, and the log has no way to delete anything else.
        """
        with self._lock:
            if index.folder(self.conn, folder_id) is None:
                raise NotFound(f"no such folder: {folder_id}")
            self._commit(eventlog.DELETE_FOLDER, folder_id)

    def log_time(self, folder_id: str, seconds: int) -> dict:
        """Record one measured stretch of work on a folder.

        The session gets its own id and the folder rides beside it, which is
        what makes a duplicated log line idempotent rather than a double count
        — see `log-time` in eventlog.py, where the argument is written down.

        Nothing about *when within the day* is stored. The event's `ts` says
        when it was stopped and its `seconds` says how long it ran, and the
        difference is not the start: a paused timer would make that a lie, and
        a start time nobody can rely on is worse than no start time. What the
        app claims is exactly what it measured.
        """
        with self._lock:
            if index.folder(self.conn, folder_id) is None:
                raise NotFound(f"no such folder: {folder_id}")

            try:
                length = int(seconds)
            except (TypeError, ValueError):
                raise CaptureError("a session length must be a whole number of seconds")
            if length < 0:
                raise CaptureError("a session cannot be negative")
            if length > MAX_SESSION_SECONDS:
                hours = MAX_SESSION_SECONDS // 3600
                raise CaptureError(
                    f"that session is longer than {hours} hours — "
                    "if the timer was left running, log what you actually did"
                )

            session_id = eventlog.new_id()
            self._commit(
                eventlog.LOG_TIME, session_id, folder=folder_id, seconds=length
            )
            return {"id": session_id, "seconds": length}

    def unlog_time(self, session_id: str) -> None:
        """Take back a session logged by mistake.

        The inverse rather than a deletion, which is the rule everywhere in
        this log: the `log-time` line stays where it was written and this one
        says it does not count. A replay of both, in either order, is the same
        answer — `unlog-time` is last-wins on the session, and the session's
        row is keyed on the id both events name.
        """
        with self._lock:
            row = self.conn.execute(
                "SELECT id FROM time_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise NotFound(f"no such session: {session_id}")
            self._commit(eventlog.UNLOG_TIME, session_id)

    def map_tag(self, folder_id: str, tag: str) -> dict:
        with self._lock:
            self._map_tag(folder_id, tag, steal=True)
            self.version += 1
            return index.folder(self.conn, folder_id)  # type: ignore[return-value]

    def unmap_tag(self, folder_id: str, tag: str) -> dict:
        with self._lock:
            folder = index.folder(self.conn, folder_id)
            if folder is None:
                raise NotFound(f"no such folder: {folder_id}")
            clean = parser.normalize_tag(tag)
            if clean in folder["tags"]:
                self._commit(eventlog.UNMAP_TAG, folder_id, tag=clean)
            return index.folder(self.conn, folder_id)  # type: ignore[return-value]

    def assign_entry(self, entry_id: str, folder_id: str | None) -> dict:
        """File an entry into a folder by hand, or take it back out.

        Post-capture filing on top of the syntax, not instead of it: the
        entry's tags still put it wherever they put it. This only ever adds a
        place, which is why unfiling cannot orphan anything.
        """
        with self._lock:
            entry = index.get(self.conn, entry_id)
            if entry is None:
                raise NotFound(f"no such entry: {entry_id}")

            if folder_id is None:
                for current in entry["manual_folders"]:
                    self._commit(eventlog.UNASSIGN, entry_id, folder=current)
            else:
                if index.folder(self.conn, folder_id) is None:
                    raise NotFound(f"no such folder: {folder_id}")
                self._commit(eventlog.ASSIGN, entry_id, folder=folder_id)
            return index.get(self.conn, entry_id)  # type: ignore[return-value]


store = Store()
