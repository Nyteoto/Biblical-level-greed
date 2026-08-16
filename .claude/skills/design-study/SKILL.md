---
name: design-study
description: Study a real interface — a public web page, or a screenshot the user drops in — and turn it into measured, actionable notes against this repo's own design tokens. Use when the user says something "feels off" and cannot say why, asks for a reference or inspiration, names a site or app to learn from ("make it more like X"), or wants a redesign grounded in something other than my taste. Produces a measured diff (type scale, spacing rhythm, radii, elevation, colour roles, density) and a short list of changes worth making here — never a copy of the source.
---

# Design study

## What this is for

"It still feels off" is a real signal and a useless instruction. This skill turns
it into numbers: render a reference, measure it, measure ours, and put the two
lists side by side. What comes out is a handful of concrete differences — "their
body text is 15/1.55 and ours is 16/1.5, and they set a 620px measure where we
run to 700" — which is something you can act on or reject. Taste arguments are
unarguable; a type scale is not.

**Every study ends in a comparison against this repo, not in a mood board.**
A finding that does not name a file and a token in `frontend/src/app.css` (or a
component under `frontend/src/lib/trophic/`) has not landed yet.

## What not to do

- **Never clone a specific site's identity.** Take the *system* — scale, rhythm,
  density, hierarchy, interaction states. Leave the brand: logos, wordmarks,
  illustration, photography, their exact palette, their licensed fonts.
- **Never download or vendor assets** from a studied site — no fonts, no images,
  no icon sets. If a font matters, name it and let the user decide to license it.
- **Only public pages.** No auth walls, no paywalls, no bypassing anything. If a
  page will not render, say so and ask the user for a screenshot instead.
- **Do not produce a redesign in one leap.** The output is notes plus a proposed
  change list. Building comes after the user picks.

## Inputs, in order of usefulness

1. **A screenshot the user drops in.** The best input, and the only one for
   native apps — Apple Photos, Day One, Things, Darkroom cannot be fetched. Read
   the image and measure by eye against known anchors (a 44px tap target, a
   16px body line). Ask for one when the target is an app rather than a site.
2. **A public URL**, rendered locally with `scripts/study.py` (below). This gives
   both the picture *and* the computed styles, which is the whole point — you
   are reading the real cascade rather than guessing from a JPEG.
3. **A design system's own documentation** (Material, Primer, Polaris, Radix,
   Geist). These publish the numbers directly; fetch and read rather than
   measure. Fastest route to a defensible scale.

## The procedure

1. **Frame the question first.** "What is off about the Log?" is not studiable.
   "Why does our album screen read as an inventory when a photo book does not?"
   is. Write the question down before fetching anything; it decides what to
   measure and what to ignore.

2. **Pick references that share our constraints.** This app is a personal
   journal of text, photographs and tags, read on an iPad in landscape at
   1194×834, on a light editorial ground, single user, no feed and no social.
   A SaaS marketing page shares none of that and will teach you nothing but
   hero sections. Better neighbours: photo books and printed journals, travel
   logs, diary apps, archive and museum collection sites, long-form editorial.

3. **Render and measure.**

   ```bash
   .venv/bin/python .claude/skills/design-study/scripts/study.py \
       https://example.com /tmp/study/example --width 1194 --height 834
   ```

   Writes `example.png` and `example.json`. **Look at the PNG** — call Read on
   it. The JSON is histograms (type sizes, radii, shadows, colours, spacing,
   measure widths) ranked by how much of the page uses each, so the top three
   rows of each are the system and the tail is noise.

4. **Measure ours the same way**, so the comparison is like for like:

   ```bash
   .venv/bin/python .claude/skills/design-study/scripts/study.py \
       http://127.0.0.1:8787/log /tmp/study/ours
   ```

   Any running instance will do — including a demo/scratch instance with more
   history in it, which is usually the more honest subject. Note the port.

5. **Read our own tokens before proposing anything.** `frontend/src/app.css` is
   the ramp, the elevation ladder and the two gradients. The canonical system
   lives in the user's Claude Design project (`Modernist`) and can be read with
   the `DesignSync` tool — `list_projects`, then `get_file` on `styles.css` and
   `theme.json`. Deviations from it are often deliberate and documented in
   `design_handoff_trophic_ui/README.md` (gitignored, on disk); check there
   before "fixing" one.

6. **Write the diff.** Six headings, and skip any that has nothing in it:
   *type scale · spacing rhythm · elevation and edges · colour roles · density ·
   states and motion.* Each finding gets: what they do, what we do, and the
   one-line change here. Rank by how much of the screen it touches.

7. **Propose, then build one.** Offer the top two or three. When the user picks,
   build it as a spike against the demo data on its own port so they can look
   rather than imagine — that is how everything in this repo has been decided.

## Measuring density, which is usually the real complaint

When something "feels off" about a screen holding a lot of content, the answer is
density more often than colour or type. Two numbers worth computing by hand from
the render:

- **Content per screenful** — how many days, entries or cards fit in 834px. If a
  reference fits nine and we fit two, that is the finding.
- **Ink ratio** — roughly what fraction of the screen is content versus ground.
  Editorial pages sit high; app chrome sits low. Ours has run low every time.

`study.py` reports both, but check them against the picture: a page whose hero
fills the fold will report a density that its article body contradicts.

**`screenfuls` lies about our own screens.** The Log and Settings are `h-dvh`
with their own internal scroll containers, so the document is always exactly one
viewport tall and the number comes back as `1`. Count what is actually visible
in the PNG instead — days, cards, rows — and compare *that* against the
reference. The measurement is honest for ordinary scrolling pages, which is what
most references are.

## House rules that constrain any proposal

Read `CLAUDE.md` before proposing anything structural. The ones that bite here:

- **The log is the truth and everything else is a projection.** A design that
  needs a value stored to be drawn is the wrong design; derive it on the read.
- **Separators are surface and shadow, never rules.** No `border-b`.
- **`/log` is a feed of days, and the date ruler is deliberately gone.** Any
  proposal that reintroduces one-day-at-a-time navigation is going backwards.
- **Scrolling is for reading, never for travelling.** Navigation must stay
  constant-cost as the journal grows.
- **The capture bar's timings are a specification** (`trophic/reference/ui-behavior/CAPTURE-BAR.md`).
  Study the capture screen's *layout* freely; leave its numbers alone.
