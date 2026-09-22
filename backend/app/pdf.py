"""A Record, printed. `8193.json` in, `8193.pdf` out, and reproducible.

    python -m backend.app.pdf 8193      # one
    python -m backend.app.pdf --all     # every sealed Record, again

Why it is shaped this way
-------------------------
**The PDF is derived and can always be made again.** It is rendered once at
the seal and never read by the app; the JSON is the Record. So when the page
size, the layout or the scale changes, `--all` reprints the whole archive and
nothing is lost — which is the reason the text was not thrown away after
printing.

**Photographs go in at the resolution they were taken.** The archive is meant
to be printed, so every image is embedded from the *original*, not from the
2048px display copy. A JPEG the camera already oriented is embedded byte for
byte; anything that needs turning (EXIF orientation) or decoding (HEIC, which
no PDF can hold) is re-encoded once, at q95. Placing a 4000px photo in an
80mm box is how a print gets ~1200dpi rather than ~600, and the file size is
what that costs.

**A video prints as its poster.** The frame the browser grabbed when the clip
was uploaded, marked as video, with its filename so the clip can be found in
`data/media/`. Nothing server-side decodes video — that would need ffmpeg on
both halves of the dual-boot machine, for one thumbnail.

**ReportLab, not an HTML-to-PDF engine.** WeasyPrint needs Pango and Cairo,
which are one `dnf` away on Fedora and a genuine installation project on
Windows; a headless browser is heavier still. ReportLab is pure wheels on
both. The type is Noto Sans Mono, vendored beside this file (OFL), because the
app's own face ships only as woff2 and because Noto covers Vietnamese.

**Ink on paper, not the screen inverted.** The app is a dark slate ground with
white as its one accent; paper is white, so the print keeps the *structure* of
the screen — the heavy number, the tiny tracked labels, one rule of emphasis —
and gives the ground back to the paper.
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from . import media, records, timeutil
from .config import PDF_DIR, PRINT_PAGE

_PAGES = {"A4": A4, "LETTER": LETTER}
if PRINT_PAGE not in _PAGES:
    raise ValueError(f"PGS_PRINT_PAGE is {PRINT_PAGE!r}; it must be one of {', '.join(_PAGES)}")
PAGE = _PAGES[PRINT_PAGE]
MARGIN = 16 * mm
# The left margin is the binder's: the holes and the margin rule live in it,
# and a punched sheet must not lose a word to the punch.
BINDER = 30 * mm
# Where a re-encode is unavoidable. High enough that it is not the weak link
# in a print; a straight JPEG is not re-encoded at all.
REENCODE_QUALITY = 95

INK = colors.HexColor("#111417")
QUIET = colors.HexColor("#6b737b")
HAIR = colors.HexColor("#c9ced3")
# The screen's rules, inverted onto paper: a ruled box, and the faint line an
# unused register row is drawn in.
RULE = colors.HexColor("#9aa2aa")
FAINT = colors.HexColor("#dde1e4")

_FONTS = Path(__file__).with_name("fonts")
_registered = False


def _register_fonts() -> None:
    global _registered
    if _registered:
        return
    pdfmetrics.registerFont(TTFont("Mono", _FONTS / "NotoSansMono-Regular.ttf"))
    pdfmetrics.registerFont(TTFont("Mono-Bold", _FONTS / "NotoSansMono-Bold.ttf"))
    pdfmetrics.registerFont(TTFont("Mono-XB", _FONTS / "NotoSansMono-ExtraBold.ttf"))
    _registered = True


def _styles() -> dict[str, ParagraphStyle]:
    def style(name: str, font: str, size: float, leading: float, color=INK, **kw):
        return ParagraphStyle(name, fontName=font, fontSize=size, leading=leading, textColor=color, **kw)

    return {
        "label": style("label", "Mono-Bold", 6, 8, QUIET, spaceAfter=1.5 * mm),
        "label_r": style("label_r", "Mono-Bold", 6, 8, QUIET, alignment=2),
        "form": style("form", "Mono-XB", 10, 12),
        "date": style("date", "Mono-XB", 24, 26),
        "field": style("field", "Mono-Bold", 13, 16),
        "fact": style("fact", "Mono-Bold", 10, 12),
        "no": style("no", "Mono", 7, 12, QUIET, alignment=1),
        "no_blank": style("no_blank", "Mono", 7, 12, HAIR, alignment=1),
        "body": style("body", "Mono", 9.5, 15),
        "caption": style("caption", "Mono", 7.5, 10, QUIET),
        "sign": style("sign", "Mono-XB", 16, 20),
    }


def _label(text: str, styles) -> Paragraph:
    # Tracked uppercase, as the screen draws its section labels. A Paragraph
    # has no letter-spacing, so the tracking is a space between letters — and
    # the gap between *words* has to be wider than that or the label reads as
    # one run. Non-breaking, because a Paragraph collapses ordinary runs.
    words = (" ".join(word) for word in text.upper().split())
    return Paragraph(escape("\u00a0\u00a0\u00a0".join(words)), styles["label"])


def _prose(text: str, style) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


# ── Images ────────────────────────────────────────────────────────────────


def _image_source(ref: str) -> tuple[object, tuple[int, int]] | None:
    """What to embed for an image ref, and its pixel size. None if unreadable.

    A plain JPEG that needs no turning is passed as a path and embedded as it
    is; everything else is decoded, turned upright and re-encoded once.
    """
    from PIL import Image as PILImage, ImageOps

    media._register_heif()
    path = media.path_for(ref)
    if path is None:
        return None
    try:
        with PILImage.open(path) as im:
            orientation = im.getexif().get(0x0112, 1)
            if im.format == "JPEG" and orientation in (1, None):
                return str(path), im.size
            upright = ImageOps.exif_transpose(im)
            if upright.mode not in ("RGB", "L"):
                upright = upright.convert("RGB")
            buffer = io.BytesIO()
            upright.save(buffer, format="JPEG", quality=REENCODE_QUALITY, subsampling=0)
            buffer.seek(0)
            return buffer, upright.size
    except Exception:
        return None


def _fitted(ref: str, max_w: float, max_h: float) -> Flowable:
    found = _image_source(ref)
    if found is None:
        return _Missing(max_w, min(max_h, max_w * 0.6))
    source, (px_w, px_h) = found
    scale = min(max_w / px_w, max_h / px_h)
    return Image(source, width=px_w * scale, height=px_h * scale)


class _Missing(Flowable):
    """A box where a picture could not be read. Honest rather than silent."""

    def __init__(self, width: float, height: float):
        super().__init__()
        self.width, self.height = width, height

    def draw(self) -> None:
        self.canv.setStrokeColor(HAIR)
        self.canv.rect(0, 0, self.width, self.height)
        self.canv.setFont("Mono", 7)
        self.canv.setFillColor(QUIET)
        self.canv.drawCentredString(self.width / 2, self.height / 2, "unreadable")


class _Mounted(Flowable):
    """A plate on the sheet: the picture inset in a hairline box, held by the
    four corner marks the screen draws."""

    PAD = 2 * mm
    MARK = 4 * mm

    def __init__(self, inner: Flowable, width: float):
        super().__init__()
        self.inner = inner
        self.width = width
        # An Image only knows its drawn size once it has been wrapped.
        self.inner_w, self.inner_h = inner.wrap(width - 2 * self.PAD, 10_000)
        self.height = self.inner_h + 2 * self.PAD

    def draw(self) -> None:
        c = self.canv
        c.setStrokeColor(HAIR)
        c.setLineWidth(0.4)
        c.rect(0, 0, self.width, self.height)
        self.inner.drawOn(c, (self.width - self.inner_w) / 2, self.PAD)
        c.setStrokeColor(QUIET)
        c.setLineWidth(1)
        m, w, h, i = self.MARK, self.width, self.height, 0.8 * mm
        for x, y, dx, dy in ((i, i, 1, 1), (w - i, i, -1, 1), (i, h - i, 1, -1), (w - i, h - i, -1, -1)):
            c.line(x, y, x + dx * m, y)
            c.line(x, y, x, y + dy * m)


def _media_cell(item: dict, width: float, styles, number: int) -> list[Flowable]:
    inner_w = width - 2 * _Mounted.PAD
    # A large plate is capped in height rather than scaled to the full width:
    # a landscape photo at 160mm is 120mm tall, which pushes the plates onto a
    # second page and leaves the first half empty.
    max_h = 78 * mm if width > 100 * mm else inner_w * 0.75
    if item["kind"] == "video":
        poster = media.view_ref(item["ref"])
        picture = (
            _fitted(poster, inner_w, max_h)
            if media.path_for(poster)
            else _Missing(inner_w, inner_w * 0.56)
        )
    else:
        picture = _fitted(item["ref"], inner_w, max_h)
    caption = f"<b>PL. {number}</b>"
    if item["kind"] == "video":
        caption += escape(f"  CLIP · {Path(item['ref']).name}")
    if item.get("caption"):
        caption += "  " + escape(item["caption"])
    return [_Mounted(picture, width), Spacer(1, 1.5 * mm), Paragraph(caption, styles["caption"])]


# ── The page ──────────────────────────────────────────────────────────────


def _mood_scale(mood: int) -> Table:
    cells = [[str(n) for n in range(1, 11)]]
    table = Table(cells, colWidths=[9 * mm] * 10, rowHeights=[9 * mm])
    style = [
        ("FONT", (0, 0), (-1, -1), "Mono", 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), QUIET),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, HAIR),
    ]
    if 1 <= mood <= 10:
        i = mood - 1
        # Selection is inversion, on paper as on the screen.
        style += [
            ("BACKGROUND", (i, 0), (i, 0), INK),
            ("TEXTCOLOR", (i, 0), (i, 0), colors.white),
            ("FONT", (i, 0), (i, 0), "Mono-XB", 9),
        ]
    table.setStyle(TableStyle(style))
    table.hAlign = "LEFT"
    return table


class _TitleLine(Flowable):
    """The form's name, tracked wide, with a rule running level with it to the
    edge — the screen's title line, which a table cell cannot centre on."""

    def __init__(self, text: str, width: float):
        super().__init__()
        self.text, self.width, self.height = text, width, 5 * mm

    def draw(self) -> None:
        c = self.canv
        c.setFont("Mono-XB", 10)
        c.setFillColor(INK)
        spaced = " ".join(self.text)
        c.drawString(0, 1.2 * mm, spaced)
        start = c.stringWidth(spaced, "Mono-XB", 10) + 4 * mm
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        c.line(start, 2.4 * mm, self.width, 2.4 * mm)


class _Stamp(Flowable):
    """The seal, stamped at an angle, as it is on the screen's register."""

    def __init__(self, label: str, time: str):
        super().__init__()
        self.label, self.time = label, time
        self.width, self.height = 36 * mm, 17 * mm

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        c.translate(self.width / 2, self.height / 2)
        c.rotate(7)  # counter-clockwise on paper is the screen's -7deg
        w, h = 30 * mm, 12.5 * mm
        c.setStrokeColor(QUIET)
        c.setLineWidth(1.4)
        c.rect(-w / 2, -h / 2, w, h)
        c.setFillColor(QUIET)
        c.setFont("Mono-XB", 6)
        c.drawCentredString(0, h / 2 - 3.6 * mm, " ".join(self.label.upper()))
        c.setFillColor(INK)
        c.setFont("Mono-XB", 13)
        c.drawCentredString(0, -h / 2 + 2.4 * mm, self.time)
        c.restoreState()


def _short_day(day: str) -> tuple[str, str]:
    d = timeutil.parse_day(day)
    return d.strftime("%d %b %y").upper(), d.strftime("%a").upper()


def _field(label: str, value: Flowable | str, styles, style: str = "field") -> list:
    body = value if isinstance(value, Flowable) else Paragraph(escape(value), styles[style])
    return [_label(label, styles), body]


def _took(record: dict) -> str:
    sitting = record.get("sitting") or {}
    if not sitting.get("began") or not sitting.get("sealed"):
        return "—"
    from datetime import datetime

    seconds = int(
        (datetime.fromisoformat(sitting["sealed"]) - datetime.fromisoformat(sitting["began"]))
        .total_seconds()
    )
    hours, minutes = divmod(max(0, seconds) // 60, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def build(record: dict, target: Path, follows: dict | None = None) -> Path:
    """Print one Record on the record sheet, the same form the screen draws.

    Single column, where the screen has two: 160mm is too narrow for a register
    beside a column of plates, and a print is read top to bottom anyway. The
    order is the screen's, reading left before right — the header, the day,
    the plates, what is carried forward, then the mood, the signature and the
    stamp that closes the form.
    """
    _register_fonts()
    styles = _styles()
    n = record["instance"]
    # The frame pads itself by 6pt a side; a table sized to the full margin
    # box overflows it and centres, which pulled every box 2mm off the title.
    frame_w = PAGE[0] - BINDER - MARGIN - 12
    date, weekday = _short_day(record["day"])
    sealed_at = ((record.get("sitting") or {}).get("sealed") or "")[11:16]

    doc = SimpleDocTemplate(
        str(target),
        pagesize=PAGE,
        leftMargin=BINDER,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN + 6 * mm,
        title=f"Record {n}",
        author=f"Instance {n}",
        subject=record["day"],
    )

    ruled = [
        ("GRID", (0, 0), (-1, -1), 0.6, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
    ]

    story: list[Flowable] = []

    story += [_TitleLine("RECORD", frame_w), Spacer(1, 3 * mm)]

    # The header: a ruled grid of labelled boxes, and the subject's face.
    subject_w = 30 * mm
    rest = frame_w - subject_w
    header = Table(
        [
            [
                _field("date", date, styles, "date"),
                _field("day", weekday, styles),
                _field("instance", str(n), styles),
                [_label("subject", styles), _fitted(record["selfie"], subject_w - 6 * mm, 32 * mm)],
            ],
            [
                _field("began", ((record.get("sitting") or {}).get("began") or "—")[11:16] or "—", styles, "fact"),
                _field("took", _took(record), styles, "fact"),
                "",
                "",
            ],
        ],
        colWidths=[rest * 0.55, rest * 0.18, rest * 0.27, subject_w],
    )
    header.setStyle(TableStyle(ruled + [("SPAN", (3, 0), (3, 1)), ("SPAN", (1, 1), (2, 1))]))
    # "took" spans the last two fact columns, so its cell holds it alone.
    story += [header, Spacer(1, 6 * mm)]

    # The day: the register, numbered by paragraph, with blank lines under it.
    rows = [line.strip() for line in record["body"].splitlines() if line.strip()]
    blanks = max(3, 9 - len(rows))
    register = [[_label("the day", styles), ""]]
    register += [
        [Paragraph(f"{i + 1:02d}", styles["no"]), _prose(row, styles["body"])]
        for i, row in enumerate(rows)
    ]
    register += [
        [Paragraph(f"{len(rows) + i + 1:02d}", styles["no_blank"]), ""] for i in range(blanks)
    ]
    table = Table(register, colWidths=[11 * mm, frame_w - 11 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("SPAN", (0, 0), (1, 0)),
        ("LINEBELOW", (0, 0), (-1, len(rows)), 0.6, RULE),
        ("LINEBELOW", (0, len(rows) + 1), (-1, -1), 0.4, FAINT),
        ("LINEAFTER", (0, 1), (0, -1), 0.4, FAINT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2 * mm),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [None]),
    ]))
    story += [table, Spacer(1, 7 * mm)]

    # The plates: a clip or the first photograph mounted large, the rest two
    # to a row, each captioned with its number.
    items = record.get("media") or []
    story.append(_label(f"plates  {len(items)}", styles))
    if items:
        gap = 5 * mm
        half = (frame_w - gap) / 2
        grid: list[list] = []
        spans: list[int] = []
        pending: list = []
        for i, item in enumerate(items):
            large = i == 0 or item["kind"] == "video"
            cell = _media_cell(item, frame_w if large else half, styles, i + 1)
            if large:
                if pending:
                    grid.append(pending + [""])
                    pending = []
                spans.append(len(grid))
                grid.append([cell, ""])
            else:
                pending.append(cell)
                if len(pending) == 2:
                    grid.append(pending)
                    pending = []
        if pending:
            grid.append(pending + [""])
        plates = Table(grid, colWidths=[half + gap / 2, half + gap / 2])
        plates.setStyle(TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
            ]
            + [("SPAN", (0, r), (1, r)) for r in spans]
        ))
        story.append(plates)
    else:
        story.append(Paragraph("No plates were mounted.", styles["caption"]))
    story.append(Spacer(1, 5 * mm))

    # What this sheet hands to the next one.
    forward = Table(
        [
            [_label("carried forward", styles), Paragraph(f"TO {n + 1}", styles["label_r"])],
            [Paragraph(escape(f"What do you want {n + 1} to do?"), styles["caption"]), ""],
            [_prose(record["wish"], styles["body"]), ""],
        ],
        colWidths=[frame_w - 30 * mm, 30 * mm],
    )
    forward.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
        ("SPAN", (0, 1), (1, 1)),
        ("SPAN", (0, 2), (1, 2)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    story += [KeepTogether([forward]), Spacer(1, 6 * mm)]

    # The foot of the form: how the day felt, who signed it, and the seal.
    close = Table(
        [[
            [_label("on a scale of 1 to 10, how do you feel?", styles), _mood_scale(int(record["mood"]))],
            [_label("signed", styles), _prose(record["signature"], styles["sign"])],
        ]],
        colWidths=[frame_w - 50 * mm, 50 * mm],
    )
    close.setStyle(TableStyle(ruled))
    stamp = _Stamp("sealed", sealed_at) if sealed_at else Spacer(1, 1)
    stamp.hAlign = "RIGHT"
    story += [KeepTogether([close, Spacer(1, 2 * mm), stamp])]

    foot = "FIRST SHEET"
    if follows:
        foot = f"FOLLOWS SHEET {follows['instance']}  ·  {_short_day(follows['day'])[0]}"

    def page(canvas, _doc) -> None:
        canvas.saveState()
        # Punched for the binder, and the margin rule beside the holes.
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        for fraction in (0.25, 0.5, 0.75):
            canvas.circle(BINDER * 0.35, PAGE[1] * fraction, 2.6 * mm)
        canvas.setStrokeColor(FAINT)
        canvas.line(BINDER * 0.68, 0, BINDER * 0.68, PAGE[1])
        # The foot.
        canvas.setFont("Mono", 6.5)
        canvas.setFillColor(QUIET)
        y = MARGIN * 0.6
        canvas.drawString(BINDER + 6, y, foot)
        canvas.drawRightString(PAGE[0] - MARGIN - 6, y, f"RECORD {n} · {canvas.getPageNumber()}")
        canvas.setStrokeColor(RULE)
        canvas.line(BINDER + 70 * mm, y + 1, PAGE[0] - MARGIN - 32 * mm, y + 1)
        canvas.restoreState()

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".pdf.part")
    doc.filename = str(partial)
    doc.build(story, onFirstPage=page, onLaterPages=page)
    partial.replace(target)
    return target


def _long_day(day: str) -> str:
    return timeutil.parse_day(day).strftime("%A, %d %B %Y")


def path_of(instance: int) -> Path:
    return PDF_DIR / f"{instance}.pdf"


def render(instance: int) -> Path:
    record = records.read(instance)
    if record is None:
        raise LookupError(f"no sealed Record {instance}")
    before = records.latest(before=instance)
    follows = {"instance": before["instance"], "day": before["day"]} if before else None
    return build(record, path_of(instance), follows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("instances", nargs="*", type=int)
    parser.add_argument("--all", action="store_true", help="reprint every sealed Record")
    args = parser.parse_args(argv)
    targets = records.numbers() if args.all else args.instances
    if not targets:
        parser.error("name an instance, or pass --all")
    for n in targets:
        print(render(n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
