"""The fixture generator, run for real.

`scripts/fixture.py` is the answer to "I need to see data that behaves like
real data" — the whole reason nobody has to open the user's own log to do UI
work. That makes it load-bearing in a way an unused script is not: if it stops
producing a valid data directory, the pressure to go and look at the real one
comes straight back.

It cannot be imported and called, because it sets `PGS_DATA_DIR` before
importing anything under `backend/` and `conftest.py` has already pointed that
at somewhere else. So it runs as a subprocess, which is also how a person runs
it, and is the only way to exercise the environment contract at all.

The generator already self-checks — it rebuilds the index and refuses to finish
if the entry count does not survive the round trip. What is added here is that
somebody runs it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "fixture.py"

# Pinned rather than today's date, so a failure is the same failure tomorrow.
# The generator defaults to today precisely because the *screens* need relative
# dates; a test needs the opposite.
ANCHOR = "2026-06-15"


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp("fixture") / "data.fixture"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(target), "--anchor", ANCHOR],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def test_it_builds_a_data_directory(built: Path):
    assert list((built / "capture" / "log").glob("*.jsonl"))
    assert list((built / "media").rglob("*.png"))
    # The tree's directories are not made any more. A fixture that still built
    # them would be quietly teaching the next reader that they still matter.
    assert not (built / "domains").exists()
    assert not (built / "log").exists()
    assert not (built / "todos.jsonl").exists()


def test_every_log_line_is_a_complete_event(built: Path):
    """Read as shape, never as content — which is all a fixture's lines are
    for, and the same discipline the real log is owed."""
    for path in (built / "capture" / "log").glob("*.jsonl"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            event = json.loads(line)
            missing = {"ts", "day", "kind", "id"} - set(event)
            assert not missing, f"{path.name}:{lineno} missing {missing}"


def test_it_refuses_a_directory_it_did_not_make(built: Path, tmp_path: Path):
    """The refusal that stands between `--out` and somebody's real data.

    Checked against a directory that merely exists, because that is what the
    live one looks like from here: no marker, and everything to lose.
    """
    someone_elses = tmp_path / "data"
    someone_elses.mkdir()
    (someone_elses / "capture").mkdir()

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(someone_elses), "--force"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode != 0
    assert "not made by this script" in result.stderr
    # --force did not help, and nothing was touched on the way to refusing.
    assert (someone_elses / "capture").is_dir()


def test_it_refuses_the_live_data_directory(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(ROOT / "data"), "--force"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode != 0
    assert "live data directory" in result.stderr


def test_the_whole_screen_vocabulary_is_present(built: Path):
    """The point of the thing: one data directory that lights up every screen.

    This is the assertion that decays first — a token dropped from the fixture
    leaves a screen with no example, and the way that gets noticed is here
    rather than by someone wondering why they have never seen a lifted tag
    rendered.
    """
    probe = (
        "import json;"
        "from backend.capture.store import Store;"
        "s = Store(); s.start();"
        "e = s.entries(limit=500);"
        "print(json.dumps({"
        "  'entries': len(e),"
        "  'folders': len(s.folders()),"
        "  'days': len(s.dates()),"
        "  'due': len(s.due_reminders()),"
        "  'with_media': sum(1 for x in e if x.get('media')),"
        "  'with_todos': sum(1 for x in e if x.get('todo_lines')),"
        "  'replies': sum(1 for x in e if x.get('reply_to')),"
        "  'tags': sum(1 for x in e if x.get('folders')),"
        "  'places': sum(1 for x in e if x.get('places')),"
        "  'patterns': sum(1 for x in e if x.get('patterns')),"
        "  'times': sum(1 for x in e if x.get('times')),"
        "  'unassigned_tags': len(s.unassigned_tags()),"
        "}));"
        "s.close()"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={**_env(built)},
    )
    assert result.returncode == 0, result.stderr
    got = json.loads(result.stdout)

    for key, least in (
        ("entries", 25),
        ("folders", 4),
        ("days", 20),
        ("due", 1),
        ("with_media", 8),
        ("with_todos", 3),
        ("replies", 1),
        ("tags", 8),
        ("places", 2),
        ("patterns", 3),
        ("times", 4),
        ("unassigned_tags", 1),
    ):
        assert got[key] >= least, f"fixture has {got[key]} {key}, wanted {least}+"


def _env(built: Path) -> dict:
    import os

    return {
        **os.environ,
        "PGS_DATA_DIR": str(built),
        "PGS_CAPTURE_INDEX_PATH": str(built / "capture" / "index.sqlite"),
    }
