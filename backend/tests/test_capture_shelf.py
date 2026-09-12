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


def test_chapters_are_contiguous_month_runs_newest_first(capture_store):
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-02-04", "first idea <film>")
    write(capture_store, "2026-06-04", "shooting <film>")
    write(capture_store, "2026-07-04", "still shooting <film>")
    capture_store.reindex()

    album = capture_store.album(film["id"], "2026")
    assert [c["range"] for c in album["chapters"]] == ["Jun–Jul", "Feb"]
    assert album["chapters"][0]["entries"] == 2


def test_a_chapter_is_named_from_the_users_own_words(capture_store):
    """Never invented: the commonest pattern or tag inside the run, minus the
    tags that only say which album this is."""
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-06-04", "day one <film> \\the-shoot")
    write(capture_store, "2026-06-05", "day two <film> \\the-shoot")
    write(capture_store, "2026-06-06", "one bad take <film> \\stuck")
    capture_store.reindex()

    assert capture_store.album(film["id"], "2026")["chapters"][0]["name"] == "The shoot"


def test_a_chapter_with_nothing_to_call_it_is_named_by_its_months(capture_store):
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-06-04", "plain line <film>")
    capture_store.reindex()

    assert capture_store.album(film["id"], "2026")["chapters"][0]["name"] == "Jun"


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
    assert len(capture_store.album(None, "2026")["entries"]) == 2


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

    assert capture_store.album(film["id"], "2026")["todos"] == {"made": 2, "done": 1}
    assert capture_store.album(film["id"], "2025")["todos"] == {"made": 1, "done": 0}


def test_the_unfiled_pile_has_a_tally_like_any_other_album(capture_store):
    """A todo nobody tagged is still a promise, and the pile is a real album.
    Filing the tag it carries moves the tally with it, with nothing to
    migrate."""
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-03", "--todo loose one <sketch>")
    capture_store.reindex()

    assert capture_store.album(None, "2026")["todos"] == {"made": 1, "done": 0}
    assert capture_store.album(folder["id"], "2026")["todos"] == {"made": 0, "done": 0}

    capture_store.map_tag(folder["id"], "sketch")
    assert capture_store.album(None, "2026")["todos"] == {"made": 0, "done": 0}
    assert capture_store.album(folder["id"], "2026")["todos"] == {"made": 1, "done": 0}


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
    assert card["todos"] == capture_store.album(folder["id"], "2026")["todos"]


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
        assert fresh.album(film["id"], "2026") == capture_store.album(film["id"], "2026")
    finally:
        fresh.close()


def test_an_album_for_a_folder_that_does_not_exist_is_refused(capture_store):
    from backend.capture.store import CaptureError

    with pytest.raises(CaptureError):
        capture_store.album("nope", "2026")


# ── Naming a chapter ──────────────────────────────────────────────────────
#
# A chapter is a run of months named from the commonest word written inside it.
# That is right often enough to be worth doing and wrong often enough to need
# overruling, so it can be named by hand — and since the run itself is derived,
# the name is anchored to a month instead. What the anchor has to survive is
# every way a run can change, which is fewer ways than it looks: entries are
# only ever appended, so a run can extend or merge but can never split.


def test_a_chapter_can_be_named_and_handed_back(capture_store):
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "in the darkroom <film> \\win")
    capture_store.reindex()

    assert capture_store.album(film["id"], "2026")["chapters"][0]["name"] == "Win"

    capture_store.name_chapter(film["id"], "2026", 3, "The long spring")
    chapter = capture_store.album(film["id"], "2026")["chapters"][0]
    assert chapter["name"] == "The long spring"
    # The reader's answer is still offered, so the panel can hand it back
    # without asking the server what it would have said.
    assert chapter["derived"] == "Win"
    assert chapter["named"] is True

    capture_store.name_chapter(film["id"], "2026", 3, "")
    assert capture_store.album(film["id"], "2026")["chapters"][0]["name"] == "Win"


def test_a_name_holds_when_the_run_grows_around_it(capture_store):
    """The anchor is a month, and a month never loses its entries. Writing in
    the months either side extends the run; the name it was given stays on the
    chapter that has grown."""
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-05-02", "<film>")
    capture_store.reindex()
    capture_store.name_chapter(film["id"], "2026", 5, "The long spring")

    write(capture_store, "2026-04-02", "<film>")
    write(capture_store, "2026-06-02", "<film>")
    capture_store.reindex()

    chapters = capture_store.album(film["id"], "2026")["chapters"]
    assert len(chapters) == 1
    assert chapters[0]["name"] == "The long spring"
    assert (chapters[0]["first_month"], chapters[0]["last_month"]) == (4, 6)


def test_two_named_runs_that_merge_keep_the_earlier_name(capture_store):
    """Both names are in the log and neither is lost; the chapter takes the one
    it began with. The rule matters because the alternative is a coin toss that
    a replay could land differently."""
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-02-02", "<film>")
    write(capture_store, "2026-04-02", "<film>")
    capture_store.reindex()
    capture_store.name_chapter(film["id"], "2026", 2, "Before")
    capture_store.name_chapter(film["id"], "2026", 4, "After")
    assert [c["name"] for c in capture_store.album(film["id"], "2026")["chapters"]] == [
        "After",
        "Before",
    ]

    write(capture_store, "2026-03-02", "<film>")
    capture_store.reindex()
    chapters = capture_store.album(film["id"], "2026")["chapters"]
    assert [c["name"] for c in chapters] == ["Before"]


def test_naming_anchors_to_the_run_s_first_month(capture_store):
    """So a rename cannot be shadowed. The chapter above keeps `Before` because
    that is where it began — and renaming it now writes to the first month of
    the run as it stands, which is the earliest anchor there is."""
    film = capture_store.create_folder("film", ["film"])
    for day in ("2026-02-02", "2026-03-02", "2026-04-02"):
        write(capture_store, day, "<film>")
    capture_store.reindex()
    capture_store.name_chapter(film["id"], "2026", 4, "Late")
    assert capture_store.album(film["id"], "2026")["chapters"][0]["name"] == "Late"

    first = capture_store.album(film["id"], "2026")["chapters"][0]["first_month"]
    capture_store.name_chapter(film["id"], "2026", first, "Early")
    assert capture_store.album(film["id"], "2026")["chapters"][0]["name"] == "Early"


def test_the_unfiled_pile_can_have_a_chapter_named_too(capture_store):
    """It is an album you can open like any other, so it is one you can name a
    chapter in. It is also the one subject here that is not a folder id."""
    write(capture_store, "2026-03-02", "loose thought")
    capture_store.reindex()
    capture_store.name_chapter(None, "2026", 3, "Odds and ends")

    assert capture_store.album(None, "2026")["chapters"][0]["name"] == "Odds and ends"


def test_a_chapter_name_survives_the_index_being_deleted(capture_store):
    """Derived like everything else: the name is in the log and nowhere else."""
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "<film>")
    capture_store.reindex()
    capture_store.name_chapter(film["id"], "2026", 3, "The long spring")

    fresh = Store()
    fresh.start()
    try:
        assert fresh.album(film["id"], "2026")["chapters"][0]["name"] == "The long spring"
    finally:
        fresh.close()


def test_a_deleted_folder_takes_its_chapter_names_with_it(capture_store):
    """The same cascade the groups and the tag mappings get. A name left behind
    would attach itself to the next folder to be given that id, which is not a
    thing that can happen — but a fold that relies on that is a fold with a
    reason to be re-read later."""
    film = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "<film>")
    capture_store.reindex()
    capture_store.name_chapter(film["id"], "2026", 3, "The long spring")
    capture_store.delete_folder(film["id"])

    # Asserted through the store on both sides of a rebuild rather than by
    # reaching into the replay: the write and the replay are one function now
    # (`index.apply`), and the thing worth pinning is that they leave the same
    # table behind. This used to check only the replay's half — which is how
    # the targeted mirror came to be the one that forgot the cascade.
    assert index.chapter_names(capture_store.conn, film["id"], "2026") == {}
    capture_store.reindex()
    assert index.chapter_names(capture_store.conn, film["id"], "2026") == {}


def test_a_chapter_name_is_refused_a_month_that_is_not_one(capture_store):
    film = capture_store.create_folder("film", ["film"])
    with pytest.raises(CaptureError):
        capture_store.name_chapter(film["id"], "2026", 13, "Nope")
    with pytest.raises(CaptureError):
        capture_store.name_chapter(film["id"], "202", 3, "Nope")


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
        (d for d in index.folder_heat(store.conn, folder_id, year) if d["day"] == day),
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

    assert [d["day"] for d in index.folder_heat(capture_store.conn, folder["id"], "2026")] == [
        "2026-03-02"
    ]


def test_the_heatmap_is_cut_by_year_like_every_other_album_figure(capture_store):
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2025-03-02", "a <film>")
    write(capture_store, "2026-03-02", "b <film>")
    clock(capture_store, folder["id"], "2025-06-01", 3600)
    capture_store.reindex()

    assert [d["day"] for d in index.folder_heat(capture_store.conn, folder["id"], "2026")] == [
        "2026-03-02"
    ]
    assert [d["day"] for d in index.folder_heat(capture_store.conn, folder["id"], "2025")] == [
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


def test_the_unfiled_pile_has_no_grid(capture_store):
    """It has no clock and no overview to draw one on — the same shape
    `folder_time_volumes` takes, and not an error."""
    write(capture_store, "2026-03-02", "loose")
    capture_store.reindex()

    assert index.folder_heat(capture_store.conn, None, "2026") == []


def test_the_album_carries_its_own_heat(capture_store):
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "a <film>")
    capture_store.reindex()

    album = capture_store.album(folder["id"], "2026")
    assert album["heat"] == [
        {"day": "2026-03-02", "entries": 1, "seconds": 0, "points": 1}
    ]


def test_the_heatmap_survives_the_index_being_deleted(capture_store):
    """Points are a fold over the log like everything else here."""
    folder = capture_store.create_folder("film", ["film"])
    write(capture_store, "2026-03-02", "a <film>")
    clock(capture_store, folder["id"], "2026-03-02", 3600)
    capture_store.reindex()

    before = index.folder_heat(capture_store.conn, folder["id"], "2026")
    assert_index_is_disposable(capture_store)
    assert index.folder_heat(capture_store.conn, folder["id"], "2026") == before


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
        for d in index.folder_heat(capture_store.conn, folder["id"], "2026")
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
