"""Plain data. Nothing here reads files or touches the database."""
from __future__ import annotations

from dataclasses import dataclass, field

# Node status values, in the order a node moves through them.
LOCKED = "locked"  # a hard prerequisite is unmet — you cannot usefully start
SEALED = "sealed"  # every prerequisite is met; the XP price has not been paid
OPEN = "open"  # only *soft* prerequisites are unmet — start anyway if you like
AVAILABLE = "available"
ACTIVE = "active"
DONE = "done"
MAINTENANCE = "maintenance"  # a completed drill that has gone stale
STANDING = "standing"  # a reminder: nothing to start, nothing to finish

# Node kinds. These decide how a node accrues, whether it completes, and how it
# renders. `drill` is the default so a file that names no kind behaves exactly
# as it did in v0.1.
DRILL = "drill"  # distinct days of repetition; decays without upkeep
STUDY = "study"  # comprehension; holds once held
PROJECT = "project"  # indivisible burst of work with phases; no session count
EXAM = "exam"  # externally scored on a date somebody else picked
SOCIAL = "social"  # needs other people; never *required* to complete
# A standing sentence, not a task. Never started, never completed, never
# counted — it exists to be read and eventually retired. Only the compiled-in
# foundation domain uses this.
REMINDER = "reminder"

KINDS = (DRILL, STUDY, PROJECT, EXAM, SOCIAL, REMINDER)

# Domain shapes. These decide how many nodes are active at once.
LADDER = "ladder"  # one thing at a time (Chinese)
STRANDS = "strands"  # parallel tracks that must advance together (Berklee)
CYCLES = "cycles"  # craft feeding repeated whole projects (AFI)

SHAPES = (LADDER, STRANDS, CYCLES)

# Season. Which domains are *acquiring* right now, and which are only being kept
# alive. The problem this solves is arithmetic: six domains acquiring at once is
# ~10h/day, but six domains merely held is ~33 min/day. You can hold six things.
# You cannot learn six things at once.
HIGH = "high"  # acquiring: the full board, or the strands the season names
LOW = "low"  # holding: only what is about to go stale renders at all
OFF = "off"  # parked: nothing renders. Legal only where nothing decays.

SEASONS = (HIGH, LOW, OFF)


@dataclass(frozen=True)
class Cadence:
    """Which days a domain is due. Two knobs, both user-set, both visible."""

    kind: str  # "daily" | "weekdays" | "every_n_days"
    n: int = 1

    def label(self) -> str:
        if self.kind == "daily":
            return "every day"
        if self.kind == "weekdays":
            return "weekdays"
        return f"every {self.n} days"


@dataclass(frozen=True)
class Node:
    id: str
    title: str
    tier: int
    order: int  # declaration index in the file; breaks tier ties deterministically
    requires: tuple[str, ...] = ()  # HARD prerequisites — these lock the node
    prefers: tuple[str, ...] = ()  # SOFT prerequisites — advisory, never lock
    # How many distinct days of work you GUESS this takes. A hypothesis, not a
    # target and not a contract: the gate decides when the node is done, and
    # this number is only ever compared against what it actually took. You may
    # finish under it, and you may keep logging past it — both are measurements
    # of the estimate, which is the only thing being tested here.
    estimate: int = 1
    min_each: str = ""  # display-only contract with yourself; never enforced
    gate: str = ""  # self-attested completion criterion; never parsed
    # How to *start*. `gate` says what done means; without this the node says
    # where it ends and never where it begins, which is only usable by someone
    # who already knows the field. Free text, one pointer per line, never
    # parsed — same contract as `gate`.
    entry: tuple[str, ...] = ()
    note: str = ""
    kind: str = DRILL
    strand: str = ""  # which parallel track this belongs to (strands domains)
    phases: tuple[str, ...] = ()  # project nodes accrue phases, not sessions
    scheduled: str = ""  # YYYY-MM-DD an exam or session actually happens
    decay_days: int = 0  # a done drill goes stale after this many idle days
    metric: str = ""  # unit for a measurable gate, e.g. "bpm"
    metric_target: int = 0

    @property
    def counts_sessions(self) -> bool:
        """Projects track phases; reminders track nothing at all."""
        return self.kind not in (PROJECT, REMINDER)

    @property
    def target(self) -> int:
        """The denominator the UI draws a progress bar against.

        For a project this is a real count — phases are enumerated, so there is
        nothing to estimate. Everywhere else it is the estimate, and the bar is
        allowed to run past it.
        """
        return len(self.phases) if self.kind == PROJECT else self.estimate


@dataclass(frozen=True)
class Season:
    """A domain's current pressure, and what ends it.

    `until` and `ends_on` are both endings, and having both is the point: a
    completion trigger alone deadlocks when the project stalls (which is what
    `project` nodes *do*), and a date alone throws away the reward for shipping
    early. The season ends on whichever arrives first.

    Nothing here auto-applies. The app says the season is over and offers the
    switch; you press it, exactly as you press `complete`.
    """

    state: str = HIGH
    strands: tuple[str, ...] = ()  # width: which strands acquire. Empty = all.
    until: str = ""  # YYYY-MM-DD deadline; the season ends here regardless
    ends_on: str = ""  # ...or early, when this node completes

    @property
    def acquiring(self) -> bool:
        return self.state == HIGH


@dataclass(frozen=True)
class Domain:
    id: str
    title: str
    priority: int  # lower sorts higher on the dashboard. This is the ranking.
    cadence: Cadence
    nodes: tuple[Node, ...] = field(default_factory=tuple)
    color: str = "amber"
    source: str = ""  # file it was loaded from, for error messages
    shape: str = LADDER
    strands: tuple[str, ...] = ()  # declared track names, in display order
    season: Season = field(default_factory=Season)
    # Compiled into the app rather than loaded from a file: not editable, not
    # deletable, exempt from unlock prices and from the focus count.
    foundation: bool = False

    @property
    def decaying_nodes(self) -> tuple[Node, ...]:
        """Nodes that rot if left alone. Decides whether the domain can be
        parked outright: a domain with none of these costs nothing to ignore."""
        return tuple(n for n in self.nodes if n.decay_days and n.kind == DRILL)

    def node(self, node_id: str) -> Node | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None


class DomainError(Exception):
    """A domain file is malformed. Message is shown verbatim in the UI."""
