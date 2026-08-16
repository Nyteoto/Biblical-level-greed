"""The HTTP surface, disk accounting, unlocking and the tool shelf.

What is left of a file that used to be about notes. The markdown notes system
went when Trophic's capture bar became the only place text is written in this
app; media ingest moved to test_media.py when it stopped being a photo
pipeline and became a blob store. The route-registration guard below is the
part worth keeping either way — it exists because a cleanup edit once deleted
a working route and nothing failed.
"""
from __future__ import annotations

import io

import pytest

from backend.app import eventlog, media


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


def _heic(size=(40, 30), colour=(40, 90, 200)) -> bytes:
    """What an iPhone actually sends. Real HEIC bytes, not a PNG standing in
    for one — the difference is what let the import ship broken."""
    from PIL import Image
    from pillow_heif import register_heif_opener

    register_heif_opener()
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="HEIF")
    return buf.getvalue()


# -- the API surface --------------------------------------------------------


def test_every_endpoint_notes_and_media_need_is_registered():
    """Added after a cleanup edit silently deleted the notes and media routes at
    once: the tests all passed, because none of them asked the app which routes
    it actually has."""
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
        "/api/domains/{domain_id}/tools",
    ):
        assert required in paths, f"{required} is not registered"


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
    monkeypatch.setattr(storage, "DATA_DIR", empty)
    monkeypatch.setattr(storage, "LOG_DIR", empty / "log")
    monkeypatch.setattr(storage, "DOMAINS_DIR", empty / "domains")
    monkeypatch.setattr(storage, "INDEX_PATH", empty / "index.sqlite")
    # Capture's half of the same data root. The report names it separately now,
    # so a fresh install has to survive its paths being absent too.
    monkeypatch.setattr(storage, "CAPTURE_LOG_DIR", empty / "capture" / "log")
    monkeypatch.setattr(storage, "CAPTURE_INDEX_PATH", empty / "capture" / "index.sqlite")

    report = storage.report()
    assert report["total_bytes"] == 0
    assert all(p["bytes"] == 0 for p in report["parts"])


# -- unlocking, through the API ---------------------------------------------


def _priced_domain(write_domain):
    write_domain(
        "u",
        """
id = "u"
title = "U"
priority = 1

[[node]]
id = "first"
title = "First"
tier = 1
estimate = 1

[[node]]
id = "second"
title = "Second"
tier = 2
estimate = 5
requires = ["first"]
""",
    )


def test_unlocking_without_the_xp_is_refused(write_domain, conn):
    """The bank is checked server-side. A client that hides the button is not a
    guarantee, and going negative is the one thing this economy must not do."""
    from fastapi.testclient import TestClient

    _priced_domain(write_domain)
    from backend.app.main import app
    from backend.app.store import store

    with TestClient(app) as client:
        store.reload_domains()
        client.post("/api/domains/u/nodes/first/complete")
        r = client.post("/api/domains/u/nodes/second/unlock")
        assert r.status_code == 409
        assert "short" in r.json()["detail"]


def test_unlocking_spends_the_bank_and_leaves_the_level(write_domain, conn):
    from fastapi.testclient import TestClient

    _priced_domain(write_domain)
    from backend.app.main import app
    from backend.app.store import store

    with TestClient(app) as client:
        store.reload_domains()
        client.post("/api/domains/u/nodes/first/complete")
        # Enough banked to afford tier II.
        eventlog.append("u", "first", eventlog.SESSION, day="2026-07-01")
        store.reindex()

        before = client.get("/api/dashboard").json()["xp"]
        eventlog.append("u", "first", eventlog.UNLOCK, day="2026-07-02", value=0.0)
        store.reindex()

        after = client.get("/api/dashboard").json()["xp"]
        assert after["total"] == before["total"]
        assert after["level"] == before["level"]


def test_a_tier_one_node_cannot_be_bought(write_domain, conn):
    from fastapi.testclient import TestClient

    _priced_domain(write_domain)
    from backend.app.main import app
    from backend.app.store import store

    with TestClient(app) as client:
        store.reload_domains()
        r = client.post("/api/domains/u/nodes/first/unlock")
        assert r.status_code == 409
        assert "costs nothing" in r.json()["detail"]


def test_unlocking_before_the_prerequisite_is_refused(write_domain, conn):
    """The price is not the only gate, and it is not the first one."""
    from fastapi.testclient import TestClient

    _priced_domain(write_domain)
    from backend.app.main import app
    from backend.app.store import store

    with TestClient(app) as client:
        store.reload_domains()
        r = client.post("/api/domains/u/nodes/second/unlock")
        assert r.status_code == 409
        assert "first" in r.json()["detail"]


# -- tools ------------------------------------------------------------------


def test_a_tool_shelf_starts_empty(data_dir):
    from backend.app import tools

    assert tools.read("guitar") == []


def test_a_tool_needs_a_name(data_dir):
    from backend.app import tools
    from backend.app.tools import ToolError

    with pytest.raises(ToolError):
        tools.add("guitar", {"model": "Stratocaster"})


def test_a_tool_round_trips_every_field(data_dir):
    from backend.app import tools

    made = tools.add(
        "guitar",
        {
            "name": "The Strat",
            "image": "2026-07/abc.jpg",
            "price_kind": "paid",
            "price": "700",
            "acquired": "2019-04-02",
            "type": "electric guitar",
            "model": "Fender Player Stratocaster",
        },
    )
    stored = tools.read("guitar")[0]
    assert stored["id"] == made["id"]
    assert stored["model"] == "Fender Player Stratocaster"
    assert stored["retired"] == ""


def test_retiring_is_a_date_not_a_delete(data_dir):
    """What a domain used to be practised on is the interesting part of the
    list, so retirement must never remove the profile."""
    from backend.app import tools

    made = tools.add("guitar", {"name": "First amp"})
    tools.update("guitar", made["id"], {"retired": "2024-01-09"})
    shelf = tools.read("guitar")
    assert len(shelf) == 1
    assert shelf[0]["retired"] == "2024-01-09"


def test_an_unknown_price_kind_falls_back_to_paid(data_dir):
    from backend.app import tools

    made = tools.add("guitar", {"name": "Pad", "price_kind": "nonsense"})
    assert made["price_kind"] == "paid"


def test_tools_survive_a_reread(data_dir):
    from backend.app import tools

    tools.add("guitar", {"name": "Capo", "price_kind": "diy"})
    tools.add("guitar", {"name": "Tuner"})
    assert [t["name"] for t in tools.read("guitar")] == ["Capo", "Tuner"]


def test_patching_one_field_leaves_the_rest_alone(write_domain, conn):
    """A PATCH is partial. Pydantic defaults made it a full overwrite: sending
    only a photo arrived as an empty name, which failed validation, so the photo
    never saved and every other field was cleared on any edit that did land."""
    from fastapi.testclient import TestClient

    from backend.app import tools
    from backend.app.main import app
    from backend.app.store import store

    _priced_domain(write_domain)
    with TestClient(app) as client:
        store.reload_domains()
        made = tools.add(
            "u",
            {"name": "The Strat", "type": "electric", "model": "Player Strat"},
        )
        r = client.patch(
            f"/api/domains/u/tools/{made['id']}",
            json={"image": "/media/2026-07/photo.jpg"},
        )
        assert r.status_code == 200, r.text
        after = r.json()["tools"][0]
        assert after["image"] == "/media/2026-07/photo.jpg"
        assert after["name"] == "The Strat"
        assert after["type"] == "electric"
        assert after["model"] == "Player Strat"


def test_clearing_a_field_on_purpose_still_works(write_domain, conn):
    """`exclude_unset` must not make empty strings unsendable — coming back into
    service is exactly a patch that sets `retired` to ""."""
    from fastapi.testclient import TestClient

    from backend.app import tools
    from backend.app.main import app
    from backend.app.store import store

    _priced_domain(write_domain)
    with TestClient(app) as client:
        store.reload_domains()
        made = tools.add("u", {"name": "Old amp", "retired": "2024-01-09"})
        r = client.patch(f"/api/domains/u/tools/{made['id']}", json={"retired": ""})
        assert r.status_code == 200, r.text
        assert r.json()["tools"][0]["retired"] == ""
        assert r.json()["tools"][0]["name"] == "Old amp"


def test_a_tool_carries_a_description(data_dir):
    from backend.app import tools

    made = tools.add(
        "guitar",
        {"name": "Red-Guy", "description": "Auto-ranging, has NCV. Leads are stiff."},
    )
    assert tools.read("guitar")[0]["description"] == made["description"]


def test_a_diy_tool_can_still_record_what_it_cost(data_dir):
    """Making a thing costs money too — the price is not a purchase field."""
    from backend.app import tools

    made = tools.add("guitar", {"name": "Cable", "price_kind": "diy", "price": "~$12 in parts"})
    assert made["price_kind"] == "diy"
    assert made["price"] == "~$12 in parts"


def test_a_disk_that_cannot_be_written_says_so(write_domain, monkeypatch):
    """A full disk, an unmounted --data-dir or a directory that lost its
    permissions are not bugs, and they used to surface as a bare 500 — which
    tells the user the app is broken when the app is fine and the disk is not.
    """
    from fastapi.testclient import TestClient

    from backend.app import eventlog
    from backend.app.main import app
    from backend.app.store import store

    write_domain(
        "d",
        'id = "d"\ntitle = "D"\npriority = 1\n\n'
        '[[node]]\nid = "n"\ntitle = "N"\ntier = 1\nestimate = 2\n',
    )

    def no_room(*args, **kwargs):
        raise OSError(28, "No space left on device")

    with TestClient(app, raise_server_exceptions=False) as client:
        store.reload_domains()
        monkeypatch.setattr(eventlog, "append", no_room)
        r = client.post("/api/domains/d/nodes/n/session")

    assert r.status_code == 507, r.text
    detail = r.json()["detail"]
    assert "No space left on device" in detail
    assert "Nothing was saved" in detail
