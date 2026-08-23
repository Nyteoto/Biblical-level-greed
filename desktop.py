#!/usr/bin/env python3
"""Native desktop window for the Personal Growth System.

Starts the FastAPI server on a free loopback port and points a native webview at
it. No browser chrome, no port to remember, nothing listening on a public
interface.

    python desktop.py                     # default data directory
    python desktop.py --data-dir /mnt/shared/pgs
    python desktop.py --browser           # no window; just open the default browser

Not Tauri: that wraps a Rust binary, and this backend is Python — it would need
the Rust toolchain plus a PyInstaller sidecar for the same window. pywebview
drives the system engine directly: WebKitGTK on Linux, WebView2 on Windows.

Both halves of a dual-boot machine run this file. They are separate checkouts
with separate virtual environments — only `--data-dir` is shared — so the only
thing that has to be portable is what is in here. The platform branches are
few and they are all about the window and about finding Tailscale.
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


# Tried in order, first one that answers wins. The bare name covers a PATH that
# already has it; the absolute paths cover the common install locations, which
# matters on Windows because the installer does not put the CLI on PATH and on
# Linux because a service manager's PATH is not a login shell's.
TAILSCALE_BINARIES = (
    "tailscale",
    "/usr/bin/tailscale",
    "/usr/local/bin/tailscale",
    r"C:\Program Files\Tailscale\tailscale.exe",
    r"C:\Program Files (x86)\Tailscale\tailscale.exe",
)


def tailscale_hint() -> str:
    """How to get the daemon running, in the words of the OS you are on.

    Worth branching for rather than printing both: the Linux instruction is a
    command you can paste, and the Windows one is emphatically not — signing in
    from the CLI there leaves the service running as the wrong identity, and
    the tray app is the only supported way in.
    """
    if sys.platform == "win32":
        return "  open the Tailscale tray app and sign in (not the command line)"
    return "  sudo systemctl enable --now tailscaled && sudo tailscale up"


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
                + tailscale_hint()
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

    # Anything raised during startup dies inside this thread, where nobody sees
    # it: the caller only learns that /api/health never answered, which reads
    # as "the app is broken" for what is usually an unmounted --data-dir or a
    # port that is already taken. Keep the exception and report it instead.
    def run() -> None:
        try:
            server.run()
        except BaseException as exc:  # noqa: BLE001 — re-raised by the caller
            startup_error.append(exc)
            raise

    startup_error: list[BaseException] = []
    thread = threading.Thread(target=run, daemon=True, name="pgs-server")
    thread.start()
    # The thread is returned, not discarded, because the process must not begin
    # interpreter shutdown while it is still running. See shutdown().
    server.startup_error = startup_error  # type: ignore[attr-defined]
    return server, thread


def shutdown(server, thread, timeout: float = 5.0) -> None:
    """Stop the server and wait for it. `daemon` stops the thread holding the
    process open but not running: exiting while uvloop is mid-callback
    segfaults in PyGILState_Ensure during interpreter finalization."""
    server.should_exit = True
    thread.join(timeout=timeout)
    if thread.is_alive():
        # A request wedged mid-flight. Escalate rather than exit underneath it.
        server.force_exit = True
        thread.join(timeout=2.0)


def _prepare_gui() -> None:
    """Environment the window needs, set before pywebview is imported.

    Both branches exist because pywebview picks its backend by probing, and
    on both operating systems the first thing it probes is not the thing that
    works here. Naming the backend outright is the difference between a
    window and a traceback.
    """
    if sys.platform == "win32":
        # WebView2, the Chromium control Edge uses. pywebview would otherwise
        # try mshtml — the Internet Explorer engine — which renders this app
        # as an unstyled column: it has no CSS grid, no custom properties and
        # no ES6, so every part of the frontend fails at once.
        os.environ.setdefault("PYWEBVIEW_GUI", "edgechromium")
        return
    _prepare_linux_gui()


def _prepare_linux_gui() -> None:
    """Three Linux fixes, applied before the window is created:
    Wayland -> XWayland (WebKitGTK dies on a native surface), naming the GTK
    backend (pywebview probes Qt first and prints a traceback), and disabling
    the DMA-BUF renderer (GBM allocation fails on NVIDIA, giving a black
    window with a fully loaded page behind it)."""
    if not sys.platform.startswith("linux"):
        return
    # A Wayland session sets GDK_BACKEND=wayland itself, so "leave it if set"
    # would preserve the value that breaks. PGS_KEEP_GDK_BACKEND opts out.
    if not os.environ.get("PGS_KEEP_GDK_BACKEND"):
        if os.environ.get("WAYLAND_DISPLAY") and os.environ.get(
            "GDK_BACKEND", "wayland"
        ).startswith("wayland"):
            os.environ["GDK_BACKEND"] = "x11"
    os.environ.setdefault("PYWEBVIEW_GUI", "gtk")

    # PGS_KEEP_DMABUF=1 to keep the accelerated path.
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
    parser.add_argument(
        "--headless",
        action="store_true",
        help="serve and nothing else: no window, no browser. This is the mode a "
        "background service wants, so a phone can reach the app whenever the "
        "machine is on rather than only while someone is looking at it.",
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
                + tailscale_hint(),
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
        failure = getattr(server, "startup_error", [])
        if failure and isinstance(failure[0], SystemExit):
            # uvicorn logs the real reason (a taken port, usually) and then
            # exits, so the cause is already on stderr just above this.
            print(
                f"server exited during startup — see the error above. "
                f"If the port is taken, drop `--port {port}` and let it pick "
                f"a free one.",
                file=sys.stderr,
            )
        elif failure:
            exc = failure[0]
            print(
                f"server failed to start: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
        else:
            print(
                f"server did not come up on {port} within 30s, and did not "
                "report an error. Try `./run.sh` to see the full log.",
                file=sys.stderr,
            )
        return 1

    if args.headless:
        print(f"serving {url}  (host {args.host})", flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        finally:
            shutdown(server, thread)
        return 0

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

    _prepare_gui()

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
