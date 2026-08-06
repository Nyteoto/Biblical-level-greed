"""Editing writes the .toml file. These pin the rules that keep that safe."""
from __future__ import annotations

import pytest

from backend.app import edits, loader, writer
from backend.app.models import Cadence, DomainError


def build(write_domain):
    """A two-node domain on disk, returned as a loaded Domain."""
    write_domain(
        "korean",
        'id = "korean"\ntitle = "Korean"\npriority = 10\ncadence = "daily"\n'
        'color = "rose"\n\n'
        '[[node]]\nid = "hangul"\ntitle = "Hangul"\ntier = 1\nsessions = 3\n\n'
        '[[node]]\nid = "grammar"\ntitle = "Grammar"\ntier = 2\n'
        'requires = ["hangul"]\nsessions = 5\n',
    )
    return loader.load_domain_file(writer.path_for("korean"))


def test_a_domain_survives_a_write_read_round_trip(write_domain):
    original = build(write_domain)
    original = edits.update_domain(original, cadence=Cadence("every_n_days", 3))
    writer.save(original)

    reloaded = loader.load_domain_file(writer.path_for("korean"))
    assert reloaded.title == original.title
    assert reloaded.priority == original.priority
    assert reloaded.color == original.color
    assert reloaded.cadence == Cadence("every_n_days", 3)
    assert [(n.id, n.tier, n.requires, n.estimate) for n in reloaded.nodes] == [
        (n.id, n.tier, n.requires, n.estimate) for n in original.nodes
    ]


def test_text_with_quotes_and_newlines_round_trips(write_domain):
    domain = build(write_domain)
    nasty = 'say "hi"\nthen \\ pause\ttab'
    domain = edits.update_node(domain, "hangul", gate=nasty, note='a "b" c')
    writer.save(domain)

    reloaded = loader.load_domain_file(writer.path_for("korean"))
    assert reloaded.node("hangul").gate == nasty
    assert reloaded.node("hangul").note == 'a "b" c'


def test_deleting_a_node_also_removes_edges_pointing_at_it(write_domain):
    domain = build(write_domain)
    updated = edits.delete_node(domain, "hangul")
    assert [n.id for n in updated.nodes] == ["grammar"]
    assert updated.node("grammar").requires == ()
    loader.validate(updated)  # must not raise: no dangling prerequisite


def test_deleting_renumbers_order_so_the_active_tie_break_stays_honest(write_domain):
    domain = build(write_domain)
    domain, _ = edits.add_node(domain, "Listening", tier=2)
    domain, _ = edits.add_node(domain, "Speaking", tier=2)

    updated = edits.delete_node(domain, "grammar")
    assert [n.order for n in updated.nodes] == list(range(len(updated.nodes)))


def test_connect_rejects_a_cycle_before_anything_is_written(write_domain):
    domain = build(write_domain)
    # grammar already requires hangul; the reverse edge closes a loop.
    with pytest.raises(DomainError, match="cycle"):
        loader.validate(edits.connect(domain, "grammar", "hangul"))

    on_disk = loader.load_domain_file(writer.path_for("korean"))
    assert on_disk.node("hangul").requires == ()


def test_connect_is_idempotent_and_disconnect_removes(write_domain):
    domain = build(write_domain)
    once = edits.connect(domain, "hangul", "grammar")
    assert once.node("grammar").requires == ("hangul",)

    gone = edits.disconnect(once, "hangul", "grammar")
    assert gone.node("grammar").requires == ()


def test_reorder_swaps_siblings_within_a_tier_only(write_domain):
    domain = build(write_domain)
    domain, _ = edits.add_node(domain, "Listening", tier=2)
    assert [n.id for n in domain.nodes if n.tier == 2] == ["grammar", "listening"]

    moved = edits.reorder(domain, "listening", -1)
    assert [n.id for n in moved.nodes if n.tier == 2] == ["listening", "grammar"]
    # Order is the active-node tie-break, so it must be contiguous after a swap.
    assert [n.order for n in moved.nodes] == list(range(len(moved.nodes)))

    # Already at the top of its tier: a no-op, not an error.
    assert edits.reorder(moved, "listening", -1) == moved


def test_new_node_ids_are_slugified_and_deduplicated(write_domain):
    domain = build(write_domain)
    domain, first = edits.add_node(domain, "Core 800 Words!")
    domain, second = edits.add_node(domain, "Core 800 Words!")
    assert first.id == "core-800-words"
    assert second.id == "core-800-words-2"


@pytest.mark.parametrize(
    "call,fragment",
    [
        (lambda d: edits.add_node(d, "  "), "needs a title"),
        (lambda d: edits.add_node(d, "X", tier=0), "tier must be"),
        (lambda d: edits.add_node(d, "X", node_id="Bad ID"), "lowercase"),
        (lambda d: edits.update_node(d, "ghost", title="X"), "unknown node"),
        (lambda d: edits.update_node(d, "hangul", colour="red"), "cannot set"),
        (lambda d: edits.connect(d, "hangul", "hangul"), "cannot require itself"),
        (lambda d: edits.connect(d, "ghost", "hangul"), "unknown node"),
        (lambda d: edits.delete_node(d, "ghost"), "unknown node"),
        (lambda d: edits.parse_cadence("weekly"), "unknown cadence"),
        (lambda d: edits.parse_cadence("every_n_days", 0), "at least 1"),
    ],
)
def test_bad_edits_are_refused_with_a_readable_message(write_domain, call, fragment):
    domain = build(write_domain)
    with pytest.raises(DomainError, match=fragment):
        call(domain)


# Everything above calls `edits` directly, which is where the rules live — and
# that is exactly how every structural endpoint stayed broken through a green
# suite. The shared `_edit` helper was deleted with the journal routes it sat
# beside; the eight callers kept calling it, and each one raised NameError and
# returned a 500. The rules were fine. Nothing reached them.
#
# So these go over HTTP. They assert little about behaviour and everything
# about the route existing and returning something other than a 500.


def _client(write_domain):
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.app.store import store

    build(write_domain)
    client = TestClient(app)
    with client:
        store.reload_domains()
        yield client


@pytest.fixture
def client(write_domain):
    yield from _client(write_domain)


def test_renaming_a_domain_over_http_succeeds(client):
    r = client.patch("/api/domains/korean", json={"title": "Korean, properly"})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Korean, properly"

    assert loader.load_domain_file(writer.path_for("korean")).title == (
        "Korean, properly"
    )


def test_every_structural_endpoint_is_reachable(client):
    """One call per endpoint that goes through `_edit`. A 500 here means the
    route is wired to something that does not exist."""
    calls = [
        ("patch", "/api/domains/korean", {"priority": 3}),
        ("post", "/api/domains/korean/season", {"state": "low"}),
        ("post", "/api/domains/korean/nodes", {"title": "Particles"}),
        ("patch", "/api/domains/korean/nodes/hangul", {"title": "Hangul, again"}),
        ("post", "/api/domains/korean/edges", {"source": "grammar", "target": "particles"}),
        ("post", "/api/domains/korean/nodes/grammar/reorder", {"direction": "up"}),
    ]
    for method, path, body in calls:
        r = getattr(client, method)(path, json=body)
        assert r.status_code < 500, f"{method.upper()} {path} → {r.status_code}: {r.text}"

    assert client.request(
        "DELETE", "/api/domains/korean/edges", params={"source": "grammar", "target": "particles"}
    ).status_code < 500
    assert client.delete("/api/domains/korean/nodes/particles").status_code < 500


def test_a_rejected_edit_is_a_400_and_leaves_the_file_alone(client):
    before = writer.path_for("korean").read_text(encoding="utf-8")
    r = client.patch("/api/domains/korean", json={"title": "   "})
    assert r.status_code == 400, r.text
    assert writer.path_for("korean").read_text(encoding="utf-8") == before


def test_editing_an_unknown_domain_is_refused_not_crashed(client):
    """Pinning what actually happens rather than what reads tidily: `mutate`
    raises DomainError for an unknown id, so this is a 400 with a readable
    message. The 404 branch in `_edit` covers a domain that vanishes between
    the write and the re-read, which is not this."""
    r = client.patch("/api/domains/ghost", json={"title": "X"})
    assert r.status_code == 400, r.text
    assert "ghost" in r.json()["detail"]
