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

from backend.app import media as blobs
from backend.app.timeutil import day_key, now

from . import colors, eventlog, index, parser
from .config import FOLDER_STATES, MAX_NAME_LEN, MAX_RAW_LEN
from .import_csv import compose_line, flex_parse_time, parse_import_csv


class CaptureError(Exception):
    """A refusal the user should read, not a bug."""


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.conn = index.connect()
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
            self.conn = index.connect()
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
                raise CaptureError(f"no such folder: {folder_id}")
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
                raise CaptureError(f"no such folder: {folder_id}")
            return found

    def unassigned_tags(self) -> list[dict]:
        with self._lock:
            return index.unassigned_tags(self.conn)

    def due_reminders(self) -> list[dict]:
        """What has come due. The clock is read here and nowhere below."""
        as_of = now().astimezone(timezone.utc).isoformat()
        with self._lock:
            return index.due_reminders(self.conn, as_of)

    # -- writes ------------------------------------------------------------

    def capture(self, raw_text: str, media: Iterable[str] = ()) -> dict:
        """Append one captured line. Log first, then mirror into the index —
        if the process dies between the two, a reindex recovers the truth.

        `media` is a list of paths already uploaded to the blob store. They are
        checked here rather than trusted, because a reference that resolves to
        nothing would be written into an append-only log and stay wrong. An
        entry may carry media and no text — a clip is a capture on its own —
        but it may not be empty of both.
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
            event = eventlog.append(
                eventlog.CAPTURE, eventlog.new_id(), text=text, media=attached
            )
            index.add_capture(self.conn, event)
            self.version += 1
            return index.get(self.conn, event["id"])  # type: ignore[return-value]

    def toggle_line(self, entry_id: str, line: int) -> dict:
        """Tick or untick one `--todo` line.

        Reads the folded state and writes its inverse, both under one lock: the
        log has no notion of "the current value", so two toggles racing would
        otherwise both read unticked and both append `check`.
        """
        with self._lock:
            entry = index.get(self.conn, entry_id)
            if entry is None:
                raise CaptureError(f"no such entry: {entry_id}")
            if line not in entry["todo_lines"]:
                raise CaptureError(f"line {line} of that entry is not a todo")

            done = set(entry["todo_done"])
            if line in done:
                eventlog.append(eventlog.UNCHECK, entry_id, line=line)
                done.discard(line)
            else:
                eventlog.append(eventlog.CHECK, entry_id, line=line)
                done.add(line)

            index.set_done(self.conn, entry_id, sorted(done))
            self.version += 1
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
                raise CaptureError(f"no such entry: {entry_id}")
            for ref in refs:
                if blobs.path_for(ref) is None:
                    raise CaptureError(f"no such media: {ref}")

            fresh = [ref for ref in refs if ref not in entry["media"]]
            if not fresh:
                return entry

            eventlog.append(eventlog.ATTACH_MEDIA, entry_id, media=fresh)
            index.set_media(self.conn, entry_id, entry["media"] + fresh)
            self.version += 1
            return index.get(self.conn, entry_id)  # type: ignore[return-value]

    def dismiss_reminder(self, entry_id: str, line: int) -> None:
        """Stop showing one reminder. Appends; the line it came from stays."""
        with self._lock:
            entry = index.get(self.conn, entry_id)
            if entry is None:
                raise CaptureError(f"no such entry: {entry_id}")
            eventlog.append(eventlog.DISMISS, entry_id, line=line)
            index.dismiss_reminder(self.conn, entry_id, line)
            self.version += 1

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
            raise CaptureError(f"no such folder: {folder_id}")
        current = index.tag_owner(self.conn, tag)
        if current == folder_id or (current is not None and not steal):
            return
        eventlog.append(eventlog.MAP_TAG, folder_id, tag=tag)
        index.map_tag(self.conn, tag, folder_id)

    def create_folder(self, name: str, tags: Iterable[str] = ()) -> dict:
        with self._lock:
            clean = self._checked_name(name)
            existing = index.folders(self.conn)
            colour = colors.next_color([f["color"] for f in existing])

            folder_id = eventlog.new_id()
            event = eventlog.append(
                eventlog.CREATE_FOLDER, folder_id, text=clean, color=colour
            )
            index.add_folder(self.conn, event)

            # A folder answers to its own name. The source arranges the same
            # thing lazily — the first entry filed by `--work` into a folder
            # with no tags upserts `work` as one — but doing it at creation
            # means the rule is "a tag maps to a folder" with no second path,
            # and `--work` needs no special case anywhere downstream.
            self._map_tag(folder_id, clean, steal=False)
            for tag in tags:
                self._map_tag(folder_id, tag, steal=True)

            self.version += 1
            return index.folder(self.conn, folder_id)  # type: ignore[return-value]

    def rename_folder(self, folder_id: str, name: str) -> dict:
        with self._lock:
            before = index.folder(self.conn, folder_id)
            if before is None:
                raise CaptureError(f"no such folder: {folder_id}")
            clean = self._checked_name(name, except_id=folder_id)

            # Nail the old name down before letting go of it. Entries written
            # `--oldname` reach this folder through the tag of that name; if
            # the rename left it unclaimed they would quietly fall out of the
            # folder they were filed into, which no rename should ever do.
            self._map_tag(folder_id, before["name"], steal=False)

            eventlog.append(eventlog.RENAME_FOLDER, folder_id, text=clean)
            index.rename_folder(self.conn, folder_id, clean)
            self._map_tag(folder_id, clean, steal=False)

            self.version += 1
            return index.folder(self.conn, folder_id)  # type: ignore[return-value]

    def set_overview(self, folder_id: str, text: str) -> dict:
        """The folder's standing description. Last write wins, like a rename.

        Empty is a real value: clearing an overview is an edit, not a deletion,
        and the card stays because the folder still has one — it is just blank.
        """
        with self._lock:
            if index.folder(self.conn, folder_id) is None:
                raise CaptureError(f"no such folder: {folder_id}")
            eventlog.append(eventlog.SET_OVERVIEW, folder_id, text=text)
            index.set_overview(self.conn, folder_id, text)
            self.version += 1
            return index.folder(self.conn, folder_id)  # type: ignore[return-value]

    def set_overview_media(self, folder_id: str, ref: str) -> dict:
        """The one picture that stands for the folder.

        Setting this on a folder with no overview yet *creates* one, empty —
        a picture is a statement that the project is worth describing, and the
        card has to exist for the picture to sit in.
        """
        with self._lock:
            if index.folder(self.conn, folder_id) is None:
                raise CaptureError(f"no such folder: {folder_id}")
            eventlog.append(
                eventlog.SET_OVERVIEW_MEDIA, folder_id, media=[ref] if ref else []
            )
            index.set_overview_media(self.conn, folder_id, ref)
            self.version += 1
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
                raise CaptureError(f"no such folder: {folder_id}")
            if folder["state"] == state:
                return folder
            eventlog.append(eventlog.SET_STATE, folder_id, text=state)
            index.set_folder_state(self.conn, folder_id, state)
            self.version += 1
            return index.folder(self.conn, folder_id)  # type: ignore[return-value]

    def delete_folder(self, folder_id: str) -> None:
        """Forget a folder, its tag mappings and its manual filings.

        Nothing written is deleted: the entries stay, their tags stay, and the
        tags land back in the unassigned pool. Deleting a folder is undoing a
        piece of filing, and the log has no way to delete anything else.
        """
        with self._lock:
            if index.folder(self.conn, folder_id) is None:
                raise CaptureError(f"no such folder: {folder_id}")
            eventlog.append(eventlog.DELETE_FOLDER, folder_id)
            index.drop_folder(self.conn, folder_id)
            self.version += 1

    def map_tag(self, folder_id: str, tag: str) -> dict:
        with self._lock:
            self._map_tag(folder_id, tag, steal=True)
            self.version += 1
            return index.folder(self.conn, folder_id)  # type: ignore[return-value]

    def unmap_tag(self, folder_id: str, tag: str) -> dict:
        with self._lock:
            folder = index.folder(self.conn, folder_id)
            if folder is None:
                raise CaptureError(f"no such folder: {folder_id}")
            clean = parser.normalize_tag(tag)
            if clean in folder["tags"]:
                eventlog.append(eventlog.UNMAP_TAG, folder_id, tag=clean)
                index.unmap_tag(self.conn, clean, folder_id)
                self.version += 1
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
                raise CaptureError(f"no such entry: {entry_id}")

            if folder_id is None:
                for current in entry["manual_folders"]:
                    eventlog.append(eventlog.UNASSIGN, entry_id, folder=current)
            else:
                if index.folder(self.conn, folder_id) is None:
                    raise CaptureError(f"no such folder: {folder_id}")
                eventlog.append(eventlog.ASSIGN, entry_id, folder=folder_id)

            index.set_manual_folder(self.conn, entry_id, folder_id)
            self.version += 1
            return index.get(self.conn, entry_id)  # type: ignore[return-value]


store = Store()
