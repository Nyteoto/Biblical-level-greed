"""Mementomori — the foundation domain, compiled in rather than loaded.

Every other tree is a `.toml` you can edit, reorder or delete. This one is not,
because it is the thing the others are *for*. A tech tree of skills is an
arbitrary structure until it is attached to a body that sleeps, walks, eats and
has to talk to people; this domain is that attachment, and being able to delete
it from the UI at 2am would defeat the point.

It is deliberately almost inert. No prices, no prerequisites, no kinds, no
estimates, no journal, no notes, no completion. A node here is a sentence you
read, not a thing you tick — every win condition below is written to be
*retired*: once it is true and boring you stop tracking it and move up.

The two exceptions are `sleep` and `movement`. Those are real drills, they
count check-offs, and they carry the best streak rate in the system — plus a
buff to everything else once the streak holds. Nothing else in this app
compounds the way sleeping properly does, so nothing else is paid like it.
"""
from __future__ import annotations

from .models import DRILL, LOW, REMINDER, Cadence, Domain, Node, Season

DOMAIN_ID = "mementomori"

# The two nodes that pay. Named here so the scorer does not have to guess which
# nodes are load-bearing, and so adding a third is a deliberate edit.
SUBSTRATE_NODES = ("sleep", "movement")


def _node(order: int, node_id: str, title: str, tier: int, gate: str, **kw) -> Node:
    return Node(
        id=node_id,
        title=title,
        tier=tier,
        order=order,
        gate=gate.strip(),
        kind=kw.pop("kind", REMINDER),
        estimate=kw.pop("estimate", 0),
        **kw,
    )


_SPEC: list[tuple[str, str, int, str, dict]] = [
    # -- Tier 0: Substrate ---------------------------------------------------
    (
        "sleep",
        "Sleep",
        0,
        """
Consistent sleep and wake times within about an hour, six nights out of seven.

The skill is defending the wind-down hour against your own evening self.

Retire it when: you wake without an alarm most days.
""",
        {"kind": DRILL, "decay_days": 2},
    ),
    (
        "movement",
        "Movement",
        0,
        """
A daily walk that happens regardless of mood, plus breaking up long sitting.

The skill is making it non-negotiable and unremarkable.

Retire it when: a day without it feels off.
""",
        {"kind": DRILL, "decay_days": 2},
    ),
    (
        "food",
        "Food",
        0,
        """
Eat at roughly regular times, protein at each meal, water by default.

The skill is keeping the kitchen stocked so the easy choice is the decent one.

Retire it when: food is a solved background process you do not think about.
Deliberately not a numbers game.
""",
        {},
    ),
    # -- Tier 1: Attention ---------------------------------------------------
    (
        "reclaimed-input",
        "Reclaimed input",
        1,
        """
Phone out of the bedroom, notifications off by default, feeds require
deliberate effort to reach.

Retire it when: you can be in a queue without reaching for it.
""",
        {},
    ),
    (
        "sustained-focus",
        "Sustained focus",
        1,
        """
One 60-90 minute single-tasked block, unbroken, most days. Measure the streak
of blocks, never the output.

Retire it when: 90 minutes stops feeling long.
""",
        {},
    ),
    (
        "boredom-tolerance",
        "Boredom tolerance",
        1,
        """
One daily stretch — a walk, a commute, waiting — with no input at all.

Retire it when: ideas start arriving there.
""",
        {},
    ),
    # -- Tier 2: Emotional literacy -----------------------------------------
    (
        "naming",
        "Naming",
        2,
        """
You can identify what you are feeling within a few minutes of it starting,
with a specific word.

Retire it when: "off" and "stressed" have been replaced by accurate nouns.
""",
        {},
    ),
    (
        "gap-tolerance",
        "Gap tolerance",
        2,
        """
You can sit with discomfort for ten minutes without reaching for the reflex
fix — scroll, snack, buy, pick a fight.

The skill is noticing the urge as an event rather than a command.

Retire it when: the urge becomes information.
""",
        {},
    ),
    (
        "separation",
        "Separation",
        2,
        """
You can state the fact, and the story about the fact, as two separate
sentences.

Retire it when: you catch the story mid-flight.
""",
        {},
    ),
    # -- Tier 3: Relationships ----------------------------------------------
    (
        "maintenance",
        "Maintenance",
        3,
        """
Proactive contact with each close person, on a rhythm you actually chose.

Countable, and the count is the point — this is where drift is invisible.
""",
        {},
    ),
    (
        "directness",
        "Directness",
        3,
        """
Asking for what you want without hedging, and declining without an elaborate
justification.

Retire it when: "no" takes one sentence.
""",
        {},
    ),
    (
        "repair",
        "Repair",
        3,
        """
Initiating repair within a week of any rupture.

This is the tier's real skill, and its rarest.

Retire it when: conflicts end in reconnection rather than quiet distance.
""",
        {},
    ),
    (
        "presence",
        "Presence",
        3,
        """
One long unstructured conversation a week. No agenda, no performing.
""",
        {},
    ),
    # -- Tier 4: Money -------------------------------------------------------
    (
        "visibility",
        "Visibility",
        4,
        """
You know your monthly inflow and outflow from memory, within 10%.
""",
        {},
    ),
    (
        "buffer",
        "Buffer",
        4,
        """
A cash reserve that grows monotonically, targeting several months of expenses.
""",
        {},
    ),
    (
        "automation",
        "Automation",
        4,
        """
Saving and investing happen without a decision.

Retire it when: the system runs whether or not you are paying attention.
""",
        {},
    ),
    (
        "calm",
        "Calm",
        4,
        """
An unexpected bill is annoying, not destabilising.

That is the actual win condition for this tier. The numbers above are proxies
for it — which is why money is the most quantifiable tier, and why that is
exactly what seduces people into starting here.
""",
        {},
    ),
    # -- Tier 5: Work and craft ---------------------------------------------
    (
        "shipping",
        "Shipping",
        5,
        """
Finished things per year, counted. Finished, not started.

Your own calibration ritual is this metric's enforcement.
""",
        {},
    ),
    (
        "deliberate-practice",
        "Deliberate practice",
        5,
        """
Time spent at the edge of ability rather than in comfortable repetition.

Retire it when: you can name your current specific weakness.
""",
        {},
    ),
    (
        "stopping",
        "Stopping",
        5,
        """
A defined end to the workday, that holds.

Retire it when: you can be idle without guilt — which is a Tier 2 skill
cashing out here.
""",
        {},
    ),
    # -- Tier 6: Meaning -----------------------------------------------------
    (
        "meaning",
        "Meaning",
        6,
        """
No metrics, on purpose. Anything countable here would be a costume.

The nearest thing to a win condition: you can answer "what is this for"
without flinching, and the answer points at something outside yourself.

It arrives by living the other tiers, not by measuring this one.
""",
        {},
    ),
]


def build() -> Domain:
    """The domain, constructed fresh. Never read from or written to disk."""
    nodes = tuple(
        _node(order, node_id, title, tier, gate, **extra)
        for order, (node_id, title, tier, gate, extra) in enumerate(_SPEC)
    )
    return Domain(
        id=DOMAIN_ID,
        title="Mementomori",
        # Sorts above everything. It is the substrate; nothing else is more
        # urgent than the body doing the learning.
        priority=0,
        cadence=Cadence(kind="daily", n=1),
        nodes=nodes,
        color="slate",
        source="<compiled in>",
        # `low` is the honest season: you are not acquiring sleep, you are
        # holding it. This also keeps it out of the focus count — maintaining
        # your own substrate must never read as spreading yourself thin.
        season=Season(state=LOW),
        foundation=True,
    )
