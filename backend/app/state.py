"""Derives everything the UI shows from (domain files + event index).

No state is stored here. Every value below is recomputed from the log, which is
what makes the ranking predictable: there is nothing remembered to surprise you.
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field

from . import eventlog, index
from .models import (
    ACTIVE,
    AVAILABLE,
    CYCLES,
    DONE,
    DRILL,
    LOCKED,
    LOW,
    MAINTENANCE,
    OFF,
    OPEN,
    PROJECT,
    SOCIAL,
    STRANDS,
    STUDY,
    Cadence,
    Domain,
    Node,
)
from .timeutil import day_key, days_between, next_midnight_iso, parse_day

# Statuses you may start work on. `open` is in here deliberately: a soft
# prerequisite is advice, not a gate, so the node stays startable.
STARTABLE = (AVAILABLE, OPEN)


@dataclass
class NodeFacts:
    """What the log says about one node."""

    session_days: set[str] = field(default_factory=set)
    completed: bool = False
    # The day the gate was called. Needed to answer "how many sessions did this
    # actually take", which is not the same as "how many sessions exist" —
    # upkeep logged after completion must not inflate the measurement.
    completed_day: str = ""
    journal: list[dict] = field(default_factory=list)
    phases_done: set[str] = field(default_factory=set)
    readings: list[dict] = field(default_factory=list)  # measurable-gate values


def _blank() -> NodeFacts:
    return NodeFacts()


def _fold(rows: list[sqlite3.Row]) -> dict[str, NodeFacts]:
    """Replay one domain's events into per-node facts.

    Within a single day a node's session is a toggle: the last session/undo
    event for that day wins. Completion is likewise the last complete/reopen,
    and each project phase is its own independent toggle.
    """
    per_day: dict[tuple[str, str], str] = {}  # (node, day) -> session|undo
    completion: dict[str, tuple[str, str]] = {}  # node -> (complete|reopen, day)
    # One reflection per node per day. Keyed like the session toggle, so the
    # last thing written that day is what stands — which lets you revise this
    # evening's entry without the log ever losing what you first wrote.
    per_journal: dict[tuple[str, str], dict] = {}
    per_phase: dict[tuple[str, str], str] = {}  # (node, phase) -> phase|phase_undo
    facts: dict[str, NodeFacts] = {}

    for row in rows:
        kind = row["kind"]
        if kind in (eventlog.SESSION, eventlog.UNDO):
            per_day[(row["node"], row["day"])] = kind
            value = row["value"]
            if kind == eventlog.SESSION and value is not None:
                facts.setdefault(row["node"], _blank()).readings.append(
                    {"day": row["day"], "value": value}
                )
        elif kind == eventlog.JOURNAL:
            per_journal[(row["node"], row["day"])] = {
                "ts": row["ts"],
                "day": row["day"],
                "text": row["text"],
            }
        elif kind in (eventlog.PHASE, eventlog.PHASE_UNDO):
            per_phase[(row["node"], row["text"])] = kind
        else:
            completion[row["node"]] = (kind, row["day"])

    for (node_id, day), kind in per_day.items():
        if kind != eventlog.SESSION:
            continue
        facts.setdefault(node_id, _blank()).session_days.add(day)
    for node_id, (kind, day) in completion.items():
        node_facts = facts.setdefault(node_id, _blank())
        node_facts.completed = kind == eventlog.COMPLETE
        node_facts.completed_day = day if node_facts.completed else ""
    for (node_id, phase), kind in per_phase.items():
        if kind == eventlog.PHASE:
            facts.setdefault(node_id, _blank()).phases_done.add(phase)
    for (node_id, _day), entry in per_journal.items():
        facts.setdefault(node_id, _blank()).journal.append(entry)

    for node_facts in facts.values():
        # Duplicated log lines need no special handling any more: keyed by
        # (node, day), a repeated entry overwrites itself.
        node_facts.journal.sort(key=lambda entry: entry["day"], reverse=True)
        node_facts.readings.sort(key=lambda entry: entry["day"])
        # An undone session leaves its reading behind; drop readings for days
        # that are no longer checked off so the chart matches the counter.
        node_facts.readings = [
            r for r in node_facts.readings if r["day"] in node_facts.session_days
        ]
    return facts


def _is_due(cadence: Cadence, today: str, last_session_day: str | None) -> bool:
    if cadence.kind == "daily":
        return True
    if cadence.kind == "weekdays":
        return parse_day(today).weekday() < 5
    if last_session_day is None:
        return True
    # Having already worked today keeps the domain on today's board rather than
    # removing it — otherwise checking a box makes the row disappear and the
    # day's denominator shrink underneath you.
    if last_session_day == today:
        return True
    return days_between(last_session_day, today) >= cadence.n


def _progress(node: Node, facts: NodeFacts) -> tuple[int, int]:
    """(done, target). A project counts phases; everything else counts days."""
    if node.kind == PROJECT:
        return len(facts.phases_done & set(node.phases)), len(node.phases)
    return len(facts.session_days), node.estimate


def _calibration(node: Node, facts: NodeFacts) -> dict:
    """How good the estimate turned out to be.

    `estimate` is a guess about how many days a node takes; the gate is what
    actually decides it is done. Those two can disagree in both directions, and
    the disagreement is the only reason the number is worth writing down:

      * finishing under the estimate says the guess was high
      * logging past it says the guess was low

    Neither is failure and neither is blocked. `settled` marks the difference
    between a measurement (the gate has been called, so `actual` is final) and a
    running total that may still move.

    Sessions logged *after* completion are upkeep, not cost, so they are
    excluded — otherwise a maintained drill would look progressively worse
    estimated forever.
    """
    if node.kind == PROJECT:
        return {}  # phases are enumerated, not estimated

    if facts.completed and facts.completed_day:
        actual = sum(1 for d in facts.session_days if d <= facts.completed_day)
    else:
        actual = len(facts.session_days)

    delta = actual - node.estimate
    return {
        "estimate": node.estimate,
        "actual": actual,
        "delta": delta,
        # None rather than 0 when nothing was logged: an unmeasured node has no
        # ratio, and pretending it is 0.0 would poison any average.
        "ratio": round(actual / node.estimate, 3) if actual else None,
        "settled": facts.completed,
        "over": delta > 0,
    }


def _domain_calibration(nodes: list[dict]) -> dict:
    """The domain's estimating bias, over settled nodes only.

    Deliberately a ratio of totals rather than a mean of ratios: a 3-session
    node finishing in 6 should not swing the number as hard as a 70-session
    node finishing in 140.
    """
    settled = [
        n["calibration"]
        for n in nodes
        if n.get("calibration", {}).get("settled") and n["calibration"]["actual"]
    ]
    if not settled:
        return {"settled_nodes": 0, "estimate": 0, "actual": 0, "ratio": None}
    estimate = sum(c["estimate"] for c in settled)
    actual = sum(c["actual"] for c in settled)
    return {
        "settled_nodes": len(settled),
        "estimate": estimate,
        "actual": actual,
        "ratio": round(actual / estimate, 3) if estimate else None,
    }


def _status(node: Node, facts: NodeFacts, done_ids: set[str], today: str) -> str:
    missing_hard = [r for r in node.requires if r not in done_ids]
    missing_soft = [r for r in node.prefers if r not in done_ids]

    if facts.completed:
        # Only a drill goes stale. Study holds, a shipped project is shipped,
        # and an exam you passed stays passed.
        if node.kind == DRILL and node.decay_days and facts.session_days:
            idle = days_between(max(facts.session_days), today)
            if idle >= node.decay_days:
                return MAINTENANCE
        return DONE
    if missing_hard:
        return LOCKED
    if missing_soft:
        return OPEN
    return AVAILABLE


def _sort_key(view: dict) -> tuple[int, int, int]:
    """An available node always outranks a merely-open one; then tier, then the
    order it was declared in the file. All three are readable off the .toml."""
    return (1 if view["status"] == OPEN else 0, view["tier"], view["order"])


def _decay_grace(decay_days: int) -> int:
    """How early a decaying node surfaces in a low season.

    A quarter of its own window, floor of two days. Proportional rather than
    fixed so a 14-day drill gets warned sooner in absolute terms than a 120-day
    one — and still readable off the .toml with one division.
    """
    return max(2, decay_days // 4)


def _at_risk(node: Node, view: dict, facts: NodeFacts, today: str) -> bool:
    """Is this node close enough to going stale that a low season should show it?

    Only completed drills decay, so only they can be at risk. This is the whole
    low-season mechanic: it needs no per-node configuration, because the domain
    already declared `decay_days` and that is exactly the information required.
    """
    if view["status"] == MAINTENANCE:
        return True  # already stale — this is the backlog, always show it
    if view["status"] != DONE or node.kind != DRILL or not node.decay_days:
        return False
    if not facts.session_days:
        return False
    idle = days_between(max(facts.session_days), today)
    return idle >= node.decay_days - _decay_grace(node.decay_days)


def _pick_active(domain: Domain, views: list[dict]) -> list[str]:
    """Which nodes are 'today's work'. Branches on the domain's shape.

    ladder  — one node, full stop.
    strands — one node per declared strand, because the curricula these trees
              come from run their strands concurrently on purpose.
    cycles  — the project you are in the middle of, plus the craft it is
              waiting on.
    """
    startable = [v for v in views if v["status"] in STARTABLE]
    if not startable:
        return []

    if domain.shape == STRANDS:
        # A high season may narrow which strands acquire. Five concurrent
        # strands is 300 min/day in electrical-engineering alone, so seasons
        # that only reorder domains would not have fixed anything.
        live = domain.season.strands or domain.strands
        picked: list[str] = []
        for strand in domain.strands:
            if strand not in live:
                continue
            in_strand = [v for v in startable if v["strand"] == strand]
            if in_strand:
                picked.append(min(in_strand, key=_sort_key)["id"])
        return picked

    if domain.shape == CYCLES:
        projects = [v for v in startable if v["kind"] == PROJECT]
        if not projects:
            return [min(startable, key=_sort_key)["id"]]
        current = min(projects, key=_sort_key)
        # The craft this project is actually waiting on — its own unmet
        # prerequisites, hard or soft. That is the honest answer to "what do I
        # do today" when the answer is "prepare for the film you are making".
        feeding = {*current["requires"], *current["prefers"]}
        support = [
            v for v in startable if v["id"] in feeding and v["kind"] != PROJECT
        ]
        if not support:
            support = [
                v
                for v in startable
                if v["kind"] != PROJECT and v["tier"] <= current["tier"]
            ][:1]
        return [current["id"], *[v["id"] for v in sorted(support, key=_sort_key)]]

    return [min(startable, key=_sort_key)["id"]]


def build_domain_view(
    conn: sqlite3.Connection, domain: Domain, today: str | None = None
) -> dict:
    today = today or day_key()
    facts = _fold(index.events_for_domain(conn, domain.id))
    empty = _blank()

    # A social node is never a prerequisite gate you have to clear — you cannot
    # schedule other people — so it counts as satisfied once it has happened at
    # least once, whether or not you ticked it complete.
    done_ids = set()
    for node in domain.nodes:
        node_facts = facts.get(node.id, empty)
        if node_facts.completed or (
            node.kind == SOCIAL and len(node_facts.session_days) >= node.estimate
        ):
            done_ids.add(node.id)

    nodes: list[dict] = []
    for node in domain.nodes:
        node_facts = facts.get(node.id, empty)
        status = _status(node, node_facts, done_ids, today)
        progress_done, progress_target = _progress(node, node_facts)

        days_until = (
            days_between(today, node.scheduled) if node.scheduled else None
        )

        nodes.append(
            {
                "id": node.id,
                "title": node.title,
                "tier": node.tier,
                "order": node.order,
                "kind": node.kind,
                "strand": node.strand,
                "requires": list(node.requires),
                "prefers": list(node.prefers),
                "estimate": node.estimate,
                "sessions_done": len(node_facts.session_days),
                "calibration": _calibration(node, node_facts),
                "counts_sessions": node.counts_sessions,
                "progress_done": progress_done,
                "progress_target": progress_target,
                "phases": list(node.phases),
                "phases_done": sorted(node_facts.phases_done & set(node.phases)),
                "scheduled": node.scheduled,
                "days_until": days_until,
                "decay_days": node.decay_days,
                "metric": node.metric,
                "metric_target": node.metric_target,
                "readings": node_facts.readings,
                "min_each": node.min_each,
                "gate": node.gate,
                "entry": list(node.entry),
                "note": node.note,
                "status": status,
                "blocked_by": [r for r in node.requires if r not in done_ids],
                "waiting_on": [r for r in node.prefers if r not in done_ids],
                "checked_today": today in node_facts.session_days,
                # Accrual met, but completion is always a deliberate human click.
                "ready_to_complete": (
                    status in STARTABLE and progress_done >= progress_target
                ),
                "last_session_day": (
                    max(node_facts.session_days) if node_facts.session_days else None
                ),
                "journal": node_facts.journal,
            }
        )

    season = domain.season
    by_id = {n["id"]: n for n in nodes}

    if season.state == OFF:
        # Nothing rots here (the loader enforced that), so there is genuinely
        # nothing to show and no cost to showing nothing.
        active_ids: list[str] = []
    elif season.state == LOW:
        # Holding, not acquiring: only what is about to go stale. On a quiet
        # week this is empty, which is the correct answer and the entire point.
        active_ids = [
            n["id"]
            for n in nodes
            if _at_risk(
                domain.node(n["id"]), n, facts.get(n["id"], empty), today
            )
        ]
        active_ids.sort(key=lambda i: by_id[i]["tier"])
    else:
        active_ids = _pick_active(domain, nodes)

    for node_id in active_ids:
        by_id[node_id]["status"] = ACTIVE

    active_nodes = [by_id[i] for i in active_ids]
    all_session_days = {d for f in facts.values() for d in f.session_days}
    last_session_day = max(all_session_days) if all_session_days else None

    # A domain counts as checked off for the day once every active node that
    # actually wants a daily check has had one. A project or an exam doesn't
    # demand one, so it is excluded — unless *nothing* active demands one, in
    # which case any check at all counts, or the row could never be satisfied.
    daily = [n for n in active_nodes if n["kind"] in (DRILL, STUDY)]
    if daily:
        checked_today = all(n["checked_today"] for n in daily)
    else:
        checked_today = any(n["checked_today"] for n in active_nodes)

    # Has this season run out? Two independent endings, whichever lands first.
    # Derived and reported, never auto-applied — the app says the season is
    # over and offers the switch, the same way it never presses `complete`.
    shipped = bool(season.ends_on and season.ends_on in done_ids)
    expired = bool(season.until and season.until <= today)
    season_days_left = days_between(today, season.until) if season.until else None

    return {
        "season": {
            "state": season.state,
            "strands": list(season.strands),
            "until": season.until,
            "ends_on": season.ends_on,
            "days_left": season_days_left,
            "shipped": shipped,
            "expired": expired,
            "over": season.acquiring and (shipped or expired),
            # Why it ended, in the words the banner will use.
            "reason": (
                f"{season.ends_on} shipped"
                if shipped
                else ("the date passed" if expired else "")
            ),
            # Whether this domain may be parked outright, straight off the file.
            "can_park": not domain.decaying_nodes,
            "decaying_count": len(domain.decaying_nodes),
        },
        "id": domain.id,
        "title": domain.title,
        "priority": domain.priority,
        "color": domain.color,
        "shape": domain.shape,
        "strands": list(domain.strands),
        "cadence": domain.cadence.kind,
        "cadence_label": domain.cadence.label(),
        "cadence_n": domain.cadence.n,
        "source": domain.source,
        "nodes": nodes,
        "tiers": sorted({n["tier"] for n in nodes}),
        "active_node_ids": active_ids,
        "active_nodes": active_nodes,
        # Kept so anything still reading the singular form keeps working.
        "active_node_id": active_ids[0] if active_ids else None,
        "active_node": active_nodes[0] if active_nodes else None,
        "due_today": _is_due(domain.cadence, today, last_session_day),
        "checked_today": checked_today,
        "last_session_day": last_session_day,
        "total_nodes": len(nodes),
        "done_nodes": len(done_ids),
        "calibration": _domain_calibration(nodes),
        "complete": not active_ids and len(done_ids) == len(nodes) > 0,
    }


def build_dashboard(
    conn: sqlite3.Connection,
    domains: list[Domain],
    errors: list[str],
    today: str | None = None,
) -> dict:
    today = today or day_key()
    views = [build_domain_view(conn, d, today) for d in domains]
    # Domains are already sorted by priority at load time; the dashboard adds no
    # ordering of its own.
    live = [v for v in views if v["due_today"] and v["active_nodes"]]
    return {
        "today": today,
        "next_rollover": next_midnight_iso(),
        "domains": views,
        "errors": errors,
        "due_count": len(live),
        "done_count": sum(1 for v in live if v["checked_today"]),
    }


def as_dict(facts: NodeFacts) -> dict:
    return asdict(facts)
