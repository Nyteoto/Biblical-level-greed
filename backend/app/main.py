"""FastAPI app. Thin: parses requests, calls the store, returns derived state."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import edits, eventlog, todos, watcher
from .config import ROOT
from .models import DomainError
from .store import store
from .timeutil import day_key

BUILD_DIR = ROOT / "frontend" / "build"


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.start()
    observer = watcher.start(store)
    try:
        yield
    finally:
        observer.stop()
        observer.join(timeout=2)
        store.close()


app = FastAPI(title="Personal Growth System", version="0.1.0", lifespan=lifespan)

# The SvelteKit dev server runs on another port; in production the built
# frontend is served from this same origin and CORS is irrelevant.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Toggle(BaseModel):
    on: bool | None = None  # omit to flip whatever the current state is
    value: float | None = None  # optional measurable-gate reading (e.g. bpm)


class PhaseIn(BaseModel):
    phase: str
    on: bool | None = None


class JournalIn(BaseModel):
    text: str


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


class TodoIn(BaseModel):
    text: str


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


@app.get("/api/dashboard")
def dashboard() -> dict:
    payload = store.dashboard()
    # Rides along on the board it belongs to, so the Today screen stays one
    # request. The checklist is not derived from domains and does not touch
    # the index — it is only served next to them.
    payload["todos"] = todos.live()
    return payload


@app.post("/api/todos")
def add_todo(body: TodoIn) -> dict:
    try:
        todos.add(body.text)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"todos": todos.live()}


@app.delete("/api/todos/{item_id}")
def complete_todo(item_id: str) -> dict:
    """Ticking an item removes it from the list and nothing from the file.

    DELETE because that is what it does from the caller's side; on disk it
    appends a `done` op, like every other completion in this app.
    """
    todos.complete(item_id)
    return {"todos": todos.live()}


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


@app.post("/api/domains/{domain_id}/nodes/{node_id}/journal")
def add_journal(domain_id: str, node_id: str, body: JournalIn) -> dict:
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "an entry needs some text")
    try:
        store.record(domain_id, node_id, eventlog.JOURNAL, text=text)
    except DomainError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"node": _node_view(domain_id, node_id)}


# -- structural edits ------------------------------------------------------
# These write the .toml file. Validation runs first, so a rejected edit leaves
# the file on disk untouched.


def _edit(domain_id: str, change) -> dict:
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


# Serve the built frontend last so it never shadows /api. The catch-all returns
# index.html for unknown paths so client-side routes like /trees/korean survive
# a page reload.
if BUILD_DIR.exists():

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = (BUILD_DIR / path).resolve()
        if path and target.is_file() and target.is_relative_to(BUILD_DIR.resolve()):
            return FileResponse(target)
        return FileResponse(BUILD_DIR / "index.html")
