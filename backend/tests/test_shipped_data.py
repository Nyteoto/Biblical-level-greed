"""The six shipped trees, checked as data.

These exist because a stale server process once round-tripped `chinese.toml`
through pre-rename code: its loader did not know the `estimate` key, defaulted
all twelve nodes to 1, and wrote that back. Nothing raised, the file stayed
valid, and the loss was only visible by noticing that a tree page read `0/1`
everywhere.

The unit tests all build their own fixtures, so none of them looked at the real
files. These do.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.app import config

REPO_DOMAINS = Path(__file__).resolve().parents[2] / "data" / "domains"
FILES = sorted(REPO_DOMAINS.glob("*.toml"))

# Loaded directly off disk rather than through the fixtures, which point at a
# throwaway data directory.
def _load(path: Path):
    from backend.app import loader

    original = config.DOMAINS_DIR
    try:
        return loader.load_domain_file(path)
    finally:
        assert config.DOMAINS_DIR is original


def test_the_shipped_trees_exist():
    assert len(FILES) == 6, [f.name for f in FILES]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_every_shipped_tree_loads(path: Path):
    domain = _load(path)
    assert domain.nodes


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_no_shipped_tree_uses_the_legacy_key(path: Path):
    """`sessions` still loads, for hand-written files from before the rename.
    But a *shipped* file using it means something wrote with old code."""
    offenders = [
        n for n, line in enumerate(path.read_text().splitlines(), 1)
        if re.match(r"^\s*sessions\s*=", line)
    ]
    assert not offenders, (
        f"{path.name} uses the legacy `sessions` key on line(s) {offenders}. "
        f"Something wrote this file with pre-rename code."
    )


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_estimates_are_not_silently_defaulted(path: Path):
    """The exact shape of the corruption: every node at the default of 1.

    A real tree has considered numbers on it. One node at 1 is a judgement; a
    whole domain at 1 is a file that lost them.
    """
    domain = _load(path)
    counted = [n for n in domain.nodes if n.kind != "project"]
    if not counted:
        return
    defaulted = [n.id for n in counted if n.estimate == 1]
    assert len(defaulted) < len(counted), (
        f"{path.name}: all {len(counted)} non-project nodes have estimate=1, "
        f"which is what a default-collapse looks like."
    )


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_every_node_carries_entry_material(path: Path):
    """The research pass put 3-5 pointers on all 107 nodes. A rewrite that
    dropped them would leave the tree unusable to a self-learner again."""
    domain = _load(path)
    missing = [n.id for n in domain.nodes if not n.entry]
    assert not missing, f"{path.name}: no `entry` on {missing}"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_every_node_states_its_gate(path: Path):
    domain = _load(path)
    missing = [n.id for n in domain.nodes if not n.gate]
    assert not missing, f"{path.name}: no `gate` on {missing}"


def test_the_trees_carry_no_prose():
    """The rationale lives in docs/, not inside the data.

    These files used to open with a comment block explaining where the
    curriculum came from — written by a model, for models, and duplicated from
    docs/sources.md. It could not survive a write, because the UI regenerates
    the file from parsed data and TOML comments are discarded at parse. That
    made every season switch delete it.

    The fix was to stop keeping it there. A `.toml` is data the user edits; the
    argument for the shape belongs in docs/sources.md and docs/domain-shapes.md,
    which is where it already was.
    """
    prose = [
        p.name
        for p in FILES
        if any(line.lstrip().startswith("#") for line in p.read_text().splitlines())
    ]
    assert not prose, f"rationale crept back into {prose} — it belongs in docs/"
