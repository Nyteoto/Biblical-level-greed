"""The HTTP surface and disk accounting.

What is left of a file that used to be about notes, then about a photo
pipeline, then about unlocking and the tool shelf. The notes system went when
Trophic's capture bar became the only place text is written; media ingest moved
to test_media.py when it stopped being a pipeline and became a blob store; the
tech tree's half went with the tech tree.

The route-registration guard below is the part worth keeping through all of it
— it exists because a cleanup edit once deleted a working route and nothing
failed. This removal is exactly that kind of edit, which is the point.
"""
from __future__ import annotations

import io

from backend.app import media


def _png(size=(40, 30), colour=(200, 40, 40)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="PNG")
    return buf.getvalue()


def _store_a_file() -> None:
    """One file in the media bucket. Written straight to disk rather than
    through the store, because these are disk-accounting tests and ingest has
    its own suite in test_media.py."""
    target = media.media_dir() / "2026-07"
    target.mkdir(parents=True, exist_ok=True)
    (target / "aaaabbbbccccdddd.jpg").write_bytes(_png(size=(400, 300)))


# -- the API surface --------------------------------------------------------


def test_every_endpoint_the_app_needs_is_registered():
    """Added after a cleanup edit silently deleted two working routes at once:
    the tests all passed, because none of them asked the app which routes it
    actually has."""
    from backend.app.main import app

    # `include_router` (capture's routes) contributes an entry that holds
    # routes rather than being one, so this has to descend rather than assume
    # every child of `app.routes` has a path of its own.
    def paths_of(routes) -> set[str]:
        found: set[str] = set()
        for route in routes:
            if hasattr(route, "path"):
                found.add(route.path)
            included = getattr(route, "original_router", None)
            found |= paths_of(getattr(included, "routes", ()))
            found |= paths_of(getattr(route, "routes", ()))
        return found

    paths = paths_of(app.routes)
    for required in (
        "/api/media",
        "/media/{relative:path}",
        "/api/health",
        "/api/storage",
        "/api/backup",
        "/api/version",
        "/api/capture/entries",
        "/api/capture/folders",
        "/api/capture/shelf",
    ):
        assert required in paths, f"{required} is not registered"


def test_no_tech_tree_route_survives():
    """The other direction, and the reason it is worth asserting: a route left
    behind would be a live endpoint reading modules that no longer exist, and
    it would 500 rather than 404 — which reads as a broken app rather than a
    removed feature."""
    from backend.app.main import app

    def paths_of(routes) -> set[str]:
        found: set[str] = set()
        for route in routes:
            if hasattr(route, "path"):
                found.add(route.path)
            included = getattr(route, "original_router", None)
            found |= paths_of(getattr(included, "routes", ()))
            found |= paths_of(getattr(route, "routes", ()))
        return found

    gone = [p for p in paths_of(app.routes) if "/domains" in p or "/dashboard" in p]
    assert not gone, f"tech tree routes still registered: {gone}"


def test_an_unknown_api_path_404s_rather_than_serving_the_app_shell():
    """The SPA fallback must not swallow /api/. Returning 200 + HTML for a
    mistyped endpoint makes a client report success while doing nothing."""
    from fastapi.testclient import TestClient

    from backend.app.main import app

    with TestClient(app) as client:
        assert client.get("/api/definitely-not-a-thing").status_code == 404


# -- storage ----------------------------------------------------------------


def test_storage_parts_sum_to_the_total(data_dir):
    """The breakdown has to account for everything under data/, or the page is
    quietly lying about where the space went."""
    from backend.app import storage

    _store_a_file()

    report = storage.report()
    assert report["total_bytes"] == sum(p["bytes"] for p in report["parts"])
    assert report["total_files"] == sum(p["files"] for p in report["parts"])


def test_storage_counts_photos_separately(data_dir):
    """Media is the one bucket git does not cover, so it is the number that
    actually matters on this page."""
    from backend.app import storage

    _store_a_file()
    parts = {p["key"]: p for p in storage.report()["parts"]}
    assert parts["media"]["files"] == 1
    assert parts["media"]["bytes"] > 0


def test_storage_survives_a_missing_data_dir(tmp_path, monkeypatch):
    """Opening settings on a fresh install must not 500."""
    from backend.app import config, storage

    empty = tmp_path / "nothing"
    monkeypatch.setattr(config, "DATA_DIR", empty)
    monkeypatch.setattr(config, "MEDIA_DIR", empty / "media")
    monkeypatch.setattr(storage, "DATA_DIR", empty)
    monkeypatch.setattr(storage, "CAPTURE_LOG_DIR", empty / "capture" / "log")
    monkeypatch.setattr(storage, "CAPTURE_INDEX_PATH", empty / "capture" / "index.sqlite")

    report = storage.report()
    assert report["total_bytes"] == 0
    assert all(p["bytes"] == 0 for p in report["parts"])


# -- the disk itself --------------------------------------------------------


def test_a_disk_that_cannot_be_written_says_so(capture_store, monkeypatch):
    """A full disk, an unmounted --data-dir or a directory that lost its
    permissions are not bugs, and they used to surface as a bare 500 — which
    tells the user the app is broken when the app is fine and the disk is not.
    """
    from fastapi.testclient import TestClient

    from backend.capture import eventlog
    from backend.app.main import app

    def no_room(*args, **kwargs):
        raise OSError(28, "No space left on device")

    with TestClient(app, raise_server_exceptions=False) as client:
        monkeypatch.setattr(eventlog, "append", no_room)
        r = client.post("/api/capture/entries", json={"raw_text": "anything at all"})

    assert r.status_code == 507, r.text
    detail = r.json()["detail"]
    assert "No space left on device" in detail
    assert "Nothing was saved" in detail
