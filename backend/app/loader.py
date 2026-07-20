"""Reads domain TOML files. These files are the source of truth and the app
never writes them back."""
from __future__ import annotations

import tomllib
from pathlib import Path

from .config import DOMAINS_DIR
from .models import (
    CYCLES,
    HIGH,
    KINDS,
    OFF,
    PROJECT,
    SEASONS,
    SHAPES,
    STRANDS,
    Cadence,
    Domain,
    DomainError,
    Node,
    Season,
)
from .timeutil import parse_day

VALID_COLORS = {"amber", "sky", "emerald", "rose", "violet", "slate"}


def _parse_cadence(raw: object, where: str) -> Cadence:
    if raw is None or raw == "daily":
        return Cadence("daily")
    if raw == "weekdays":
        return Cadence("weekdays")
    if isinstance(raw, dict) and "every_n_days" in raw:
        n = raw["every_n_days"]
        if not isinstance(n, int) or n < 1:
            raise DomainError(f"{where}: every_n_days must be an integer >= 1")
        return Cadence("every_n_days", n)
    raise DomainError(
        f"{where}: cadence must be \"daily\", \"weekdays\", "
        f"or {{ every_n_days = N }} (got {raw!r})"
    )


def _str_list(raw: object, node_id: str, field: str, where: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or any(not isinstance(r, str) for r in raw):
        raise DomainError(f"{where}: node `{node_id}` {field} must be a list of strings")
    return tuple(raw)


def _parse_season(raw: object, where: str) -> Season:
    if raw is None:
        return Season()
    if not isinstance(raw, dict):
        raise DomainError(f"{where}: [season] must be a table")

    state = raw.get("state", HIGH)
    if state not in SEASONS:
        raise DomainError(
            f"{where}: season state must be one of {', '.join(SEASONS)} "
            f"(got {state!r})"
        )

    strands_raw = raw.get("strands", [])
    if not isinstance(strands_raw, list) or any(
        not isinstance(s, str) for s in strands_raw
    ):
        raise DomainError(f"{where}: season strands must be a list of strings")

    until = str(raw.get("until", ""))
    if until:
        try:
            parse_day(until)
        except ValueError as exc:
            raise DomainError(
                f"{where}: season until must be YYYY-MM-DD (got {until!r})"
            ) from exc

    return Season(
        state=state,
        strands=tuple(strands_raw),
        until=until,
        ends_on=str(raw.get("ends_on", "")),
    )


def _check_season(domain: Domain) -> None:
    """The one rule that matters: you may only park what does not rot.

    This is checked against the *file*, never against the log, so it stays a
    static property you can see by reading the toml. `electrical-engineering`
    declares no `decay_days` anywhere and can therefore be switched off for a
    year at zero cost; `guitar` has nine decaying nodes and cannot. That
    asymmetry is real, it is already in the data, and it should be enforced
    rather than remembered.
    """
    season = domain.season

    if season.state == OFF and domain.decaying_nodes:
        names = ", ".join(n.id for n in domain.decaying_nodes[:3])
        extra = "" if len(domain.decaying_nodes) <= 3 else ", …"
        raise DomainError(
            f"{domain.source}: season state `off` is not allowed here — "
            f"{len(domain.decaying_nodes)} nodes decay ({names}{extra}). "
            f"Parking them means returning to a wall of maintenance. "
            f"Use `low`, which shows only what is about to go stale."
        )

    if season.strands:
        if domain.shape != STRANDS:
            raise DomainError(
                f"{domain.source}: season `strands` narrows which strands "
                f"acquire, so it is only meaningful when shape is `strands` "
                f"(shape here is `{domain.shape}`)"
            )
        unknown = [s for s in season.strands if s not in domain.strands]
        if unknown:
            raise DomainError(
                f"{domain.source}: season strand `{unknown[0]}` is not one of "
                f"{', '.join(domain.strands)}"
            )

    if season.ends_on and not domain.node(season.ends_on):
        raise DomainError(
            f"{domain.source}: season ends_on `{season.ends_on}`, "
            f"which does not exist in this domain"
        )


def _parse_node(raw: dict, index: int, where: str) -> Node:
    for required in ("id", "title"):
        if not raw.get(required):
            raise DomainError(f"{where}: node #{index + 1} is missing `{required}`")

    node_id = raw["id"]
    tier = raw.get("tier", 1)
    if not isinstance(tier, int) or tier < 1:
        raise DomainError(f"{where}: node `{node_id}` tier must be an integer >= 1")

    # `sessions` was the old name, when the number read as a target. It is still
    # accepted so hand-written files from before the rename keep loading; the
    # writer only ever emits `estimate`.
    estimate = raw.get("estimate", raw.get("sessions", 1))
    if not isinstance(estimate, int) or estimate < 1:
        raise DomainError(
            f"{where}: node `{node_id}` estimate must be an integer >= 1"
        )

    kind = raw.get("kind", "drill")
    if kind not in KINDS:
        raise DomainError(
            f"{where}: node `{node_id}` kind must be one of "
            f"{', '.join(KINDS)} (got {kind!r})"
        )

    requires = _str_list(raw.get("requires", []), node_id, "requires", where)
    prefers = _str_list(raw.get("prefers", []), node_id, "prefers", where)
    phases = _str_list(raw.get("phases", []), node_id, "phases", where)
    entry = _str_list(raw.get("entry", []), node_id, "entry", where)

    overlap = set(requires) & set(prefers)
    if overlap:
        raise DomainError(
            f"{where}: node `{node_id}` lists {', '.join(sorted(overlap))} as both a "
            f"hard requirement and a soft one — pick one"
        )

    # A project accrues phases instead of days, so it must say what its phases
    # are. This is the rule that stops `sessions = 20` being invented to fill a
    # required field on something that is really one indivisible burst of work.
    if kind == PROJECT and not phases:
        raise DomainError(
            f"{where}: node `{node_id}` is a project, so it must declare `phases` "
            f"(a project tracks phases, not sessions)"
        )
    if phases and kind != PROJECT:
        raise DomainError(
            f"{where}: node `{node_id}` declares phases but is kind `{kind}` — "
            f"only projects have phases"
        )
    if len(set(phases)) != len(phases):
        raise DomainError(f"{where}: node `{node_id}` has duplicate phase names")

    scheduled = str(raw.get("scheduled", ""))
    if scheduled:
        try:
            parse_day(scheduled)
        except ValueError as exc:
            raise DomainError(
                f"{where}: node `{node_id}` scheduled must be YYYY-MM-DD "
                f"(got {scheduled!r})"
            ) from exc

    decay_days = raw.get("decay_days", 0)
    if not isinstance(decay_days, int) or decay_days < 0:
        raise DomainError(f"{where}: node `{node_id}` decay_days must be an integer >= 0")

    metric_target = raw.get("metric_target", 0)
    if not isinstance(metric_target, int) or metric_target < 0:
        raise DomainError(
            f"{where}: node `{node_id}` metric_target must be an integer >= 0"
        )

    return Node(
        id=node_id,
        title=raw["title"],
        tier=tier,
        order=index,
        requires=requires,
        prefers=prefers,
        estimate=estimate,
        min_each=str(raw.get("min_each", "")),
        gate=str(raw.get("gate", "")),
        entry=entry,
        note=str(raw.get("note", "")),
        kind=kind,
        strand=str(raw.get("strand", "")),
        phases=phases,
        scheduled=scheduled,
        decay_days=decay_days,
        metric=str(raw.get("metric", "")),
        metric_target=metric_target,
    )


def _check_graph(domain: Domain) -> None:
    ids = [n.id for n in domain.nodes]
    seen: set[str] = set()
    for node_id in ids:
        if node_id in seen:
            raise DomainError(f"{domain.source}: duplicate node id `{node_id}`")
        seen.add(node_id)

    # Soft edges are checked exactly like hard ones: they still draw a line on
    # the tree, so they must point backwards and must not form a cycle. The only
    # thing that differs is whether an unmet edge locks the node.
    for node in domain.nodes:
        for label, edges in (("requires", node.requires), ("prefers", node.prefers)):
            for req in edges:
                if req not in seen:
                    raise DomainError(
                        f"{domain.source}: node `{node.id}` {label} `{req}`, "
                        f"which does not exist in this domain"
                    )
                if req == node.id:
                    raise DomainError(
                        f"{domain.source}: node `{node.id}` {label} itself"
                    )

    by_id = {n.id: n for n in domain.nodes}

    def edges_of(node_id: str) -> tuple[str, ...]:
        node = by_id[node_id]
        return node.requires + node.prefers

    # Cycle detection: a tech tree must be a DAG or nothing ever unlocks.
    UNVISITED, VISITING, DONE_ = 0, 1, 2
    mark = dict.fromkeys(by_id, UNVISITED)

    def visit(node_id: str, trail: list[str]) -> None:
        if mark[node_id] == DONE_:
            return
        if mark[node_id] == VISITING:
            cycle = " -> ".join(trail[trail.index(node_id):] + [node_id])
            raise DomainError(f"{domain.source}: prerequisite cycle: {cycle}")
        mark[node_id] = VISITING
        for req in edges_of(node_id):
            visit(req, trail + [node_id])
        mark[node_id] = DONE_

    for node_id in by_id:
        visit(node_id, [])

    # A prerequisite at the same or later tier renders as a backward edge and
    # means the tree is mis-tiered. Cheap check, saves confusing layouts.
    for node in domain.nodes:
        for label, edges in (("requires", node.requires), ("prefers", node.prefers)):
            for req in edges:
                if by_id[req].tier >= node.tier:
                    raise DomainError(
                        f"{domain.source}: node `{node.id}` (tier {node.tier}) "
                        f"{label} `{req}` (tier {by_id[req].tier}) — prerequisites "
                        f"must be an earlier tier"
                    )

    # Strands are declared once on the domain so the dashboard has a stable
    # display order. A node naming a strand that doesn't exist is a typo.
    if domain.shape == STRANDS:
        if not domain.strands:
            raise DomainError(
                f"{domain.source}: shape is `strands`, so the domain must declare "
                f"`strands = [...]`"
            )
        for node in domain.nodes:
            if not node.strand:
                raise DomainError(
                    f"{domain.source}: node `{node.id}` has no `strand`, but this "
                    f"domain's shape is `strands`"
                )
            if node.strand not in domain.strands:
                raise DomainError(
                    f"{domain.source}: node `{node.id}` is in strand "
                    f"`{node.strand}`, which is not one of "
                    f"{', '.join(domain.strands)}"
                )
    elif domain.strands:
        raise DomainError(
            f"{domain.source}: `strands` is only meaningful when shape is "
            f"`strands` (shape here is `{domain.shape}`)"
        )

    # A cycles domain is defined by having projects to cycle through.
    if domain.shape == CYCLES and not any(n.kind == PROJECT for n in domain.nodes):
        raise DomainError(
            f"{domain.source}: shape is `cycles`, so at least one node must be "
            f"kind `project`"
        )


def validate(domain: Domain) -> Domain:
    """Run the same checks a file on disk gets. Call before saving an edit."""
    _check_graph(domain)
    _check_season(domain)
    return domain


def load_domain_file(path: Path) -> Domain:
    where = path.name
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise DomainError(f"{where}: invalid TOML — {exc}") from exc

    domain_id = raw.get("id") or path.stem
    priority = raw.get("priority", 100)
    if not isinstance(priority, int):
        raise DomainError(f"{where}: priority must be an integer")

    color = raw.get("color", "amber")
    if color not in VALID_COLORS:
        raise DomainError(
            f"{where}: color must be one of {', '.join(sorted(VALID_COLORS))}"
        )

    shape = raw.get("shape", "ladder")
    if shape not in SHAPES:
        raise DomainError(
            f"{where}: shape must be one of {', '.join(SHAPES)} (got {shape!r})"
        )

    strands_raw = raw.get("strands", [])
    if not isinstance(strands_raw, list) or any(
        not isinstance(s, str) for s in strands_raw
    ):
        raise DomainError(f"{where}: strands must be a list of strings")
    if len(set(strands_raw)) != len(strands_raw):
        raise DomainError(f"{where}: duplicate strand name")

    nodes = tuple(
        _parse_node(entry, i, where)
        for i, entry in enumerate(raw.get("node", []))
    )

    domain = Domain(
        id=domain_id,
        title=raw.get("title", domain_id),
        priority=priority,
        cadence=_parse_cadence(raw.get("cadence"), where),
        nodes=nodes,
        color=color,
        source=where,
        shape=shape,
        strands=tuple(strands_raw),
        season=_parse_season(raw.get("season"), where),
    )
    _check_graph(domain)
    _check_season(domain)
    return domain


def load_all() -> tuple[list[Domain], list[str]]:
    """Returns (domains sorted by priority, error messages).

    A broken file never takes down the app — its error is surfaced in the UI and
    the remaining domains still load.
    """
    domains: list[Domain] = []
    errors: list[str] = []

    if not DOMAINS_DIR.exists():
        return domains, errors

    for path in sorted(DOMAINS_DIR.glob("*.toml")):
        try:
            domains.append(load_domain_file(path))
        except DomainError as exc:
            errors.append(str(exc))
        except OSError as exc:
            errors.append(f"{path.name}: could not read — {exc}")

    seen: dict[str, str] = {}
    unique: list[Domain] = []
    for domain in domains:
        if domain.id in seen:
            errors.append(
                f"{domain.source}: domain id `{domain.id}` already defined in "
                f"{seen[domain.id]} — skipping"
            )
            continue
        seen[domain.id] = domain.source
        unique.append(domain)

    unique.sort(key=lambda d: (d.priority, d.title))
    return unique, errors
