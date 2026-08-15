"""CSV import: somebody else's rows become ordinary lines in this log.

The reader and the date parser have 48 golden fixtures between them, so what
is tested here is the seam the port invented — folding the tag and pattern
columns back into the text, because this app has nowhere else to keep them.
"""
from __future__ import annotations

import json

import pytest

from backend.capture.import_csv import CsvRow, compose_line


def log_lines() -> list[dict]:
    from backend.capture.config import LOG_DIR

    out = []
    for path in sorted(LOG_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def test_the_tag_columns_are_written_into_the_line(capture_store):
    """Otherwise they would be gone on the next rebuild: this log has no
    column to put them in, only the text."""
    result = capture_store.import_csv(
        "time,text,tags,patterns\n"
        "2026-03-01,shipped the importer,deploy,win\n"
    )

    assert result == {"imported": 1, "skipped": 0, "header": "full"}
    entry = capture_store.entries(limit=1)[0]
    assert entry["raw_text"] == "shipped the importer <deploy> \\win"
    assert entry["folders"] == ["deploy"]
    assert entry["patterns"] == ["win"]


def test_syntax_already_in_the_text_is_not_written_twice(capture_store):
    """A file this app exported has to round-trip without growing."""
    assert compose_line(
        CsvRow(time="", text="<deploy> shipped it \\win", tags=["deploy"], patterns=["win"])
    ) == "<deploy> shipped it \\win"


def test_imported_rows_keep_their_own_dates(capture_store):
    capture_store.import_csv(
        "time,text\n2026-03-01 09:30,an old thought\n2026-04-02,a newer one\n"
    )

    days = sorted(e["day"] for e in capture_store.entries(limit=10))
    assert days == ["2026-03-01", "2026-04-02"]
    # The day on the event and the day derived from its timestamp agree, or
    # the log and the index would disagree about which day it belongs to.
    for event in log_lines():
        assert event["ts"].startswith(event["day"])


def test_a_row_whose_time_makes_no_sense_still_keeps_its_words(capture_store):
    capture_store.import_csv("time,text\nwhenever,the words are the point\n")

    entries = capture_store.entries(limit=10)
    assert len(entries) == 1
    assert entries[0]["clean_text"] == "the words are the point"


def test_a_headerless_file_ignores_the_tag_columns(capture_store):
    """The source refuses to guess at the shape of a file it did not write."""
    capture_store.import_csv("2026-03-01,a bare row,deploy,win\n")

    entry = capture_store.entries(limit=1)[0]
    assert entry["raw_text"] == "a bare row"
    assert entry["folders"] == []


def test_an_oversized_row_is_skipped_and_counted(capture_store):
    from backend.capture.config import MAX_RAW_LEN

    result = capture_store.import_csv(
        f"time,text\n2026-03-01,{'x' * (MAX_RAW_LEN + 1)}\n2026-03-02,fine\n"
    )

    assert result["imported"] == 1 and result["skipped"] == 1
    assert len(capture_store.entries(limit=10)) == 1


def test_imported_entries_land_in_folders_like_any_other(capture_store):
    """The whole reason the syntax goes back into the text: an import is not
    a second kind of entry, so nothing downstream needs to know about it."""
    folder = capture_store.create_folder("Work")
    capture_store.map_tag(folder["id"], "deploy")

    capture_store.import_csv("time,text,tags\n2026-03-01,shipped it,deploy\n")

    assert len(capture_store.folder_detail(folder["id"])["entries"]) == 1


def test_importing_nothing_writes_nothing(capture_store):
    assert capture_store.import_csv("") == {
        "imported": 0,
        "skipped": 0,
        "header": "none",
    }
    assert log_lines() == []


@pytest.fixture
def client(capture_store):
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.capture.store import store as global_store

    global_store.reindex()
    with TestClient(app) as test_client:
        yield test_client


def test_import_over_http(client):
    r = client.post(
        "/api/capture/import",
        json={"csv": "time,text,tags\n2026-03-01,over the wire,deploy\n"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1
