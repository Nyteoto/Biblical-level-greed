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
    agree, or the index has stopped being disposable."""
    from backend.capture.config import INDEX_PATH

    INDEX_PATH.unlink()
    fresh = Store()
    fresh.start()
    return fresh


def assert_index_is_disposable(store: Store) -> None:
    fresh = rebuilt_from_log(store)
    try:
        assert fresh.folders() == store.folders()
        assert fresh.vocab() == store.vocab()
        assert fresh.unassigned_tags() == store.unassigned_tags()
        assert fresh.entries(limit=500) == store.entries(limit=500)
    finally:
        fresh.close()


# ── The registry ──────────────────────────────────────────────────────────


def test_a_new_folder_is_given_the_next_palette_colour(capture_store):
    first = capture_store.create_folder("Work")
    second = capture_store.create_folder("Home")

    assert first["color"] == "#60a5fa"
    assert second["color"] == "#f472b6"


def test_a_folder_answers_to_its_own_name(capture_store):
    """The one deliberate addition to the source's model. It is what lets
    `--work` and `<work>` mean the same thing with no special case."""
    folder = capture_store.create_folder("Work")

    assert folder["tags"] == ["work"]
    assert capture_store.vocab()["tag_to_folder"] == {"work": folder["id"]}


def test_the_directive_and_the_tag_reach_the_same_folder(capture_store):
    folder = capture_store.create_folder("Work")
    by_tag = capture_store.capture("<work> shipped the parser")
    by_directive = capture_store.capture("--work shipped the folders")

    inside = [e["id"] for e in capture_store.folder_detail(folder["id"])["entries"]]
    assert sorted(inside) == sorted([by_tag["id"], by_directive["id"]])


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

    assert capture_store.folders()[0]["tags"] == ["work"]
    assert sorted(capture_store.folders()[1]["tags"]) == ["garden", "home"]


def test_naming_a_folder_never_steals_a_tag_that_is_already_filed(capture_store):
    """A folder claims its own name only if nothing else has it. Otherwise
    creating a folder could silently empty another one."""
    work = capture_store.create_folder("Work")
    capture_store.map_tag(work["id"], "garden")

    garden = capture_store.create_folder("Garden")

    assert garden["tags"] == []
    assert capture_store.vocab()["tag_to_folder"]["garden"] == work["id"]


def test_renaming_keeps_the_old_name_working(capture_store):
    """Entries filed by `--admin` reach the folder through the tag `admin`. A
    rename that let go of it would drop them out of the folder they are in."""
    folder = capture_store.create_folder("Admin")
    entry = capture_store.capture("--admin filed the tax return")

    capture_store.rename_folder(folder["id"], "Paperwork")

    after = capture_store.folder_detail(folder["id"])
    assert after["folder"]["name"] == "Paperwork"
    assert sorted(after["folder"]["tags"]) == ["admin", "paperwork"]
    assert [e["id"] for e in after["entries"]] == [entry["id"]]


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
    folder = capture_store.create_folder("Work")
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
    work = capture_store.create_folder("Work")
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

    assert capture_store.vocab()["tags"] == ["deploy", "work"]


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
        "create-folder",
        "map-tag",  # the folder claiming its own name
        "map-tag",
        "unmap-tag",
        "rename-folder",
        "map-tag",  # the new name; the old one was already held
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
    folder = capture_store.create_folder("Work")
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
