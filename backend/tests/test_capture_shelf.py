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

from backend.capture import eventlog, index

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

    INDEX_PATH.unlink()
    fresh = Store()
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
