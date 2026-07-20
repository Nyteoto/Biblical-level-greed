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
Python half anyway — two build systems to maintain for the same window. pywebview
uses the OS's own engine directly: WebKitGTK on Linux, and on Windows the
Edge WebView2 runtime that ships with Windows 10 and 11, so neither platform
needs a bundled browser. If a tray icon or an auto-updater is ever wanted, the
frontend and API stay exactly as they are and only this file gets replaced.
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


def serve(port: int) -> "uvicorn.Server":  # noqa: F821
    import uvicorn

    # Imported *after* PGS_DATA_DIR is set: config reads the environment at
    # import time, so importing earlier would bind the wrong directory.
    from backend.app.main import app

    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", access_log=False
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True, name="pgs-server").start()
    return server


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

    port = args.port or free_port()
    server = serve(port)
    url = f"http://127.0.0.1:{port}"

    if not wait_until_up(port):
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
            return 0

    _prepare_linux_gui()

    try:
        import webview
    except ImportError:
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
    # Blocks until the window is closed; the server thread is a daemon and dies
    # with the process.
    webview.start()
    server.should_exit = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
