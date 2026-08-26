"""FastAPI app. Thin: parses requests, calls the store, returns derived state.

What is left here after the tech tree
-------------------------------------
This file used to host two sibling apps in one process. The tech tree is gone,
so `backend/app/` is no longer "the tree's half" — it is the **host and the
shared floor**: the process, the disk, the blob store, the backup, and the
frontend. Capture's own logic stayed where it always was, in
`backend/capture/`, and reaches this file through one router.

The split is worth keeping rather than flattening. `media.py`, `config.py`,
`timeutil.py`, `storage.py` and `backup.py` are about the *machine* — a data
directory that may be on an unmounted disk, a photo library with one copy, a
day boundary in the user's zone. `backend/capture/` is about what the user
wrote. Those are different subjects, and a module that knows about both is the
thing this repo has spent its whole history not being.
"""
from __future__ import annotations

import os
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend.capture.api import router as capture_router
from backend.capture.store import CaptureError, store as capture_store

from . import backup, config, media, storage
from .config import ROOT
from .media import MediaError
from .timeutil import day_key
from .version import API_VERSION

# When this process came up. The version check reads it too: a server that
# restarted is a server whose Python is as new as its files.
_STARTED = datetime.now(timezone.utc).isoformat()

BUILD_DIR = ROOT / "frontend" / "build"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Before anything opens a file: if the data lives on a disk that is not
    # mounted, say so and stop rather than quietly starting a second history.
    config.check_data_dir()
    capture_store.start()
    # Wreckage from uploads that died with their connection. Nothing is in
    # flight at startup, so anything old enough is certainly abandoned.
    media.sweep_parts()
    try:
        yield
    finally:
        capture_store.close()


app = FastAPI(title="Trophic", version="0.1.0", lifespan=lifespan)

# The SvelteKit dev server runs on another port; in production the built
# frontend is served from this same origin and CORS is irrelevant.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(CaptureError)
async def _capture_refusal(request: Request, exc: CaptureError) -> JSONResponse:
    """A refusal from capture's store, answered with the code it chose itself.

    Handled centrally for the same reason `OSError` is, and with one more:
    every capture route used to carry its own identical `try/except` — fourteen
    of them — ending in a call that read the exception's *message* to pick
    between 404 and 400. The code is a property of the refusal now (see
    `CaptureError.status`), so the routes are back to being what api.py's
    docstring says they are: parse, call the store, return derived state.
    """
    return JSONResponse(status_code=exc.status, content={"detail": str(exc)})


@app.exception_handler(OSError)
async def _disk_trouble(request: Request, exc: OSError) -> JSONResponse:
    """Every write in this app ends at a file, so every write can fail for
    reasons that are not bugs: a full disk, a `--data-dir` on a volume that is
    not mounted, a directory that lost its permissions.

    Handled centrally rather than at each call site because the answer is the
    same everywhere and the alternative is a bare 500 — which tells the user
    the app is broken when in fact their disk is. The UI prints `detail`, so
    this is what they will read.
    """
    return JSONResponse(
        status_code=507,
        content={
            "detail": (
                f"cannot write to {config.DATA_DIR}: {exc.strerror or exc}. "
                "Nothing was saved. Check the disk is mounted, has space, and "
                "is writable."
            )
        },
    )


# -- the machine ------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "today": day_key(),
        "events_indexed": capture_store.indexed,
        "log_warnings": capture_store.warnings,
        "version": capture_store.version,
    }


@app.get("/api/storage")
def storage_report() -> dict:
    """What the app is using on disk. Walks the tree on request rather than
    tracking it: this is opened rarely and a stale number is worse than a slow
    one."""
    return storage.report()


@app.get("/api/backup")
def backup_status() -> dict:
    """When the copy on the other disk was last made, and whether one is
    running now. See `backup.py` for why this reads a stamp file rather than
    measuring the destination."""
    return backup.status()


@app.post("/api/backup")
def backup_now() -> dict:
    """Start a run and return immediately; the screen polls the GET.

    Every refusal `backup.sh` makes is still made — this starts the script, it
    does not reimplement any part of it.
    """
    return backup.start()


@app.get("/api/version")
def api_version() -> dict:
    """What this process is. Cheap enough to call on every app start."""
    return {"api": API_VERSION, "since": _STARTED}


@app.post("/api/restart")
def restart_server() -> dict:
    """Restart the service in front of this process.

    The app cannot restart *itself* — `Restart=on-failure` means a clean exit
    stays exited — so this asks systemd to do it. Spawned and abandoned rather
    than waited on, because the thing being restarted is the process that would
    do the waiting: the reply has to leave before the server does.
    """
    unit = os.environ.get("PGS_SERVICE", "pgs.service")
    try:
        subprocess.Popen(
            ["systemctl", "--user", "restart", unit],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(500, f"could not restart {unit}: {exc}") from exc
    return {"ok": True, "unit": unit}


# -- media ------------------------------------------------------------------


@app.post("/api/media")
async def upload_media(
    request: Request,
    name: str = "",
    poster_for: str | None = None,
    folder: str = "",
) -> dict:
    """Store one upload, byte for byte, and derive a display copy.

    The body is the file itself rather than a multipart form: the browser
    streams a `File` straight into `fetch`, and this streams it straight to
    disk, so nothing here scales with the size of the thing being uploaded.
    `name` carries the original filename because the extension decides how the
    file will later be served — see media.py.

    `folder` is where the capture bar is about to file this — the pinned folder,
    or a `<tag>` already in the draft. It only ever reaches the *filename*: see
    media.py for why that is a snapshot of the upload rather than a claim about
    membership, which this app resolves and never stores.

    `poster_for` is the second half of video: the browser grabs a frame,
    posts it here, and it lands in the display-copy slot of the clip it names.
    """
    if poster_for is not None:
        data = await request.body()  # a poster is a small JPEG, never a video
        ref = media.save_poster(poster_for, data)
        if ref is None:
            raise HTTPException(404, "no such media to attach a poster to")
        return {"ok": True, "view_url": f"/media/{ref}"}

    length = request.headers.get("content-length")
    try:
        relative, written = await media.write_stream(
            request.stream(),
            day_key(),
            name,
            expected=int(length) if length and length.isdigit() else None,
            folder=folder,
        )
    except MediaError as exc:
        raise HTTPException(400, str(exc)) from exc

    view = media.derive_view(relative)
    return {
        "ok": True,
        "url": f"/media/{relative}",
        "path": relative,
        "view_url": f"/media/{view}" if view else f"/media/{relative}",
        "kind": media.kind_of(relative),
        "bytes": written,
    }


@app.get("/media/{relative:path}")
def get_media(relative: str):
    target = media.path_for(relative)
    if target is None:
        raise HTTPException(404, "no such media")
    # Random id, never rewritten, so it can be cached hard.
    return FileResponse(
        target, headers={"cache-control": "public, max-age=31536000, immutable"}
    )


# Mounted before the SPA catch-all, like every other /api route.
app.include_router(capture_router)


# Serve the built frontend last so it never shadows /api. The catch-all returns
# index.html for unknown paths so client-side routes like /folders/abc survive
# a page reload.
if BUILD_DIR.exists():

    # Serving with no cache headers at all lets a browser heuristically cache
    # the app shell, which is exactly wrong for a single-page app: the shell
    # names content-hashed bundles, so a stale shell asks for chunks that no
    # longer exist and the client router fails on any route added since. That
    # is what a phone reported as a 500 on a page the server was returning 200
    # for. The two rules below are the standard pairing and remove the class.
    IMMUTABLE = "public, max-age=31536000, immutable"  # content-hashed filenames
    REVALIDATE = "no-cache"  # may be stored, must be revalidated before use

    def _static(target: Path, path: str) -> FileResponse:
        hashed = path.startswith("_app/immutable/")
        return FileResponse(
            target, headers={"cache-control": IMMUTABLE if hashed else REVALIDATE}
        )

    # HEAD as well as GET: caches and proxies use it to revalidate, and a
    # static file server answering 405 to it is simply wrong. FastAPI does not
    # imply HEAD from GET, so it has to be named.
    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str):
        # An unmatched /api/ path must 404, not fall through to the app shell.
        # Returning 200 + HTML for a mistyped endpoint means a client — an iOS
        # Shortcut, say — reports success and silently does nothing.
        if path.startswith("api/"):
            raise HTTPException(404, f"no such endpoint: /{path}")
        target = (BUILD_DIR / path).resolve()
        if path and target.is_file() and target.is_relative_to(BUILD_DIR.resolve()):
            return _static(target, path)
        return _static(BUILD_DIR / "index.html", "index.html")
