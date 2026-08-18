"""The app icon: the capture bar's indicator notch, condensed until it reads.

The real notch is 600x14 — a hairline with a shallow tab hanging off it — and at
192px that is a scratch. What is kept are the *proportions* and the one detail
that makes the shape itself: the shoulders are curves, not corners.

    M0,0 L600,0 L600,2 L345,2 C342,2 340,13 335,13 ...

That `C` is the tab easing out of the bar's bottom edge and back into its own,
horizontal to horizontal, so the tab appears to be drawn *out of* the line
rather than stuck onto it. Mitre those two joins into corners and the mark reads
as a T with a wedge on it.

Two things are deliberately not faithful. The tab is wider — scaled honestly it
came out a spike, which at icon size reads as a defect in the bar. And its
bottom corners are lightly rounded, because a 2px chamfer in the source is below
a pixel at 32px and simply vanishes, taking the softness with it.

Everything — all four PNGs and the favicon — comes off the fractions below, so
the mark cannot drift between the home screen and the tab strip.

    .venv/bin/python scripts/icon.py
"""
from PIL import Image, ImageDraw, ImageFilter

GROUND = (10, 17, 22, 255)
PHOSPHOR = (79, 255, 159)

# Fractions of the icon's side.
BAR_L, BAR_R = 0.13, 0.87
BAR_T, BAR_B = 0.40, 0.475
TAB_TL, TAB_TR = 0.315, 0.685   # where the shoulders leave the bar
TAB_BL, TAB_BR = 0.365, 0.635   # the tab's own bottom edge
TAB_B = 0.645
CORNER = 0.018                  # the light round on the bottom corners


def cubic(p0, c1, c2, p3, steps=18):
    """A cubic Bézier as points. PIL draws polygons, not paths, so the curve is
    sampled — at these sizes eighteen segments is already past what a pixel can
    tell apart."""
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        out.append(
            (
                u * u * u * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t * t * t * p3[0],
                u * u * u * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t * t * t * p3[1],
            )
        )
    return out


def outline(at):
    """The mark, clockwise from its top left."""
    dx = TAB_TR - TAB_BR      # how far the shoulder travels inward
    pts = [(at(BAR_L), at(BAR_T)), (at(BAR_R), at(BAR_T)), (at(BAR_R), at(BAR_B))]

    # Right shoulder: out of the bar's bottom edge, into the tab's slope. The
    # control points hold each end horizontal, which is what the source does.
    pts += cubic(
        (at(TAB_TR), at(BAR_B)),
        (at(TAB_TR - dx * 0.35), at(BAR_B)),
        (at(TAB_TR - dx * 0.55), at(TAB_B)),
        (at(TAB_BR), at(TAB_B)),
    )
    # The bottom edge, with its corners eased rather than mitred.
    pts += cubic(
        (at(TAB_BR), at(TAB_B)),
        (at(TAB_BR - CORNER * 0.5), at(TAB_B + CORNER * 0.35)),
        (at(TAB_BL + CORNER * 0.5), at(TAB_B + CORNER * 0.35)),
        (at(TAB_BL), at(TAB_B)),
        steps=10,
    )
    pts += cubic(
        (at(TAB_BL), at(TAB_B)),
        (at(TAB_TL + dx * 0.55), at(TAB_B)),
        (at(TAB_TL + dx * 0.35), at(BAR_B)),
        (at(TAB_TL), at(BAR_B)),
    )
    pts.append((at(BAR_L), at(BAR_B)))
    return pts


def notch(size: int, pad: float = 0.0) -> Image.Image:
    S = size
    img = Image.new("RGBA", (S, S), GROUND)
    sc = 1.0 - pad
    at = lambda f: S / 2 + (f - 0.5) * S * sc
    shape = outline(at)

    # The halo first, under the mark: the same idea as the shadow ladder in
    # app.css, where elevation is emission and a lit thing carries a halo.
    for alpha, blur in ((150, 0.045), (90, 0.11)):
        g = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(g).polygon(shape, fill=(*PHOSPHOR, alpha))
        img.alpha_composite(g.filter(ImageFilter.GaussianBlur(S * blur)))

    ImageDraw.Draw(img).polygon(shape, fill=(*PHOSPHOR, 255))

    # Scanlines, so the icon is the same screen as the app.
    ln = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(ln)
    step = max(2, round(S / 64))
    for y in range(0, S, step):
        d.rectangle([0, y, S, y], fill=(0, 0, 0, 40))
    img.alpha_composite(ln)
    return img


def favicon() -> str:
    """The same shape as a real path, so the curves survive at 16px where a
    sampled polygon would show its segments."""
    f = lambda v: round(v * 64, 2)
    dx = TAB_TR - TAB_BR
    return f"""<!-- The capture bar's indicator notch. Same fractions as the PNGs —
     see `scripts/icon.py`, which draws both. The shoulders are curves because
     that is what makes the tab look drawn out of the line rather than stuck
     onto it. -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" fill="#0a1116"/>
  <g filter="url(#glow)">
    <path fill="#4fff9f" d="M{f(BAR_L)},{f(BAR_T)} H{f(BAR_R)} V{f(BAR_B)}
      H{f(TAB_TR)}
      C{f(TAB_TR - dx * 0.35)},{f(BAR_B)} {f(TAB_TR - dx * 0.55)},{f(TAB_B)} {f(TAB_BR)},{f(TAB_B)}
      H{f(TAB_BL)}
      C{f(TAB_TL + dx * 0.55)},{f(TAB_B)} {f(TAB_TL + dx * 0.35)},{f(BAR_B)} {f(TAB_TL)},{f(BAR_B)}
      H{f(BAR_L)} Z"/>
  </g>
  <defs>
    <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="2.2" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
</svg>
"""


if __name__ == "__main__":
    out = "frontend/static/"
    notch(512).save(out + "icon-512.png")
    notch(192).save(out + "icon-192.png")
    notch(180).save(out + "apple-touch-icon.png")
    # Maskable is cropped to the circle inside the middle 80%, so it is drawn
    # small enough to survive that: the `any` art fills more than the safe zone.
    notch(512, pad=0.34).save(out + "icon-maskable.png")
    open(out + "favicon.svg", "w").write(favicon())
    print("icons written from one set of fractions")
