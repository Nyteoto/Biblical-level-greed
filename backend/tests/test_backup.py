"""The Settings screen's backup button, and the stamp it reads.

`backup.py` is deliberately thin — it shells out to `backup.sh` and reports
what the script said — so what is worth testing is exactly the seam: that the
script's own refusals reach the screen verbatim, that the destination it is
given is the one it runs against, and that asking twice does not start two
rsyncs over the same tree.

**No test here runs the real script.** Every one of them points `SCRIPT` at a
stub in `tmp_path`, because the real one copies the media library and its
whole reason for existing is that it touches another disk. A suite that
exercised it would be a suite that could write to the backup drive.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app import backup


@pytest.fixture
def dest(tmp_path, monkeypatch) -> Path:
    """A throwaway destination, and a module with no memory of earlier runs.

    The running flag and the last result are process globals — that is what
    lets a GET report on a run some earlier POST started — so they have to be
    reset between tests or one test's failure becomes the next one's status.
    """
    target = tmp_path / "pgs-backup"
    target.mkdir()
    monkeypatch.setenv("PGS_BACKUP_DIR", str(target))
    monkeypatch.setattr(backup, "_running", False)
    monkeypatch.setattr(backup, "_last", None)
    return target


def script(tmp_path, monkeypatch, body: str) -> Path:
    """A stand-in for `backup.sh`, which records its arguments."""
    path = tmp_path / "fake-backup.sh"
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)
    monkeypatch.setattr(backup, "SCRIPT", path)
    return path


def settle(timeout: float = 10.0) -> dict:
    """Wait for the background run to finish and hand back the final status.

    `start()` returns while the thread is still going — the screen polls — so
    every assertion about a result has to wait for one.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not backup.status()["running"]:
            return backup.status()
        time.sleep(0.02)
    raise AssertionError("the backup thread never cleared its flag")


# -- the stamp --------------------------------------------------------------


def test_a_destination_that_has_never_been_written_to_says_so(dest):
    """No stamp is not an error and not a guess. The screen has to be able to
    say "never" — a first backup is the one most worth prompting."""
    status = backup.status()

    assert status["last"] is None
    assert status["seconds_ago"] is None
    assert status["running"] is False
    assert status["destination"] == str(dest)


def test_the_stamp_is_read_and_aged(dest):
    """The only question that matters about a backup is when it last actually
    worked, so the age is computed here rather than left to the client."""
    written = datetime.now(timezone.utc) - timedelta(hours=3)
    (dest / ".last-backup").write_text(written.isoformat() + "\n")

    status = backup.status()

    assert status["last"] == written.isoformat()
    assert 3 * 3600 - 60 <= status["seconds_ago"] <= 3 * 3600 + 60


def test_a_stamp_in_another_zone_is_aged_against_utc(dest):
    """The script writes local time. Comparing that to `now()` without
    converting would report a backup made minutes ago as hours old, or —
    worse, since the machine is at GMT+7 — as being in the future."""
    written = datetime.now(timezone(timedelta(hours=7))) - timedelta(minutes=10)
    (dest / ".last-backup").write_text(written.isoformat())

    assert 9 * 60 <= backup.status()["seconds_ago"] <= 11 * 60


def test_an_unreadable_stamp_is_the_same_as_no_stamp(dest):
    """Garbage in the file tells you nothing about the backup. Saying "never"
    is honest; parsing half of it into a date would not be."""
    (dest / ".last-backup").write_text("who knows")

    status = backup.status()

    assert status["last"] is None
    assert status["seconds_ago"] is None


def test_a_missing_destination_is_not_an_error(tmp_path, monkeypatch):
    """An unmounted backup disk is the ordinary case this has to survive —
    Settings still has to render, with the button still offered."""
    monkeypatch.setenv("PGS_BACKUP_DIR", str(tmp_path / "not-mounted"))
    monkeypatch.setattr(backup, "_running", False)

    assert backup.status()["last"] is None


# -- running the script -----------------------------------------------------


def test_the_script_is_run_against_the_configured_destination(
    dest, tmp_path, monkeypatch
):
    """The destination is passed, not assumed. `PGS_BACKUP_DIR` is how the
    second disk moves without an edit, and it would be pointless if the button
    ran the script's own default instead."""
    argv = tmp_path / "argv"
    script(tmp_path, monkeypatch, f'echo "$1" > {argv}')

    backup.start()
    settle()

    assert argv.read_text().strip() == str(dest)


def test_a_refusal_reaches_the_screen_verbatim(dest, tmp_path, monkeypatch):
    """This is the whole point of shelling out. `backup.sh` refuses when the
    destination resolves to the same device as `data/` — the check that
    catches an unmounted disk — and that sentence is a better message than any
    status code this could invent from a return value."""
    refusal = "backup.sh: destination is on the same device as data/, refusing"
    script(tmp_path, monkeypatch, f'echo "{refusal}" >&2; exit 1')

    backup.start()
    result = settle()["result"]

    assert result["ok"] is False
    assert result["message"] == refusal


def test_a_successful_run_reports_its_last_line(dest, tmp_path, monkeypatch):
    """rsync is chatty and the screen has one line. The last thing the script
    said is its summary."""
    script(tmp_path, monkeypatch, 'echo "copying"; echo "done, 2.5 GB"')

    backup.start()
    result = settle()["result"]

    assert result["ok"] is True
    assert result["message"] == "done, 2.5 GB"


def test_a_missing_script_is_reported_rather_than_raised(dest, tmp_path, monkeypatch):
    """A packaged copy without `backup.sh` beside it should say so on the
    screen. It must also leave the flag down — a start that never started must
    not lock the button out until a restart."""
    monkeypatch.setattr(backup, "SCRIPT", tmp_path / "gone.sh")

    status = backup.start()

    assert status["result"]["ok"] is False
    assert "gone.sh" in status["result"]["message"]
    assert backup.status()["running"] is False


def test_asking_twice_does_not_start_a_second_run(dest, tmp_path, monkeypatch):
    """One run at a time. Two rsyncs over the same tree at once is the failure
    this guards, and an impatient second tap is how it would happen."""
    runs = tmp_path / "runs"
    script(tmp_path, monkeypatch, f'echo x >> {runs}; sleep 1')

    backup.start()
    assert backup.status()["running"] is True
    backup.start()  # while the first is still going
    settle()

    assert runs.read_text().count("x") == 1


def test_the_status_endpoint_answers_without_a_backup_disk(dest):
    """Settings loads this on every visit, so it has to be cheap and it has to
    work with nothing mounted."""
    from fastapi.testclient import TestClient

    from backend.app.main import app

    with TestClient(app) as client:
        body = client.get("/api/backup").json()

    assert body["destination"] == str(dest)
    assert body["running"] is False
    assert "source" in body
