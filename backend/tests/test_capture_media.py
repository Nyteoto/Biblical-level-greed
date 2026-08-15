"""Media on a capture, and the one property that has to survive it.

A file reference is not derivable from anything — unlike `clean_text`, the tag
lists and the todo indices, which the parser recomputes on every rebuild. So it
goes on the event, and the test that matters is the same one every other part
of this app has: throw the index away and it all comes back.
"""
from __future__ import annotations

import io
import json

import pytest

from backend.app import media as blobs
from backend.capture.store import CaptureError, Store


def _stored(day="2026-08", name="aaaabbbbccccdddd.jpg") -> str:
    """A file in the blob store, put there directly. Ingest has its own suite;
    what matters here is only that the reference resolves."""
    from PIL import Image

    target = blobs.media_dir() / day
    target.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    Image.new("RGB", (12, 8), (90, 90, 90)).save(buf, format="JPEG")
    (target / name).write_bytes(buf.getvalue())
    return f"{day}/{name}"


def log_events() -> list[dict]:
    from backend.capture.config import LOG_DIR

    out = []
    for path in sorted(LOG_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def test_a_capture_can_carry_media(capture_store):
    ref = _stored()
    entry = capture_store.capture("<gym> squats", media=[ref])

    assert entry["media"] == [ref]
    assert log_events()[0]["media"] == [ref]


def test_a_clip_is_a_capture_on_its_own(capture_store):
    """No text at all. A video of the thing is the record of the thing."""
    ref = _stored(name="ffffeeeeddddcccc.mp4")
    entry = capture_store.capture("", media=[ref])

    assert entry["clean_text"] == ""
    assert entry["media"] == [ref]


def test_still_nothing_to_capture_when_both_are_empty(capture_store):
    with pytest.raises(CaptureError):
        capture_store.capture("   ", media=[])
    assert log_events() == []


def test_a_reference_to_nothing_is_refused(capture_store):
    """The log is append-only, so a bad reference written once is wrong
    forever. Checked before the event, not after."""
    with pytest.raises(CaptureError):
        capture_store.capture("a thought", media=["2026-08/not-there.jpg"])
    assert log_events() == []


def test_media_survives_deleting_the_index(capture_store):
    """The claim the architecture rests on, now that entries carry files."""
    first = _stored(name="1111111111111111.jpg")
    second = _stored(name="2222222222222222.mp4")
    with_media = capture_store.capture("<gym> two of them", media=[first, second])
    capture_store.capture("no media here")

    before = capture_store.entries(limit=10)

    from backend.capture.config import INDEX_PATH

    INDEX_PATH.unlink()
    rebuilt = Store()
    rebuilt.start()
    try:
        assert rebuilt.entries(limit=10) == before
        # By id, not by position: two captures inside one second sort by id,
        # and ids are random.
        assert rebuilt.entry(with_media["id"])["media"] == [first, second]
    finally:
        rebuilt.close()


def test_an_entry_without_media_says_so_rather_than_omitting_it(capture_store):
    """The field is always present on the way out, so the client never has to
    check whether it exists before reading it."""
    entry = capture_store.capture("just words")

    assert entry["media"] == []
    # ...but the log line stays clean: omitted when unset, like every other
    # optional field the event carries.
    assert "media" not in log_events()[0]


def test_media_does_not_disturb_the_derived_fields(capture_store):
    ref = _stored()
    entry = capture_store.capture("<gym> squats \\heavy --todo log it", media=[ref])

    assert entry["folders"] == ["gym"]
    assert entry["patterns"] == ["heavy"]
    assert entry["todo_lines"] == [0]
    assert entry["media"] == [ref]


def test_an_entry_with_media_lands_in_its_folder(capture_store):
    """Nothing downstream needs to know an entry has a file on it."""
    folder = capture_store.create_folder("Gym")
    ref = _stored()
    capture_store.capture("<gym> squats", media=[ref])

    inside = capture_store.folder_detail(folder["id"])["entries"]
    assert len(inside) == 1 and inside[0]["media"] == [ref]


def test_media_can_arrive_after_the_entry(capture_store):
    """The capture bar's promise: the line is sent immediately and a two-
    gigabyte clip catches up. Making the entry wait would turn the fastest
    screen in the app into the slowest."""
    entry = capture_store.capture("<gym> squats")
    assert entry["media"] == []

    late = _stored(name="4444444444444444.mp4")
    updated = capture_store.attach_media(entry["id"], [late])

    assert updated["media"] == [late]
    assert [e["kind"] for e in log_events()] == ["capture", "attach-media"]


def test_attaching_twice_does_not_duplicate(capture_store):
    """A retried attach — the upload landed but the response was lost."""
    entry = capture_store.capture("a thought")
    ref = _stored()

    capture_store.attach_media(entry["id"], [ref])
    again = capture_store.attach_media(entry["id"], [ref])

    assert again["media"] == [ref]
    assert [e["kind"] for e in log_events()] == ["capture", "attach-media"]


def test_attachments_accumulate_in_the_order_they_landed(capture_store):
    entry = capture_store.capture("three files")
    refs = [_stored(name=f"{n}{n}{n}{n}{n}{n}{n}{n}{n}{n}{n}{n}{n}{n}{n}{n}.jpg") for n in "abc"]
    for ref in refs:
        capture_store.attach_media(entry["id"], [ref])

    assert capture_store.entry(entry["id"])["media"] == refs


def test_a_late_attachment_survives_the_index_being_deleted(capture_store):
    entry = capture_store.capture("<gym> squats")
    late = _stored(name="5555555555555555.mp4")
    capture_store.attach_media(entry["id"], [late])

    from backend.capture.config import INDEX_PATH

    INDEX_PATH.unlink()
    rebuilt = Store()
    rebuilt.start()
    try:
        assert rebuilt.entry(entry["id"])["media"] == [late]
    finally:
        rebuilt.close()


def test_attaching_to_nothing_is_refused(capture_store):
    ref = _stored()
    with pytest.raises(CaptureError):
        capture_store.attach_media("nosuchentry", [ref])


@pytest.fixture
def client(capture_store):
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.capture.store import store as global_store

    global_store.reindex()
    with TestClient(app) as test_client:
        yield test_client


def test_upload_then_capture_over_the_wire(client):
    """The round trip the capture bar actually makes: file first, entry second."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (1, 2, 3)).save(buf, format="PNG")

    upload = client.post("/api/media?name=shot.png", content=buf.getvalue())
    assert upload.status_code == 200, upload.text
    ref = upload.json()["path"]

    created = client.post(
        "/api/capture/entries", json={"raw_text": "<gym> squats", "media": [ref]}
    )
    assert created.status_code == 201, created.text
    assert created.json()["entry"]["media"] == [ref]


def test_the_wire_refuses_a_reference_to_nothing(client):
    r = client.post(
        "/api/capture/entries", json={"raw_text": "x", "media": ["2026-08/ghost.jpg"]}
    )
    assert r.status_code == 400
