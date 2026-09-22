"""Finding a past entry by what it says.

Before this, every read in capture's API was scoped by when or where
something was filed — a day, a span, a folder — and nothing let you ask "what
did I write about X". `search_entries` is a plain case-insensitive substring
match against `clean_text`, not a virtual FTS table: nothing in this index is
stored beyond `raw_text` either way, and a scan over one person's archive is
cheap enough that a second index would be solving a problem this app does not
have.
"""
from __future__ import annotations

import pytest

from backend.capture import eventlog, index


def test_search_finds_a_word_in_an_entry(capture_store):
    capture_store.capture("worked on the C major scale today")
    capture_store.capture("unrelated entry about breakfast")

    found = capture_store.search("major scale")
    assert len(found) == 1
    assert "major scale" in found[0]["clean_text"]


def test_search_is_case_insensitive(capture_store):
    capture_store.capture("Practiced Arpeggios for an hour")
    assert len(capture_store.search("arpeggios")) == 1


def test_search_reads_clean_text_not_the_stripped_directive(capture_store):
    """A directive and a todo are stripped out of what a search should ever
    surface — the same text a search finds is the text the log shows back."""
    capture_store.capture("--todo practice scales --work")
    assert capture_store.search("todo") == []
    assert capture_store.search("work") == []
    assert len(capture_store.search("practice scales")) == 1


def test_search_results_carry_home_folder(capture_store):
    """A result is somewhere to land, not just a snippet — the same
    resolution `home_folder()` gives the banner."""
    folder = capture_store.create_folder("Guitar")
    capture_store.map_tag(folder["id"], "guitar")
    capture_store.capture("<guitar> practiced scales")
    capture_store.capture("scales with no folder")

    found = {e["raw_text"]: e["home_folder"] for e in capture_store.search("scales")}
    assert found["<guitar> practiced scales"] == folder["id"]
    assert found["scales with no folder"] is None


def test_search_scopes_to_a_folder(capture_store):
    folder = capture_store.create_folder("Guitar")
    capture_store.capture("<guitar> practiced scales")
    capture_store.capture("practiced scales elsewhere")
    capture_store.map_tag(folder["id"], "guitar")

    scoped = capture_store.search("scales", index.InFolder(folder["id"]))
    assert len(scoped) == 1
    assert scoped[0]["folders"] == ["guitar"]


def test_search_scopes_to_the_unfiled_pile(capture_store):
    """The pile is an album you can open, so it is one you can search.

    It could not be, before scopes: the wire spelled the pile `None` and
    `search_entries` took `None` for "do not filter", so this search returned
    the filed entry as well and looked like it had worked. That is the whole
    argument for the scope being a value with a name — the two meanings were
    indistinguishable in the signature and the wrong one came back quietly.
    """
    folder = capture_store.create_folder("Guitar")
    capture_store.capture("<guitar> practiced scales")
    capture_store.capture("practiced scales elsewhere")
    capture_store.map_tag(folder["id"], "guitar")

    pile = capture_store.search("scales", index.UNFILED)
    assert [e["raw_text"] for e in pile] == ["practiced scales elsewhere"]
    assert len(capture_store.search("scales")) == 2


def test_search_scopes_to_a_day_span(capture_store):
    capture_store.capture("scales today")
    day = capture_store.entries(limit=1)[0]["day"]

    assert len(capture_store.search("scales", start=day, end=day)) == 1
    assert capture_store.search("scales", start="1999-01-01", end="1999-01-02") == []


def test_a_percent_sign_is_not_a_wildcard(capture_store):
    """`%` and `_` are LIKE metacharacters. A search for one must match itself
    rather than acting as a pattern over everything else in the log."""
    capture_store.capture("scored 90% today")
    capture_store.capture("a completely different entry")

    assert len(capture_store.search("90%")) == 1


def test_an_empty_query_finds_nothing(capture_store):
    capture_store.capture("anything at all")
    assert capture_store.search("   ") == []


def test_search_is_newest_first(capture_store):
    """`ts` is second-resolution and a capture's id is a random uuid, so two
    lines written in the same wall-clock second need an explicit, distinct
    `ts` to test ordering by — the same reason
    `test_out_of_order_and_duplicated_lines_fold_the_same` writes events by
    hand instead of calling `capture()` back to back."""
    eventlog.append(
        eventlog.CAPTURE, eventlog.new_id(), text="scales, take one",
        ts="2026-01-01T10:00:00+00:00", day="2026-01-01",
    )
    eventlog.append(
        eventlog.CAPTURE, eventlog.new_id(), text="scales, take two",
        ts="2026-01-01T10:00:05+00:00", day="2026-01-01",
    )
    capture_store.reindex()

    found = capture_store.search("scales")
    assert [e["raw_text"] for e in found] == ["scales, take two", "scales, take one"]


# ── The wire ──────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    """The app over a clean capture dir — see `test_capture_time.py`, which
    explains why `data_dir` is not enough."""
    import shutil

    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.capture import config as capture_config

    shutil.rmtree(capture_config.CAPTURE_DIR, ignore_errors=True)
    capture_config.ensure_dirs()
    with TestClient(app) as test_client:
        yield test_client


def test_the_wire_scopes_a_search_to_the_pile(client):
    """`?folder=unfiled` is the pile, at the wire as everywhere else.

    This is where the bug was: the route translated `unfiled` to `None` on its
    way down, and `None` was what this read took for "do not filter". The
    answer came back looking right — entries, newest first, some of them even
    correct — which is why it wanted a check at the layer that was wrong.
    """
    made = client.post("/api/capture/folders", json={"name": "Guitar"})
    folder_id = made.json()["folder"]["id"]
    client.patch(f"/api/capture/folders/{folder_id}", json={"add_tags": ["guitar"]})
    client.post("/api/capture/entries", json={"raw_text": "<guitar> practiced scales"})
    client.post("/api/capture/entries", json={"raw_text": "practiced scales elsewhere"})

    everything = client.get("/api/capture/search?q=scales").json()
    assert len(everything["entries"]) == 2

    pile = client.get("/api/capture/search?q=scales&folder=unfiled").json()
    assert [e["raw_text"] for e in pile["entries"]] == ["practiced scales elsewhere"]

    filed = client.get(f"/api/capture/search?q=scales&folder={folder_id}").json()
    assert [e["raw_text"] for e in filed["entries"]] == ["<guitar> practiced scales"]
