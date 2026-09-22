"""The restart endpoint, which has two supervisors to speak to.

Neither of them can be spoken to here — restarting the service under a test
run would take the test run with it — so what is pinned is the argv, which is
the part that was wrong. `/api/restart` answered only to systemd for as long
as it existed, and on Windows it failed with `[WinError 2]` naming a unit file
that is not a thing that platform has. Nothing caught it because nothing here
had ever asked what the command was.

`monkeypatch` on `_WINDOWS` rather than a skip, so both branches are checked
from either operating system: the whole point is that one of the two is always
the one nobody is running today.
"""
from __future__ import annotations

import subprocess

from backend.app import main


def test_linux_asks_systemd(monkeypatch):
    monkeypatch.setattr(main, "_WINDOWS", False)
    assert main._restart_command("pgs.service") == [
        "systemctl",
        "--user",
        "restart",
        "pgs.service",
    ]


def test_windows_drives_the_scheduled_task(monkeypatch):
    monkeypatch.setattr(main, "_WINDOWS", True)
    argv = main._restart_command("PGS Server")
    # 5.1, and never pwsh — it is what the task itself runs.
    assert argv[0] == "powershell.exe"
    script = argv[-1]
    # Task Scheduler has no "restart", and the order is the whole of it.
    assert script.index("Stop-ScheduledTask") < script.index("Start-ScheduledTask")
    # Without the wait the start is swallowed by -MultipleInstances IgnoreNew.
    assert "Start-Sleep" in script
    assert script.count("'PGS Server'") == 2


def test_a_quoted_unit_name_cannot_break_out(monkeypatch):
    """The name comes from the environment and PowerShell doubles its quotes."""
    monkeypatch.setattr(main, "_WINDOWS", True)
    script = main._restart_command("it's; Stop-Computer")[-1]
    assert "'it''s; Stop-Computer'" in script
    # The payload stays inside the quotes: the script still ends at the name
    # it was given, with no third statement hanging off the end of it.
    assert script.endswith("Start-ScheduledTask -TaskName 'it''s; Stop-Computer'")


def test_the_child_outlives_the_server(monkeypatch):
    """The helper is what brings the app back, so it must survive the app.

    `start_new_session` is a POSIX call and is silently ignored on Windows,
    where the equivalent is a pair of creation flags — and where the flag that
    looks right, DETACHED_PROCESS, stops the helper running at all while
    reporting success. That one is asserted *absent* on purpose: it is the
    shape of the bug, not a detail of the fix.
    """
    seen: dict = {}

    def fake_popen(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return None

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    # The Windows flags exist only in a Windows build of `subprocess`, so on
    # Linux the branch under test cannot even be evaluated without them. These
    # are the documented Win32 values.
    for name, value in (
        ("CREATE_NO_WINDOW", 0x08000000),
        ("CREATE_BREAKAWAY_FROM_JOB", 0x01000000),
        ("DETACHED_PROCESS", 0x00000008),
    ):
        monkeypatch.setattr(subprocess, name, value, raising=False)

    monkeypatch.setattr(main, "_WINDOWS", True)
    main.restart_server()
    flags = seen["kwargs"]["creationflags"]
    # Task Scheduler stops a task by killing its job object, so without this
    # the helper dies with the server it is restarting and the app never comes
    # back — having already replied that it would.
    assert flags & subprocess.CREATE_BREAKAWAY_FROM_JOB
    assert flags & subprocess.CREATE_NO_WINDOW
    # Mutually exclusive with CREATE_NO_WINDOW, and it fails by doing nothing
    # quietly: CreateProcess succeeds, Popen raises nothing, the child never
    # runs. Nothing downstream can notice, so it is pinned here.
    assert not flags & subprocess.DETACHED_PROCESS
    assert "start_new_session" not in seen["kwargs"]

    monkeypatch.setattr(main, "_WINDOWS", False)
    main.restart_server()
    assert seen["kwargs"]["start_new_session"] is True
    assert "creationflags" not in seen["kwargs"]
