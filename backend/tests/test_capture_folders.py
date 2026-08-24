"""Folders and the tag taxonomy: a registry folded out of the same log.

The rule under test almost everywhere here is that **membership is resolved,
not stored**. An entry is in a folder because one of its tags points there, or
because it was filed there by hand — never because a row somewhere says so.
Everything that follows from that (mapping is retroactive, deleting a folder
loses no writing, renaming strands nothing) is what these cover.

The parser is not retested here; it has 1185 golden fixtures of its own.
"""
from __future__ import annotations

import json

from backend.capture import eventlog, index
from backend.capture.store import CaptureError, Store

import pytest


def log_kinds() -> list[str]:
    from backend.capture.config import LOG_DIR

    out = []
    for path in sorted(LOG_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line)["kind"])
    return out


def rebuilt_from_log(store: Store) -> Store:
    """A second store built from nothing but the log. The comparison every
    test here ends with: the targeted index writes and the full replay have to
    agree, or the index has stopped being disposable.

    The replay gets its own index file so that the store it is compared against
    keeps its own. This used to delete the shared one and let the first store go
    on reading the unlinked inode — true on POSIX, and on Windows an error,
    because an open file cannot be deleted at all.
    """
    from backend.capture.config import INDEX_PATH

    fresh = Store(INDEX_PATH.with_name("index-replay.sqlite"))
    fresh.start()
    return fresh


def assert_index_is_disposable(store: Store) -> None:
    fresh = rebuilt_from_log(store)
    try:
        assert fresh.folders() == store.folders()
        assert fresh.vocab() == store.vocab()
        assert fresh.unassigned_tags() == store.unassigned_tags()
        assert fresh.entries(limit=500) == store.entries(limit=500)
        # Membership itself, and not only the registry behind it. The targeted
        # writes and the replay have to agree about *what is in each folder* —
        # which is the half that broke when a third route in appeared and one
        # read had its own copy of the rule.
        for folder in store.folders():
            assert (
                fresh.folder_detail(folder["id"])["entries"]
                == store.folder_detail(folder["id"])["entries"]
            )
    finally:
        fresh.close()


# ── The registry ──────────────────────────────────────────────────────────


def test_a_new_folder_is_given_the_next_palette_colour(capture_store):
    first = capture_store.create_folder("Work")
    second = capture_store.create_folder("Home")

    assert first["color"] == "#60a5fa"
    assert second["color"] == "#f472b6"


def test_a_new_folder_claims_no_tag_at_all(capture_store):
    """The registry holds the words the user chose, and nothing else.

    A folder used to claim the tag of its own name at creation, so that a
    `--directive` reached it through the ordinary mapping. What that cost was a
    word per folder in the registry that nobody had ever typed — noise in the
    one list whose whole job is to say which non-obvious words point where.
    """
    folder = capture_store.create_folder("Work")

    assert folder["tags"] == []
    assert capture_store.vocab()["tag_to_folder"] == {}
    assert capture_store.tags() == []


def test_the_directive_reaches_the_folder_by_its_name_and_the_tag_does_not(capture_store):
    """The two routes, and why they are not the same route.

    A directive names the folder outright, so it resolves against the folder's
    name and needs no mapping. A tag is a word you chose — `<work>` means
    whatever you have said it means, and until you say so it means nothing.
    That is the whole point of the mapping screen, and it is why creating a
    folder called Work must not quietly decide that `<work>` belongs to it.
    """
    folder = capture_store.create_folder("Work")
    by_tag = capture_store.capture("<work> shipped the parser")
    by_directive = capture_store.capture("--work shipped the folders")

    inside = [e["id"] for e in capture_store.folder_detail(folder["id"])["entries"]]
    assert inside == [by_directive["id"]]

    # And the tag arrives the moment it is pointed here — retroactively, like
    # every other mapping.
    capture_store.map_tag(folder["id"], "work")
    inside = [e["id"] for e in capture_store.folder_detail(folder["id"])["entries"]]
    assert sorted(inside) == sorted([by_tag["id"], by_directive["id"]])


def test_a_directive_naming_nothing_waits_rather_than_being_lost(capture_store):
    """The source resolves the directive at write time and drops it when no
    folder answers. Here the word is on the raw line and in its own column, so
    the folder made for it next year collects everything that was waiting."""
    entry = capture_store.capture("--greenhouse the frame is up")

    assert capture_store.entry(entry["id"])["directive"] == "greenhouse"
    assert capture_store.unassigned_tags() == []  # a directive is not a loose tag

    folder = capture_store.create_folder("Greenhouse")
    inside = [e["id"] for e in capture_store.folder_detail(folder["id"])["entries"]]
    assert inside == [entry["id"]]


def test_mapping_a_tag_is_retroactive(capture_store):
    """Nothing migrates. The entries were already in the folder's answer set;
    the mapping is what makes the folder ask the question."""
    capture_store.capture("<deploy> shipped it")
    capture_store.capture("<deploy> shipped it again")
    folder = capture_store.create_folder("Work")

    assert capture_store.folder_detail(folder["id"])["entries"] == []

    capture_store.map_tag(folder["id"], "deploy")
    assert len(capture_store.folder_detail(folder["id"])["entries"]) == 2


def test_a_tag_belongs_to_one_folder_and_mapping_moves_it(capture_store):
    work = capture_store.create_folder("Work")
    home = capture_store.create_folder("Home")
    capture_store.map_tag(work["id"], "garden")

    capture_store.map_tag(home["id"], "garden")

    assert capture_store.folders()[0]["tags"] == []
    assert capture_store.folders()[1]["tags"] == ["garden"]


def test_naming_a_folder_after_a_mapped_tag_disturbs_nothing(capture_store):
    """Creating a folder called Garden while `<garden>` points at Work used to
    risk emptying Work; a folder claims nothing now, so there is nothing to
    steal. The two routes go on meaning what they said: the tag goes where it
    was pointed, the directive goes to the folder it names."""
    work = capture_store.create_folder("Work")
    capture_store.map_tag(work["id"], "garden")
    tagged = capture_store.capture("<garden> the beds along the east wall")

    garden = capture_store.create_folder("Garden")
    named = capture_store.capture("--garden the beds along the east wall")

    assert garden["tags"] == []
    assert capture_store.vocab()["tag_to_folder"]["garden"] == work["id"]
    assert [e["id"] for e in capture_store.folder_detail(work["id"])["entries"]] == [
        tagged["id"]
    ]
    assert [e["id"] for e in capture_store.folder_detail(garden["id"])["entries"]] == [
        named["id"]
    ]


def test_renaming_keeps_the_old_name_working(capture_store):
    """Entries written `--admin` reach the folder by its name, so a rename
    would drop them out of the folder they were filed into — which no rename
    should ever do. A folder goes on answering to every name it has had.

    And it costs nothing in the registry: the names are their own derived
    table, not tags. A rename used to claim both the old name and the new one
    as tags, which is two more words nobody typed.
    """
    folder = capture_store.create_folder("Admin")
    entry = capture_store.capture("--admin filed the tax return")

    capture_store.rename_folder(folder["id"], "Paperwork")

    after = capture_store.folder_detail(folder["id"])
    assert after["folder"]["name"] == "Paperwork"
    assert after["folder"]["tags"] == []
    assert [e["id"] for e in after["entries"]] == [entry["id"]]

    # And the new name answers too, from here on.
    later = capture_store.capture("--paperwork and the receipts")
    inside = [e["id"] for e in capture_store.folder_detail(folder["id"])["entries"]]
    assert sorted(inside) == sorted([entry["id"], later["id"]])
    assert_index_is_disposable(capture_store)


def test_a_name_answers_for_one_folder_and_the_newest_claim_wins(capture_store):
    """A name belongs to one folder, the way a tag does. Making a new folder
    called Admin takes `--admin` back from the one that used to be called it —
    a name means what it means now, and a directive that resolved to two
    folders would be the second kind of membership this model cannot have."""
    old = capture_store.create_folder("Admin")
    entry = capture_store.capture("--admin filed the tax return")
    capture_store.rename_folder(old["id"], "Paperwork")

    fresh = capture_store.create_folder("Admin")

    assert capture_store.folder_detail(old["id"])["entries"] == []
    assert [e["id"] for e in capture_store.folder_detail(fresh["id"])["entries"]] == [
        entry["id"]
    ]
    assert_index_is_disposable(capture_store)


def test_deleting_a_folder_lets_go_of_its_names(capture_store):
    """The cascade `folder_tags` already had. A name pointing at a folder that
    is gone would make the entry look filed into nothing."""
    folder = capture_store.create_folder("Admin")
    entry = capture_store.capture("--admin filed the tax return")

    capture_store.delete_folder(folder["id"])

    assert capture_store.entries(limit=10)[0]["id"] == entry["id"]
    assert capture_store.entry(entry["id"])["directive"] == "admin"
    assert_index_is_disposable(capture_store)


def test_deleting_a_folder_keeps_every_word_that_was_in_it(capture_store):
    folder = capture_store.create_folder("Work")
    entry = capture_store.capture("<work> shipped it")
    capture_store.assign_entry(entry["id"], folder["id"])

    capture_store.delete_folder(folder["id"])

    assert capture_store.folders() == []
    assert len(capture_store.entries(limit=10)) == 1
    # The tag goes back in the pool rather than vanishing with the folder.
    assert capture_store.unassigned_tags() == [{"tag": "work", "count": 1}]
    assert capture_store.entry(entry["id"])["manual_folders"] == []


def test_a_folder_counts_what_the_union_says_is_in_it(capture_store):
    """The chip's number. Tagged in and filed in by hand, counted once."""
    folder = capture_store.create_folder("Work", ["work"])
    capture_store.capture("standup <work>")
    capture_store.capture("also standup <work>")
    filed = capture_store.capture("no tag on this one")
    capture_store.assign_entry(filed["id"], folder["id"])
    # Both routes into the same folder must not double-count.
    both = capture_store.capture("belt and braces <work>")
    capture_store.assign_entry(both["id"], folder["id"])

    assert capture_store.folders()[0]["entry_count"] == 4
    assert_index_is_disposable(capture_store)


# ── A folder's life ───────────────────────────────────────────────────────
#
# What makes a folder a project rather than a standing interest. Three states
# on one list rather than two kinds of thing, so nothing has to be classified
# before it can be captured into and a hobby that becomes a project is one
# event rather than a migration.


def test_a_folder_starts_with_no_lifecycle(capture_store):
    """The default, and the commonest: an interest you keep, not a project."""
    assert capture_store.create_folder("Filmmaking")["state"] == ""


def test_a_folder_can_be_taken_up_and_finished(capture_store):
    folder = capture_store.create_folder("Kitchen table")

    assert capture_store.set_folder_state(folder["id"], "active")["state"] == "active"
    assert capture_store.set_folder_state(folder["id"], "shipped")["state"] == "shipped"
    # ...and put back down again. Nothing here is one-way.
    assert capture_store.set_folder_state(folder["id"], "")["state"] == ""


def test_an_unknown_state_is_refused(capture_store):
    folder = capture_store.create_folder("Kitchen table")

    with pytest.raises(CaptureError):
        capture_store.set_folder_state(folder["id"], "nearly")
    assert capture_store.folders()[0]["state"] == ""


def test_setting_the_state_it_already_has_writes_nothing(capture_store):
    """An idempotent write should not add a line to an append-only log."""
    folder = capture_store.create_folder("Kitchen table")
    capture_store.set_folder_state(folder["id"], "active")
    before = len(log_kinds())

    capture_store.set_folder_state(folder["id"], "active")

    assert len(log_kinds()) == before


def test_the_state_is_last_wins_like_every_other_fold(capture_store):
    folder = capture_store.create_folder("Kitchen table")
    for state in ("active", "shipped", "active"):
        capture_store.set_folder_state(folder["id"], state)

    assert capture_store.folders()[0]["state"] == "active"
    assert log_kinds().count("set-state") == 3  # nothing was rewritten


def test_a_state_survives_the_index_being_deleted(capture_store):
    folder = capture_store.create_folder("Kitchen table")
    capture_store.set_folder_state(folder["id"], "shipped")

    assert_index_is_disposable(capture_store)
    fresh = rebuilt_from_log(capture_store)
    try:
        assert fresh.folders()[0]["state"] == "shipped"
    finally:
        fresh.close()


def test_a_state_for_a_deleted_folder_is_dropped_not_resurrected(capture_store):
    folder = capture_store.create_folder("Kitchen table")
    capture_store.delete_folder(folder["id"])

    path = eventlog.log_path_for("2099-01-01")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "ts": "2099-01-01T00:00:00+00:00",
                    "day": "2099-01-01",
                    "kind": "set-state",
                    "id": folder["id"],
                    "text": "active",
                }
            )
            + "\n"
        )

    capture_store.reindex()
    assert capture_store.folders() == []


# ── Filing by hand ────────────────────────────────────────────────────────


def test_filing_an_entry_by_hand_adds_a_place_rather_than_replacing_one(
    capture_store,
):
    work = capture_store.create_folder("Work", ["work"])
    reading = capture_store.create_folder("Reading")
    entry = capture_store.capture("<work> a thought that also belongs elsewhere")

    capture_store.assign_entry(entry["id"], reading["id"])

    assert len(capture_store.folder_detail(work["id"])["entries"]) == 1
    assert len(capture_store.folder_detail(reading["id"])["entries"]) == 1


def test_refiling_replaces_and_unfiling_clears(capture_store):
    work = capture_store.create_folder("Work")
    reading = capture_store.create_folder("Reading")
    entry = capture_store.capture("no tags at all")

    capture_store.assign_entry(entry["id"], work["id"])
    capture_store.assign_entry(entry["id"], reading["id"])
    assert capture_store.entry(entry["id"])["manual_folders"] == [reading["id"]]

    capture_store.assign_entry(entry["id"], None)
    assert capture_store.entry(entry["id"])["manual_folders"] == []
    assert capture_store.folder_detail(reading["id"])["entries"] == []


def test_filing_into_a_folder_that_is_not_there_is_refused(capture_store):
    entry = capture_store.capture("a thought")

    with pytest.raises(CaptureError):
        capture_store.assign_entry(entry["id"], "nosuchfolder")
    with pytest.raises(CaptureError):
        capture_store.assign_entry("nosuchentry", None)


# ── The unassigned pool ───────────────────────────────────────────────────


def test_the_pool_holds_what_no_folder_has_claimed(capture_store):
    capture_store.capture("<deploy> one")
    capture_store.capture("<deploy> two \\win")
    capture_store.capture("<garden> three")
    folder = capture_store.create_folder("Work")
    capture_store.map_tag(folder["id"], "deploy")

    # Commonest first; `\win` is a sentiment, not a tag, and never appears.
    assert capture_store.unassigned_tags() == [{"tag": "garden", "count": 1}]


def test_a_mapped_tag_joins_the_vocabulary_before_it_is_ever_written(
    capture_store,
):
    folder = capture_store.create_folder("Work")
    capture_store.map_tag(folder["id"], "deploy")

    assert capture_store.vocab()["tags"] == ["deploy"]


# ── Names ─────────────────────────────────────────────────────────────────


def test_a_folder_name_must_be_present_short_and_unused(capture_store):
    from backend.capture.config import MAX_NAME_LEN

    capture_store.create_folder("Work")

    with pytest.raises(CaptureError):
        capture_store.create_folder("   ")
    with pytest.raises(CaptureError):
        capture_store.create_folder("x" * (MAX_NAME_LEN + 1))
    # Case-insensitively unused: `--work` must not be a coin toss.
    with pytest.raises(CaptureError):
        capture_store.create_folder("WORK")

    assert len(capture_store.folders()) == 1


def test_a_refused_folder_writes_nothing(capture_store):
    with pytest.raises(CaptureError):
        capture_store.create_folder("")

    assert log_kinds() == []


# ── The log is still the truth ────────────────────────────────────────────


def test_every_folder_change_is_an_append(capture_store):
    folder = capture_store.create_folder("Work")
    capture_store.map_tag(folder["id"], "deploy")
    capture_store.unmap_tag(folder["id"], "deploy")
    capture_store.rename_folder(folder["id"], "Job")
    entry = capture_store.capture("a thought")
    capture_store.assign_entry(entry["id"], folder["id"])
    capture_store.assign_entry(entry["id"], None)
    capture_store.delete_folder(folder["id"])

    assert log_kinds() == [
        "create-folder",  # and no map-tag: a folder claims no name of its own
        "map-tag",
        "unmap-tag",
        "rename-folder",  # nothing was written `--work`, so nothing is claimed
        "capture",
        "assign",
        "unassign",
        "delete-folder",
    ]


def test_deleting_the_index_reproduces_the_whole_registry(capture_store):
    """The claim the architecture rests on, now that the registry is in it."""
    work = capture_store.create_folder("Work")
    capture_store.create_folder("Reading")
    capture_store.map_tag(work["id"], "deploy")
    entry = capture_store.capture("<deploy> shipped it --todo tell them")
    capture_store.toggle_line(entry["id"], 0)
    capture_store.assign_entry(entry["id"], work["id"])
    capture_store.rename_folder(work["id"], "Job")

    assert_index_is_disposable(capture_store)


def test_a_folder_event_that_lost_its_folder_is_dropped_not_resurrected(
    capture_store,
):
    """A backup restored halfway, or a log file re-appended: the fold has to
    survive events naming a folder that no longer exists."""
    folder = capture_store.create_folder("Work")
    capture_store.delete_folder(folder["id"])

    path = eventlog.log_path_for("2099-01-01")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "ts": "2099-01-01T00:00:00+00:00",
                    "day": "2099-01-01",
                    "kind": "map-tag",
                    "id": folder["id"],
                    "tag": "ghost",
                }
            )
            + "\n"
        )

    capture_store.reindex()
    assert capture_store.folders() == []
    assert capture_store.vocab()["tag_to_folder"] == {}


def test_an_unmap_that_arrives_late_cannot_steal_a_tag_back(capture_store):
    """`unmap-tag` names the folder it is unmapping *from*. Without that, a
    duplicated line from an old backup would silently unfile a live tag."""
    work = capture_store.create_folder("Work")
    home = capture_store.create_folder("Home")
    capture_store.map_tag(work["id"], "garden")

    events = [
        {
            "ts": "2099-01-01T00:00:00+00:00",
            "day": "2099-01-01",
            "kind": "map-tag",
            "id": home["id"],
            "tag": "garden",
        },
        {
            "ts": "2099-01-02T00:00:00+00:00",
            "day": "2099-01-02",
            "kind": "unmap-tag",
            "id": work["id"],  # stale: work no longer holds it
            "tag": "garden",
        },
    ]
    path = eventlog.log_path_for("2099-01-01")
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")

    capture_store.reindex()
    assert capture_store.vocab()["tag_to_folder"]["garden"] == home["id"]


def test_the_folder_screen_counts_sentiments_over_what_is_in_it(capture_store):
    folder = capture_store.create_folder("Work", ["work"])
    capture_store.capture("<work> \\win \\shipped")
    capture_store.capture("<work> \\win")
    capture_store.capture("<home> \\win")  # not in this folder

    assert capture_store.folder_detail(folder["id"])["sentiments"] == [
        {"name": "win", "count": 2},
        {"name": "shipped", "count": 1},
    ]


# ── Over HTTP ─────────────────────────────────────────────────────────────
#
# The router is thin, but "thin" has already been wrong once in this repo: the
# tech tree's structural routes all 500'd on a helper that had been deleted,
# and every rule they were protecting was fine. These assert the routes exist
# and that the tri-state on `assign_folder` survives the wire.


@pytest.fixture
def client(capture_store):
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.capture.store import store as global_store

    global_store.reindex()
    with TestClient(app) as test_client:
        yield test_client


def test_every_folder_route_is_reachable(client):
    created = client.post("/api/capture/folders", json={"name": "Work"})
    assert created.status_code == 201, created.text
    folder_id = created.json()["folder"]["id"]

    assert client.get("/api/capture/folders").status_code == 200
    assert client.get(f"/api/capture/folders/{folder_id}").status_code == 200
    assert client.get("/api/capture/tags/unassigned").status_code == 200
    assert (
        client.patch(
            f"/api/capture/folders/{folder_id}",
            json={"name": "Job", "add_tags": ["deploy"], "remove_tags": ["work"]},
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/api/capture/folders/{folder_id}/group",
            json={"year": "2026", "name": "Field"},
        ).status_code
        == 200
    )
    assert client.delete(f"/api/capture/folders/{folder_id}").status_code == 200


def test_the_state_travels_over_the_wire(client):
    folder_id = client.post("/api/capture/folders", json={"name": "Work"}).json()[
        "folder"
    ]["id"]

    taken_up = client.patch(
        f"/api/capture/folders/{folder_id}", json={"state": "active"}
    )
    assert taken_up.json()["folder"]["state"] == "active"

    # The empty string is a value, not an omission: it has to reach the store
    # and clear the state rather than read as "nothing to change".
    cleared = client.patch(f"/api/capture/folders/{folder_id}", json={"state": ""})
    assert cleared.status_code == 200
    assert cleared.json()["folder"]["state"] == ""

    refused = client.patch(
        f"/api/capture/folders/{folder_id}", json={"state": "nearly"}
    )
    assert refused.status_code == 400


def test_a_missing_folder_is_a_404_and_a_bad_name_is_a_400(client):
    assert client.get("/api/capture/folders/ghost").status_code == 404
    assert client.delete("/api/capture/folders/ghost").status_code == 404

    client.post("/api/capture/folders", json={"name": "Work"})
    duplicate = client.post("/api/capture/folders", json={"name": "work"})
    assert duplicate.status_code == 400


def test_assigning_and_unassigning_over_the_wire(client):
    folder_id = client.post("/api/capture/folders", json={"name": "Work"}).json()[
        "folder"
    ]["id"]
    entry_id = client.post(
        "/api/capture/entries", json={"raw_text": "an unfiled thought"}
    ).json()["entry"]["id"]

    filed = client.patch(
        f"/api/capture/entries/{entry_id}", json={"assign_folder": folder_id}
    )
    assert filed.json()["entry"]["manual_folders"] == [folder_id]

    # `null` is "unfile", and is not the same request as sending nothing.
    cleared = client.patch(
        f"/api/capture/entries/{entry_id}", json={"assign_folder": None}
    )
    assert cleared.json()["entry"]["manual_folders"] == []
    assert client.patch(f"/api/capture/entries/{entry_id}", json={}).status_code == 400


# ── Shelf groups ──────────────────────────────────────────────────────────
#
# A group is an arrangement of one year's shelf and nothing else. The tests
# that matter are the ones pinning that it stays cosmetic: it must not move a
# single entry, and the same folder must be free to sit somewhere else next
# year. Everything here goes through the index-is-disposable check as well,
# because `set_folder_group` writes the table twice — once as a targeted
# mirror, once by replay — and the two drifting apart is the failure this
# whole design is supposed to make impossible.


def test_a_folder_starts_in_no_group(capture_store):
    capture_store.capture("first light <garden>")
    folder = capture_store.create_folder("Garden", ["garden"])
    year = capture_store.shelf(None)["years"][0]

    album = next(a for a in capture_store.shelf(year)["albums"] if a["id"] == folder["id"])
    assert album["group"] == ""
    assert capture_store.shelf(year)["groups"] == []


def test_naming_a_group_creates_it(capture_store):
    capture_store.capture("first light <garden>")
    folder = capture_store.create_folder("Garden", ["garden"])
    year = capture_store.shelf(None)["years"][0]

    shelf = capture_store.set_folder_group(folder["id"], year, "Field")

    assert shelf["groups"] == ["Field"]
    assert next(a for a in shelf["albums"] if a["id"] == folder["id"])["group"] == "Field"


def test_the_last_folder_out_takes_the_group_with_it(capture_store):
    """There is no `delete-group` because there is nothing to delete. A group
    exists exactly while something names it."""
    capture_store.capture("first light <garden>")
    folder = capture_store.create_folder("Garden", ["garden"])
    year = capture_store.shelf(None)["years"][0]

    capture_store.set_folder_group(folder["id"], year, "Field")
    shelf = capture_store.set_folder_group(folder["id"], year, "")

    assert shelf["groups"] == []
    assert next(a for a in shelf["albums"] if a["id"] == folder["id"])["group"] == ""


def test_a_folder_is_grouped_per_year_not_once(capture_store):
    """The whole reason `set-group` carries a year. Grouping the 2026 shelf
    must say nothing about how 2025's was arranged."""
    capture_store.capture("first light <garden>")
    folder = capture_store.create_folder("Garden", ["garden"])

    capture_store.set_folder_group(folder["id"], "2025", "Field")
    capture_store.set_folder_group(folder["id"], "2026", "Archive")

    assert capture_store.shelf("2025")["groups"] == ["Field"]
    assert capture_store.shelf("2026")["groups"] == ["Archive"]
    assert (
        capture_store.album(folder["id"], "2025")["group"] == "Field"
    )
    assert (
        capture_store.album(folder["id"], "2026")["group"] == "Archive"
    )


def test_the_all_years_shelf_has_no_groups(capture_store):
    """A group is an arrangement of a year, so across every year at once there
    is no answer that is not a guess. The all view keeps the plain grid."""
    capture_store.capture("first light <garden>")
    folder = capture_store.create_folder("Garden", ["garden"])
    year = capture_store.shelf(None)["years"][0]
    capture_store.set_folder_group(folder["id"], year, "Field")

    everything = capture_store.shelf(None)
    assert everything["groups"] == []
    assert all(a["group"] == "" for a in everything["albums"])


def test_grouping_moves_no_entry(capture_store):
    """The cosmetic guarantee, stated as a test: membership is still resolved
    from tags, and a heading over a card cannot become a second kind of it."""
    capture_store.capture("first light <garden>")
    capture_store.capture("nothing filed here")
    folder = capture_store.create_folder("Garden", ["garden"])
    year = capture_store.shelf(None)["years"][0]

    before = capture_store.album(folder["id"], year)["entries"]
    capture_store.set_folder_group(folder["id"], year, "Field")

    assert capture_store.album(folder["id"], year)["entries"] == before
    assert capture_store.shelf(year)["unfiled"] == 1


def test_groups_keep_the_order_they_were_first_named_in(capture_store):
    capture_store.capture("a <one>")
    capture_store.capture("b <two>")
    capture_store.capture("c <three>")
    one = capture_store.create_folder("One", ["one"])
    two = capture_store.create_folder("Two", ["two"])
    three = capture_store.create_folder("Three", ["three"])
    year = capture_store.shelf(None)["years"][0]

    capture_store.set_folder_group(two["id"], year, "Second")
    capture_store.set_folder_group(one["id"], year, "First")
    # Joining an existing group must not move that group to the end.
    capture_store.set_folder_group(three["id"], year, "Second")

    assert capture_store.shelf(year)["groups"] == ["Second", "First"]


def test_a_group_is_last_wins_like_every_other_fold(capture_store):
    capture_store.capture("first light <garden>")
    folder = capture_store.create_folder("Garden", ["garden"])
    year = capture_store.shelf(None)["years"][0]

    for name in ("Field", "Archive", "Field"):
        capture_store.set_folder_group(folder["id"], year, name)

    assert capture_store.shelf(year)["groups"] == ["Field"]
    assert log_kinds().count("set-group") == 3  # nothing was rewritten


def test_a_group_survives_the_index_being_deleted(capture_store):
    capture_store.capture("a <one>")
    capture_store.capture("b <two>")
    one = capture_store.create_folder("One", ["one"])
    two = capture_store.create_folder("Two", ["two"])
    year = capture_store.shelf(None)["years"][0]
    capture_store.set_folder_group(two["id"], year, "Second")
    capture_store.set_folder_group(one["id"], year, "First")

    assert_index_is_disposable(capture_store)
    fresh = rebuilt_from_log(capture_store)
    try:
        # Order included: `seq` is what carries it, and a replay that numbered
        # the groups differently would reshuffle the shelf on every restart.
        assert fresh.shelf(year)["groups"] == capture_store.shelf(year)["groups"]
        assert [(a["id"], a["group"]) for a in fresh.shelf(year)["albums"]] == [
            (a["id"], a["group"]) for a in capture_store.shelf(year)["albums"]
        ]
    finally:
        fresh.close()


def test_deleting_a_folder_takes_its_grouping_with_it(capture_store):
    capture_store.capture("first light <garden>")
    folder = capture_store.create_folder("Garden", ["garden"])
    year = capture_store.shelf(None)["years"][0]
    capture_store.set_folder_group(folder["id"], year, "Field")

    capture_store.delete_folder(folder["id"])

    assert capture_store.shelf(year)["groups"] == []
    assert_index_is_disposable(capture_store)


def test_a_group_for_a_deleted_folder_is_dropped_not_resurrected(capture_store):
    folder = capture_store.create_folder("Garden")
    capture_store.delete_folder(folder["id"])

    path = eventlog.log_path_for("2099-01-01")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "ts": "2099-01-01T00:00:00+00:00",
                    "day": "2099-01-01",
                    "kind": "set-group",
                    "id": folder["id"],
                    "year": "2099",
                    "text": "Field",
                }
            )
            + "\n"
        )

    fresh = rebuilt_from_log(capture_store)
    try:
        assert fresh.folders() == []
        assert fresh.shelf("2099")["groups"] == []
    finally:
        fresh.close()


def test_a_group_name_is_tidied_and_capped(capture_store):
    from backend.capture.config import GROUP_NAME_MAX

    capture_store.capture("first light <garden>")
    folder = capture_store.create_folder("Garden", ["garden"])
    year = capture_store.shelf(None)["years"][0]

    capture_store.set_folder_group(folder["id"], year, "  Field   work  ")
    assert capture_store.shelf(year)["groups"] == ["Field work"]

    with pytest.raises(CaptureError):
        capture_store.set_folder_group(folder["id"], year, "x" * (GROUP_NAME_MAX + 1))


def test_grouping_refuses_a_year_that_is_not_one(capture_store):
    folder = capture_store.create_folder("Garden")
    with pytest.raises(CaptureError):
        capture_store.set_folder_group(folder["id"], "all", "Field")


def test_grouping_an_absent_folder_is_refused(capture_store):
    with pytest.raises(CaptureError):
        capture_store.set_folder_group("nope", "2026", "Field")


def test_the_group_travels_over_the_wire(client):
    client.post("/api/capture/entries", json={"raw_text": "first light <garden>"})
    folder_id = client.post(
        "/api/capture/folders", json={"name": "Garden", "tags": ["garden"]}
    ).json()["folder"]["id"]
    year = client.get("/api/capture/shelf").json()["years"][0]

    grouped = client.put(
        f"/api/capture/folders/{folder_id}/group",
        json={"year": year, "name": "Field"},
    )
    assert grouped.status_code == 200, grouped.text
    # The shelf comes back, because one move can create a heading or empty one
    # out of existence and a folder-shaped answer would say neither.
    assert grouped.json()["groups"] == ["Field"]

    refused = client.put(
        f"/api/capture/folders/{folder_id}/group",
        json={"year": "all", "name": "Field"},
    )
    assert refused.status_code == 400


# ── Renaming and deleting a group ─────────────────────────────────────────
#
# Both are whole-group edits `set-group` cannot express one folder at a time.
# The subtle one is `seq`: neither edit is allowed to reshuffle the shelf, and
# the targeted mirror and the replay have to agree about that or the order
# changes every time the index is rebuilt.


def _three_folders(store):
    store.capture("a <one>")
    store.capture("b <two>")
    store.capture("c <three>")
    return (
        store.create_folder("One", ["one"]),
        store.create_folder("Two", ["two"]),
        store.create_folder("Three", ["three"]),
    )


def test_renaming_a_group_carries_its_folders(capture_store):
    one, two, _ = _three_folders(capture_store)
    year = capture_store.shelf(None)["years"][0]
    capture_store.set_folder_group(one["id"], year, "Field")
    capture_store.set_folder_group(two["id"], year, "Field")

    shelf = capture_store.rename_group(year, "Field", "Outdoors")

    assert shelf["groups"] == ["Outdoors"]
    assert {a["id"] for a in shelf["albums"] if a["group"] == "Outdoors"} == {
        one["id"],
        two["id"],
    }
    assert log_kinds().count("rename-group") == 1  # one event, not one per folder


def test_renaming_keeps_the_group_where_it_was_on_the_shelf(capture_store):
    one, two, _ = _three_folders(capture_store)
    year = capture_store.shelf(None)["years"][0]
    capture_store.set_folder_group(one["id"], year, "First")
    capture_store.set_folder_group(two["id"], year, "Second")

    capture_store.rename_group(year, "First", "Renamed")

    assert capture_store.shelf(year)["groups"] == ["Renamed", "Second"]


def test_renaming_onto_an_existing_group_merges_into_it(capture_store):
    one, two, three = _three_folders(capture_store)
    year = capture_store.shelf(None)["years"][0]
    capture_store.set_folder_group(one["id"], year, "Keep")
    capture_store.set_folder_group(two["id"], year, "Merge")
    capture_store.set_folder_group(three["id"], year, "Merge")

    shelf = capture_store.rename_group(year, "Merge", "Keep")

    assert shelf["groups"] == ["Keep"]
    assert sum(1 for a in shelf["albums"] if a["group"] == "Keep") == 3


def test_a_merge_keeps_the_older_slot(capture_store):
    """The survivor is the group that was there first, so the shelf must not
    reorder itself because something was renamed into it."""
    one, two, three = _three_folders(capture_store)
    year = capture_store.shelf(None)["years"][0]
    capture_store.set_folder_group(one["id"], year, "Early")
    capture_store.set_folder_group(two["id"], year, "Later")
    capture_store.set_folder_group(three["id"], year, "Last")

    # Fold "Early" into "Last": the surviving name is Last, and its slot is the
    # one it already had — third — not Early's first.
    capture_store.rename_group(year, "Early", "Last")

    assert capture_store.shelf(year)["groups"] == ["Later", "Last"]
    assert_index_is_disposable(capture_store)


def test_deleting_a_group_returns_its_folders_to_the_loose_grid(capture_store):
    one, two, _ = _three_folders(capture_store)
    year = capture_store.shelf(None)["years"][0]
    capture_store.set_folder_group(one["id"], year, "Field")
    capture_store.set_folder_group(two["id"], year, "Field")

    shelf = capture_store.delete_group(year, "Field")

    assert shelf["groups"] == []
    assert all(a["group"] == "" for a in shelf["albums"])


def test_deleting_a_group_deletes_no_folder_and_no_entry(capture_store):
    """The guarantee worth stating out loud, because "delete" beside a shelf of
    projects reads worse than it is."""
    one, two, three = _three_folders(capture_store)
    year = capture_store.shelf(None)["years"][0]
    capture_store.set_folder_group(one["id"], year, "Field")

    before_folders = {f["id"] for f in capture_store.folders()}
    before_entries = capture_store.entries(limit=500)

    capture_store.delete_group(year, "Field")

    assert {f["id"] for f in capture_store.folders()} == before_folders
    assert capture_store.entries(limit=500) == before_entries


def test_deleting_one_group_leaves_the_others_where_they_were(capture_store):
    one, two, three = _three_folders(capture_store)
    year = capture_store.shelf(None)["years"][0]
    capture_store.set_folder_group(one["id"], year, "First")
    capture_store.set_folder_group(two["id"], year, "Second")
    capture_store.set_folder_group(three["id"], year, "Third")

    capture_store.delete_group(year, "Second")

    assert capture_store.shelf(year)["groups"] == ["First", "Third"]
    assert_index_is_disposable(capture_store)


def test_a_rename_and_a_delete_survive_the_index_being_deleted(capture_store):
    one, two, three = _three_folders(capture_store)
    year = capture_store.shelf(None)["years"][0]
    capture_store.set_folder_group(one["id"], year, "First")
    capture_store.set_folder_group(two["id"], year, "Second")
    capture_store.set_folder_group(three["id"], year, "Third")
    capture_store.rename_group(year, "First", "Renamed")
    capture_store.delete_group(year, "Second")

    assert_index_is_disposable(capture_store)
    fresh = rebuilt_from_log(capture_store)
    try:
        assert fresh.shelf(year)["groups"] == capture_store.shelf(year)["groups"]
        assert [(a["id"], a["group"]) for a in fresh.shelf(year)["albums"]] == [
            (a["id"], a["group"]) for a in capture_store.shelf(year)["albums"]
        ]
    finally:
        fresh.close()


def test_a_group_edit_is_per_year_like_the_grouping_itself(capture_store):
    one, _, _ = _three_folders(capture_store)
    capture_store.set_folder_group(one["id"], "2025", "Field")
    capture_store.set_folder_group(one["id"], "2026", "Field")

    capture_store.rename_group("2026", "Field", "Outdoors")

    assert capture_store.shelf("2025")["groups"] == ["Field"]
    assert capture_store.shelf("2026")["groups"] == ["Outdoors"]


def test_editing_a_group_that_is_not_there_is_refused(capture_store):
    with pytest.raises(CaptureError):
        capture_store.rename_group("2026", "Nothing", "Something")
    with pytest.raises(CaptureError):
        capture_store.delete_group("2026", "Nothing")


def test_a_group_cannot_be_renamed_to_nothing(capture_store):
    one, _, _ = _three_folders(capture_store)
    year = capture_store.shelf(None)["years"][0]
    capture_store.set_folder_group(one["id"], year, "Field")

    with pytest.raises(CaptureError):
        capture_store.rename_group(year, "Field", "   ")


def test_the_group_edits_travel_over_the_wire(client):
    client.post("/api/capture/entries", json={"raw_text": "first light <garden>"})
    folder_id = client.post(
        "/api/capture/folders", json={"name": "Garden", "tags": ["garden"]}
    ).json()["folder"]["id"]
    year = client.get("/api/capture/shelf").json()["years"][0]
    client.put(
        f"/api/capture/folders/{folder_id}/group", json={"year": year, "name": "Field"}
    )

    renamed = client.post(
        "/api/capture/groups/rename",
        json={"year": year, "name": "Field", "to": "Outdoors"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["groups"] == ["Outdoors"]

    removed = client.post(
        "/api/capture/groups/delete", json={"year": year, "name": "Outdoors"}
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["groups"] == []

    assert (
        client.post(
            "/api/capture/groups/delete", json={"year": year, "name": "Outdoors"}
        ).status_code
        == 404
    )


# ── Arranging the shelf ───────────────────────────────────────────────────
#
# Groups are drawn in the order they were first named until the user says
# otherwise. What follows covers the saying-otherwise: one event carrying the
# whole order, for the reason `order-groups` gives in eventlog.py.


def three_groups(store):
    """Three folders under three headings, in first-named order."""
    for tag in ("one", "two", "three"):
        store.capture(f"a line <{tag}>")
    ids = [store.create_folder(name.title(), [name])["id"] for name in ("one", "two", "three")]
    year = store.shelf(None)["years"][0]
    for folder_id, group in zip(ids, ("First", "Second", "Third")):
        store.set_folder_group(folder_id, year, group)
    assert store.shelf(year)["groups"] == ["First", "Second", "Third"]
    return year, ids


def test_the_groups_can_be_arranged_by_hand(capture_store):
    year, _ = three_groups(capture_store)

    shelf = capture_store.order_groups(year, ["Third", "First", "Second"])

    assert shelf["groups"] == ["Third", "First", "Second"]
    assert capture_store.shelf(year)["groups"] == ["Third", "First", "Second"]


def test_an_arrangement_survives_the_index_being_deleted(capture_store):
    year, _ = three_groups(capture_store)
    capture_store.order_groups(year, ["Third", "Second", "First"])

    assert_index_is_disposable(capture_store)
    fresh = rebuilt_from_log(capture_store)
    try:
        assert fresh.shelf(year)["groups"] == ["Third", "Second", "First"]
    finally:
        fresh.close()


def test_a_group_the_arrangement_did_not_name_keeps_its_place(capture_store):
    """A partial order is not an error. What it does not mention keeps its
    relative order behind what it does — which is what makes an arrangement
    written against a shelf that has since grown still mean something."""
    year, _ = three_groups(capture_store)

    shelf = capture_store.order_groups(year, ["Third"])

    assert shelf["groups"] == ["Third", "First", "Second"]


def test_the_same_arrangement_twice_is_the_same_shelf(capture_store):
    """The property a move would not have: a duplicated line — a restored
    backup, an interrupted write — lands on the same shelf the first one did."""
    year, _ = three_groups(capture_store)
    order = ["Second", "Third", "First"]

    capture_store.order_groups(year, order)
    capture_store.order_groups(year, order)

    assert capture_store.shelf(year)["groups"] == order
    assert log_kinds().count("order-groups") == 2  # nothing was rewritten
    fresh = rebuilt_from_log(capture_store)
    try:
        assert fresh.shelf(year)["groups"] == order
    finally:
        fresh.close()


def test_a_group_named_after_an_arrangement_stands_at_the_end(capture_store):
    year, _ = three_groups(capture_store)
    capture_store.order_groups(year, ["Third", "Second", "First"])

    capture_store.capture("a line <four>")
    fourth = capture_store.create_folder("Four", ["four"])
    capture_store.set_folder_group(fourth["id"], year, "Fourth")

    assert capture_store.shelf(year)["groups"] == ["Third", "Second", "First", "Fourth"]
    # The half worth pinning: the targeted write numbers the newcomer's slot
    # and so does the replay, and they have to agree or the shelf reshuffles
    # itself on the next launch.
    fresh = rebuilt_from_log(capture_store)
    try:
        assert fresh.shelf(year)["groups"] == ["Third", "Second", "First", "Fourth"]
    finally:
        fresh.close()


def test_arranging_a_group_that_is_not_there_is_refused(capture_store):
    year, _ = three_groups(capture_store)

    with pytest.raises(CaptureError, match="no such group"):
        capture_store.order_groups(year, ["Third", "Nowhere"])

    # And nothing was written: a refused edit leaves the shelf as it was.
    assert capture_store.shelf(year)["groups"] == ["First", "Second", "Third"]
    assert "order-groups" not in log_kinds()


def test_arranging_refuses_a_year_that_is_not_one(capture_store):
    with pytest.raises(CaptureError, match="not a year"):
        capture_store.order_groups("last", ["First"])


def test_the_arrangement_is_per_year_like_the_grouping(capture_store):
    """A shelf is a year's, and so is the order of the headings on it."""
    capture_store.capture("a line <one>")
    capture_store.capture("b line <two>")
    one = capture_store.create_folder("One", ["one"])
    two = capture_store.create_folder("Two", ["two"])
    year = capture_store.shelf(None)["years"][0]
    other = str(int(year) - 1)

    capture_store.set_folder_group(one["id"], year, "First")
    capture_store.set_folder_group(two["id"], year, "Second")
    capture_store.set_folder_group(one["id"], other, "First")
    capture_store.set_folder_group(two["id"], other, "Second")

    capture_store.order_groups(year, ["Second", "First"])

    assert capture_store.shelf(year)["groups"] == ["Second", "First"]
    assert capture_store.shelf(other)["groups"] == ["First", "Second"]


def test_the_arrangement_travels_over_the_wire(client):
    for tag in ("one", "two"):
        client.post("/api/capture/entries", json={"raw_text": f"a line <{tag}>"})
    ids = [
        client.post("/api/capture/folders", json={"name": tag.title(), "tags": [tag]})
        .json()["folder"]["id"]
        for tag in ("one", "two")
    ]
    year = client.get("/api/capture/shelf").json()["years"][0]
    for folder_id, group in zip(ids, ("First", "Second")):
        client.put(
            f"/api/capture/folders/{folder_id}/group", json={"year": year, "name": group}
        )

    arranged = client.post(
        "/api/capture/groups/order", json={"year": year, "order": ["Second", "First"]}
    )
    assert arranged.status_code == 200, arranged.text
    assert arranged.json()["groups"] == ["Second", "First"]

    assert (
        client.post(
            "/api/capture/groups/order", json={"year": year, "order": ["Nowhere"]}
        ).status_code
        == 404
    )


# ── Lifting a tag ─────────────────────────────────────────────────────────
#
# Presentation, and only presentation: the line is untouched and so is where it
# files. These pin that boundary from both sides.


def test_a_tag_can_be_lifted_and_put_back(capture_store):
    capture_store.capture("first light <garden>")

    assert capture_store.lift_tag("garden", True) == ["garden"]
    assert capture_store.vocab()["lifted"] == ["garden"]

    assert capture_store.lift_tag("garden", False) == []
    assert capture_store.vocab()["lifted"] == []


def test_lifting_changes_no_line_and_no_membership(capture_store):
    """The whole rule. A lifted tag still files exactly where it did, and the
    raw line is what it always was — this log cannot edit one."""
    capture_store.capture("first light <garden>")
    folder = capture_store.create_folder("Garden", ["garden"])
    before = capture_store.entries(limit=10)

    capture_store.lift_tag("garden", True)

    assert capture_store.entries(limit=10) == before
    assert [e["raw_text"] for e in capture_store.entries(limit=10)] == [
        "first light <garden>"
    ]
    inside = capture_store.folder_detail(folder["id"])["entries"]
    assert len(inside) == 1


def test_a_lifted_tag_is_still_a_tag(capture_store):
    """It is offered by the autocomplete and it is still claimed by its
    folder. Only the brackets stop being drawn."""
    capture_store.capture("first light <garden>")
    folder = capture_store.create_folder("Garden", ["garden"])
    capture_store.lift_tag("garden", True)

    vocab = capture_store.vocab()
    assert "garden" in vocab["tags"]
    assert vocab["tag_to_folder"] == {"garden": folder["id"]}


def test_lifting_is_last_wins_and_writes_nothing_twice(capture_store):
    capture_store.capture("first light <garden>")

    for lifted in (True, True, False, False, True):
        capture_store.lift_tag("garden", lifted)

    assert capture_store.vocab()["lifted"] == ["garden"]
    # Three changes of mind, three events — the repeats are not written at all.
    assert log_kinds().count("lift-tag") == 2
    assert log_kinds().count("unlift-tag") == 1


def test_a_lift_survives_the_index_being_deleted(capture_store):
    capture_store.capture("first light <garden> <shed>")
    capture_store.lift_tag("shed", True)

    assert_index_is_disposable(capture_store)


def test_a_lift_outlives_the_folder_that_claimed_the_tag(capture_store):
    """Lifting is a fact about a word, not about a folder — which is why it is
    not a column on the mapping. Deleting the folder cascades the mapping away
    and leaves the lift standing."""
    capture_store.capture("first light <garden>")
    folder = capture_store.create_folder("Garden", ["garden"])
    capture_store.lift_tag("garden", True)

    capture_store.delete_folder(folder["id"])

    assert capture_store.vocab()["lifted"] == ["garden"]
    assert_index_is_disposable(capture_store)


def test_a_tag_to_lift_is_tidied_like_any_other(capture_store):
    capture_store.capture("first light <garden>")

    assert capture_store.lift_tag("  GARDEN  ", True) == ["garden"]

    with pytest.raises(CaptureError, match="needs a name"):
        capture_store.lift_tag("   ", True)


def test_the_tag_census_says_what_is_lifted_and_where_it_lands(capture_store):
    capture_store.capture("first light <garden> <shed>")
    capture_store.capture("more light <garden>")
    folder = capture_store.create_folder("Garden", ["garden"])
    capture_store.lift_tag("shed", True)

    census = capture_store.tags()

    assert census == [
        {"tag": "garden", "count": 2, "folder": folder["id"], "lifted": False},
        {"tag": "shed", "count": 1, "folder": "", "lifted": True},
    ]


def test_the_census_is_what_was_written_not_what_was_claimed(capture_store):
    """A folder claims the tag of its own name at creation, so the mapping
    knows tags nobody has typed. Lifting is about appearances in a line, and a
    tag with no lines has none to strip."""
    capture_store.create_folder("Garden")

    assert capture_store.tags() == []


def test_the_lift_travels_over_the_wire(client):
    client.post("/api/capture/entries", json={"raw_text": "first light <garden>"})

    lifted = client.post("/api/capture/tags/lift", json={"tag": "garden", "lifted": True})
    assert lifted.status_code == 200, lifted.text
    assert lifted.json()["lifted"] == ["garden"]
    assert client.get("/api/capture/vocab").json()["lifted"] == ["garden"]

    census = client.get("/api/capture/tags").json()["tags"]
    assert census == [{"tag": "garden", "count": 1, "folder": "", "lifted": True}]

    back = client.post("/api/capture/tags/lift", json={"tag": "garden", "lifted": False})
    assert back.json()["lifted"] == []


def test_a_directive_is_not_a_word_in_the_vocabulary(capture_store):
    """The autocomplete offers tags, times, patterns and places — the words you
    write. A directive names a folder, and the folder list is beside it."""
    capture_store.capture("--greenhouse <frames> the frame is up")

    vocab = capture_store.vocab()
    assert vocab["tags"] == ["frames"]
    assert "greenhouse" not in vocab["tags"]


def test_a_lifted_tag_stops_asking_to_be_filed(capture_store):
    """The mapping screen exists to be emptied. A tag you have lifted is a word
    you have already said is not a tag, so leaving it on that screen would have
    it go on asking the one question you have answered."""
    capture_store.capture("<tagtest> a line I no longer mean that way")
    capture_store.capture("<garden> the beds along the east wall")

    assert [t["tag"] for t in capture_store.unassigned_tags()] == ["garden", "tagtest"]

    capture_store.lift_tag("tagtest", True)
    assert [t["tag"] for t in capture_store.unassigned_tags()] == ["garden"]

    # And it comes back the moment it is put back, like everything else here.
    capture_store.lift_tag("tagtest", False)
    assert [t["tag"] for t in capture_store.unassigned_tags()] == ["garden", "tagtest"]


def test_the_directive_survives_the_index_being_deleted(capture_store):
    """The column is derived from the raw line on every rebuild, so retuning
    the parser re-files every directive ever written with no migration."""
    folder = capture_store.create_folder("Greenhouse")
    capture_store.capture("--greenhouse the frame is up")
    capture_store.capture("<greenhouse> a tag nobody pointed anywhere")

    fresh = rebuilt_from_log(capture_store)
    try:
        assert len(fresh.folder_detail(folder["id"])["entries"]) == 1
        assert fresh.unassigned_tags() == [{"tag": "greenhouse", "count": 1}]
    finally:
        fresh.close()
