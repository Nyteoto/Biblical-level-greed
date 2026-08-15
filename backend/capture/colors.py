"""The folder palette, and the rule for picking the next colour.

A port of the `FOLDER_PALETTE` half of `trophic/reference/logic/colors.ts`. The
syntax and UI colour maps in that file did *not* come with it: those are the
frontend's, they already live in `frontend/src/lib/trophic/colors.ts`, and
their lightness was retuned there for a dark background. Only the folder
palette crossed the language boundary, because only the folder palette is
*assigned* rather than displayed — a new folder is handed a colour once, at
creation, and that colour goes into the log. The choice has to be made where
the write happens.

Two behaviours here look like bugs and are the specification, both pinned by
the `next_color` corpus (11 cases):

 - **Comparison is exact-string.** A `#60A5FA` already in use does not match
   `#60a5fa`, so the same hue can be handed out twice. Normalising the case
   would be the obvious cleanup and would break the fixtures.
 - **Past the end of the palette it wraps on `len(existing)`, not on the count
   of distinct colours.** Delete a folder and the next one created can repeat a
   colour that an earlier wrap already used.
"""
from __future__ import annotations

# Order is significant: colours are handed out down this list.
FOLDER_PALETTE = (
    "#60a5fa",  # blue
    "#f472b6",  # pink
    "#34d399",  # emerald
    "#fbbf24",  # amber
    "#a78bfa",  # violet
    "#fb7185",  # rose
    "#22d3ee",  # cyan
    "#facc15",  # yellow
    "#4ade80",  # green
    "#f97316",  # orange
)


def next_color(existing: list[str]) -> str:
    """The first palette colour not in `existing`; once they are all taken,
    the one at `len(existing) % len(palette)`."""
    used = set(existing)
    for colour in FOLDER_PALETTE:
        if colour not in used:
            return colour
    return FOLDER_PALETTE[len(existing) % len(FOLDER_PALETTE)]
