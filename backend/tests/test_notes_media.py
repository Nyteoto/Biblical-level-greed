"""Notes and media.

The distinction these tests exist to protect: a **note** is mutable knowledge
in a file, a **journal entry** is an immutable event in the log. Conflating
them would have cost the append-only property that sync, XP and calibration all
depend on, so the tests check the separation as much as the behaviour.
"""
from __future__ import annotations

import io

import pytest

from backend.app import config, eventlog, media, notes
from backend.app.notes import NoteError


def _png(size=(40, 30), colour=(200, 40, 40)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="PNG")
    return buf.getvalue()


def _heic(size=(40, 30), colour=(40, 90, 200)) -> bytes:
    """What an iPhone actually sends. Real HEIC bytes, not a PNG standing in
    for one — the difference is what let the import ship broken."""
    from PIL import Image
    from pillow_heif import register_heif_opener

    register_heif_opener()
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="HEIF")
    return buf.getvalue()


# -- notes ------------------------------------------------------------------


def test_a_missing_note_is_empty_not_an_error(data_dir):
    assert notes.read("guitar", "hands-and-tone") == ""


def test_a_note_round_trips(data_dir):
    notes.write("guitar", "hands-and-tone", "# Picking\n\nkeep the wrist loose")
    assert notes.read("guitar", "hands-and-tone").startswith("# Picking")


def test_a_note_is_mutable_unlike_a_journal_entry(data_dir):
    """The whole reason notes are files and not events."""
    notes.write("guitar", "hands-and-tone", "first thought")
    notes.write("guitar", "hands-and-tone", "revised thought")
    assert notes.read("guitar", "hands-and-tone") == "revised thought"


def test_append_keeps_a_blank_line_between_blocks(data_dir):
    notes.write("guitar", "hands-and-tone", "existing")
    notes.append("guitar", "hands-and-tone", "![photo](/media/x.jpg)")
    assert notes.read("guitar", "hands-and-tone") == (
        "existing\n\n![photo](/media/x.jpg)\n"
    )


def test_append_to_an_empty_note_does_not_lead_with_blank_lines(data_dir):
    notes.append("guitar", "hands-and-tone", "first")
    assert notes.read("guitar", "hands-and-tone") == "first\n"


def test_it_lands_where_a_human_can_find_it(data_dir):
    notes.write("guitar", "hands-and-tone", "x")
    assert (config.DATA_DIR / "notes" / "guitar" / "hands-and-tone.md").is_file()


@pytest.mark.parametrize(
    "domain,node",
    [("../etc", "x"), ("guitar", "../../etc/passwd"), ("guitar", "a/b"), ("", "x")],
)
def test_ids_that_would_escape_the_notes_directory_are_refused(data_dir, domain, node):
    """Both ids come straight off the URL, so they are validated rather than
    trusted — otherwise `../` writes wherever it likes."""
    with pytest.raises(NoteError):
        notes.write(domain, node, "x")


def test_an_absurdly_large_note_is_refused(data_dir):
    with pytest.raises(NoteError):
        notes.write("guitar", "hands-and-tone", "x" * (notes.MAX_BYTES + 1))


def test_writing_a_note_leaves_the_event_log_alone(data_dir):
    """A note is not an event. Nothing about it should reach the log."""
    notes.write("guitar", "hands-and-tone", "some knowledge")
    events, _ = eventlog.read_all()
    assert events == []


# -- media ------------------------------------------------------------------


def test_an_image_is_stored_and_addressable(data_dir):
    rel = media.save(_png(), "2026-07-20")
    assert rel.startswith("2026-07/") and rel.endswith(".jpg")
    assert media.path_for(rel) is not None


def test_images_are_grouped_by_month_like_the_log(data_dir):
    rel = media.save(_png(), "2026-11-03")
    assert rel.startswith("2026-11/")


def test_a_large_photo_is_downscaled(data_dir):
    """A 5 MB phone photo should not be stored as one."""
    from PIL import Image

    rel = media.save(_png(size=(5000, 4000)), "2026-07-20")
    with Image.open(media.path_for(rel)) as out:
        assert max(out.size) == media.MAX_EDGE
        assert out.size == (media.MAX_EDGE, int(media.MAX_EDGE * 4000 / 5000))


def test_a_small_image_is_not_upscaled(data_dir):
    from PIL import Image

    rel = media.save(_png(size=(40, 30)), "2026-07-20")
    with Image.open(media.path_for(rel)) as out:
        assert out.size == (40, 30)


def test_output_is_jpeg_whatever_went_in(data_dir):
    """A browser cannot draw HEIC, so nothing may leave here as anything else."""
    from PIL import Image

    rel = media.save(_png(), "2026-07-20")
    with Image.open(media.path_for(rel)) as out:
        assert out.format == "JPEG"


def test_an_iphone_heic_is_accepted(data_dir):
    """Pillow cannot read HEIC unaided, and an iPhone shoots it by default —
    so this is the whole photo path, and it failed at `Image.open` until
    pillow-heif was registered. The old test asserted HEIC in its docstring
    and passed a PNG, which is why nobody noticed.
    """
    from PIL import Image

    rel = media.save(_heic(size=(60, 40)), "2026-07-20")
    with Image.open(media.path_for(rel)) as out:
        assert out.format == "JPEG"
        assert out.size == (60, 40)


def test_a_heic_upload_survives_the_endpoint(write_domain, conn):
    """End to end, the way an iPhone actually posts it: raw HEIC body, straight
    at the endpoint. Every other endpoint test sends a PNG, which no phone
    sends, so all of them passed while the real path was broken."""
    from fastapi.testclient import TestClient

    write_domain(
        "h",
        """
id = "h"
title = "H"
priority = 1

[[node]]
id = "first"
title = "First"
tier = 1
estimate = 5
""",
    )
    from backend.app.main import app
    from backend.app.store import store

    with TestClient(app) as client:
        store.reload_domains()
        r = client.post(
            "/api/media?domain=h&node=first",
            content=_heic(),
            headers={"content-type": "image/heic"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["attached_to_note"] is True
        assert "![photo](/media/" in notes.read("h", "first")


def test_exif_orientation_is_applied_then_dropped(data_dir):
    """A sideways photo in the journal is worse than a slightly larger file,
    and the rest of EXIF is location and device data nobody asked to keep."""
    from PIL import Image

    buf = io.BytesIO()
    img = Image.new("RGB", (60, 20), (10, 200, 10))
    exif = img.getexif()
    exif[274] = 6  # rotate 90° CW
    img.save(buf, format="JPEG", exif=exif)

    rel = media.save(buf.getvalue(), "2026-07-20")
    with Image.open(media.path_for(rel)) as out:
        assert out.size == (20, 60)  # transposed
        assert not dict(out.getexif())  # and the tags are gone


def test_rubbish_is_refused_rather_than_stored(data_dir):
    with pytest.raises(media.MediaError):
        media.save(b"this is not an image", "2026-07-20")


def test_an_empty_upload_is_refused(data_dir):
    with pytest.raises(media.MediaError):
        media.save(b"", "2026-07-20")


@pytest.mark.parametrize("escape", ["../../etc/passwd", "/etc/passwd", "../secrets"])
def test_media_paths_cannot_escape_the_media_root(data_dir, escape):
    assert media.path_for(escape) is None


def test_a_photo_can_be_appended_to_a_note(data_dir):
    """End to end at the module level: an image lands on disk and the note
    gains a markdown reference to it."""
    rel = media.save(_png(), "2026-07-20")
    notes.append("guitar", "hands-and-tone", f"![whiteboard](/media/{rel})")
    text = notes.read("guitar", "hands-and-tone")
    assert f"](/media/{rel})" in text
    assert media.path_for(rel) is not None


# -- the API surface --------------------------------------------------------


def test_every_endpoint_notes_and_media_need_is_registered():
    """Added after a cleanup edit silently deleted the notes and media routes at
    once: the tests all passed, because none of them asked the app which routes
    it actually has."""
    from backend.app.main import app

    paths = {r.path for r in app.routes}
    for required in (
        "/api/media",
        "/media/{relative:path}",
        "/api/domains/{domain_id}/notes",
        "/api/domains/{domain_id}/notes/{slug}",
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


def test_an_unknown_domain_stores_nothing(write_domain, conn):
    """A mistyped domain used to save the image and *then* 404, leaving a file
    nothing referenced — indistinguishable from a real photo afterwards."""
    from fastapi.testclient import TestClient

    write_domain(
        "k",
        """
id = "k"
title = "K"
priority = 1

[[node]]
id = "first"
title = "First"
tier = 1
estimate = 5
""",
    )
    from backend.app.main import app
    from backend.app.store import store

    with TestClient(app) as client:
        store.reload_domains()
        before = list(media.media_dir().rglob("*.jpg"))
        r = client.post(
            "/api/media?domain=nope-not-a-domain&node=first",
            content=_png(),
            headers={"content-type": "image/png"},
        )
        assert r.status_code == 404, r.text
        assert list(media.media_dir().rglob("*.jpg")) == before, "orphan file written"


# -- storage ----------------------------------------------------------------


def test_storage_parts_sum_to_the_total(data_dir):
    """The breakdown has to account for everything under data/, or the page is
    quietly lying about where the space went."""
    from backend.app import storage

    notes.write("guitar", "hands-and-tone", "x" * 500)
    media.save(_png(), "2026-07-20")

    report = storage.report()
    assert report["total_bytes"] == sum(p["bytes"] for p in report["parts"])
    assert report["total_files"] == sum(p["files"] for p in report["parts"])


def test_storage_counts_photos_separately(data_dir):
    """Media is the one bucket git does not cover, so it is the number that
    actually matters on this page."""
    from backend.app import storage

    media.save(_png(size=(400, 300)), "2026-07-20")
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


# -- domain notes -----------------------------------------------------------


def test_a_domain_folder_starts_empty(data_dir):
    assert notes.listing("guitar") == []


def test_creating_a_note_titles_the_file_and_the_document(data_dir):
    slug = notes.create("guitar", "Tone chasing, week 3")
    assert slug == "tone-chasing-week-3"
    assert notes.read("guitar", slug).startswith("# Tone chasing, week 3")


def test_two_notes_with_the_same_title_do_not_collide(data_dir):
    first = notes.create("guitar", "Practice log")
    second = notes.create("guitar", "Practice log")
    assert first != second
    assert len(notes.listing("guitar")) == 2


def test_the_listing_reads_the_title_from_the_document(data_dir):
    """A note that names itself should not also be named by its filename."""
    notes.write("guitar", "whatever", "# The real title\n\nbody text here\n")
    entry = notes.listing("guitar")[0]
    assert entry["title"] == "The real title"
    assert entry["preview"] == "body text here"


def test_old_per_node_notes_are_readable_as_domain_notes(data_dir):
    """The migration is that there isn't one: `chinese/pinyin-tones.md` was a
    node note yesterday and reads as a titled document today."""
    notes.write("chinese", "pinyin-tones", "third tone sandhi is the whole thing")
    entry = notes.listing("chinese")[0]
    assert entry["slug"] == "pinyin-tones"
    assert entry["title"] == "Pinyin tones"


def test_newest_note_leads_the_list(data_dir):
    import os
    import time

    notes.write("guitar", "older", "x")
    time.sleep(0.01)
    notes.write("guitar", "newer", "y")
    os.utime(notes.path_for("guitar", "newer"), (time.time(), time.time()))
    assert [n["slug"] for n in notes.listing("guitar")][0] == "newer"


@pytest.mark.parametrize("bad", ["../etc", "a/b", ""])
def test_note_ids_that_would_escape_the_folder_are_refused(data_dir, bad):
    with pytest.raises(NoteError):
        notes.write("guitar", bad, "x")


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
