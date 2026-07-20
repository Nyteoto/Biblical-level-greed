#!/usr/bin/env python3
"""Native desktop window for the Personal Growth System.

Starts the FastAPI server on a free loopback port and points a native webview at
it. No browser chrome, no port to remember, nothing listening on a public
interface.

    python desktop.py                     # default data directory
    python desktop.py --data-dir /mnt/shared/pgs
    python desktop.py --browser           # no window; just open the default browser

WHY NOT TAURI: Tauri wraps a *Rust* binary. This backend is Python, so a Tauri
build would need the Rust toolchain plus a PyInstaller sidecar to carry the
Python half anyway — two build systems to maintain for the same window.
pywebview drives WebKitGTK directly, so nothing is bundled. If a tray icon or
an auto-updater is ever wanted, the frontend and API stay exactly as they are
and only this file gets replaced.

Linux only. The cross-platform guards below are kept because they cost nothing
and removing them would be a change with no upside, but nothing else here is
tested anywhere but Linux.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent

WINDOW_TITLE = "Personal Growth System"
WINDOW_MIN = (900, 640)
WINDOW_SIZE = (1180, 860)


def free_port() -> int:
    """Ask the OS for a port nobody is using, rather than hoping 8787 is free."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_until_up(port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.15)
    return False


TAILSCALE_BINARIES = (
    "tailscale",
    r"C:\Program Files\Tailscale\tailscale.exe",
    "/usr/bin/tailscale",
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
)


def tailscale_ip() -> str | None:
    """This machine's address on the tailnet, or None if it is not up.

    Asking Tailscale rather than the user is not just convenience: binding the
    tailnet interface *specifically* is what makes running without
    authentication defensible. `--host 0.0.0.0` on a café network exposes the
    same app to everyone on it; this address is reachable only by your own
    signed-in devices.
    """
    import subprocess

    for binary in TAILSCALE_BINARIES:
        try:
            out = subprocess.run(
                [binary, "ip", "-4"], capture_output=True, text=True, timeout=10
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            continue
        address = out.stdout.strip().splitlines()
        if out.returncode == 0 and address:
            return address[0].strip()
        if "not running" in (out.stderr or "").lower():
            raise SystemExit(
                "Tailscale is installed but its daemon is not running.\n"
                "  Linux:   sudo systemctl enable --now tailscaled && sudo tailscale up\n"
                "  Windows: open the Tailscale tray app and sign in"
            )
    return None


def serve(port: int, host: str = "127.0.0.1") -> tuple["uvicorn.Server", threading.Thread]:  # noqa: F821
    import uvicorn

    # Imported *after* PGS_DATA_DIR is set: config reads the environment at
    # import time, so importing earlier would bind the wrong directory.
    from backend.app.main import app

    config = uvicorn.Config(
        app, host=host, port=port, log_level="warning", access_log=False
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="pgs-server")
    thread.start()
    # The thread is returned, not discarded, because the process must not begin
    # interpreter shutdown while it is still running. See shutdown().
    return server, thread


def shutdown(server, thread, timeout: float = 5.0) -> None:
    """Stop the server and *wait for it*, before the interpreter tears down.

    Marking the thread `daemon` stops it holding the process open, but it does
    not stop it running. uvicorn only notices `should_exit` when its event loop
    next ticks (~100ms), so returning immediately after setting it raced
    interpreter finalization against uvloop's C timer callback:

        main thread   Py_Exit -> __run_exit_handlers -> _dl_fini
        uvloop thread uv__run_timers -> PyGILState_Ensure -> SIGSEGV

    PyGILState_Ensure cannot allocate a thread state once finalization has
    begun, so the process segfaulted on every clean exit — after all work was
    already flushed, which is why it cost nothing but noise and a 13MB core
    dump each time. Joining the thread removes the race entirely.
    """
    server.should_exit = True
    thread.join(timeout=timeout)
    if thread.is_alive():
        # A request wedged mid-flight. Escalate rather than exit underneath it.
        server.force_exit = True
        thread.join(timeout=2.0)


def _prepare_linux_gui() -> None:
    """Two Linux-only papercuts, both fixed before the window is created.

    1. WebKitGTK's compositing fails on a native Wayland surface here — the
       window opens and then dies with `Error 71 (Protocol error) dispatching
       to Wayland display`. Rendering through XWayland works, and XWayland is
       present in every Wayland session that can run GTK apps at all. Only set
       when the user has not chosen a backend themselves.
    2. pywebview probes Qt before GTK and prints an import traceback when qtpy
       is absent, which it always is here. Naming the backend skips the noise.
    """
    if not sys.platform.startswith("linux"):
        return
    # A Wayland session exports GDK_BACKEND=wayland itself, so "leave it alone
    # if it is already set" would preserve precisely the value that breaks.
    # Override it, and leave one explicit way out.
    if not os.environ.get("PGS_KEEP_GDK_BACKEND"):
        if os.environ.get("WAYLAND_DISPLAY") and os.environ.get(
            "GDK_BACKEND", "wayland"
        ).startswith("wayland"):
            os.environ["GDK_BACKEND"] = "x11"
    os.environ.setdefault("PYWEBVIEW_GUI", "gtk")

    # 3. WebKitGTK 2.42+ composites through a DMA-BUF renderer that allocates
    #    GBM buffers. On NVIDIA under XWayland that allocation fails —
    #    `Failed to create GBM buffer of size WxH: Invalid argument`, logged
    #    once per frame attempt at exactly the window size — and WebKit then
    #    has nowhere to draw, so the window appears but stays **solid black**.
    #    The page is loaded and fully interactive underneath; only the paint is
    #    missing, which is why the DOM probes in testing all passed while the
    #    window showed nothing.
    #
    #    Falling back to the pre-DMA-BUF path costs nothing perceptible for a
    #    static dashboard and fixes it outright. Set PGS_KEEP_DMABUF=1 to keep
    #    the accelerated path if a future driver makes this unnecessary.
    if not os.environ.get("PGS_KEEP_DMABUF"):
        os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")


def main() -> int:
    parser = argparse.ArgumentParser(description=WINDOW_TITLE)
    parser.add_argument(
        "--data-dir",
        help="where domains, log and todos live. Point both operating systems "
        "at one shared folder and there is nothing left to sync.",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="skip the native window and open the default browser instead",
    )
    parser.add_argument("--port", type=int, default=0, help="fixed port (default: any free one)")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="interface to bind. Use `tailscale` to bind this machine's tailnet "
        "address, which is the recommended way to reach it from a phone. "
        "THERE IS NO AUTHENTICATION: anything that can route to the bound "
        "address can read and rewrite your log, so do not use 0.0.0.0 on a "
        "network you do not control.",
    )
    args = parser.parse_args()

    if args.data_dir:
        data_dir = Path(args.data_dir).expanduser().resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        os.environ["PGS_DATA_DIR"] = str(data_dir)
        # The index is a rebuildable cache and belongs beside the data it
        # projects, or two machines sharing a folder would each keep a stale
        # copy in their own checkout.
        os.environ.setdefault("PGS_INDEX_PATH", str(data_dir / "index.sqlite"))

    if not (ROOT / "frontend" / "build" / "index.html").exists():
        print(
            "The frontend is not built yet.\n"
            "  cd frontend && npm install && npm run build",
            file=sys.stderr,
        )
        return 1

    if args.host == "tailscale":
        found = tailscale_ip()
        if not found:
            print(
                "Could not find a Tailscale address. Is it installed and signed in?\n"
                "  Linux:   sudo systemctl enable --now tailscaled && sudo tailscale up\n"
                "  Windows: install from tailscale.com/download and sign in via the tray",
                file=sys.stderr,
            )
            return 1
        args.host = found

    port = args.port or free_port()
    server, thread = serve(port, args.host)
    url = f"http://127.0.0.1:{port}"

    if args.host != "127.0.0.1":
        # Loud, every time. The app has no login, so the network *is* the
        # access control, and that is only true if the interface is private.
        print(
            f"\n  Serving on {args.host}:{port} — reachable beyond this machine.\n"
            f"  There is no authentication. Anyone who can route to this address\n"
            f"  can read your journal and rewrite your history.\n"
            f"  Use a Tailscale/WireGuard address, not 0.0.0.0, unless you mean it.\n",
            file=sys.stderr,
        )

    if not wait_until_up(port):
        shutdown(server, thread)
        print(f"server did not come up on {port}", file=sys.stderr)
        return 1

    if args.browser:
        import webbrowser

        webbrowser.open(url)
        print(f"→ {url}   (ctrl-c to stop)")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        finally:
            shutdown(server, thread)
        return 0

    _prepare_linux_gui()

    try:
        import webview
    except ImportError:
        shutdown(server, thread)
        print(
            "pywebview is not installed, so there is no native window.\n"
            "  pip install pywebview      (then re-run)\n"
            "  python desktop.py --browser   (to use the browser instead)",
            file=sys.stderr,
        )
        return 1

    webview.create_window(
        WINDOW_TITLE,
        url,
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=WINDOW_MIN,
        background_color="#171310",
    )
    # Blocks until the window is closed. The shutdown is in a `finally` so that
    # a crash in the GUI still stops the server thread before exit.
    try:
        webview.start()
    finally:
        shutdown(server, thread)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
