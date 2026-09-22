"""The clock: measured stretches of work, attributed to a folder.

The rule under test almost everywhere here is that **a total is a sum over
events and is stored nowhere**, and the one property that makes such a sum
safe in this log: *applying the same line twice must not change the answer.*

Everything else in capture's log folds last-wins onto a state, so a duplicated
line — from a restored backup, or a write interrupted halfway — says the same
thing twice and lands the same way. A duration accumulates, which is a shape
this log had never carried before. Giving each session its own id is what
brings it back under the same rule, and `test_a_duplicated_session_line_does_
not_double_count` is the test that decides whether that worked.
"""
from __future__ import annotations

import json

from backend.capture import eventlog, index
from backend.capture.store import CaptureError, NotFound, Store

import pytest

from .test_capture_folders import assert_index_is_disposable, rebuilt_from_log


def seconds_of(store: Store, folder_id: str) -> int:
    return index.folder(store.conn, folder_id)["seconds"]


# ── Logging a session ─────────────────────────────────────────────────────


def test_a_session_lands_on_the_folder(capture_store):
    folder = capture_store.create_folder("Darkroom")
    capture_store.log_time(folder["id"], 3600)

    assert seconds_of(capture_store, folder["id"]) == 3600
    assert_index_is_disposable(capture_store)


def test_sessions_add_up(capture_store):
    folder = capture_store.create_folder("Darkroom")
    capture_store.log_time(folder["id"], 1800)
    capture_store.log_time(folder["id"], 900)
    capture_store.log_time(folder["id"], 45)

    assert seconds_of(capture_store, folder["id"]) == 2745


def test_a_folder_with_no_sessions_reads_zero_rather_than_missing(capture_store):
    folder = capture_store.create_folder("Darkroom")
    assert seconds_of(capture_store, folder["id"]) == 0


def test_time_is_attributed_per_folder(capture_store):
    one = capture_store.create_folder("Darkroom")
    two = capture_store.create_folder("Garden")
    capture_store.log_time(one["id"], 600)

    assert seconds_of(capture_store, one["id"]) == 600
    assert seconds_of(capture_store, two["id"]) == 0


def test_a_zero_length_session_is_a_real_session(capture_store):
    """Started and stopped. The row exists, so it can be found and taken back;
    the total is unmoved, because nothing happened."""
    folder = capture_store.create_folder("Darkroom")
    session = capture_store.log_time(folder["id"], 0)

    assert seconds_of(capture_store, folder["id"]) == 0
    assert [s["id"] for s in index.time_sessions(capture_store.conn, folder["id"])] == [
        session["id"]
    ]


# ── The property the whole design turns on ────────────────────────────────


def test_a_duplicated_session_line_does_not_double_count(capture_store):
    """The shape a restored backup or an interrupted write produces.

    A summed fold over an event keyed on the *folder* would count this twice.
    Keyed on the session, the second apply replaces the first one's row.
    """
    folder = capture_store.create_folder("Darkroom")
    capture_store.log_time(folder["id"], 1800)

    events = eventlog.read_all()[0]
    logged = [e for e in events if e["kind"] == eventlog.LOG_TIME]
    assert len(logged) == 1

    with capture_store.conn:
        index.apply(capture_store.conn, logged[0])
        index.apply(capture_store.conn, logged[0])

    assert seconds_of(capture_store, folder["id"]) == 1800


def test_sessions_replayed_out_of_order_reach_the_same_total(capture_store):
    folder = capture_store.create_folder("Darkroom")
    for length in (600, 1200, 90):
        capture_store.log_time(folder["id"], length)

    forwards = seconds_of(capture_store, folder["id"])

    events = eventlog.read_all()[0]
    with capture_store.conn:
        for event in reversed(events):
            index.apply(capture_store.conn, event)

    assert seconds_of(capture_store, folder["id"]) == forwards == 1890


# ── Taking one back ───────────────────────────────────────────────────────


def test_a_session_can_be_taken_back(capture_store):
    folder = capture_store.create_folder("Darkroom")
    keep = capture_store.log_time(folder["id"], 600)
    drop = capture_store.log_time(folder["id"], 3600)

    capture_store.unlog_time(drop["id"])

    assert seconds_of(capture_store, folder["id"]) == 600
    assert [s["id"] for s in index.time_sessions(capture_store.conn, folder["id"])] == [
        keep["id"]
    ]
    assert_index_is_disposable(capture_store)


def test_taking_one_back_appends_rather_than_deletes(capture_store):
    """The append-only commitment. The `log-time` line is still in the file."""
    folder = capture_store.create_folder("Darkroom")
    session = capture_store.log_time(folder["id"], 600)
    capture_store.unlog_time(session["id"])

    kinds = [e["kind"] for e in eventlog.read_all()[0]]
    assert kinds.count(eventlog.LOG_TIME) == 1
    assert kinds.count(eventlog.UNLOG_TIME) == 1


def test_a_repeated_unlog_line_is_harmless(capture_store):
    folder = capture_store.create_folder("Darkroom")
    capture_store.log_time(folder["id"], 600)
    session = capture_store.log_time(folder["id"], 3600)
    capture_store.unlog_time(session["id"])

    events = eventlog.read_all()[0]
    undo = [e for e in events if e["kind"] == eventlog.UNLOG_TIME][0]
    with capture_store.conn:
        index.apply(capture_store.conn, undo)
        index.apply(capture_store.conn, undo)

    assert seconds_of(capture_store, folder["id"]) == 600


def test_unlogging_something_that_is_not_there_is_a_refusal(capture_store):
    with pytest.raises(NotFound):
        capture_store.unlog_time("nosuchsession")


# ── Refusals ──────────────────────────────────────────────────────────────


def test_a_session_on_a_missing_folder_is_a_refusal(capture_store):
    with pytest.raises(NotFound):
        capture_store.log_time("nosuchfolder", 600)


def test_a_negative_session_is_a_refusal(capture_store):
    folder = capture_store.create_folder("Darkroom")
    with pytest.raises(CaptureError):
        capture_store.log_time(folder["id"], -1)


def test_a_forgotten_timer_is_refused_rather_than_clamped(capture_store):
    """A quiet clamp would write a number nobody measured into a log that
    cannot be edited. Saying no leaves the browser holding the real one."""
    from backend.capture.config import MAX_SESSION_SECONDS

    folder = capture_store.create_folder("Darkroom")
    with pytest.raises(CaptureError):
        capture_store.log_time(folder["id"], MAX_SESSION_SECONDS + 1)

    assert seconds_of(capture_store, folder["id"]) == 0


def test_the_cap_itself_is_allowed(capture_store):
    from backend.capture.config import MAX_SESSION_SECONDS

    folder = capture_store.create_folder("Darkroom")
    capture_store.log_time(folder["id"], MAX_SESSION_SECONDS)
    assert seconds_of(capture_store, folder["id"]) == MAX_SESSION_SECONDS


# ── Deleting the folder underneath ────────────────────────────────────────


def test_deleting_a_folder_takes_its_time_with_it(capture_store):
    """Unlike entries, which survive: an entry is only *resolved* into a
    folder, while a session is a measurement of one and cannot be re-resolved
    onto anything."""
    folder = capture_store.create_folder("Darkroom")
    capture_store.capture("a frame <darkroom>")
    capture_store.log_time(folder["id"], 3600)

    capture_store.delete_folder(folder["id"])

    assert index.folder_seconds(capture_store.conn) == {}
    # The writing is untouched.
    assert len(capture_store.entries(limit=10)) == 1
    assert_index_is_disposable(capture_store)


def test_a_session_for_a_folder_that_never_existed_is_dropped_on_replay(
    capture_store,
):
    """The same guard `set-group` has. The event stays in the log; the row
    does not appear, because a total attributed to nothing cannot be read."""
    with capture_store.conn:
        index.apply(
            capture_store.conn,
            {
                "ts": "2026-09-01T10:00:00+07:00",
                "day": "2026-09-01",
                "kind": eventlog.LOG_TIME,
                "id": "sessionid0001",
                "folder": "ghost",
                "seconds": 600,
            },
        )
    assert index.folder_seconds(capture_store.conn) == {}


# ── Cutting it by year and by month ───────────────────────────────────────


def _log_on(store: Store, folder_id: str, day: str, seconds: int) -> None:
    """A session on a named day. `append` stamps today, so the day is forced
    the way the CSV importer forces a `ts`."""
    event = eventlog.append(
        eventlog.LOG_TIME,
        eventlog.new_id(),
        folder=folder_id,
        seconds=seconds,
        day=day,
        ts=f"{day}T18:00:00+07:00",
    )
    with store.conn:
        index.apply(store.conn, event)


def test_a_year_holds_only_its_own_sessions(capture_store):
    folder = capture_store.create_folder("Darkroom")
    _log_on(capture_store, folder["id"], "2025-11-03", 3600)
    _log_on(capture_store, folder["id"], "2026-02-14", 1800)

    assert index.folder_seconds(capture_store.conn, "2026") == {folder["id"]: 1800}
    assert index.folder_seconds(capture_store.conn, "2025") == {folder["id"]: 3600}
    # No year at all is every year, which is what the `all` shelf asks for.
    assert index.folder_seconds(capture_store.conn, None) == {folder["id"]: 5400}


def test_the_monthly_totals_line_up_with_the_twelve_bars(capture_store):
    folder = capture_store.create_folder("Darkroom")
    _log_on(capture_store, folder["id"], "2026-01-09", 600)
    _log_on(capture_store, folder["id"], "2026-01-20", 300)
    _log_on(capture_store, folder["id"], "2026-08-02", 7200)

    volumes = index.folder_time_volumes(capture_store.conn, index.InFolder(folder["id"]), "2026")
    assert len(volumes) == 12
    assert volumes[0] == 900
    assert volumes[7] == 7200
    assert sum(volumes) == 8100


def test_the_unfiled_pile_can_never_be_clocked(capture_store):
    """A session is logged from a folder's own screen, so there is no gesture
    that produces one nothing has claimed."""
    assert index.folder_time_volumes(capture_store.conn, index.UNFILED, "2026") == [0] * 12


# ── What the screens read ─────────────────────────────────────────────────


def test_the_album_carries_the_clock(capture_store):
    folder = capture_store.create_folder("Darkroom")
    capture_store.capture("a frame <darkroom>")
    capture_store.map_tag(folder["id"], "darkroom")
    _log_on(capture_store, folder["id"], "2026-08-02", 5400)

    album = capture_store.album(index.InFolder(folder["id"]), "2026")
    assert album["seconds"] == 5400
    assert album["time_volumes"][7] == 5400
    assert [s["seconds"] for s in album["sessions"]] == [5400]


def test_the_shelf_card_carries_the_year_not_all_time(capture_store):
    folder = capture_store.create_folder("Darkroom")
    capture_store.map_tag(folder["id"], "darkroom")
    capture_store.capture("a frame <darkroom>")
    _log_on(capture_store, folder["id"], "2025-06-01", 3600)
    _log_on(capture_store, folder["id"], "2026-06-01", 60)

    card = [a for a in capture_store.shelf("2026")["albums"] if a["id"] == folder["id"]][0]
    assert card["seconds"] == 60
    # The folder record underneath it is all-time, like `all_time_count`.
    assert card["all_time_count"] >= 0
    assert seconds_of(capture_store, folder["id"]) == 3660


# ── The wire ──────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    """The app over a clean capture dir.

    Not `data_dir` — that fixture clears the *tech tree's* files, and capture
    keeps its own, so a client built on it inherits whatever the previous test
    in this file wrote. The app's store is started by the lifespan and replays
    the log it finds, so the log is what has to be empty.
    """
    import shutil

    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.capture import config as capture_config

    shutil.rmtree(capture_config.CAPTURE_DIR, ignore_errors=True)
    capture_config.ensure_dirs()
    with TestClient(app) as test_client:
        yield test_client


def test_the_endpoints_log_and_take_back(client):
    made = client.post("/api/capture/folders", json={"name": "Darkroom"})
    folder_id = made.json()["folder"]["id"]

    posted = client.post(
        f"/api/capture/folders/{folder_id}/time", json={"seconds": 1800}
    )
    assert posted.status_code == 201
    session_id = posted.json()["session"]["id"]

    album = client.get(f"/api/capture/album?folder={folder_id}&year=all").json()
    assert album["seconds"] == 1800

    dropped = client.delete(f"/api/capture/time/{session_id}")
    assert dropped.status_code == 200
    album = client.get(f"/api/capture/album?folder={folder_id}&year=all").json()
    assert album["seconds"] == 0


def test_the_endpoint_refuses_a_forgotten_timer(client):
    made = client.post("/api/capture/folders", json={"name": "Darkroom"})
    folder_id = made.json()["folder"]["id"]

    refused = client.post(
        f"/api/capture/folders/{folder_id}/time", json={"seconds": 60 * 60 * 48}
    )
    assert refused.status_code == 400
