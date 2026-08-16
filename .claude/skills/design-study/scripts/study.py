"""Render a page offscreen and measure the system it is built on.

Why WebKitGTK rather than a screenshot service: it is the same engine the
packaged app runs in (`desktop.py`), it needs no network service, and it can
hand back the *computed* styles as well as the picture. A JPEG tells you a
heading looks big; this tells you it is 34px/800 with -0.03em and that nothing
else on the page uses that size.

The histograms are weighted by how much of the page uses each value, so the top
few rows of each are the system and the long tail is noise. Read them that way —
a page with forty radii does not have forty radii, it has three and some
accidents.

Usage:
    study.py <url> <out-prefix> [--width 1194] [--height 834] [--wait 6]

Writes <out-prefix>.png and <out-prefix>.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import GLib, Gtk, WebKit2  # noqa: E402

# The session is Wayland and WebKitGTK dies with "GDK is not able to create a
# GL context" unless it is pushed onto X11 with software rendering.
for key, value in (
    ("WEBKIT_DISABLE_COMPOSITING_MODE", "1"),
    ("GDK_BACKEND", "x11"),
    ("LIBGL_ALWAYS_SOFTWARE", "1"),
):
    os.environ.setdefault(key, value)

MEASURE = r"""
(function () {
  const seen = {type: {}, radius: {}, shadow: {}, ink: {}, ground: {}, gap: {}, measure: {}};
  const bump = (bag, key, weight) => { if (key) bag[key] = (bag[key] || 0) + weight; };
  const vw = window.innerWidth, vh = window.innerHeight;

  let inked = 0, textNodes = 0, blocks = 0;

  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    if (r.top > vh * 3) continue;              // three screenfuls is plenty
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') continue;

    const area = Math.min(r.width, vw) * Math.min(r.height, vh);
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());

    if (own) {
      textNodes++;
      // Weighted by how much text there is, so body copy outranks one heading.
      const chars = el.textContent.trim().length;
      bump(seen.type,
        `${parseFloat(cs.fontSize)}px/${cs.fontWeight}/${cs.lineHeight}/${cs.letterSpacing}/${cs.fontFamily.split(',')[0].replace(/"/g,'')}`,
        chars);
      bump(seen.ink, cs.color, chars);
      // The measure: how wide a column of text is allowed to get.
      if (chars > 80) bump(seen.measure, `${Math.round(r.width / 10) * 10}px`, 1);
      inked += area * 0.35;
    }

    const bg = cs.backgroundColor;
    if (bg && bg !== 'rgba(0, 0, 0, 0)') { bump(seen.ground, bg, area); inked += area * 0.05; }
    if (cs.borderRadius && cs.borderRadius !== '0px') bump(seen.radius, cs.borderRadius, area / 1000);
    if (cs.boxShadow && cs.boxShadow !== 'none') bump(seen.shadow, cs.boxShadow, area / 1000);

    const flexish = cs.display.includes('flex') || cs.display.includes('grid');
    if (flexish && cs.gap && cs.gap !== 'normal') bump(seen.gap, cs.gap, 1);
    for (const side of ['paddingTop', 'paddingLeft']) {
      const v = parseFloat(cs[side]);
      if (v > 0) bump(seen.gap, `${v}px`, 0.5);
    }
    if (r.height > 24) blocks++;
  }

  const rank = (bag, n) => Object.entries(bag)
    .sort((a, b) => b[1] - a[1]).slice(0, n)
    .map(([value, weight]) => ({value, weight: Math.round(weight)}));

  return JSON.stringify({
    url: location.href,
    viewport: {width: vw, height: vh},
    page_height: document.documentElement.scrollHeight,
    screenfuls: +(document.documentElement.scrollHeight / vh).toFixed(1),
    type_scale: rank(seen.type, 12),
    ink: rank(seen.ink, 6),
    ground: rank(seen.ground, 6),
    radii: rank(seen.radius, 8),
    shadows: rank(seen.shadow, 6),
    spacing: rank(seen.gap, 12),
    measure: rank(seen.measure, 4),
    density: {
      text_elements: textNodes,
      blocks_over_24px: blocks,
      ink_ratio: +(inked / (vw * vh)).toFixed(2)
    }
  });
})();
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out", help="path prefix; .png and .json are appended")
    ap.add_argument("--width", type=int, default=1194, help="iPad 11 landscape")
    ap.add_argument("--height", type=int, default=834)
    ap.add_argument("--wait", type=float, default=6.0, help="seconds before measuring")
    ap.add_argument(
        "--mask-media",
        action="store_true",
        help="flatten every image to a grey plate before the snapshot. Use on any "
        "page showing the user's own photographs — data/media is private and "
        "does not stop being private because it arrived through a browser.",
    )
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    win = Gtk.OffscreenWindow()
    win.set_default_size(args.width, args.height)
    view = WebKit2.WebView()
    win.add(view)
    win.show_all()
    view.load_uri(args.url)

    state: dict = {"failed": None}

    def measure() -> bool:
        if args.mask_media:
            view.run_javascript(
                "(function(){const s=document.createElement('style');"
                "s.textContent='img,video{filter:brightness(0) invert(0.82)!important}';"
                "document.head.appendChild(s);})();",
                None,
                None,
                None,
            )

        def got(v, res):
            try:
                data = json.loads(v.run_javascript_finish(res).get_js_value().to_string())
            except Exception as exc:  # noqa: BLE001
                state["failed"] = str(exc)
                Gtk.main_quit()
                return
            out.with_suffix(".json").write_text(json.dumps(data, indent=2))
            snap(data)

        view.run_javascript(MEASURE, None, got)
        return False

    def snap(data: dict) -> None:
        def wrote(v, res):
            try:
                v.get_snapshot_finish(res).write_to_png(str(out.with_suffix(".png")))
            except Exception as exc:  # noqa: BLE001
                state["failed"] = str(exc)
            Gtk.main_quit()

        view.get_snapshot(
            WebKit2.SnapshotRegion.FULL_DOCUMENT, WebKit2.SnapshotOptions.NONE, None, wrote
        )

    GLib.timeout_add(int(args.wait * 1000), measure)
    # A page that never loads must not hang the session.
    GLib.timeout_add(int((args.wait + 25) * 1000), lambda: (Gtk.main_quit(), False)[1])
    Gtk.main()

    if state["failed"]:
        print(f"could not study {args.url}: {state['failed']}", file=sys.stderr)
        return 1
    if not out.with_suffix(".json").exists():
        print(
            f"{args.url} produced nothing — it may need auth, block automation, or "
            "render only under JS this engine will not run. Ask for a screenshot.",
            file=sys.stderr,
        )
        return 1

    data = json.loads(out.with_suffix(".json").read_text())
    print(f"{out.with_suffix('.png')}  {data['screenfuls']} screenfuls, "
          f"ink ratio {data['density']['ink_ratio']}")
    for row in data["type_scale"][:4]:
        print(f"  type  {row['value']}")
    for row in data["radii"][:3]:
        print(f"  radius {row['value']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
