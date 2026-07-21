"""The v0.2 taxonomy: node kinds, domain shapes, soft edges, phases, metrics.

Each test names the domain that forced the behaviour to exist, because the
whole taxonomy came out of six researched trees rather than from theory.
"""
from __future__ import annotations

import pytest

from backend.app import edits, eventlog, loader, writer
from backend.app.models import (
    ACTIVE,
    AVAILABLE,
    DONE,
    LOCKED,
    MAINTENANCE,
    OPEN,
    DomainError,
)

# -- soft vs hard blocking --------------------------------------------------
# EE says "you cannot"; AFI says "go anyway". The tree has to say which.

SOFT_AND_HARD = """
id = "d"
title = "D"
priority = 1

[[node]]
id = "root"
title = "Root"
tier = 1
sessions = 1

[[node]]
id = "hard-child"
title = "Hard child"
tier = 2
requires = ["root"]
sessions = 1

[[node]]
id = "soft-child"
title = "Soft child"
tier = 2
prefers = ["root"]
sessions = 1
"""


def test_hard_prerequisite_locks_but_soft_only_advises(write_domain, node_of, unlock):
    write_domain("d", SOFT_AND_HARD)
    # Both children are tier II, so buy them out of `sealed` first: this test is
    # about prerequisites, not about the price.
    unlock("d", "hard-child", 2)
    unlock("d", "soft-child", 2)
    assert node_of("d", "hard-child")["status"] == LOCKED
    assert node_of("d", "soft-child")["status"] == OPEN


def test_soft_blocked_node_reports_what_it_is_waiting_on(write_domain, node_of):
    write_domain("d", SOFT_AND_HARD)
    soft = node_of("d", "soft-child")
    assert soft["waiting_on"] == ["root"]
    assert soft["blocked_by"] == []  # nothing is actually blocking it


def test_completing_the_prerequisite_clears_both(write_domain, node_of, log, unlock):
    write_domain("d", SOFT_AND_HARD)
    unlock("d", "hard-child", 2)
    unlock("d", "soft-child", 2)
    log("d", "root", eventlog.COMPLETE, "2026-07-19")
    assert node_of("d", "hard-child")["status"] in (AVAILABLE, ACTIVE)
    assert node_of("d", "soft-child")["status"] in (AVAILABLE, ACTIVE)


def test_an_available_node_outranks_a_merely_open_one(write_domain, view):
    write_domain("d", SOFT_AND_HARD)
    # root is available, soft-child is open — root must be the active one.
    assert view("d")["active_node_ids"] == ["root"]


def test_an_edge_cannot_be_both_hard_and_soft(write_domain, view):
    write_domain(
        "d",
        """
id = "d"
title = "D"

[[node]]
id = "a"
title = "A"
tier = 1

[[node]]
id = "b"
title = "B"
tier = 2
requires = ["a"]
prefers = ["a"]
""",
    )
    domains, errors = loader.load_all()
    assert any("both a hard requirement and a soft one" in e for e in errors)


def test_soft_edges_are_tier_checked_like_hard_ones(write_domain):
    write_domain(
        "d",
        """
id = "d"
title = "D"

[[node]]
id = "a"
title = "A"
tier = 2

[[node]]
id = "b"
title = "B"
tier = 2
prefers = ["a"]
""",
    )
    _, errors = loader.load_all()
    assert any("must be an earlier tier" in e for e in errors)


# -- domain shapes ----------------------------------------------------------

LADDER = """
id = "l"
title = "L"
shape = "ladder"

[[node]]
id = "a"
title = "A"
tier = 1

[[node]]
id = "b"
title = "B"
tier = 1
"""

STRANDS = """
id = "s"
title = "S"
shape = "strands"
strands = ["left", "right"]

[[node]]
id = "l1"
title = "L1"
tier = 1
strand = "left"

[[node]]
id = "l2"
title = "L2"
tier = 2
strand = "left"
requires = ["l1"]

[[node]]
id = "r1"
title = "R1"
tier = 1
strand = "right"
"""


def test_a_ladder_activates_exactly_one_node(write_domain, view):
    write_domain("l", LADDER)
    assert view("l")["active_node_ids"] == ["a"]


def test_strands_activate_one_node_each(write_domain, view):
    """The Berklee finding: harmony, ear and technique run concurrently."""
    write_domain("s", STRANDS)
    assert view("s")["active_node_ids"] == ["l1", "r1"]


def test_strands_advance_independently(write_domain, view, log, unlock):
    write_domain("s", STRANDS)
    unlock("s", "l2", 2)
    log("s", "l1", eventlog.COMPLETE, "2026-07-19")
    # The left strand moves on; the right strand is untouched by it.
    assert view("s")["active_node_ids"] == ["l2", "r1"]


def test_strands_domain_must_declare_its_strands(write_domain):
    write_domain(
        "s",
        """
id = "s"
title = "S"
shape = "strands"

[[node]]
id = "a"
title = "A"
tier = 1
""",
    )
    _, errors = loader.load_all()
    assert any("the domain must declare" in e for e in errors)


def test_a_node_cannot_name_an_undeclared_strand(write_domain):
    write_domain(
        "s",
        """
id = "s"
title = "S"
shape = "strands"
strands = ["left"]

[[node]]
id = "a"
title = "A"
tier = 1
strand = "nope"
""",
    )
    _, errors = loader.load_all()
    assert any("not one of" in e for e in errors)


CYCLES = """
id = "c"
title = "C"
shape = "cycles"

[[node]]
id = "craft"
title = "Craft"
tier = 1
sessions = 5

[[node]]
id = "unrelated"
title = "Unrelated"
tier = 1
sessions = 5

[[node]]
id = "film"
title = "Film"
tier = 2
kind = "project"
phases = ["prep", "shoot", "post"]
prefers = ["craft"]
"""


def test_cycles_activate_the_project_plus_what_it_waits_on(write_domain, view, unlock):
    """The AFI finding: the film is startable now, craft feeds it."""
    write_domain("c", CYCLES)
    unlock("c", "film", 2)
    active = view("c")["active_node_ids"]
    assert active[0] == "film"  # the project leads
    assert "craft" in active  # the craft it is waiting on comes with it
    assert "unrelated" not in active


def test_a_cycles_domain_needs_at_least_one_project(write_domain):
    write_domain(
        "c",
        """
id = "c"
title = "C"
shape = "cycles"

[[node]]
id = "a"
title = "A"
tier = 1
""",
    )
    _, errors = loader.load_all()
    assert any("at least one node must be kind `project`" in e for e in errors)


# -- projects: phases instead of sessions -----------------------------------

PROJECT = """
id = "p"
title = "P"
shape = "cycles"

[[node]]
id = "film"
title = "Film"
tier = 1
kind = "project"
phases = ["prep", "shoot", "post"]
"""


def test_a_project_counts_phases_not_days(write_domain, node_of, log):
    write_domain("p", PROJECT)
    node = node_of("p", "film")
    assert node["counts_sessions"] is False
    assert node["progress_target"] == 3

    log("p", "film", eventlog.PHASE, "2026-07-19", text="prep")
    node = node_of("p", "film")
    assert node["progress_done"] == 1
    assert node["phases_done"] == ["prep"]


def test_checking_a_project_off_daily_does_not_advance_it(write_domain, node_of, log):
    """You cannot do 12% of a shoot day — this is the whole point."""
    write_domain("p", PROJECT)
    for day in ("2026-07-17", "2026-07-18", "2026-07-19"):
        log("p", "film", eventlog.SESSION, day)
    node = node_of("p", "film")
    assert node["sessions_done"] == 3  # the days are still recorded
    assert node["progress_done"] == 0  # but the project has not moved
    assert node["ready_to_complete"] is False


def test_a_project_is_ready_once_every_phase_is_ticked(write_domain, node_of, log):
    write_domain("p", PROJECT)
    for phase in ("prep", "shoot", "post"):
        log("p", "film", eventlog.PHASE, "2026-07-19", text=phase)
    assert node_of("p", "film")["ready_to_complete"] is True


def test_a_phase_can_be_unticked(write_domain, node_of, log):
    write_domain("p", PROJECT)
    log("p", "film", eventlog.PHASE, "2026-07-18", text="prep")
    log("p", "film", eventlog.PHASE_UNDO, "2026-07-19", text="prep")
    assert node_of("p", "film")["phases_done"] == []


def test_a_project_must_declare_phases(write_domain):
    write_domain(
        "p",
        """
id = "p"
title = "P"

[[node]]
id = "film"
title = "Film"
tier = 1
kind = "project"
""",
    )
    _, errors = loader.load_all()
    assert any("must declare `phases`" in e for e in errors)


def test_only_projects_have_phases(write_domain):
    write_domain(
        "p",
        """
id = "p"
title = "P"

[[node]]
id = "a"
title = "A"
tier = 1
phases = ["one"]
""",
    )
    _, errors = loader.load_all()
    assert any("only projects have phases" in e for e in errors)


# -- drill decay ------------------------------------------------------------

DECAY = """
id = "k"
title = "K"

[[node]]
id = "rudiments"
title = "Rudiments"
tier = 1
sessions = 1
decay_days = 30

[[node]]
id = "theory"
title = "Theory"
tier = 1
kind = "study"
sessions = 1
decay_days = 30
"""


def test_a_completed_drill_goes_stale_after_its_decay_window(
    write_domain, node_of, log
):
    write_domain("k", DECAY)
    log("k", "rudiments", eventlog.SESSION, "2026-05-01")
    log("k", "rudiments", eventlog.COMPLETE, "2026-05-01")
    # 2026-07-20 is 80 days later, well past the 30-day window.
    assert node_of("k", "rudiments")["status"] == MAINTENANCE


def test_a_fresh_drill_stays_done(write_domain, node_of, log):
    write_domain("k", DECAY)
    log("k", "rudiments", eventlog.SESSION, "2026-07-19")
    log("k", "rudiments", eventlog.COMPLETE, "2026-07-19")
    assert node_of("k", "rudiments")["status"] == DONE


def test_study_never_decays(write_domain, node_of, log):
    """Comprehension holds once held; only repetition rots."""
    write_domain("k", DECAY)
    log("k", "theory", eventlog.SESSION, "2026-05-01")
    log("k", "theory", eventlog.COMPLETE, "2026-05-01")
    assert node_of("k", "theory")["status"] == DONE


# -- measurable gates -------------------------------------------------------

METRIC = """
id = "m"
title = "M"

[[node]]
id = "roll"
title = "Roll"
tier = 1
sessions = 5
metric = "bpm"
metric_target = 140
"""


def test_a_session_can_carry_a_reading(write_domain, node_of, log):
    write_domain("m", METRIC)
    log("m", "roll", eventlog.SESSION, "2026-07-18", value=120)
    log("m", "roll", eventlog.SESSION, "2026-07-19", value=132)
    node = node_of("m", "roll")
    assert node["metric"] == "bpm"
    assert node["metric_target"] == 140
    assert [r["value"] for r in node["readings"]] == [120, 132]


def test_undoing_a_session_drops_its_reading(write_domain, node_of, log):
    """The chart must never disagree with the counter."""
    write_domain("m", METRIC)
    log("m", "roll", eventlog.SESSION, "2026-07-18", value=120)
    log("m", "roll", eventlog.SESSION, "2026-07-19", value=132)
    log("m", "roll", eventlog.UNDO, "2026-07-19")
    node = node_of("m", "roll")
    assert node["sessions_done"] == 1
    assert [r["value"] for r in node["readings"]] == [120]


# -- social nodes -----------------------------------------------------------


def test_a_social_node_satisfies_dependents_without_being_completed(
    write_domain, node_of, log, unlock
):
    """You cannot schedule other people, so it should not be a hard gate."""
    write_domain(
        "so",
        """
id = "so"
title = "So"

[[node]]
id = "band"
title = "Band"
tier = 1
kind = "social"
sessions = 2

[[node]]
id = "after"
title = "After"
tier = 2
requires = ["band"]
""",
    )
    unlock("so", "after", 2)
    assert node_of("so", "after")["status"] == LOCKED
    log("so", "band", eventlog.SESSION, "2026-07-18")
    log("so", "band", eventlog.SESSION, "2026-07-19")
    assert node_of("so", "after")["status"] in (AVAILABLE, ACTIVE)


# -- validation of the new fields -------------------------------------------


@pytest.mark.parametrize(
    "body,message",
    [
        ('kind = "nonsense"', "kind must be one of"),
        ('scheduled = "not-a-date"', "scheduled must be YYYY-MM-DD"),
        ("decay_days = -1", "decay_days must be an integer >= 0"),
        ("metric_target = -5", "metric_target must be an integer >= 0"),
    ],
)
def test_bad_node_fields_are_rejected(write_domain, body, message):
    write_domain(
        "bad",
        f"""
id = "bad"
title = "Bad"

[[node]]
id = "a"
title = "A"
tier = 1
{body}
""",
    )
    _, errors = loader.load_all()
    assert any(message in e for e in errors), errors


def test_unknown_shape_is_rejected(write_domain):
    write_domain("bad", 'id = "bad"\ntitle = "Bad"\nshape = "spiral"\n')
    _, errors = loader.load_all()
    assert any("shape must be one of" in e for e in errors)


def test_strands_without_the_strands_shape_is_rejected(write_domain):
    write_domain(
        "bad", 'id = "bad"\ntitle = "Bad"\nshape = "ladder"\nstrands = ["a"]\n'
    )
    _, errors = loader.load_all()
    assert any("only meaningful when shape is" in e for e in errors)


# -- the writer must round-trip every new field -----------------------------


def test_every_new_field_survives_a_rewrite(write_domain):
    """A UI edit rewrites the whole file. Anything the writer forgets is data
    silently destroyed, so assert the round-trip rather than trusting it."""
    write_domain(
        "rt",
        """
id = "rt"
title = "Round trip"
priority = 7
color = "violet"
shape = "strands"
strands = ["one", "two"]

[[node]]
id = "a"
title = "A"
tier = 1
strand = "one"
kind = "drill"
sessions = 9
min_each = "20 min"
metric = "bpm"
metric_target = 140
decay_days = 30
gate = "G"
note = "N"
entry = ["Book: something, with a comma", "Search: two words"]

[[node]]
id = "b"
title = "B"
tier = 2
strand = "two"
kind = "project"
phases = ["prep", "ship"]
requires = ["a"]
prefers = ["a"]

[[node]]
id = "c"
title = "C"
tier = 3
strand = "two"
kind = "exam"
scheduled = "2026-11-14"
requires = ["b"]
sessions = 3
""",
    )
    # `b` requiring and preferring `a` is rejected, so drop the duplicate first.
    domains, errors = loader.load_all()
    assert errors  # proves the overlap check fires
    write_domain(
        "rt",
        (
            (loader.DOMAINS_DIR / "rt.toml").read_text().replace(
                'prefers = ["a"]\n', ""
            )
        ),
    )
    domains, errors = loader.load_all()
    assert not errors, errors

    original = next(d for d in domains if d.id != "mementomori")
    reparsed = loader.load_domain_file(
        _rewrite(original)
    )
    assert writer.to_toml(reparsed) == writer.to_toml(original)
    assert reparsed.strands == ("one", "two")
    assert reparsed.node("a").metric_target == 140
    assert reparsed.node("a").decay_days == 30
    assert reparsed.node("b").phases == ("prep", "ship")
    assert reparsed.node("c").scheduled == "2026-11-14"
    # `entry` is the field most likely to be silently dropped: it is the only
    # multi-line list the writer emits, and losing it would cost the research
    # that makes a node startable at all.
    assert reparsed.node("a").entry == (
        "Book: something, with a comma",
        "Search: two words",
    )
    assert reparsed.node("b").entry == ()


def _rewrite(domain):
    """Serialise a domain and hand back the path it was written to."""
    return writer.save(domain)


# -- authoring through the API ----------------------------------------------
# Three bugs found by trying to use the UI after the taxonomy landed: the
# creation path knew nothing about shapes or kinds, so it could not produce a
# valid node in four of the six domains, and no domain could ever become
# `strands` at all.

STRANDS_DOMAIN = """
id = "s"
title = "S"
shape = "strands"
strands = ["left", "right"]

[[node]]
id = "a"
title = "A"
tier = 1
strand = "left"
"""


def _domain(domain_id: str):
    domains, errors = loader.load_all()
    assert not errors, errors
    return next(d for d in domains if d.id == domain_id)


def test_adding_a_node_to_a_strands_domain_defaults_its_strand(write_domain):
    """Was a hard failure: the UI sends no strand, so the add was rejected."""
    write_domain("s", STRANDS_DOMAIN)
    updated, node = edits.add_node(_domain("s"), title="New one", tier=1)
    assert node.strand == "left"  # the first declared strand
    loader.validate(updated)


def test_adding_a_node_can_name_its_strand_and_kind(write_domain):
    write_domain("s", STRANDS_DOMAIN)
    updated, node = edits.add_node(
        _domain("s"),
        title="A project",
        tier=2,
        kind="project",
        strand="right",
        phases=["prep", "ship"],
    )
    assert (node.kind, node.strand, node.phases) == ("project", "right", ("prep", "ship"))
    loader.validate(updated)


def test_a_project_added_without_phases_is_refused(write_domain):
    write_domain("s", STRANDS_DOMAIN)
    with pytest.raises(DomainError, match="must declare its phases"):
        edits.add_node(_domain("s"), title="Bad", tier=1, kind="project")


def test_a_ladder_can_become_strands(write_domain):
    """Was a deadlock: nodes could not name a strand until the domain declared
    one, and the domain could not declare one while nodes were strandless."""
    write_domain(
        "l",
        """
id = "l"
title = "L"
shape = "ladder"

[[node]]
id = "a"
title = "A"
tier = 1

[[node]]
id = "b"
title = "B"
tier = 2
requires = ["a"]
""",
    )
    updated = edits.update_domain(_domain("l"), shape="strands", strands=("x", "y"))
    assert [n.strand for n in updated.nodes] == ["x", "x"]  # migrated, not rejected
    loader.validate(updated)


def test_leaving_strands_clears_the_node_strands(write_domain):
    write_domain("s", STRANDS_DOMAIN)
    updated = edits.update_domain(_domain("s"), shape="ladder")
    assert updated.strands == ()
    assert all(n.strand == "" for n in updated.nodes)
    loader.validate(updated)


def test_a_new_strands_domain_must_declare_strands(write_domain, data_dir):
    with pytest.raises(DomainError, match="must declare at least one strand"):
        edits.create_domain(title="Nope", shape="strands")


def test_converting_a_node_to_a_project_requires_phases(write_domain):
    write_domain("s", STRANDS_DOMAIN)
    with pytest.raises(DomainError, match="needs phases"):
        edits.update_node(_domain("s"), "a", kind="project")


def test_converting_to_a_project_with_phases_drops_the_session_count(write_domain):
    write_domain("s", STRANDS_DOMAIN)
    updated = edits.update_node(
        _domain("s"), "a", kind="project", phases=["one", "two"]
    )
    node = updated.node("a")
    assert node.kind == "project"
    assert node.phases == ("one", "two")
    assert node.counts_sessions is False
    loader.validate(updated)


def test_converting_away_from_a_project_drops_its_phases(write_domain):
    write_domain(
        "p",
        """
id = "p"
title = "P"

[[node]]
id = "film"
title = "Film"
tier = 1
kind = "project"
phases = ["prep", "shoot"]
""",
    )
    updated = edits.update_node(_domain("p"), "film", kind="drill")
    assert updated.node("film").phases == ()
    loader.validate(updated)


# -- seasons: deliberate neglect --------------------------------------------
# Six domains acquiring at once is ~10h/day. Six domains merely held is ~33
# min/day. The season is the mechanism for the difference, and its central
# claim is that `decay_days` — which the trees already declared — is enough
# information to decide what a parked domain still owes you.

SEASONAL = """
id = "s"
title = "S"
priority = 1
shape = "strands"
strands = ["hands", "theory"]

[season]
state = "high"
strands = ["hands"]
until = "2026-09-01"
ends_on = "gate-node"

[[node]]
id = "rots"
title = "Rots"
tier = 1
strand = "hands"
kind = "drill"
sessions = 1
decay_days = 20

[[node]]
id = "holds"
title = "Holds"
tier = 1
strand = "theory"
kind = "study"
sessions = 1

[[node]]
id = "gate-node"
title = "Gate node"
tier = 2
strand = "hands"
kind = "project"
phases = ["ship"]
requires = ["rots"]
"""


def test_a_high_season_narrows_to_the_strands_it_names(write_domain, view):
    """Seasons that only reordered domains would not have fixed the arithmetic:
    five concurrent strands is 300 min/day inside one domain."""
    write_domain("s", SEASONAL)
    assert view("s")["active_node_ids"] == ["rots"]  # `holds` is out of season


def test_widening_the_season_brings_the_other_strand_back(write_domain, view):
    write_domain("s", SEASONAL.replace('strands = ["hands"]\n', "", 1))
    assert set(view("s")["active_node_ids"]) == {"rots", "holds"}


def test_a_low_season_shows_nothing_until_something_is_about_to_rot(
    write_domain, view, log
):
    """The whole low-season mechanic. No per-node configuration: `decay_days`
    was always enough to say what a held domain still owes you."""
    write_domain("s", SEASONAL.replace('state = "high"', 'state = "low"'))
    log("s", "rots", eventlog.SESSION, day="2026-07-01")
    log("s", "rots", eventlog.COMPLETE, day="2026-07-01")

    # decay_days = 20, grace = 20 // 4 = 5, so it surfaces on day 15.
    assert view("s", today="2026-07-10")["active_node_ids"] == []
    assert view("s", today="2026-07-16")["active_node_ids"] == ["rots"]


def test_a_low_season_still_shows_what_has_already_gone_stale(
    write_domain, view, log
):
    write_domain("s", SEASONAL.replace('state = "high"', 'state = "low"'))
    log("s", "rots", eventlog.SESSION, day="2026-07-01")
    log("s", "rots", eventlog.COMPLETE, day="2026-07-01")
    stale = view("s", today="2026-08-30")
    assert stale["active_node_ids"] == ["rots"]
    assert next(n for n in stale["nodes"] if n["id"] == "rots")["status"] == ACTIVE


def test_an_off_season_shows_nothing_at_all(write_domain, view):
    write_domain("s", SEASONAL.replace("decay_days = 20\n", "").replace(
        'state = "high"', 'state = "off"'
    ))
    assert view("s")["active_node_ids"] == []


def test_a_domain_that_rots_cannot_be_parked(write_domain):
    """The asymmetry that makes seasons safe: electrical-engineering declares no
    decay anywhere and can be switched off for a year; guitar has nine decaying
    nodes and would come back to a wall of maintenance."""
    write_domain("s", SEASONAL.replace('state = "high"', 'state = "off"'))
    _, errors = loader.load_all()
    assert errors and "not allowed" in errors[0] and "Use `low`" in errors[0]


def test_the_season_ends_when_its_trigger_node_ships(write_domain, view, log):
    write_domain("s", SEASONAL)
    assert view("s")["season"]["over"] is False
    log("s", "gate-node", eventlog.COMPLETE, day="2026-07-19")
    ended = view("s")["season"]
    assert ended["over"] is True and ended["reason"] == "gate-node shipped"


def test_the_season_also_ends_when_the_date_passes(write_domain, view):
    """A completion trigger alone deadlocks: projects stall, which is precisely
    what `project` nodes model. The date is the escape hatch."""
    write_domain("s", SEASONAL)
    assert view("s", today="2026-08-31")["season"]["over"] is False
    ended = view("s", today="2026-09-02")["season"]
    assert ended["over"] is True and ended["reason"] == "the date passed"


def test_a_finished_season_is_reported_and_never_auto_applied(
    write_domain, view, log
):
    """The app says the season is over. It does not switch it, for the same
    reason it never presses `complete` for you."""
    write_domain("s", SEASONAL)
    log("s", "gate-node", eventlog.COMPLETE, day="2026-07-19")
    after = view("s")
    assert after["season"]["over"] is True
    assert after["season"]["state"] == "high"  # unchanged on disk


def test_season_survives_a_rewrite(write_domain):
    write_domain("s", SEASONAL)
    domains, errors = loader.load_all()
    assert not errors, errors
    reparsed = loader.load_domain_file(
        _rewrite(next(d for d in domains if d.id != "mementomori"))
    )
    assert reparsed.season.state == "high"
    assert reparsed.season.strands == ("hands",)
    assert reparsed.season.until == "2026-09-01"
    assert reparsed.season.ends_on == "gate-node"


def test_dropping_a_strand_does_not_strand_the_season(write_domain):
    """Same deadlock `_reconcile_strands` solves: a season pointing at a track
    that no longer exists would make the domain unloadable."""
    write_domain("s", SEASONAL)
    domains, _ = loader.load_all()
    narrowed = edits.update_domain(
        next(d for d in domains if d.id != "mementomori"), shape="ladder", strands=[]
    )
    assert narrowed.season.strands == ()
    loader.validate(narrowed)


# -- estimates, and calibrating them ----------------------------------------
# `estimate` is a hypothesis about how many days a node takes. The gate decides
# when it is actually done. The gap between the two is the only reason the
# number is worth recording, so it must be measurable in BOTH directions.

ESTIMATED = """
id = "e"
title = "E"
priority = 1

[[node]]
id = "guess"
title = "Guess"
tier = 1
estimate = 10
gate = "when it is actually good"
"""


def test_the_old_sessions_key_still_loads(write_domain):
    """Renaming the concept must not orphan a hand-written file."""
    write_domain("e", ESTIMATED.replace("estimate = 10", "sessions = 10"))
    domains, errors = loader.load_all()
    assert not errors, errors
    assert next(d for d in domains if d.id != "mementomori").node("guess").estimate == 10


def test_the_writer_emits_the_new_name(write_domain):
    write_domain("e", ESTIMATED.replace("estimate = 10", "sessions = 10"))
    domains, _ = loader.load_all()
    text = writer.to_toml(next(d for d in domains if d.id == "e"))
    assert "estimate = 10" in text
    assert "sessions" not in text


def test_finishing_under_the_estimate_is_recorded(write_domain, node_of, log):
    """The estimate was high. That is data, not failure."""
    for day in ("2026-07-16", "2026-07-17", "2026-07-18"):
        log("e", "guess", eventlog.SESSION, day)
    write_domain("e", ESTIMATED)
    log("e", "guess", eventlog.COMPLETE, "2026-07-18")

    cal = node_of("e", "guess")["calibration"]
    assert cal["estimate"] == 10
    assert cal["actual"] == 3
    assert cal["delta"] == -7
    assert cal["settled"] is True
    assert cal["over"] is False


def test_sessions_can_be_logged_past_the_estimate(write_domain, node_of, log):
    """Nothing clamps at the estimate. Overshoot is the other half of the
    measurement and has to be recordable."""
    write_domain("e", ESTIMATED)
    for n in range(14):
        log("e", "guess", eventlog.SESSION, f"2026-07-{n + 1:02d}")

    node = node_of("e", "guess")
    assert node["sessions_done"] == 14
    assert node["progress_done"] == 14  # not capped at the estimate of 10
    assert node["calibration"]["delta"] == 4
    assert node["calibration"]["over"] is True
    assert node["calibration"]["settled"] is False  # still running


def test_upkeep_after_completion_does_not_inflate_the_measurement(
    write_domain, node_of, log
):
    """Otherwise a well-maintained drill would look progressively worse
    estimated forever, which is the opposite of the truth."""
    write_domain("e", ESTIMATED)
    for day in ("2026-07-01", "2026-07-02", "2026-07-03"):
        log("e", "guess", eventlog.SESSION, day)
    log("e", "guess", eventlog.COMPLETE, "2026-07-03")
    for day in ("2026-07-10", "2026-07-11"):  # maintenance, months of it later
        log("e", "guess", eventlog.SESSION, day)

    node = node_of("e", "guess")
    assert node["sessions_done"] == 5  # every session is still counted
    assert node["calibration"]["actual"] == 3  # but the *cost* was 3
    assert node["calibration"]["delta"] == -7


def test_reopening_unsettles_the_measurement(write_domain, node_of, log):
    write_domain("e", ESTIMATED)
    log("e", "guess", eventlog.SESSION, "2026-07-01")
    log("e", "guess", eventlog.COMPLETE, "2026-07-01")
    log("e", "guess", eventlog.REOPEN, "2026-07-02")
    assert node_of("e", "guess")["calibration"]["settled"] is False


def test_an_unstarted_node_has_no_ratio(write_domain, node_of):
    """Zero sessions is not a ratio of 0.0 — it is an absence, and averaging it
    in would poison the domain's bias."""
    write_domain("e", ESTIMATED)
    assert node_of("e", "guess")["calibration"]["ratio"] is None


def test_a_project_has_no_calibration(write_domain, node_of):
    """Phases are enumerated, not estimated. There is nothing to be wrong about."""
    write_domain("p", PROJECT)
    assert node_of("p", "film")["calibration"] == {}


def test_domain_bias_weights_by_size_not_by_node(write_domain, view, log):
    """A 2-session node finishing in 4 must not swing the number as hard as a
    100-session node finishing in 110, so it is a ratio of totals."""
    write_domain(
        "e",
        """
id = "e"
title = "E"
priority = 1

[[node]]
id = "small"
title = "Small"
tier = 1
estimate = 2

[[node]]
id = "big"
title = "Big"
tier = 2
estimate = 100
""",
    )
    for n in range(4):  # small: 2x over
        log("e", "small", eventlog.SESSION, f"2026-06-{n + 1:02d}")
    log("e", "small", eventlog.COMPLETE, "2026-06-04")
    for n in range(10):  # big: only a little over, but far heavier
        log("e", "big", eventlog.SESSION, f"2026-07-{n + 1:02d}")
    log("e", "big", eventlog.COMPLETE, "2026-07-10")

    cal = view("e")["calibration"]
    assert cal["settled_nodes"] == 2
    assert cal["estimate"] == 102
    assert cal["actual"] == 14
    # A mean of ratios would be (2.0 + 0.1) / 2 = 1.05. Weighted, it is 0.137.
    assert cal["ratio"] == round(14 / 102, 3)


def test_unsettled_nodes_are_left_out_of_the_domain_bias(write_domain, view, log):
    write_domain("e", ESTIMATED)
    for n in range(5):
        log("e", "guess", eventlog.SESSION, f"2026-07-{n + 1:02d}")
    assert view("e")["calibration"]["settled_nodes"] == 0


# -- upkeep before the rot -------------------------------------------------


def test_a_completed_drill_can_be_topped_up_before_it_goes_stale(
    write_domain, node_of, log
):
    """`decay_days` exists to prompt maintenance *before* the skill rots.
    Requiring the node to reach `maintenance` first would invert that: you
    could only repair the lapse, never prevent it."""
    write_domain(
        "d",
        """
id = "d"
title = "D"
[[node]]
id = "hands"
title = "Hands"
tier = 1
kind = "drill"
estimate = 2
decay_days = 20
""",
    )
    log("d", "hands", eventlog.SESSION, "2026-07-01")
    log("d", "hands", eventlog.COMPLETE, "2026-07-01")

    node = node_of("d", "hands", today="2026-07-10")
    assert node["status"] == DONE
    assert node["decay_days"] == 20  # the UI enables upkeep off exactly this

    # A top-up lands as an ordinary session and pushes the decay clock out.
    log("d", "hands", eventlog.SESSION, "2026-07-10")
    assert node_of("d", "hands", today="2026-07-25")["status"] == DONE
    # ...whereas without it, the same date would have gone stale.
    assert node_of("d", "hands", today="2026-08-05")["status"] == MAINTENANCE


def test_upkeep_does_not_disturb_the_calibration(write_domain, node_of, log):
    """Topping up must not make a well-maintained node look badly estimated."""
    write_domain(
        "d",
        """
id = "d"
title = "D"
[[node]]
id = "hands"
title = "Hands"
tier = 1
kind = "drill"
estimate = 2
decay_days = 20
""",
    )
    log("d", "hands", eventlog.SESSION, "2026-07-01")
    log("d", "hands", eventlog.COMPLETE, "2026-07-01")
    for day in ("2026-07-10", "2026-07-20", "2026-07-30"):
        log("d", "hands", eventlog.SESSION, day)

    cal = node_of("d", "hands", today="2026-08-01")["calibration"]
    assert cal["actual"] == 1  # the cost, not the upkeep
    assert cal["settled"] is True
