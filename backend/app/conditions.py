"""What a node requires before you may start it.

Prerequisites used to be the only answer, checked inline in `_status`. They are
now one condition among several, because starting something is a resource
decision and the resources are going to keep multiplying — an XP price today,
and later whatever else turns out to gate a real commitment.

Adding a condition means writing one function and decorating it. Nothing else in
the codebase changes: `_status` asks whether they are all met, and the UI renders
whatever list comes back, so a new kind of gate appears in the panel and on the
card without either of them learning about it.

A condition is *never* a hint. Soft prerequisites stay out of here on purpose:
they advise, and advice must not be able to stop you starting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .models import Node


@dataclass(frozen=True)
class Condition:
    """One gate, already evaluated. `met` is the only field logic reads."""

    key: str
    met: bool
    # What it is, in the fewest words that fit on a card.
    label: str
    # Why it is not met, or how it was satisfied. Shown when there is room.
    detail: str = ""
    # Set when the condition has a price the user pays to clear it. The UI turns
    # this into the pill; nothing else may spend without one.
    cost: float = 0.0


@dataclass
class Context:
    """Everything a condition may look at. Deliberately narrow: a condition that
    needs something not in here is a condition that needs a deliberate decision
    about coupling, not a quiet import."""

    node: Node
    domain_id: str
    # Nodes in this domain that count as finished.
    done_ids: set[str]
    # Has the unlock already been bought? A fact from the log, not a balance.
    unlocked: bool
    # What this node's unlock costs. 0 means it needs no unlocking.
    price: float
    today: str
    extras: dict = field(default_factory=dict)


Evaluator = Callable[[Context], Condition | None]

_EVALUATORS: list[Evaluator] = []


def condition(fn: Evaluator) -> Evaluator:
    """Register a gate. Order here is the order the UI shows them in."""
    _EVALUATORS.append(fn)
    return fn


@condition
def prerequisites(ctx: Context) -> Condition | None:
    """The tree's own edges. Hard `requires` only."""
    missing = [r for r in ctx.node.requires if r not in ctx.done_ids]
    if not ctx.node.requires:
        return None
    return Condition(
        key="prerequisites",
        met=not missing,
        label="Prerequisites",
        detail=(
            "" if not missing else f"needs {', '.join(missing)}"
        ),
    )


@condition
def unlock_price(ctx: Context) -> Condition | None:
    """The XP cost of starting a tier II+ node.

    Tier I is free everywhere: every tree has to be enterable, and the season
    system already caps how many you may enter at once. Above that, starting is
    a purchase, and the price is deliberately more than the node below it can
    possibly earn — see `xp.unlock_price`.
    """
    if ctx.price <= 0:
        return None
    return Condition(
        key="unlock_price",
        met=ctx.unlocked,
        label="Unlock",
        detail="" if ctx.unlocked else f"{ctx.price:g} XP",
        cost=0.0 if ctx.unlocked else ctx.price,
    )


def evaluate(ctx: Context) -> list[Condition]:
    """Every condition that applies to this node, in registration order."""
    found = []
    for evaluator in _EVALUATORS:
        result = evaluator(ctx)
        if result is not None:
            found.append(result)
    return found


def unmet(conditions: list[Condition]) -> list[Condition]:
    return [c for c in conditions if not c.met]


def as_dicts(conditions: list[Condition]) -> list[dict]:
    return [
        {
            "key": c.key,
            "met": c.met,
            "label": c.label,
            "detail": c.detail,
            "cost": c.cost,
        }
        for c in conditions
    ]
