"""The year shelf and the album view — the two derived reads the Log is built
on since it stopped being one flat feed.

The rule under test throughout is the one the shelf exists to make good on:
**an album is a folder seen through one year, and that pairing is stored
nowhere.** Every count, every month volume and every chapter here is
recomputed from the day key on the read, which is why moving a tag's mapping
re-cuts the whole shelf with nothing to migrate — and why deleting the index
cannot change a single number on the screen.
"""
from __future__ import annotations

import json
from datetime import timedelta

from backend.app.timeutil import now

from backend.capture import eventlog, index
from backend.capture.store import CaptureError, Store

from .test_capture_folders import assert_index_is_disposable

import pytest


def write(store, day: str, text: str, media: list[str] | None = None) -> str:
    """One capture, on a day of the test's choosing.

    Written straight into the log rather than through `store.capture()`,
    because the whole point of these reads is what happens across months and
    years and the clock only ever offers today. This is the same shape
    `eventlog.append` writes; the store then replays it like any other line.
    """
    entry_id = eventlog.new_id()
    path = eventlog.log_path_for(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "ts": f"{day}T09:00:00+07:00",
                    "day": day,
                    "kind": "capture",
                    "id": entry_id,
                    "text": text,
                    **({"media": media} if media else {}),
                }
            )
            + "\n"
        )
    return entry_id


# ── The year split ────────────────────────────────────────────────────────


def test_an_album_is_a_folder_seen_through_one_year(capture_store):
    capture_store.create_folder("film", ["film"])
    write(capture_store, "2025-03-02", "started it <film>")
    write(capture_store, "2026-02-04", "picked it up again <film>")
    write(capture_store, "2026-08-15", "colour pass <film>")
    capture_store.reindex()

    shelf = capture_store.shelf("2026")
    album = next(a for a in shelf["albums"] if a["name"] == "film")
    assert album["entry_count"] == 2
    # The folder's own count is all of history, and both are offered: the card
    # is about this year, the sidebar is about the project.
    assert album["all_time_count"] == 3

    assert capture_store.shelf("2025")["albums"][0]["entry_count"] == 1


def test_no_year_means_the_whole_log(capture_store):
    """The yearly restart is a setting, and turning it off must not be a
    different screen — it is the same read with the filter dropped."""
    capture_store.create_folder("film", ["film"])
    write(capture_store, "2025-03-02", "one <film>")
    write(capture_store, "2026-02-04", "two <film>")
    capture_store.reindex()

    assert capture_store.shelf(None)["albums"][0]["entry_count"] == 2


def test_the_year_rail_lists_only_years_with_something_in_them(capture_store):
    write(capture_store, "2024-01-02", "a")
    write(capture_store, "2026-01-02", "b")
    capture_store.reindex()

    assert capture_store.shelf("2026")["years"] == ["2026", "2024"]


def test_the_previous_year_is_the_next_one_down_not_the_one_before(capture_store):
    """`2025` with nothing in it is not a year to hand back to; the foot of the
    shelf offers the next year that exists."""
    capture_store.create_folder("film", ["film"])
    write(capture_store, "2023-05-02", "old <film>")
    write(capture_store, "2026-05-02", "new <film>")
    capture_store.reindex()

    assert capture_store.shelf("2026")["previous"] == {"year": "2023", "entries": 1}


# ── Volumes and chapters ──────────────────────────────────────────────────


def test_the_sparkline_is_twelve_months_january_first(capture_store):
    capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-02-04", "a <film>")
    write(capture_store, "2026-02-11", "b <film>")
    write(capture_store, "2026-08-15", "c <film>")
    capture_store.reindex()

    album = capture_store.shelf("2026")["albums"][0]
    assert album["volumes"] == [0, 2, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0]
    assert album["months"] == "Feb–Aug"


def test_a_folder_nobody_has_cut_has_no_chapters(capture_store):
    """**The whole of the change.** This used to find runs of consecutive
    months and name each from the commonest word inside it. Nothing is
    chaptered now until you say where a chapter begins."""
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-02-04", "first idea <film>")
    write(capture_store, "2026-06-04", "shooting <film>")
    capture_store.reindex()

    assert capture_store.album(index.InFolder(film["id"]), "2026")["chapters"] == []


def test_a_cut_runs_until_the_next_one(capture_store):
    film = capture_store.create_folder("film", ["film"])
    for day in ("2026-02-04", "2026-06-04", "2026-07-04", "2026-11-02"):
        write(capture_store, day, "<film>")
    capture_store.reindex()
    capture_store.split_chapter(film["id"], "2026-02", "Reading around it")
    capture_store.split_chapter(film["id"], "2026-06", "The shoot")

    chapters = capture_store.album(index.InFolder(film["id"]), "2026")["chapters"]
    # Newest first, as everything in this app reads.
    assert [c["name"] for c in chapters] == ["The shoot", "Reading around it"]
    assert [c["range"] for c in chapters] == ["Jun–Dec", "Feb–May"]
    # The last cut runs to the end of the year, so November is in it.
    assert chapters[0]["entries"] == 3
    assert chapters[1]["entries"] == 1


def test_a_cut_needs_no_entries_in_the_month_it_names(capture_store):
    """You cut where something began, which is not always a day you wrote on.
    The old reading could not express that at all: a run was made *of* months
    with entries in them."""
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-05-20", "<film>")
    capture_store.reindex()
    capture_store.split_chapter(film["id"], "2026-03", "From the top")

    chapter = capture_store.album(index.InFolder(film["id"]), "2026")["chapters"][0]
    assert (chapter["first_month"], chapter["last_month"]) == (3, 12)
    assert chapter["entries"] == 1


# ── The unfiled pile ──────────────────────────────────────────────────────


def test_unfiled_is_everything_no_folder_has_claimed(capture_store):
    """A tag nothing points at leaves its entry unfiled — that pile is the
    dashed card, and it is an album you can open like any other."""
    capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "in the album <film>")
    write(capture_store, "2026-03-03", "loose <sketch>")
    write(capture_store, "2026-03-04", "no tags at all")
    capture_store.reindex()

    assert capture_store.shelf("2026")["unfiled"] == 2
    assert len(capture_store.album(index.UNFILED, "2026")["entries"]) == 2


def test_mapping_a_tag_moves_it_out_of_unfiled_with_nothing_to_migrate(capture_store):
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-03", "loose <sketch>")
    capture_store.reindex()
    assert capture_store.shelf("2026")["unfiled"] == 1

    capture_store.map_tag(folder["id"], "sketch")
    assert capture_store.shelf("2026")["unfiled"] == 0
    assert capture_store.shelf("2026")["albums"][0]["entry_count"] == 1


# ── What the cards say ────────────────────────────────────────────────────


def test_the_overview_counts_promises_made_in_here_and_kept(capture_store):
    """The folder's own tally, and it is the album's — this folder through the
    year on screen, like every other figure on that card. A todo written into
    it last year belongs to last year's overview."""
    film = capture_store.create_folder("film", ["film"])
    first = write(capture_store, "2026-03-02", "--todo book the studio <film>")
    write(capture_store, "2026-03-09", "--todo call back <film>")
    write(capture_store, "2025-11-02", "--todo last year's <film>")
    capture_store.reindex()
    capture_store.toggle_line(first, 0)

    assert capture_store.album(index.InFolder(film["id"]), "2026")["todos"] == {"made": 2, "done": 1}
    assert capture_store.album(index.InFolder(film["id"]), "2025")["todos"] == {"made": 1, "done": 0}


def test_the_unfiled_pile_has_a_tally_like_any_other_album(capture_store):
    """A todo nobody tagged is still a promise, and the pile is a real album.
    Filing the tag it carries moves the tally with it, with nothing to
    migrate."""
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-03", "--todo loose one <sketch>")
    capture_store.reindex()

    assert capture_store.album(index.UNFILED, "2026")["todos"] == {"made": 1, "done": 0}
    assert capture_store.album(index.InFolder(folder["id"]), "2026")["todos"] == {"made": 0, "done": 0}

    capture_store.map_tag(folder["id"], "sketch")
    assert capture_store.album(index.UNFILED, "2026")["todos"] == {"made": 0, "done": 0}
    assert capture_store.album(index.InFolder(folder["id"]), "2026")["todos"] == {"made": 1, "done": 0}


def test_the_card_counts_media_and_leads_with_the_newest(capture_store, tmp_path):
    capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "old shot <film>", ["a/one.jpg"])
    write(capture_store, "2026-03-09", "new shot <film>", ["a/two.jpg", "a/three.jpg"])
    capture_store.reindex()

    album = capture_store.shelf("2026")["albums"][0]
    assert album["media_count"] == 3
    assert album["lead"][0] == "a/two.jpg"


def test_the_card_carries_the_folder_s_todo_tally_for_the_year(capture_store):
    """The same pair the overview shows, on the shelf, cut to the year like
    every other figure on the card."""
    capture_store.create_folder("film", ["film"])
    first = write(capture_store, "2026-03-02", "--todo book the studio <film>")
    write(capture_store, "2026-03-09", "--todo call back <film>")
    write(capture_store, "2025-11-02", "--todo last year's <film>")
    capture_store.reindex()
    capture_store.toggle_line(first, 0)

    card = capture_store.shelf("2026")["albums"][0]
    assert card["todos"] == {"made": 2, "done": 1}
    assert capture_store.shelf("2025")["albums"][0]["todos"] == {"made": 1, "done": 0}


def test_a_shelf_card_and_the_album_agree_about_the_tally(capture_store):
    """Two reads of one fold. They are counted from the same rows by the same
    function precisely so they cannot drift — the card is what you decide to
    open the album from."""
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "--todo one <film>\n--todo two <film>")
    write(capture_store, "2026-04-02", "no promises here <film>")
    capture_store.reindex()

    card = capture_store.shelf("2026")["albums"][0]
    assert card["todos"] == capture_store.album(index.InFolder(folder["id"]), "2026")["todos"]


def test_an_album_with_nothing_this_year_is_not_on_the_shelf(capture_store):
    """A year you did not touch a project is not one of its albums. An active
    folder stays, because a project just started has nothing in it yet and is
    still the thing you are doing."""
    capture_store.create_folder("old", ["old"])
    started = capture_store.create_folder("new", ["new"])
    capture_store.set_folder_state(started["id"], "active")
    write(capture_store, "2025-03-02", "last year <old>")
    capture_store.reindex()

    names = [a["name"] for a in capture_store.shelf("2026")["albums"]]
    assert names == ["new"]


def test_an_empty_folder_stays_on_the_shelf_whatever_its_state(capture_store):
    """The bug this is here for: a folder with nothing in it yet was kept on
    the shelf only while it was marked `active`, so marking one `open` or
    `shipped` made it disappear from every year at once. Nothing was deleted
    and nothing could be — but a folder you cannot see is a folder you have
    lost, and three of them were."""
    for state in ("", "active", "shipped"):
        folder = capture_store.create_folder(f"empty {state or 'open'}", [])
        if state:
            capture_store.set_folder_state(folder["id"], state)

    names = {a["name"] for a in capture_store.shelf("2026")["albums"]}
    assert names == {"empty open", "empty active", "empty shipped"}


def test_a_folder_with_a_history_still_drops_out_of_a_year_it_missed(capture_store):
    """The rule that was always right, and is untouched: an album is a folder
    seen through one year, and a year you did not touch it is not one of its
    years. Only *never used at all* is the exception."""
    capture_store.create_folder("film", ["film"])
    write(capture_store, "2025-03-02", "shot something <film>")
    capture_store.reindex()

    assert [a["name"] for a in capture_store.shelf("2025")["albums"]] == ["film"]
    assert capture_store.shelf("2026")["albums"] == []


def test_albums_come_back_busiest_first(capture_store):
    capture_store.create_folder("quiet", ["quiet"])
    capture_store.create_folder("busy", ["busy"])
    write(capture_store, "2026-03-02", "a <quiet>")
    write(capture_store, "2026-03-02", "b <busy>")
    write(capture_store, "2026-03-03", "c <busy>")
    capture_store.reindex()

    assert [a["name"] for a in capture_store.shelf("2026")["albums"]] == ["busy", "quiet"]


# ── Where the newest line is ──────────────────────────────────────────────


def test_latest_is_the_newest_album_not_the_biggest(capture_store):
    """`Opens on: latest day` reads `shelf["latest"]`, and this is why it
    cannot read `albums[0]` instead: that list is sorted busiest-first, which is
    the right order to read the shelf in and the wrong answer to "where was I".
    A big old project would win it every time."""
    capture_store.create_folder("busy", ["busy"])
    capture_store.create_folder("quiet", ["quiet"])
    write(capture_store, "2026-03-02", "a <busy>")
    write(capture_store, "2026-03-03", "b <busy>")
    write(capture_store, "2026-06-01", "c <quiet>")
    capture_store.reindex()

    shelf = capture_store.shelf("2026")
    assert [a["name"] for a in shelf["albums"]] == ["busy", "quiet"]

    quiet = next(a for a in shelf["albums"] if a["name"] == "quiet")
    assert shelf["latest"]["folder"] == quiet["id"]
    assert shelf["latest"]["day"] == "2026-06-01"


def test_latest_points_at_the_unfiled_pile_when_that_is_newest(capture_store):
    """Someone who has never made a folder has an empty `albums` list, which is
    what made this setting do nothing at all rather than something imperfect.
    Unfiled is a destination."""
    write(capture_store, "2026-03-02", "no tags at all")
    write(capture_store, "2026-03-03", "still nothing")
    capture_store.reindex()

    shelf = capture_store.shelf("2026")
    assert shelf["albums"] == []
    assert shelf["unfiled"] == 2
    assert shelf["latest"] == {
        "folder": None,
        "day": "2026-03-03",
        "ts": shelf["latest"]["ts"],
    }


def test_latest_is_none_for_a_year_with_nothing_in_it(capture_store):
    write(capture_store, "2025-03-02", "last year")
    capture_store.reindex()

    assert capture_store.shelf("2026")["latest"] is None


# ── Still disposable ──────────────────────────────────────────────────────


def test_the_shelf_survives_the_index_being_deleted(capture_store):
    """Nothing on this screen is stored, so a rebuild has to reproduce it
    exactly — the same promise the rest of the index makes."""
    from backend.capture.config import INDEX_PATH
    from backend.capture.store import Store

    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-02-04", "a <film> \\win")
    write(capture_store, "2026-08-15", "b <film>")
    capture_store.reindex()
    before = capture_store.shelf("2026")

    fresh = Store(INDEX_PATH.with_name("index-replay.sqlite"))
    fresh.start()
    try:
        assert fresh.shelf("2026") == before
        assert fresh.album(index.InFolder(film["id"]), "2026") == capture_store.album(index.InFolder(film["id"]), "2026")
    finally:
        fresh.close()


def test_an_album_for_a_folder_that_does_not_exist_is_refused(capture_store):
    from backend.capture.store import CaptureError

    with pytest.raises(CaptureError):
        capture_store.album(index.InFolder("nope"), "2026")


# ── Cutting a chapter ─────────────────────────────────────────────────────
#
# A chapter begins where you cut it and runs until the next cut. The cut is the
# chapter's identity — which is what the derived version never had, and why the
# event it replaces could only anchor a name to a month and hope. Cutting and
# naming are one event, so a rename is a re-cut and applying the same line
# twice is the same chapter.


def test_cutting_again_at_the_same_month_is_the_rename(capture_store):
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "in the darkroom <film>")
    capture_store.reindex()

    capture_store.split_chapter(film["id"], "2026-03", "The long spring")
    assert capture_store.album(index.InFolder(film["id"]), "2026")["chapters"][0]["name"] == "The long spring"

    capture_store.split_chapter(film["id"], "2026-03", "The long wet spring")
    chapters = capture_store.album(index.InFolder(film["id"]), "2026")["chapters"]
    assert len(chapters) == 1
    assert chapters[0]["name"] == "The long wet spring"


def test_a_cut_with_no_name_is_a_chapter_and_not_a_deletion(capture_store):
    """The state the old event could not hold: you know where something began
    before you know what to call it."""
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "<film>")
    capture_store.reindex()
    capture_store.split_chapter(film["id"], "2026-03", "")

    chapters = capture_store.album(index.InFolder(film["id"]), "2026")["chapters"]
    assert len(chapters) == 1
    assert chapters[0]["name"] == ""
    # The range is what the screens draw in place of a name. Nothing invents
    # a word for it.
    assert chapters[0]["range"] == "Mar–Dec"


def test_a_cut_can_be_taken_back_and_the_writing_stays(capture_store):
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "<film>")
    write(capture_store, "2026-07-02", "<film>")
    capture_store.reindex()
    capture_store.split_chapter(film["id"], "2026-03", "Early")
    capture_store.split_chapter(film["id"], "2026-07", "Late")

    album = capture_store.unsplit_chapter(film["id"], "2026-07")
    assert [c["name"] for c in album["chapters"]] == ["Early"]
    # A chapter is a heading over the log, never a container of it.
    assert len(album["entries"]) == 2
    assert album["chapters"][0]["entries"] == 2


def test_a_cut_before_the_year_opens_it(capture_store):
    """The cuts are a timeline and a year is a window onto it, so the chapter
    you were in in November is the chapter January is in — clipped to the year
    you are looking at, because that is the part this album holds."""
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2025-11-04", "<film>")
    write(capture_store, "2026-01-08", "<film>")
    capture_store.reindex()
    capture_store.split_chapter(film["id"], "2025-11", "Winter work")

    chapters = capture_store.album(index.InFolder(film["id"]), "2026")["chapters"]
    assert len(chapters) == 1
    assert chapters[0]["name"] == "Winter work"
    # Clipped, but the cut it carries is the real one — that is what
    # `?chapter=` names and it is not in this year.
    assert (chapters[0]["first_month"], chapters[0]["last_month"]) == (1, 12)
    assert chapters[0]["month"] == "2025-11"
    assert chapters[0]["entries"] == 1


def test_entries_before_the_first_cut_belong_to_no_chapter(capture_store):
    """Counted and said out loud rather than swept into an opening chapter
    nobody asked for."""
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-01-04", "<film>")
    write(capture_store, "2026-02-04", "<film>")
    write(capture_store, "2026-06-04", "<film>")
    capture_store.reindex()
    capture_store.split_chapter(film["id"], "2026-06", "The shoot")

    album = capture_store.album(index.InFolder(film["id"]), "2026")
    assert album["uncut"] == 2
    assert album["chapters"][0]["entries"] == 1


def test_the_unfiled_pile_can_be_cut_too(capture_store):
    """It is an album you can open like any other, so it is one you can cut a
    chapter in. It is also the one subject here that is not a folder id."""
    write(capture_store, "2026-03-02", "loose thought")
    capture_store.reindex()
    capture_store.split_chapter(None, "2026-03", "Odds and ends")

    assert capture_store.album(index.UNFILED, "2026")["chapters"][0]["name"] == "Odds and ends"


def test_a_cut_survives_the_index_being_deleted(capture_store):
    """Derived like everything else: the cut is in the log and nowhere else."""
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "<film>")
    capture_store.reindex()
    capture_store.split_chapter(film["id"], "2026-03", "The long spring")

    fresh = Store()
    fresh.start()
    try:
        assert fresh.album(index.InFolder(film["id"]), "2026")["chapters"][0]["name"] == "The long spring"
    finally:
        fresh.close()


def test_a_deleted_folder_takes_its_cuts_with_it(capture_store):
    """The same cascade the groups and the tag mappings get. A cut left behind
    would attach itself to the next folder to be given that id, which is not a
    thing that can happen — but a fold that relies on that is a fold with a
    reason to be re-read later."""
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "<film>")
    capture_store.reindex()
    capture_store.split_chapter(film["id"], "2026-03", "The long spring")
    capture_store.delete_folder(film["id"])

    # Asserted on both sides of a rebuild rather than by reaching into the
    # replay: the write and the replay are one function now (`index.apply`),
    # and the thing worth pinning is that they leave the same table behind.
    assert index.chapter_splits(capture_store.conn, index.InFolder(film["id"])) == []
    capture_store.reindex()
    assert index.chapter_splits(capture_store.conn, index.InFolder(film["id"])) == []


def test_a_cut_is_refused_a_month_that_is_not_one(capture_store):
    film = capture_store.create_folder("film", ["film"])
    for bad in ("2026-13", "2026", "26-03", "2026-3"):
        with pytest.raises(CaptureError):
            capture_store.split_chapter(film["id"], bad, "Nope")
    with pytest.raises(CaptureError):
        capture_store.unsplit_chapter(film["id"], "2026-00")


def test_the_shelf_counts_the_same_chapters_the_album_does(capture_store):
    """Two readings of one number is how a card and a screen come to disagree
    about how many chapters a project has."""
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-02-04", "<film>")
    write(capture_store, "2026-06-04", "<film>")
    capture_store.reindex()
    capture_store.split_chapter(film["id"], "2026-02", "One")
    capture_store.split_chapter(film["id"], "2026-06", "Two")

    card = capture_store.shelf("2026")["albums"][0]
    assert card["chapters"] == len(capture_store.album(index.InFolder(film["id"]), "2026")["chapters"]) == 2


# ── Points, the heatmap, and the order they put the shelf in ──────────────
#
# A day is worth one point per entry and one per twenty minutes clocked. Both
# halves are folds over rows and neither is stored, which is the same contract
# `entry_count` and `folder_seconds` hold — the tests below are mostly about
# keeping the *two* readings of that number in agreement: what the heatmap
# draws for a day, and what the shelf sorts a month of them by.


def clock(store, folder_id: str, day: str, seconds: int) -> None:
    """A session attributed to a named day, straight into the log.

    The `day` is forced and the `ts` is pushed a second ahead, which is the
    opposite of what `write` above does and is deliberate on both counts.

    `ts` is replay order, and `apply` drops a session whose folder does not
    exist yet — deliberately, see the branch. Every folder in these tests is
    created by the store a fraction of a second earlier, so a session stamped
    on its own past day sorts *before* the folder it names and vanishes on the
    next rebuild; stamped in the same second, the tie falls to file order and
    the 2025 log is read before the 2026 one, which loses it just the same. A
    real log never has either shape, because a folder is always minutes or
    hours older than the first session logged into it. The second is what
    buys that back. Every read here is keyed on `day`, which is why forcing
    only that puts the session where the test wants it.
    """
    event = eventlog.append(
        eventlog.LOG_TIME,
        eventlog.new_id(),
        folder=folder_id,
        seconds=seconds,
        day=day,
        ts=(now() + timedelta(seconds=1)).isoformat(timespec="seconds"),
    )
    with store.conn:
        index.apply(store.conn, event)


def heat_on(store, folder_id: str, year: str | None, day: str) -> dict | None:
    return next(
        (d for d in index.heat(store.conn, year, index.InFolder(folder_id)) if d["day"] == day),
        None,
    )


def test_an_entry_of_any_length_is_worth_one_point(capture_store):
    """Length is not measured anywhere in this app and is not measured here.
    A word and a paragraph are the same day's work as far as the grid knows."""
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "ok <film>")
    write(capture_store, "2026-03-02", "a much longer line about the thing <film>")
    capture_store.reindex()

    assert heat_on(capture_store, folder["id"], "2026", "2026-03-02")["points"] == 2


def test_twenty_minutes_is_worth_one_point_and_nineteen_is_worth_none(capture_store):
    """Truncating division, on purpose. "Every twenty minutes" means the ones
    that completed — rounding nineteen up would be the grid inventing work."""
    folder = capture_store.create_folder("film", ["film"])
    clock(capture_store, folder["id"], "2026-03-02", 19 * 60)
    clock(capture_store, folder["id"], "2026-03-03", 20 * 60)
    clock(capture_store, folder["id"], "2026-03-04", 59 * 60)

    assert heat_on(capture_store, folder["id"], "2026", "2026-03-02")["points"] == 0
    assert heat_on(capture_store, folder["id"], "2026", "2026-03-03")["points"] == 1
    assert heat_on(capture_store, folder["id"], "2026", "2026-03-04")["points"] == 2


def test_a_day_that_was_only_worked_is_still_a_day(capture_store):
    """Nineteen minutes scores nothing and is still reported. The cell draws as
    ground, and pressing it says what actually happened — a fold that dropped
    the row would make the readout disagree with the log."""
    folder = capture_store.create_folder("film", ["film"])
    clock(capture_store, folder["id"], "2026-03-02", 5 * 60)

    day = heat_on(capture_store, folder["id"], "2026", "2026-03-02")
    assert day == {"day": "2026-03-02", "entries": 0, "seconds": 300, "points": 0}


def test_the_two_halves_add_up(capture_store):
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "a <film>")
    write(capture_store, "2026-03-02", "b <film>")
    clock(capture_store, folder["id"], "2026-03-02", 65 * 60)
    capture_store.reindex()

    day = heat_on(capture_store, folder["id"], "2026", "2026-03-02")
    assert day["entries"] == 2 and day["seconds"] == 3900
    assert day["points"] == 5  # two written, three twenty-minute stretches


def test_the_heatmap_only_carries_days_with_something_on_them(capture_store):
    """A year is 365 cells and the client lays out a calendar for itself."""
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "a <film>")
    capture_store.reindex()

    assert [d["day"] for d in index.heat(capture_store.conn, "2026", index.InFolder(folder["id"]))] == [
        "2026-03-02"
    ]


def test_the_heatmap_is_cut_by_year_like_every_other_album_figure(capture_store):
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2025-03-02", "a <film>")
    write(capture_store, "2026-03-02", "b <film>")
    clock(capture_store, folder["id"], "2025-06-01", 3600)
    capture_store.reindex()

    assert [d["day"] for d in index.heat(capture_store.conn, "2026", index.InFolder(folder["id"]))] == [
        "2026-03-02"
    ]
    assert [d["day"] for d in index.heat(capture_store.conn, "2025", index.InFolder(folder["id"]))] == [
        "2025-03-02",
        "2025-06-01",
    ]


def test_the_heatmap_reaches_a_folder_every_way_an_entry_can(capture_store):
    """Membership is resolved, and the grid asks the same view everything else
    asks. A line filed by hand counts exactly like a tagged one."""
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "tagged <film>")
    loose = write(capture_store, "2026-03-02", "filed by hand")
    write(capture_store, "2026-03-02", "--film by directive")
    capture_store.reindex()
    capture_store.assign_entry(loose, folder["id"])

    assert heat_on(capture_store, folder["id"], "2026", "2026-03-02")["entries"] == 3


def test_the_unfiled_pile_has_days_but_no_clock(capture_store):
    """It used to have no grid at all, and the reason was where the grid was
    *drawn*: inside a folder's overview, which the pile has not got.

    The grid moved to the Map lens, where `unfiled` is a filter you can select
    like any other, so an empty answer would now be a lie about days that
    happened. What stays true is the clock: `log-time` names a folder and this
    is the absence of one, so there is no gesture that could produce an unfiled
    session.
    """
    write(capture_store, "2026-03-02", "loose")
    capture_store.reindex()

    days = index.heat(capture_store.conn, "2026", index.UNFILED)
    assert [d["day"] for d in days] == ["2026-03-02"]
    assert days[0]["entries"] == 1
    assert days[0]["seconds"] == 0


def test_heat_across_everything_is_the_folders_plus_the_pile(capture_store):
    """The Map lens asks for the year with no folder chosen, and that has to
    be every entry rather than the union of the ones that found a home."""
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "tagged <film>")
    write(capture_store, "2026-03-02", "loose")
    write(capture_store, "2026-03-05", "also loose")
    capture_store.reindex()

    everything = {d["day"]: d["entries"] for d in index.heat(capture_store.conn, "2026")}
    filed = {d["day"]: d["entries"] for d in index.heat(capture_store.conn, "2026", index.InFolder(folder["id"]))}
    pile = {d["day"]: d["entries"] for d in index.heat(capture_store.conn, "2026", index.UNFILED)}

    assert everything == {"2026-03-02": 2, "2026-03-05": 1}
    assert filed == {"2026-03-02": 1}
    assert pile == {"2026-03-02": 1, "2026-03-05": 1}
    # The whole is the parts, which is the property that makes the filter
    # chips add up to the `all` they sit beside.
    for day, n in everything.items():
        assert n == filed.get(day, 0) + pile.get(day, 0)


def test_heat_everything_is_cut_by_the_year(capture_store):
    write(capture_store, "2026-03-02", "this year")
    write(capture_store, "2025-11-04", "last year")
    capture_store.reindex()

    assert [d["day"] for d in index.heat(capture_store.conn, "2026")] == ["2026-03-02"]
    assert [d["day"] for d in index.heat(capture_store.conn, "2025")] == ["2025-11-04"]
    assert len(index.heat(capture_store.conn, None)) == 2


def test_the_album_no_longer_carries_a_year_of_days(capture_store):
    """The year is Map's question, asked through `/heat` with a scope.

    It used to ride on the album payload as well, which meant two queries on
    every folder change to answer something the reading lens does not draw.
    The fold is unchanged and still reachable at this scope — that is what the
    second half asserts — so what went is the duplication, not the reading.
    """
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "a <film>")
    capture_store.reindex()

    assert "heat" not in capture_store.album(index.InFolder(folder["id"]), "2026")
    assert capture_store.heat("2026", index.InFolder(folder["id"])) == [
        {"day": "2026-03-02", "entries": 1, "seconds": 0, "points": 1}
    ]


def test_the_heatmap_survives_the_index_being_deleted(capture_store):
    """Points are a fold over the log like everything else here."""
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "a <film>")
    clock(capture_store, folder["id"], "2026-03-02", 3600)
    capture_store.reindex()

    before = index.heat(capture_store.conn, "2026", index.InFolder(folder["id"]))
    assert_index_is_disposable(capture_store)
    assert index.heat(capture_store.conn, "2026", index.InFolder(folder["id"])) == before


# ── The order of the shelf ────────────────────────────────────────────────


def test_the_shelf_is_ordered_by_the_last_month_not_by_size(capture_store):
    """The whole point of the change: a big finished project does not sit at
    the front of the shelf all year above the one you opened this morning."""
    capture_store.create_folder("old", ["old"])
    capture_store.create_folder("live", ["live"])
    for day in range(1, 21):
        write(capture_store, f"2026-02-{day:02d}", "a <old>")
    write(capture_store, "2026-09-06", "b <live>")
    capture_store.reindex()

    shelf = index.shelf(capture_store.conn, "2026", "2026-09-08")
    assert [a["name"] for a in shelf["albums"]] == ["live", "old"]
    # And the same shelf read as history puts them back in size order.
    assert [a["name"] for a in index.shelf(capture_store.conn, "2026")["albums"]] == [
        "old",
        "live",
    ]


def test_time_counts_toward_the_order_the_way_writing_does(capture_store):
    """Twenty minutes is an entry, here as everywhere. An hour at the desk
    outranks two lines typed."""
    written = capture_store.create_folder("written", ["written"])
    worked = capture_store.create_folder("worked", ["worked"])
    write(capture_store, "2026-09-06", "a <written>")
    write(capture_store, "2026-09-06", "b <written>")
    clock(capture_store, worked["id"], "2026-09-06", 60 * 60)
    capture_store.reindex()

    shelf = index.shelf(capture_store.conn, "2026", "2026-09-08")
    assert [a["name"] for a in shelf["albums"]] == ["worked", "written"]
    assert [a["momentum"] for a in shelf["albums"]] == [3, 2]


def test_the_month_is_a_rolling_thirty_days(capture_store):
    """Inclusive of today and of the day thirty back; nothing older counts."""
    inside = capture_store.create_folder("inside", ["inside"])
    outside = capture_store.create_folder("outside", ["outside"])
    write(capture_store, "2026-08-10", "just inside <inside>")
    write(capture_store, "2026-08-09", "just outside <outside>")
    write(capture_store, "2026-08-09", "and again <outside>")
    capture_store.reindex()

    shelf = index.shelf(capture_store.conn, "2026", "2026-09-08")
    warm = {a["name"]: a["momentum"] for a in shelf["albums"]}
    assert warm == {"inside": 1, "outside": 0}


def test_the_month_crosses_new_year(capture_store):
    """A rolling month is a fact about the work, not about the calendar. Asked
    on the 3rd of January what you have been doing lately, a shelf that
    answered "nothing, the year is new" would be answering a different
    question — and the project you were deep in over Christmas would spend its
    first fortnight of January at the bottom of the shelf.

    Both albums here have exactly one line in 2026, which is what puts them on
    this shelf at all; what separates them is December."""
    capture_store.create_folder("december", ["december"])
    capture_store.create_folder("neither", ["neither"])
    write(capture_store, "2025-12-28", "a <december>")
    write(capture_store, "2025-12-29", "b <december>")
    write(capture_store, "2026-01-02", "c <december>")
    write(capture_store, "2026-01-02", "d <neither>")
    capture_store.reindex()

    shelf = index.shelf(capture_store.conn, "2026", "2026-01-03")
    assert [a["name"] for a in shelf["albums"]] == ["december", "neither"]
    assert [a["momentum"] for a in shelf["albums"]] == [3, 1]
    # The album's own figures stay cut to the year, as they always were.
    assert [a["entry_count"] for a in shelf["albums"]] == [1, 1]


def test_a_past_year_reads_the_way_it_always_did(capture_store):
    """Momentum is about now, so a shelf of 2025 has none of it and falls all
    the way through to the old order — busiest first, then by name."""
    capture_store.create_folder("quiet", ["quiet"])
    capture_store.create_folder("busy", ["busy"])
    write(capture_store, "2025-03-02", "a <quiet>")
    write(capture_store, "2025-03-02", "b <busy>")
    write(capture_store, "2025-03-03", "c <busy>")
    capture_store.reindex()

    shelf = index.shelf(capture_store.conn, "2025", "2026-09-08")
    assert [a["name"] for a in shelf["albums"]] == ["busy", "quiet"]
    assert [a["momentum"] for a in shelf["albums"]] == [0, 0]


def test_the_order_ties_break_on_size_then_on_name(capture_store):
    """A reload must never reorder a list you are reading."""
    for name in ("cedar", "alder", "birch"):
        capture_store.create_folder(name, [name])
    write(capture_store, "2026-09-06", "a <cedar>")
    write(capture_store, "2026-09-06", "a <alder>")
    write(capture_store, "2026-09-06", "a <birch>")
    write(capture_store, "2026-01-10", "older <birch>")
    capture_store.reindex()

    shelf = index.shelf(capture_store.conn, "2026", "2026-09-08")
    assert [a["name"] for a in shelf["albums"]] == ["birch", "alder", "cedar"]


def test_momentum_agrees_with_the_days_the_heatmap_draws(capture_store):
    """The one pinning that matters: the shelf's sort key is a sum of exactly
    the numbers the grid shows, so the order can always be explained by
    pointing at the cells. Two implementations, one answer — the same
    arrangement `todo_tally` and the shelf's todo count are held to."""
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-09-01", "a <film>")
    write(capture_store, "2026-09-01", "b <film>")
    write(capture_store, "2026-09-04", "c <film>")
    clock(capture_store, folder["id"], "2026-09-01", 45 * 60)
    clock(capture_store, folder["id"], "2026-09-07", 3 * 3600)
    # Older than the window, so the grid has it and the sort key must not.
    write(capture_store, "2026-01-05", "ancient <film>")
    capture_store.reindex()

    since, until = index.momentum_window("2026-09-08")
    drawn = sum(
        d["points"]
        for d in index.heat(capture_store.conn, "2026", index.InFolder(folder["id"]))
        if since <= d["day"] <= until
    )
    assert index.momentum(capture_store.conn, since, until)[folder["id"]] == drawn
    assert drawn == 3 + 2 + 9


def test_the_cap_is_the_ramps_and_not_the_counts(capture_store):
    """"Max at 10 points" is a property of the light. A day past it keeps
    counting, here and in the order — clipping the number as well as the
    brightness would make the readout disagree with the sort."""
    folder = capture_store.create_folder("film", ["film"])
    for _ in range(14):
        write(capture_store, "2026-09-06", "a <film>")
    capture_store.reindex()

    assert heat_on(capture_store, folder["id"], "2026", "2026-09-06")["points"] == 14
    shelf = index.shelf(capture_store.conn, "2026", "2026-09-08")
    assert shelf["albums"][0]["momentum"] == 14
