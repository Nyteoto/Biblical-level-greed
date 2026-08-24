"""The Settings screen's backup button, and the stamp it reads.

`backup.py` is deliberately thin — it picks one of two scripts by platform,
shells out, and reports what the script said — so what is worth testing is
exactly the seam: that the script's own refusals reach the screen verbatim,
that the destination it is given is the one it runs against, that asking twice
does not start two copies over the same tree, and that the argv is right for
both operating systems even though only one of them can run this suite.

**No test here runs the real script.** Every one of them points `SCRIPT` at a
stub in `tmp_path`, because the real one copies the media library and its
whole reason for existing is that it touches another disk. A suite that
exercised it would be a suite that could write to the backup drive.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

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


def script(tmp_path, monkeypatch, sh: str, ps1: str) -> Path:
    """A stand-in for the real backup script, in the language of this platform.

    Two bodies rather than one, because `_command` hands a `.ps1` to
    powershell.exe and runs a `.sh` directly by its shebang. A stub that only
    spoke `sh` failed every test through this helper on Windows, and failed
    them misleadingly: the argv under test was right and the fake script it
    named was simply not runnable. The seam is the thing being tested, so the
    stub has to be the kind of file the seam actually runs.
    """
    if backup._WINDOWS:
        path = tmp_path / "fake-backup.ps1"
        path.write_text(ps1 + "\n", encoding="utf-8")
    else:
        path = tmp_path / "fake-backup.sh"
        path.write_text("#!/bin/sh\n" + sh + "\n", encoding="utf-8")
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
    script(
        tmp_path,
        monkeypatch,
        f'echo "$1" > {argv}',
        f"$args[0] | Set-Content -LiteralPath '{argv}'",
    )

    backup.start()
    settle()

    assert argv.read_text(encoding="utf-8").strip() == str(dest)


def test_a_refusal_reaches_the_screen_verbatim(dest, tmp_path, monkeypatch):
    """This is the whole point of shelling out. `backup.sh` refuses when the
    destination resolves to the same device as `data/` — the check that
    catches an unmounted disk — and that sentence is a better message than any
    status code this could invent from a return value."""
    refusal = "backup.sh: destination is on the same device as data/, refusing"
    script(
        tmp_path,
        monkeypatch,
        f'echo "{refusal}" >&2; exit 1',
        f"[Console]::Error.WriteLine('{refusal}'); exit 1",
    )

    backup.start()
    result = settle()["result"]

    assert result["ok"] is False
    assert result["message"] == refusal


def test_a_successful_run_reports_its_last_line(dest, tmp_path, monkeypatch):
    """rsync is chatty and the screen has one line. The last thing the script
    said is its summary."""
    script(
        tmp_path,
        monkeypatch,
        'echo "copying"; echo "done, 2.5 GB"',
        "Write-Output 'copying'; Write-Output 'done, 2.5 GB'",
    )

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
    script(
        tmp_path,
        monkeypatch,
        f'echo x >> {runs}; sleep 1',
        f"Add-Content -LiteralPath '{runs}' -Value 'x'; Start-Sleep -Seconds 1",
    )

    backup.start()
    assert backup.status()["running"] is True
    backup.start()  # while the first is still going
    settle()

    assert runs.read_text(encoding="utf-8").count("x") == 1


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


# -- which script, and how it is run ----------------------------------------
#
# The dual-boot half. There are two scripts because `rsync` and `df` have no
# Windows equivalent worth shimming, and the seam between them is three lines
# in `_command` — which is exactly the amount of platform logic that rots
# silently, because the machine running the suite only ever exercises one side
# of it. So both sides are pinned here, on either platform.


def test_the_posix_script_is_run_directly(monkeypatch):
    """A `.sh` carries its own shebang, so it is its own argv[0]. Handing it to
    an interpreter would work and would also mean the Linux path stopped being
    the simple one for no gain."""
    # PurePosixPath, not Path: on Windows `Path` is a WindowsPath, which
    # stringifies a posix path back with backslashes and fails this on the
    # separator rather than on anything to do with the argv. The Windows case
    # below needs no such care — a backslash path is already literal on both.
    monkeypatch.setattr(backup, "_WINDOWS", False)
    monkeypatch.setattr(backup, "SCRIPT", PurePosixPath("/opt/pgs/backup.sh"))

    assert backup._command(PurePosixPath("/mnt/data/pgs-backup")) == [
        "/opt/pgs/backup.sh",
        "/mnt/data/pgs-backup",
    ]


def test_the_windows_script_is_handed_to_powershell(monkeypatch):
    """Windows has no shebang, so a `.ps1` is data until something runs it —
    and the default execution policy refuses unsigned local scripts, with an
    error about publishers that says nothing about backups. Both facts are
    load-bearing, so both flags are asserted rather than the file name alone."""
    monkeypatch.setattr(backup, "_WINDOWS", True)
    monkeypatch.setattr(backup, "SCRIPT", Path(r"C:\pgs\backup.ps1"))

    argv = backup._command(Path(r"D:\pgs-backup"))

    assert argv[0] == "powershell.exe"
    assert "-ExecutionPolicy" in argv and "Bypass" in argv
    # The script and the destination stay the last two words, in that order:
    # -File consumes the next argument and everything after it is the script's.
    assert argv[-2:] == [r"C:\pgs\backup.ps1", r"D:\pgs-backup"]


def test_the_destination_is_still_passed_on_windows(dest, tmp_path, monkeypatch):
    """`PGS_BACKUP_DIR` is how the second disk moves without an edit. The
    Windows branch adds five words before the script name, and dropping the
    destination off the end while doing that would silently back up to the
    script's own default instead."""
    monkeypatch.setattr(backup, "_WINDOWS", True)
    monkeypatch.setattr(backup, "SCRIPT", Path(r"C:\pgs\backup.ps1"))

    assert backup._command(backup.destination())[-1] == str(dest)


def test_both_scripts_are_present_in_the_checkout():
    """Neither operating system can run the other's script, and neither clone
    can test it. The one thing this side can check is that the file the other
    side will reach for is actually in the repo — which is how the Windows
    installer went missing the first time, and stayed missing for a month."""
    root = Path(backup.__file__).resolve().parents[2]

    assert (root / "backup.sh").is_file()
    assert (root / "backup.ps1").is_file()
