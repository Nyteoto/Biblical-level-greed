"""FastAPI app. Thin: parses requests, calls the store, returns derived state."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.capture.api import router as capture_router
from backend.capture.store import store as capture_store

from . import backup, config, edits, eventlog, media, storage, tools, watcher, xp
from .config import ROOT
from .media import MediaError
from .models import DomainError
from .tools import ToolError
from .store import store
from .timeutil import day_key

BUILD_DIR = ROOT / "frontend" / "build"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Before anything opens a file: if the data lives on a disk that is not
    # mounted, say so and stop rather than quietly starting a second history.
    config.check_data_dir()
    store.start()
    # capture is a sibling app sharing this process: its own log, its own
    # index, no shared state with the tree beyond the data root.
    capture_store.start()
    # Wreckage from uploads that died with their connection. Nothing is in
    # flight at startup, so anything old enough is certainly abandoned.
    media.sweep_parts()
    observer = watcher.start(store)
    try:
        yield
    finally:
        observer.stop()
        observer.join(timeout=2)
        store.close()
        capture_store.close()


app = FastAPI(title="Personal Growth System", version="0.1.0", lifespan=lifespan)

# The SvelteKit dev server runs on another port; in production the built
# frontend is served from this same origin and CORS is irrelevant.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class Toggle(BaseModel):
    on: bool | None = None  # omit to flip whatever the current state is
    value: float | None = None  # optional measurable-gate reading (e.g. bpm)


class PhaseIn(BaseModel):
    phase: str
    on: bool | None = None


class DomainIn(BaseModel):
    title: str
    id: str | None = None
    priority: int = 100
    cadence: str = "daily"
    cadence_n: int = 1
    color: str = "amber"
    shape: str = "ladder"
    strands: list[str] = []


class DomainPatch(BaseModel):
    title: str | None = None
    priority: int | None = None
    cadence: str | None = None
    cadence_n: int | None = None
    color: str | None = None
    shape: str | None = None
    strands: list[str] | None = None


class SeasonIn(BaseModel):
    state: str | None = None  # high | low | off
    strands: list[str] | None = None  # width: which strands acquire
    until: str | None = None  # YYYY-MM-DD, the deadline
    ends_on: str | None = None  # node whose completion ends the season early


class NodeIn(BaseModel):
    title: str
    tier: int = 1
    estimate: int = 1
    requires: list[str] = []
    min_each: str = ""
    gate: str = ""
    entry: list[str] = []
    note: str = ""
    kind: str = "drill"
    strand: str = ""
    prefers: list[str] = []
    phases: list[str] = []
    scheduled: str = ""
    decay_days: int = 0
    metric: str = ""
    metric_target: int = 0


class NodePatch(BaseModel):
    title: str | None = None
    tier: int | None = None
    estimate: int | None = None
    requires: list[str] | None = None
    min_each: str | None = None
    gate: str | None = None
    entry: list[str] | None = None
    note: str | None = None
    kind: str | None = None
    strand: str | None = None
    prefers: list[str] | None = None
    phases: list[str] | None = None
    scheduled: str | None = None
    decay_days: int | None = None
    metric: str | None = None
    metric_target: int | None = None


class EdgeIn(BaseModel):
    source: str  # the prerequisite
    target: str  # the node that now requires it
    soft: bool = False  # a soft edge advises but never locks


class ReorderIn(BaseModel):
    direction: int  # -1 up, +1 down, within the node's tier


def _domain_view(domain_id: str) -> dict:
    view = store.domain_view(domain_id)
    if view is None:
        raise HTTPException(404, f"unknown domain `{domain_id}`")
    return view


def _node_view(domain_id: str, node_id: str) -> dict:
    view = store.domain_view(domain_id)
    if view is None:
        raise HTTPException(404, f"unknown domain `{domain_id}`")
    for node in view["nodes"]:
        if node["id"] == node_id:
            return node
    raise HTTPException(404, f"unknown node `{node_id}`")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "today": day_key(),
        "domains": len(store.domains),
        "events_indexed": store.indexed,
        "log_warnings": store.warnings,
        "domain_errors": store.errors,
        "version": store.version,
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


@app.get("/api/dashboard")
def dashboard() -> dict:
    return store.dashboard()


# -- tools: the instruments a domain is practised with ----------------------


class ToolIn(BaseModel):
    name: str = ""
    description: str = ""
    image: str = ""
    price_kind: str = "paid"
    price: str = ""
    acquired: str = ""
    retired: str = ""
    type: str = ""
    model: str = ""


@app.get("/api/domains/{domain_id}/tools")
def list_tools(domain_id: str) -> dict:
    _domain_view(domain_id)
    try:
        return {"tools": tools.read(domain_id)}
    except ToolError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/domains/{domain_id}/tools", status_code=201)
def add_tool(domain_id: str, body: ToolIn) -> dict:
    _domain_view(domain_id)
    try:
        tools.add(domain_id, body.model_dump())
    except ToolError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"tools": tools.read(domain_id)}


@app.patch("/api/domains/{domain_id}/tools/{tool_id}")
def patch_tool(domain_id: str, tool_id: str, body: ToolIn) -> dict:
    """Partial by design: only the fields actually present in the request move.

    `model_dump()` would return every field including its default, so a PATCH
    carrying just a photo would arrive as an empty name and wipe the profile —
    which is exactly what it did.
    """
    _domain_view(domain_id)
    try:
        tools.update(domain_id, tool_id, body.model_dump(exclude_unset=True))
    except ToolError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"tools": tools.read(domain_id)}


@app.delete("/api/domains/{domain_id}/tools/{tool_id}")
def drop_tool(domain_id: str, tool_id: str) -> dict:
    _domain_view(domain_id)
    try:
        tools.remove(domain_id, tool_id)
    except ToolError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"tools": tools.read(domain_id)}


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


@app.get("/api/domains")
def domains() -> dict:
    return {"domains": [store.domain_view(d.id) for d in store.domains]}


@app.get("/api/domains/{domain_id}")
def domain(domain_id: str) -> dict:
    view = store.domain_view(domain_id)
    if view is None:
        raise HTTPException(404, f"unknown domain `{domain_id}`")
    return view


@app.post("/api/domains/{domain_id}/nodes/{node_id}/session")
def toggle_session(domain_id: str, node_id: str, body: Toggle | None = None) -> dict:
    node = _node_view(domain_id, node_id)
    want_on = (body.on if body and body.on is not None else not node["checked_today"])
    if want_on == node["checked_today"]:
        return {"changed": False, "node": node}

    try:
        store.record(
            domain_id,
            node_id,
            eventlog.SESSION if want_on else eventlog.UNDO,
            value=body.value if body and want_on else None,
        )
    except DomainError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"changed": True, "node": _node_view(domain_id, node_id)}


@app.post("/api/domains/{domain_id}/nodes/{node_id}/complete")
def toggle_complete(domain_id: str, node_id: str, body: Toggle | None = None) -> dict:
    node = _node_view(domain_id, node_id)
    currently_done = node["status"] == "done"
    want_on = body.on if body and body.on is not None else not currently_done
    if want_on == currently_done:
        return {"changed": False, "node": node}

    try:
        store.record(
            domain_id, node_id, eventlog.COMPLETE if want_on else eventlog.REOPEN
        )
    except DomainError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"changed": True, "domain": store.domain_view(domain_id)}


@app.post("/api/domains/{domain_id}/nodes/{node_id}/phase")
def toggle_phase(domain_id: str, node_id: str, body: PhaseIn) -> dict:
    """Tick one phase of a project. A project accrues phases, not days."""
    node = _node_view(domain_id, node_id)
    if node["kind"] != "project":
        raise HTTPException(400, f"`{node_id}` is not a project — it has no phases")
    if body.phase not in node["phases"]:
        raise HTTPException(
            400, f"`{body.phase}` is not a phase of `{node_id}`"
        )

    currently_on = body.phase in node["phases_done"]
    want_on = body.on if body.on is not None else not currently_on
    if want_on == currently_on:
        return {"changed": False, "node": node}

    try:
        store.record(
            domain_id,
            node_id,
            eventlog.PHASE if want_on else eventlog.PHASE_UNDO,
            text=body.phase,
        )
    except DomainError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"changed": True, "node": _node_view(domain_id, node_id)}


@app.post("/api/domains/{domain_id}/nodes/{node_id}/unlock")
def unlock_node(domain_id: str, node_id: str) -> dict:
    """Buy a node out of `sealed`. Permanent: there is no relock.

    The price is written into the event, so retuning the economy later cannot
    make a past purchase unaffordable or change what it cost. Affordability is
    checked here rather than in the board, because the bank is global and a
    domain view only knows about itself.
    """
    node = _node_view(domain_id, node_id)
    price = xp.unlock_price(node["tier"])
    if price <= 0:
        raise HTTPException(409, f"`{node_id}` is tier I and costs nothing")
    if node["unlocked"]:
        raise HTTPException(409, f"`{node_id}` is already unlocked")

    blocked = [c for c in node["conditions"] if not c["met"] and c["key"] != "unlock_price"]
    if blocked:
        raise HTTPException(
            409,
            f"`{node_id}` is not ready to unlock: "
            + "; ".join(c["detail"] or c["label"] for c in blocked),
        )

    try:
        store.spend_unlock(domain_id, node_id, price)
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc

    return {"node": _node_view(domain_id, node_id), "xp": store.dashboard()["xp"]}


def _edit(domain_id: str, change) -> dict:
    """Apply a structural edit and return the domain as the UI wants it back.

    Every structural endpoint goes through here so that validation, the write
    and the refreshed view stay in one place: `store.mutate` validates the new
    Domain before it touches the file, so a rejected edit is a 400 and the
    `.toml` on disk is untouched.
    """
    try:
        store.mutate(domain_id, change)
    except DomainError as exc:
        raise HTTPException(400, str(exc)) from exc
    view = store.domain_view(domain_id)
    if view is None:
        raise HTTPException(404, f"unknown domain `{domain_id}`")
    return view


@app.post("/api/domains", status_code=201)
def create_domain(body: DomainIn) -> dict:
    try:
        domain = store.create_domain(
            title=body.title,
            priority=body.priority,
            cadence=edits.parse_cadence(body.cadence, body.cadence_n),
            color=body.color,
            domain_id=body.id,
            shape=body.shape,
            strands=body.strands,
        )
    except DomainError as exc:
        raise HTTPException(400, str(exc)) from exc
    return store.domain_view(domain.id) or {}


@app.patch("/api/domains/{domain_id}")
def patch_domain(domain_id: str, body: DomainPatch) -> dict:
    fields = body.model_dump(exclude_none=True)
    cadence_kind = fields.pop("cadence", None)
    cadence_n = fields.pop("cadence_n", None)
    try:
        if cadence_kind is not None:
            fields["cadence"] = edits.parse_cadence(cadence_kind, cadence_n or 1)
    except DomainError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _edit(domain_id, lambda d: edits.update_domain(d, **fields))


@app.post("/api/domains/{domain_id}/season")
def set_season(domain_id: str, body: SeasonIn) -> dict:
    """Switch a domain between acquiring, holding and parked.

    Deliberately its own endpoint rather than a field on the domain PATCH: this
    is the one edit that changes what the *whole board* shows tomorrow, and it
    should be as easy to find in the log of what you did as it is in the UI.
    """
    fields = body.model_dump(exclude_none=True)
    return _edit(domain_id, lambda d: edits.set_season(d, **fields))


@app.delete("/api/domains/{domain_id}")
def delete_domain(domain_id: str) -> dict:
    try:
        store.delete_domain(domain_id)
    except DomainError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"deleted": domain_id}


@app.post("/api/domains/{domain_id}/nodes", status_code=201)
def create_node(domain_id: str, body: NodeIn) -> dict:
    created: dict = {}

    def change(domain):
        updated, node = edits.add_node(
            domain,
            **body.model_dump(),
        )
        created["id"] = node.id
        return updated

    view = _edit(domain_id, change)
    return {"created": created.get("id"), "domain": view}


@app.patch("/api/domains/{domain_id}/nodes/{node_id}")
def patch_node(domain_id: str, node_id: str, body: NodePatch) -> dict:
    fields = body.model_dump(exclude_none=True)
    return _edit(domain_id, lambda d: edits.update_node(d, node_id, **fields))


@app.delete("/api/domains/{domain_id}/nodes/{node_id}")
def delete_node(domain_id: str, node_id: str) -> dict:
    return _edit(domain_id, lambda d: edits.delete_node(d, node_id))


@app.post("/api/domains/{domain_id}/edges")
def connect_nodes(domain_id: str, body: EdgeIn) -> dict:
    return _edit(domain_id, lambda d: edits.connect(d, body.source, body.target, soft=body.soft))


@app.delete("/api/domains/{domain_id}/edges")
def disconnect_nodes(domain_id: str, source: str, target: str) -> dict:
    return _edit(domain_id, lambda d: edits.disconnect(d, source, target))


@app.post("/api/domains/{domain_id}/nodes/{node_id}/reorder")
def reorder_node(domain_id: str, node_id: str, body: ReorderIn) -> dict:
    return _edit(domain_id, lambda d: edits.reorder(d, node_id, body.direction))


@app.post("/api/admin/reindex")
def reindex() -> dict:
    """Rebuild the index from the log. Safe at any time; changes nothing."""
    store.reindex()
    return {"events_indexed": store.indexed, "warnings": store.warnings}


@app.post("/api/admin/reload")
def reload_domains() -> dict:
    store.reload_domains()
    return {"domains": len(store.domains), "errors": store.errors}


# Mounted before the SPA catch-all, like every other /api route.
app.include_router(capture_router)


# Serve the built frontend last so it never shadows /api. The catch-all returns
# index.html for unknown paths so client-side routes like /trees/korean survive
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
