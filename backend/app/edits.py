"""Pure transformations on a Domain.

Every function returns a new Domain; nothing is written here. The caller
validates the result and only then saves, so a rejected edit leaves the file on
disk exactly as it was.
"""
from __future__ import annotations

from dataclasses import replace

from .models import (
    KINDS,
    PROJECT,
    SEASONS,
    SHAPES,
    STRANDS,
    Cadence,
    Domain,
    DomainError,
    Node,
)
from .writer import slugify, validate_slug

MAX_TIER = 40


def parse_cadence(kind: str, n: int = 1) -> Cadence:
    if kind in ("daily", "weekdays"):
        return Cadence(kind)
    if kind == "every_n_days":
        if n < 1:
            raise DomainError("every_n_days must be at least 1")
        return Cadence(kind, n)
    raise DomainError(f"unknown cadence `{kind}`")


def create_domain(
    title: str,
    priority: int = 100,
    cadence: Cadence | None = None,
    color: str = "amber",
    domain_id: str | None = None,
    taken: set[str] | None = None,
    shape: str = "ladder",
    strands: list[str] | None = None,
) -> Domain:
    if not title.strip():
        raise DomainError("a domain needs a title")
    slug = validate_slug(domain_id, "domain id") if domain_id else slugify(
        title, taken or set()
    )
    if taken and slug in taken:
        raise DomainError(f"domain `{slug}` already exists")
    if shape not in SHAPES:
        raise DomainError(f"unknown shape `{shape}`")
    if shape == STRANDS and not strands:
        raise DomainError("a `strands` domain must declare at least one strand")
    return Domain(
        id=slug,
        title=title.strip(),
        priority=priority,
        cadence=cadence or Cadence("daily"),
        nodes=(),
        color=color,
        source=f"{slug}.toml",
        shape=shape,
        strands=tuple(strands or ()),
    )


def update_domain(domain: Domain, **fields) -> Domain:
    allowed = {"title", "priority", "cadence", "color", "shape", "strands"}
    unknown = set(fields) - allowed
    if unknown:
        raise DomainError(f"cannot set {', '.join(sorted(unknown))} on a domain")
    if "title" in fields and not str(fields["title"]).strip():
        raise DomainError("a domain needs a title")
    if "shape" in fields and fields["shape"] not in SHAPES:
        raise DomainError(f"unknown shape `{fields['shape']}`")
    if "strands" in fields:
        fields["strands"] = tuple(fields["strands"])
    return _reconcile_season(_reconcile_strands(replace(domain, **fields)))


def set_season(
    domain: Domain,
    state: str | None = None,
    strands: list[str] | None = None,
    until: str | None = None,
    ends_on: str | None = None,
) -> Domain:
    """Change a domain's season. Validation (can it be parked, do the strands
    and the trigger node exist) happens in the loader, same as every other
    edit, so a rejected switch never touches the file."""
    season = domain.season
    if state is not None and state not in SEASONS:
        raise DomainError(f"unknown season state `{state}`")
    return replace(
        domain,
        season=replace(
            season,
            state=season.state if state is None else state,
            strands=season.strands if strands is None else tuple(strands),
            until=season.until if until is None else until,
            ends_on=season.ends_on if ends_on is None else ends_on,
        ),
    )


def _reconcile_season(domain: Domain) -> Domain:
    """A season's width names strands, so it cannot outlive them.

    Same deadlock as `_reconcile_strands`: changing shape away from `strands`,
    or renaming them, would otherwise leave a season pointing at tracks that no
    longer exist and make the domain unloadable.
    """
    season = domain.season
    if not season.strands:
        return domain
    kept = tuple(s for s in season.strands if s in domain.strands)
    if kept == season.strands:
        return domain
    return replace(domain, season=replace(season, strands=kept))


def _reconcile_strands(domain: Domain) -> Domain:
    """Keep every node's `strand` consistent with the domain's shape.

    Without this a domain can never *become* `strands`: a node may not name a
    strand until the domain declares one, and the domain may not declare one
    while its nodes are strandless. That is a deadlock, so changing the shape
    migrates the nodes along with it — unassigned nodes land in the first
    strand, which is visible, reversible, and better than an error the user
    cannot act on.
    """
    if domain.shape == STRANDS:
        if not domain.strands:
            return domain  # let validation report the missing declaration
        valid = set(domain.strands)
        default = domain.strands[0]
        nodes = tuple(
            node if node.strand in valid else replace(node, strand=default)
            for node in domain.nodes
        )
    else:
        # `strands` is only meaningful on a strands domain, and so is the
        # per-node field. Drop both rather than leaving dead data in the file.
        domain = replace(domain, strands=())
        nodes = tuple(
            replace(node, strand="") if node.strand else node
            for node in domain.nodes
        )
    return replace(domain, nodes=nodes)


def _renumber(nodes: tuple[Node, ...]) -> tuple[Node, ...]:
    """`order` is the tie-breaker for which node is active, so it must always
    match the file's actual declaration order."""
    return tuple(replace(node, order=i) for i, node in enumerate(nodes))


def add_node(
    domain: Domain,
    title: str,
    tier: int = 1,
    estimate: int = 1,
    requires: list[str] | None = None,
    min_each: str = "",
    gate: str = "",
    entry: list[str] | None = None,
    note: str = "",
    node_id: str | None = None,
    kind: str = "drill",
    strand: str = "",
    prefers: list[str] | None = None,
    phases: list[str] | None = None,
    scheduled: str = "",
    decay_days: int = 0,
    metric: str = "",
    metric_target: int = 0,
) -> tuple[Domain, Node]:
    if not title.strip():
        raise DomainError("a node needs a title")
    if not 1 <= tier <= MAX_TIER:
        raise DomainError(f"tier must be between 1 and {MAX_TIER}")
    if kind not in KINDS:
        raise DomainError(f"unknown node kind `{kind}`")
    # A project with no phases has nothing to accrue, so refuse it here rather
    # than writing a file the loader will reject on the way back in.
    if kind == PROJECT and not phases:
        raise DomainError("a project node must declare its phases")

    taken = {n.id for n in domain.nodes}
    slug = validate_slug(node_id, "node id") if node_id else slugify(title, taken)
    if slug in taken:
        raise DomainError(f"node `{slug}` already exists in this domain")

    # On a strands domain every node needs a strand, so fall back to the first
    # rather than rejecting the add outright — otherwise the UI cannot create a
    # node at all without the caller knowing the domain's shape first.
    if domain.shape == STRANDS and not strand:
        if not domain.strands:
            raise DomainError(
                "this domain's shape is `strands` but it declares none — "
                "add strands to the domain first"
            )
        strand = domain.strands[0]

    node = Node(
        id=slug,
        title=title.strip(),
        tier=tier,
        order=len(domain.nodes),
        requires=tuple(requires or ()),
        prefers=tuple(prefers or ()),
        estimate=max(1, estimate),
        min_each=min_each,
        gate=gate,
        entry=tuple(entry or ()),
        note=note,
        kind=kind,
        strand=strand,
        phases=tuple(phases or ()),
        scheduled=scheduled,
        decay_days=max(0, decay_days),
        metric=metric,
        metric_target=max(0, metric_target),
    )
    return replace(domain, nodes=domain.nodes + (node,)), node


def update_node(domain: Domain, node_id: str, **fields) -> Domain:
    allowed = {
        "title", "tier", "estimate", "requires", "min_each", "gate", "note",
        "kind", "strand", "prefers", "phases", "scheduled", "decay_days",
        "metric", "metric_target", "entry",
    }
    unknown = set(fields) - allowed
    if unknown:
        raise DomainError(f"cannot set {', '.join(sorted(unknown))} on a node")

    if "title" in fields and not str(fields["title"]).strip():
        raise DomainError("a node needs a title")
    if "tier" in fields and not 1 <= int(fields["tier"]) <= MAX_TIER:
        raise DomainError(f"tier must be between 1 and {MAX_TIER}")
    if "kind" in fields and fields["kind"] not in KINDS:
        raise DomainError(f"unknown node kind `{fields['kind']}`")
    if "estimate" in fields:
        fields["estimate"] = max(1, int(fields["estimate"]))
    for key in ("decay_days", "metric_target"):
        if key in fields:
            fields[key] = max(0, int(fields[key]))
    for key in ("requires", "prefers", "phases", "entry"):
        if key in fields:
            fields[key] = tuple(fields[key])

    found = False
    nodes = []
    for node in domain.nodes:
        if node.id == node_id:
            nodes.append(_reconcile_kind(replace(node, **fields)))
            found = True
        else:
            nodes.append(node)
    if not found:
        raise DomainError(f"unknown node `{node_id}`")
    return replace(domain, nodes=tuple(nodes))


def _reconcile_kind(node: Node) -> Node:
    """Keep a node's fields consistent with the kind it has just been given.

    Changing kind is the single most consequential edit in the schema, because
    a project accrues phases and everything else accrues days. Rather than let
    the two coexist and quietly disagree, the losing field is dropped.
    """
    if node.kind == PROJECT:
        if not node.phases:
            raise DomainError(
                f"`{node.id}` is a project, so it needs phases — a project "
                f"tracks phases, not sessions"
            )
        # A project has no session target; keep the file honest about that.
        return replace(node, estimate=1)
    if node.phases:
        return replace(node, phases=())
    return node


def delete_node(domain: Domain, node_id: str) -> Domain:
    if domain.node(node_id) is None:
        raise DomainError(f"unknown node `{node_id}`")
    # Dangling prerequisites would fail validation, so drop the edges too —
    # both the hard ones and the soft ones.
    kept = tuple(
        replace(
            node,
            requires=tuple(r for r in node.requires if r != node_id),
            prefers=tuple(r for r in node.prefers if r != node_id),
        )
        for node in domain.nodes
        if node.id != node_id
    )
    return replace(domain, nodes=_renumber(kept))


def connect(domain: Domain, source: str, target: str, soft: bool = False) -> Domain:
    """Draw an edge: `target` now requires `source`.

    A soft edge is advice — it draws on the tree and orders the work, but it
    never locks the target. Drawing one kind removes the other, so an edge is
    always exactly one of the two.
    """
    if source == target:
        raise DomainError("a node cannot require itself")
    for node_id in (source, target):
        if domain.node(node_id) is None:
            raise DomainError(f"unknown node `{node_id}`")

    node = domain.node(target)
    assert node is not None
    requires = tuple(r for r in node.requires if r != source)
    prefers = tuple(r for r in node.prefers if r != source)
    if soft:
        prefers += (source,)
    else:
        requires += (source,)
    return update_node(domain, target, requires=requires, prefers=prefers)


def disconnect(domain: Domain, source: str, target: str) -> Domain:
    node = domain.node(target)
    if node is None:
        raise DomainError(f"unknown node `{target}`")
    return update_node(
        domain,
        target,
        requires=tuple(r for r in node.requires if r != source),
        prefers=tuple(r for r in node.prefers if r != source),
    )


def reorder(domain: Domain, node_id: str, direction: int) -> Domain:
    """Move a node up or down within its tier — this decides which of two
    unlocked siblings is the active one."""
    nodes = list(domain.nodes)
    idx = next((i for i, n in enumerate(nodes) if n.id == node_id), None)
    if idx is None:
        raise DomainError(f"unknown node `{node_id}`")

    tier = nodes[idx].tier
    siblings = [i for i, n in enumerate(nodes) if n.tier == tier]
    at = siblings.index(idx)
    swap_with = at + direction
    if not 0 <= swap_with < len(siblings):
        return domain

    a, b = siblings[at], siblings[swap_with]
    nodes[a], nodes[b] = nodes[b], nodes[a]
    return replace(domain, nodes=_renumber(tuple(nodes)))
