"""Serialises a Domain back to TOML.

The files stay the source of truth and stay hand-editable. A write from the UI
regenerates the whole file, so anything not in the schema — comments especially
— does not survive it. That is why no rationale is kept in the trees: it lives
in docs/, where editing a season cannot delete it.

stdlib has a TOML reader and no writer; this is deliberately the smallest one
that covers our schema rather than a general-purpose emitter.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .config import DOMAINS_DIR, ensure_dirs
from .models import DRILL, Domain, DomainError, Node, Season

SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def slugify(text: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "node"
    if base[0].isdigit():
        base = f"n-{base}"
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def validate_slug(value: str, what: str) -> str:
    if not SLUG_OK.match(value):
        raise DomainError(
            f"{what} `{value}` must be lowercase letters, digits and hyphens"
        )
    return value


def _cadence_line(domain: Domain) -> str:
    if domain.cadence.kind == "every_n_days":
        return f"cadence  = {{ every_n_days = {domain.cadence.n} }}"
    return f"cadence  = {quote(domain.cadence.kind)}"


def _list_line(key: str, values: tuple[str, ...]) -> str:
    return f"{key:<8} = [{', '.join(quote(v) for v in values)}]"


def _block_list(key: str, values: tuple[str, ...]) -> str:
    """A list whose items are long enough that one-per-line stays readable.

    `entry` holds sentences, not slugs, so the single-line form used for
    `requires` would produce a 400-column line nobody can hand-edit.
    """
    items = "".join(f"    {quote(v)},\n" for v in values)
    return f"{key:<8} = [\n{items}]"


def _node_block(node: Node) -> str:
    lines = [
        "[[node]]",
        f"id       = {quote(node.id)}",
        f"title    = {quote(node.title)}",
        f"tier     = {node.tier}",
    ]
    # `kind` is omitted when it's the default, so a plain v0.1 file stays plain.
    if node.kind != DRILL:
        lines.append(f"kind     = {quote(node.kind)}")
    if node.strand:
        lines.append(f"strand   = {quote(node.strand)}")
    if node.requires:
        lines.append(_list_line("requires", node.requires))
    if node.prefers:
        lines.append(_list_line("prefers", node.prefers))
    if node.phases:
        lines.append(_list_line("phases", node.phases))
    # A project accrues phases, so writing a session count would be a lie.
    if node.counts_sessions:
        lines.append(f"estimate = {node.estimate}")
    for key, value in (
        ("min_each", node.min_each),
        ("scheduled", node.scheduled),
        ("metric", node.metric),
    ):
        if value:
            lines.append(f"{key:<8} = {quote(value)}")
    for key, number in (
        ("metric_target", node.metric_target),
        ("decay_days", node.decay_days),
    ):
        if number:
            lines.append(f"{key:<8} = {number}")
    for key, value in (("gate", node.gate), ("note", node.note)):
        if value:
            lines.append(f"{key:<8} = {quote(value)}")
    # Last, because it is the longest thing in the block.
    if node.entry:
        lines.append(_block_list("entry", node.entry))
    return "\n".join(lines)


def to_toml(domain: Domain) -> str:
    head = [
        f"id       = {quote(domain.id)}",
        f"title    = {quote(domain.title)}",
        f"priority = {domain.priority}",
        _cadence_line(domain),
        f"color    = {quote(domain.color)}",
        f"shape    = {quote(domain.shape)}",
    ]
    if domain.strands:
        head.append(_list_line("strands", domain.strands))

    # `[season]` is a TOML table, so it has to sit after the domain's scalars
    # and before the first [[node]] — everything after a table header belongs
    # to that table. Omitted entirely when it is the default, so a file that
    # never opted into seasons stays exactly as it was.
    season = domain.season
    if season != Season():
        head.append("")
        head.append("[season]")
        head.append(f"state    = {quote(season.state)}")
        if season.strands:
            head.append(_list_line("strands", season.strands))
        for key, value in (("until", season.until), ("ends_on", season.ends_on)):
            if value:
                head.append(f"{key:<8} = {quote(value)}")

    blocks = "\n\n".join(_node_block(n) for n in domain.nodes)
    joined = "\n".join(head)
    return f"{joined}\n\n{blocks}\n" if blocks else f"{joined}\n"


def path_for(domain_id: str) -> Path:
    return DOMAINS_DIR / f"{domain_id}.toml"


def save(domain: Domain) -> Path:
    """Write atomically so a crash can never leave a half-written domain file."""
    ensure_dirs()
    target = path_for(domain.id)
    handle, tmp_name = tempfile.mkstemp(dir=str(DOMAINS_DIR), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(to_toml(domain))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return target


def delete(domain_id: str) -> None:
    path_for(domain_id).unlink(missing_ok=True)
