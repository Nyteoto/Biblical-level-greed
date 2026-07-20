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
    """An iPhone sends HEIC; a browser cannot draw it."""
    from PIL import Image

    rel = media.save(_png(), "2026-07-20")
    with Image.open(media.path_for(rel)) as out:
        assert out.format == "JPEG"


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
    """The Shortcut flow, end to end at the module level: an image lands on
    disk and the note gains a markdown reference to it."""
    rel = media.save(_png(), "2026-07-20")
    notes.append("guitar", "hands-and-tone", f"![whiteboard](/media/{rel})")
    text = notes.read("guitar", "hands-and-tone")
    assert f"](/media/{rel})" in text
    assert media.path_for(rel) is not None


# -- the API surface --------------------------------------------------------


def test_every_endpoint_the_shortcut_needs_is_registered():
    """Added after a cleanup edit silently deleted the notes, media and active
    routes at once: the tests all passed, because none of them asked the app
    which routes it actually has."""
    from backend.app.main import app

    paths = {r.path for r in app.routes}
    for required in (
        "/api/active",
        "/api/media",
        "/media/{relative:path}",
        "/api/domains/{domain_id}/nodes/{node_id}/note",
        "/api/domains/{domain_id}/nodes/{node_id}/journal",
    ):
        assert required in paths, f"{required} is not registered"


def test_an_unknown_api_path_404s_rather_than_serving_the_app_shell():
    """The SPA fallback must not swallow /api/. Returning 200 + HTML for a
    mistyped endpoint makes a client — an iOS Shortcut, say — report success
    while silently doing nothing."""
    from fastapi.testclient import TestClient

    from backend.app.main import app

    with TestClient(app) as client:
        assert client.get("/api/definitely-not-a-thing").status_code == 404


def test_naming_only_a_domain_attaches_to_what_it_is_working_on(write_domain, conn):
    """The whole reason the Shortcut can be two actions instead of six: the
    phone says "guitar" and the server resolves what that means today, rather
    than fetching a list, showing a picker and unpacking the choice."""
    from fastapi.testclient import TestClient

    write_domain(
        "g",
        """
id = "g"
title = "G"
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
            "/api/media?domain=g",
            content=_png(),
            headers={"content-type": "image/png"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["attached_to_note"] is True
        assert "![photo](/media/" in notes.read("g", "first")
