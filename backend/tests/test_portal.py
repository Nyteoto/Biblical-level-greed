"""The day, the sitting and the seal.

Every rule the Portal enforces is a rule about the clock, so every test here
names the instant it means. Nothing reads the real time: `day` takes `now` as
an argument, and the route tests pin `timeutil.now` — a suite that passed at
noon and failed at 23:30 would be testing the weather.
"""
from __future__ import annotations

import io
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.app import config, day, media, pdf, records, remarks, timeutil
from backend.app.day import DayError

DAY = "2026-09-22"


def at(clock: str, on: str = DAY) -> datetime:
    return datetime.fromisoformat(f"{on}T{clock}").replace(tzinfo=timeutil.TZ)


def _png(size=(40, 30)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, (90, 120, 150)).save(buf, format="PNG")
    return buf.getvalue()


def _blob(name: str, body: bytes | None = None) -> str:
    """A stored file, as the upload route would have left it."""
    ref = f"{DAY[:7]}/{name}"
    target = media.media_dir() / ref
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_png() if body is None else body)
    return ref


def _fields(**over) -> dict:
    fields = {"body": "Walked.", "wish": "Walk again.", "signature": "8193", "mood": 6}
    fields.update(over)
    return fields


@pytest.fixture
def awake(data_dir):
    """An Instance that has taken its selfie at noon."""
    ref = _blob("selfie.png")
    day.take_selfie(ref, "image", at("12:00"))
    return ref


@pytest.fixture
def sitting(awake):
    return day.begin_sitting(at("19:05"))


# ── Numbering and the window ──────────────────────────────────────────────


def test_the_day_the_portal_opened_is_instance_8193():
    assert timeutil.instance_of("2026-09-22") == 8193
    assert timeutil.day_of(8193) == "2026-09-22"


@pytest.mark.parametrize(
    "clock, open_",
    [("18:59:59", False), ("19:00", True), ("22:59:59", True), ("23:00", False)],
)
def test_the_window_is_seven_to_eleven(clock, open_):
    assert timeutil.in_window(at(clock)) is open_


def test_the_window_is_read_in_the_users_zone():
    """12:00 UTC is 19:00 at GMT+7: open, whatever the machine's own zone."""
    from datetime import timezone

    assert timeutil.in_window(datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc))


# ── Waking ────────────────────────────────────────────────────────────────


def test_nobody_has_woken_yet(data_dir):
    assert day.phase(day.settle(at("09:00")), at("09:00")) == "unborn"


def test_a_selfie_wakes_the_instance(awake):
    state = day.settle(at("12:01"))
    assert day.phase(state, at("12:01")) == "awake"
    assert state["instance"] == 8193


def test_a_video_is_not_a_mugshot(data_dir):
    ref = _blob("clip.mp4", b"\x00" * 32)
    with pytest.raises(DayError):
        day.take_selfie(ref, "video", at("12:00"))
    assert media.path_for(ref) is None


def test_a_retake_replaces_the_first_selfie(awake):
    second = _blob("again.png")
    day.take_selfie(second, "image", at("12:05"))
    assert media.path_for(awake) is None
    assert day.settle(at("12:06"))["selfie"] == second


# ── The sitting ───────────────────────────────────────────────────────────


def test_a_sitting_cannot_begin_before_seven(awake):
    with pytest.raises(DayError):
        day.begin_sitting(at("18:30"))


def test_a_sitting_needs_a_selfie_first(data_dir):
    with pytest.raises(DayError):
        day.begin_sitting(at("19:05"))


def test_there_is_one_sitting_a_day(sitting):
    with pytest.raises(DayError, match="already under way"):
        day.begin_sitting(at("19:06"))


def test_leaving_ends_the_day_and_takes_everything_with_it(sitting, awake):
    clip = _blob("clip.mp4", b"\x00" * 32)
    day.attach(sitting, clip, "video", at("19:10"))
    day.leave(sitting, at("19:11"))

    state = day.settle(at("19:12"))
    assert day.phase(state, at("19:12")) == "terminated"
    assert state["reason"] == "left"
    assert media.path_for(awake) is None
    assert media.path_for(clip) is None


def test_a_terminated_day_cannot_be_sat_again(sitting):
    day.leave(sitting, at("19:07"))
    with pytest.raises(DayError):
        day.take_selfie(_blob("new.png"), "image", at("19:12"))
    with pytest.raises(DayError):
        day.begin_sitting(at("19:13"))


def test_a_sitting_that_goes_quiet_is_over(sitting):
    grace = config.SITTING_GRACE_SECONDS
    day.beat(sitting, at("19:10"))
    alive = at("19:10").timestamp() + grace - 1
    dead = at("19:10").timestamp() + grace + 1
    assert day.phase(day.settle(datetime.fromtimestamp(alive, timeutil.TZ)), at("19:10")) == "sitting"
    state = day.settle(datetime.fromtimestamp(dead, timeutil.TZ))
    assert state["terminated"] and state["reason"] == "silent"


def test_a_heartbeat_keeps_it_alive(sitting):
    for minute in range(6, 40, 3):
        day.beat(sitting, at(f"19:{minute:02d}"))
    assert day.phase(day.settle(at("19:40")), at("19:40")) == "sitting"


def test_the_wrong_token_is_not_the_sitting(sitting):
    with pytest.raises(DayError) as caught:
        day.beat("somebody-else", at("19:06"))
    assert caught.value.status == 403


def test_eleven_oclock_ends_an_unsealed_day(sitting):
    for hour in range(19, 23):
        for minute in range(0 if hour > 19 else 6, 60, 4):
            day.beat(sitting, at(f"{hour}:{minute:02d}"))
    state = day.settle(at("23:00"))
    assert state["reason"] == "deadline"


def test_a_day_nobody_woke_for_is_terminated_after_eleven(data_dir):
    assert day.phase(day.settle(at("23:30")), at("23:30")) == "terminated"


def test_the_next_day_starts_clean(sitting, awake):
    state = day.settle(at("08:00", on="2026-09-23"))
    assert state is None
    assert not config.TODAY_PATH.exists()
    assert media.path_for(awake) is None
    assert day.phase(None, at("08:00", on="2026-09-23")) == "unborn"


def test_four_media_and_no_more(sitting):
    for i in range(config.MAX_MEDIA):
        day.attach(sitting, _blob(f"m{i}.png"), "image", at("19:10"))
    extra = _blob("m9.png")
    with pytest.raises(DayError):
        day.attach(sitting, extra, "image", at("19:11"))
    assert media.path_for(extra) is None


def test_detaching_deletes_the_file(sitting):
    ref = _blob("oops.png")
    day.attach(sitting, ref, "image", at("19:10"))
    day.detach(sitting, ref, at("19:11"))
    assert media.path_for(ref) is None
    assert day.settle(at("19:12"))["media"] == []


# ── Committable ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "over, gap",
    [
        ({"body": ""}, "the record"),
        ({"body": "   \n  "}, "the record"),
        ({"body": "..."}, "the record"),
        ({"wish": ""}, "what the next Instance should do"),
        ({"signature": ""}, "the signature"),
        ({"mood": None}, "how you feel"),
        ({"mood": 0}, "how you feel"),
        ({"mood": 11}, "how you feel"),
    ],
)
def test_every_field_must_hold_a_word_or_a_digit(over, gap):
    state = {"selfie": "x.png", "media": []}
    assert any(g.startswith(gap) for g in day.missing(state, _fields(**over)))


def test_one_digit_is_enough():
    assert day.missing({"selfie": "x.png", "media": []}, _fields(body="7", wish="8")) == []


def test_any_script_counts_as_a_word():
    assert day.missing({"selfie": "x.png"}, _fields(body="Hôm nay trời mưa")) == []


def test_the_selfie_is_the_picture_a_record_needs():
    assert day.missing({"selfie": None, "media": []}, _fields()) == ["at least one picture"]
    assert day.missing({"selfie": "x.png", "media": []}, _fields()) == []


# ── The seal ──────────────────────────────────────────────────────────────


def test_a_commit_seals_the_record(sitting, awake):
    clip = _blob("clip.mp4", b"\x00" * 32)
    day.attach(sitting, clip, "video", at("19:06"))
    record = day.commit(sitting, _fields(captions={clip: "the river"}), at("19:09"))

    assert record["instance"] == 8193
    assert record["selfie"] == awake
    assert record["media"] == [{"ref": clip, "kind": "video", "caption": "the river"}]
    assert records.read(8193) == record
    assert not config.TODAY_PATH.exists()
    # The Record owns its media now; the day being gone must not take it.
    assert media.path_for(clip) is not None
    assert day.phase(day.settle(at("20:01")), at("20:01")) == "sealed"


def test_an_incomplete_draft_is_refused_and_the_sitting_survives(sitting):
    with pytest.raises(DayError) as caught:
        day.commit(sitting, _fields(body=""), at("19:08"))
    assert caught.value.status == 422
    assert day.phase(day.settle(at("19:09")), at("19:09")) == "sitting"


def test_a_sealed_record_is_never_written_twice(sitting):
    day.commit(sitting, _fields(), at("19:08"))
    before = records.path_of(8193).read_bytes()
    with pytest.raises(records.SealedError):
        records.write({"instance": 8193, "body": "rewritten"})
    assert records.path_of(8193).read_bytes() == before


def test_a_sealed_day_is_not_terminated_at_eleven(sitting):
    day.commit(sitting, _fields(), at("19:08"))
    assert day.phase(day.settle(at("23:30")), at("23:30")) == "sealed"


def test_the_latest_record_is_the_highest_number(data_dir):
    for n in (8190, 8188, 8191):
        records.write({"instance": n, "mood": 5})
    assert records.latest()["instance"] == 8191
    assert records.latest(before=8191)["instance"] == 8190


# ── Remarks ───────────────────────────────────────────────────────────────


def test_the_first_instance_is_told_so(data_dir):
    assert remarks.context(8193)["first"]


def test_the_failed_are_counted_from_the_gap(data_dir):
    records.write({"instance": 8188, "mood": 5})
    assert remarks.context(8193)["gap"] == 4


def test_a_remark_holds_still_for_the_whole_day(data_dir):
    records.write({"instance": 8192, "mood": 5})
    assert remarks.pick(8193) == remarks.pick(8193)
    assert "{" not in remarks.pick(8193)


def test_every_pool_names_a_condition_that_exists():
    for pool in remarks._pools():
        assert pool["when"] in remarks._CONDITIONS, pool["when"]


def _lines(when: str) -> list[str]:
    return next(p["lines"] for p in remarks._pools() if p["when"] == when)


def test_a_failure_is_addressed_before_anything_else(data_dir):
    """Exclusive: a day after a failure hears about the failure, whatever
    else yesterday's Record would have offered to talk about."""
    records.write({"instance": 8191, "mood": 9, "wish": "rest", "body": "x"})
    facts = remarks.context(8193)
    assert remarks.pick(8193) in [l.format_map(remarks._Leave(facts)) for l in _lines("failed")]


def test_an_ordinary_day_draws_from_everything_that_holds(data_dir):
    records.write(
        {"instance": 8192, "mood": 5, "wish": "Call home.", "signature": "8192", "body": "short"}
    )
    facts = remarks.context(8193)
    held = [
        l.format_map(remarks._Leave(facts))
        for w in ("wish", "terse", "no_media", "always")
        for l in _lines(w)
    ]
    assert remarks.pick(8193) in held


def test_yesterdays_wish_can_be_quoted(data_dir):
    records.write({"instance": 8192, "mood": 5, "wish": "Call home.", "body": "x"})
    facts = remarks.context(8193)
    assert facts["wish"] == "Call home."
    assert "Call home." in _lines("wish")[0].format_map(remarks._Leave(facts))


def test_waking_inside_the_window_is_remarked_on(data_dir):
    records.write({"instance": 8192, "mood": 5, "body": "x"})
    assert remarks.context(8193, at("19:30"))["late"]
    assert not remarks.context(8193, at("09:00"))["late"]
    assert remarks.pick(8193, at("19:30")) in _lines("late")


def test_no_line_leaves_a_placeholder_unfilled_when_there_is_a_record(data_dir):
    """Every placeholder a line can use exists whenever a Record does."""
    records.write(
        {"instance": 8192, "mood": 5, "wish": "w", "signature": "s", "body": "b", "media": []}
    )
    facts = remarks.context(8193, at("12:00"))
    for pool in remarks._pools():
        if pool["when"] == "first":
            continue
        for line in pool["lines"]:
            assert "{" not in line.format_map(remarks._Leave(facts)), line


# ── The print ─────────────────────────────────────────────────────────────


def test_the_print_embeds_the_original_at_full_resolution(data_dir):
    """At the pixel size it was taken, not the 2048px display copy's."""
    selfie = _blob("big.png", _png(size=(3000, 4000)))
    records.write(
        {
            "instance": 8193,
            "day": DAY,
            "selfie": selfie,
            "media": [{"ref": _blob("clip.mp4", b"\x00" * 16), "kind": "video", "caption": ""}],
            "body": "Line one\nLine <two> & three",
            "wish": "Carry on.",
            "signature": "8193",
            "mood": 7,
        }
    )
    target = pdf.render(8193)
    data = target.read_bytes()
    assert data.startswith(b"%PDF")
    assert b"/Width 3000" in data and b"/Height 4000" in data


def _pages(path) -> int:
    import re

    return len(re.findall(rb"/Type /Page\b(?!s)", path.read_bytes()))


def test_a_book_starts_every_record_on_a_front(data_dir):
    """Printed duplex, two one-page days must not share a sheet: the second
    would be on the back of the first and neither could be filed alone. So a
    blank back is left after any Record that ends on a front."""
    for n, day in ((8191, "2026-09-20"), (8192, "2026-09-21")):
        records.write(
            {"instance": n, "day": day, "selfie": _blob(f"s{n}.png"), "media": [],
             "body": "x", "wish": "y", "signature": str(n), "mood": 5}
        )
    single = pdf.render(8191)
    assert _pages(single) == 1
    bound = pdf.book([8191, 8192], config.PDF_DIR / "book.pdf")
    assert _pages(bound) == 3  # 8191 · blank back · 8192


def test_every_page_is_laid_out_on_its_own_side(data_dir, monkeypatch):
    """A front's text block sits right of the binder margin, a back's left of
    it — decided by page number, the same as the holes. It once drifted after
    the page break between two Records: page 3 was laid out as a back while
    its holes were drawn as a front."""
    seen: dict[int, float] = {}
    real = pdf._decorate

    def spy(canvas, doc):
        seen[canvas.getPageNumber()] = doc.frame._x1
        real(canvas, doc)

    monkeypatch.setattr(pdf, "_decorate", spy)
    long = "\n".join(f"Line {i} of a long day." for i in range(40))
    for n, day, body in ((8190, "2026-09-19", long), (8191, "2026-09-20", "x"), (8192, "2026-09-21", long)):
        records.write(
            {"instance": n, "day": day, "selfie": _blob(f"s{n}.png"), "media": [],
             "body": body, "wish": "y", "signature": str(n), "mood": 5}
        )
    pdf.book([8190, 8191, 8192], config.PDF_DIR / "book.pdf")
    assert len(seen) >= 4
    for page, x in seen.items():
        assert x == (pdf.BINDER if page % 2 else pdf.MARGIN), (page, x)


# ── Through the routes ────────────────────────────────────────────────────


@pytest.fixture
def client(data_dir, monkeypatch):
    clock = {"now": at("12:00")}
    monkeypatch.setattr(timeutil, "now", lambda: clock["now"])
    from backend.app.main import app

    with TestClient(app) as test_client:
        test_client.clock = clock
        yield test_client


def test_a_whole_day_through_the_api(client):
    shot = client.post("/api/media?name=me.png", content=_png()).json()
    assert client.post("/api/portal/selfie", json={"ref": shot["path"]}).json()["phase"] == "awake"
    assert client.post("/api/portal/sitting").status_code == 409  # noon

    client.clock["now"] = at("19:30")
    token = client.post("/api/portal/sitting").json()["token"]
    photo = client.post("/api/media?name=river.jpg", content=_png()).json()["path"]
    assert client.post("/api/portal/media", json={"token": token, "ref": photo}).status_code == 200
    assert client.post("/api/portal/beat", json={"token": token}).status_code == 200

    sealed = client.post(
        "/api/portal/commit", json={"token": token, **_fields(captions={photo: "river"})}
    ).json()
    assert sealed["phase"] == "sealed" and sealed["printed"]
    assert client.get("/api/portal/pdf/8193").headers["content-type"] == "application/pdf"

    client.clock["now"] = at("09:00", on="2026-09-23")
    tomorrow = client.get("/api/portal").json()
    assert tomorrow["instance"] == 8194 and tomorrow["previous"] == 8193
    assert client.get("/api/portal/latest").json()["record"]["body"] == "Walked."


def test_a_beacon_ends_the_sitting(client):
    shot = client.post("/api/media?name=me.png", content=_png()).json()
    client.post("/api/portal/selfie", json={"ref": shot["path"]})
    client.clock["now"] = at("19:30")
    token = client.post("/api/portal/sitting").json()["token"]
    # sendBeacon posts text/plain, and the route has to take it as sent.
    client.post("/api/portal/leave", content=token, headers={"content-type": "text/plain"})
    assert client.get("/api/portal").json()["phase"] == "terminated"


def test_a_sealed_poster_cannot_be_swapped(client):
    r = client.post("/api/media?poster_for=2026-09/nope.mov", content=_png())
    assert r.status_code == 404


def test_the_routes_the_page_needs_are_registered():
    """Added after a cleanup edit once deleted working routes and nothing
    failed, because no test asked the app which routes it has."""
    from backend.app.main import app

    paths = {getattr(r, "path", None) for r in app.routes}
    for required in (
        "/api/media",
        "/media/{relative:path}",
        "/api/portal",
        "/api/portal/selfie",
        "/api/portal/latest",
        "/api/portal/sitting",
        "/api/portal/beat",
        "/api/portal/leave",
        "/api/portal/media",
        "/api/portal/commit",
        "/api/portal/pdf/{instance}",
    ):
        assert required in paths, required


def test_an_unknown_api_path_404s_rather_than_serving_the_app_shell(client):
    assert client.get("/api/definitely-not-a-thing").status_code == 404


def test_today_json_is_the_only_thing_a_day_writes_before_the_seal(awake):
    written = sorted(p.name for p in config.PORTAL_DIR.rglob("*") if p.is_file())
    assert written == ["today.json"]
    assert json.loads(config.TODAY_PATH.read_text())["selfie"] == awake
