"""The blob store: what arrives is what is kept.

These exist because the module they cover used to do the opposite. Every
upload was decoded, downscaled to 2048px, re-encoded to JPEG q82 and stripped
of its EXIF, and anything that was not a still image was refused outright.
That was defensible for a tech tree's illustrations and is not for a journal,
so the tests that pinned it are gone and these pin its inverse:

  - the original is byte-identical to what was sent, whatever it is;
  - the display copy is a *second* file and its absence is never fatal;
  - the size cap is gone, and a truncated write is impossible;
  - Range requests answer 206, which is what makes video seekable.

`write_stream` is driven through the endpoint rather than called directly.
It is an async generator consumer and there is no pytest-asyncio here, but
more to the point the endpoint *is* the path a phone takes, and the old suite
learned that lesson once already — see the HEIC test it grew after every
endpoint test had been sending PNGs.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from backend.app import media


def _png(size=(40, 30), colour=(200, 40, 40)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="PNG")
    return buf.getvalue()


def _heic(size=(40, 30), colour=(40, 90, 200)) -> bytes:
    from PIL import Image
    from pillow_heif import register_heif_opener

    register_heif_opener()
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="HEIF")
    return buf.getvalue()


def _jpeg_with_exif(size=(60, 20)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    img = Image.new("RGB", size, (10, 200, 10))
    exif = img.getexif()
    exif[274] = 6  # orientation: rotate 90° CW
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


@pytest.fixture
def client(data_dir):
    from backend.app.main import app

    with TestClient(app) as test_client:
        yield test_client


def _upload(client, body: bytes, name: str):
    return client.post(f"/api/media?name={name}", content=body)


# ── The original is the point ─────────────────────────────────────────────


def test_the_stored_file_is_byte_identical_to_what_was_sent(client):
    """The whole reason this module was rewritten."""
    sent = _jpeg_with_exif()
    r = _upload(client, sent, "IMG_0001.jpg")
    assert r.status_code == 200, r.text

    stored = media.path_for(r.json()["path"])
    assert stored is not None
    assert stored.read_bytes() == sent


def test_exif_survives_on_the_original(client):
    """It used to be stripped. A journal that quietly discards when and where
    a photo was taken is throwing away the part that dates it."""
    from PIL import Image

    r = _upload(client, _jpeg_with_exif(), "IMG_0002.jpg")
    with Image.open(media.path_for(r.json()["path"])) as out:
        assert dict(out.getexif())


def test_a_file_keeps_its_own_extension(client):
    """`FileResponse` types the response off the suffix, so a clip stored as
    `.jpg` would be served as an image and refuse to play."""
    for name, suffix in (("clip.MOV", ".mov"), ("photo.PNG", ".png")):
        r = _upload(client, b"\x00" * 64, name)
        assert r.status_code == 200, r.text
        assert r.json()["path"].endswith(suffix)


def test_video_is_accepted_and_not_decoded(client):
    """Not a real MP4 — the point is that nothing here tries to read it."""
    sent = b"\x00\x00\x00\x18ftypmp42" + b"\xff" * 512
    r = _upload(client, sent, "clip.mp4")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "video"
    assert media.path_for(body["path"]).read_bytes() == sent


def test_the_old_cap_is_gone(client):
    """41 MB: one byte-run over what the previous ceiling refused."""
    assert not hasattr(media, "MAX_UPLOAD")
    big = b"\x7f" * (41 * 1024 * 1024)
    r = _upload(client, big, "long.mp4")
    assert r.status_code == 200, r.text
    assert r.json()["bytes"] == len(big)
    assert media.path_for(r.json()["path"]).stat().st_size == len(big)


def test_files_are_grouped_by_month_like_the_log(client):
    r = _upload(client, _png(), "a.png")
    assert r.json()["path"][:8].endswith("/") or "/" in r.json()["path"]
    assert len(r.json()["path"].split("/")[0]) == 7  # YYYY-MM


# ── The display copy ──────────────────────────────────────────────────────


def test_an_image_gets_a_downscaled_display_copy(client):
    from PIL import Image

    r = _upload(client, _png(size=(5000, 4000)), "big.png")
    body = r.json()

    # The original keeps its resolution...
    with Image.open(media.path_for(body["path"])) as original:
        assert original.size == (5000, 4000)

    # ...and the copy is what the log will draw.
    assert body["view_url"] != body["url"]
    view = media.path_for(body["view_url"].removeprefix("/media/"))
    with Image.open(view) as small:
        assert max(small.size) == media.VIEW_EDGE
        assert small.format == "JPEG"


def test_a_heic_gets_a_jpeg_copy_because_nothing_else_renders_heic(client):
    from PIL import Image

    r = _upload(client, _heic(size=(60, 40)), "IMG_0003.heic")
    body = r.json()
    assert body["path"].endswith(".heic")  # the original is untouched

    with Image.open(media.path_for(media.view_ref(body["path"]))) as out:
        assert out.format == "JPEG"
        assert out.size == (60, 40)


def test_a_video_has_no_display_copy_until_a_poster_arrives(client):
    r = _upload(client, b"\x00" * 64, "clip.mov")
    body = r.json()
    # Falls back to the original rather than pointing at a file that is not there.
    assert body["view_url"] == body["url"]
    assert media.path_for(media.view_ref(body["path"])) is None

    posted = client.post(
        f"/api/media?poster_for={body['path']}", content=_png(size=(64, 36))
    )
    assert posted.status_code == 200, posted.text
    assert media.path_for(media.view_ref(body["path"])) is not None


def test_a_poster_for_nothing_is_a_404(client):
    r = client.post("/api/media?poster_for=2026-01/nope.mov", content=_png())
    assert r.status_code == 404


def test_an_undecodable_image_still_stores_it(client):
    """No display copy is not an error. The file is what matters."""
    r = _upload(client, b"not really a png at all", "broken.png")
    assert r.status_code == 200, r.text
    body = r.json()
    assert media.path_for(body["path"]) is not None
    assert body["view_url"] == body["url"]


# ── Refusals ──────────────────────────────────────────────────────────────


def test_an_extension_the_store_does_not_know_is_refused(client):
    for name in ("payload.exe", "notes.txt", "noextension"):
        r = _upload(client, b"whatever", name)
        assert r.status_code == 400, name


def test_an_empty_upload_is_refused_and_leaves_nothing_behind(client, data_dir):
    r = _upload(client, b"", "empty.mp4")
    assert r.status_code == 400
    # Not even a stray .part file from the aborted write.
    assert not list(media.media_dir().rglob("*")) or not [
        p for p in media.media_dir().rglob("*") if p.is_file()
    ]


@pytest.mark.parametrize("escape", ["../../etc/passwd", "/etc/passwd", "../secrets"])
def test_media_paths_cannot_escape_the_media_root(data_dir, escape):
    assert media.path_for(escape) is None


# ── Serving, which is what makes video watchable ──────────────────────────


def test_a_range_request_is_answered_with_206(client):
    """Free from Starlette's FileResponse today. Pinned here so a dependency
    bump cannot quietly take away seeking."""
    body = b"".join(bytes([i % 256]) for i in range(1000))
    rel = _upload(client, body, "clip.mp4").json()["path"]

    r = client.get(f"/media/{rel}", headers={"Range": "bytes=100-199"})
    assert r.status_code == 206
    assert r.headers["content-range"] == "bytes 100-199/1000"
    assert r.content == body[100:200]


def test_the_whole_file_still_serves_without_a_range(client):
    body = _png()
    rel = _upload(client, body, "a.png").json()["path"]

    r = client.get(f"/media/{rel}")
    assert r.status_code == 200
    assert r.content == body
    assert r.headers["accept-ranges"] == "bytes"


def test_a_video_is_served_as_video(client):
    """The content type comes off the suffix; if it said image/jpeg the
    browser would put it in an <img> and nothing would play."""
    rel = _upload(client, b"\x00" * 64, "clip.mp4").json()["path"]
    r = client.get(f"/media/{rel}")
    assert r.headers["content-type"].startswith("video/")


def test_missing_media_is_a_404_not_the_app_shell(client):
    assert client.get("/media/2026-01/nothing.mp4").status_code == 404
