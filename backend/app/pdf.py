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
MARGIN = 18 * mm
# Where a re-encode is unavoidable. High enough that it is not the weak link
# in a print; a straight JPEG is not re-encoded at all.
REENCODE_QUALITY = 95

INK = colors.HexColor("#111417")
QUIET = colors.HexColor("#6b737b")
HAIR = colors.HexColor("#c9ced3")

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
    return {
        "label": ParagraphStyle(
            "label", fontName="Mono-Bold", fontSize=6.5, leading=9,
            textColor=QUIET, spaceAfter=2 * mm,
        ),
        "title": ParagraphStyle(
            "title", fontName="Mono-XB", fontSize=34, leading=36, textColor=INK,
        ),
        "body": ParagraphStyle(
            "body", fontName="Mono", fontSize=9.5, leading=15, textColor=INK,
        ),
        "caption": ParagraphStyle(
            "caption", fontName="Mono", fontSize=7.5, leading=10, textColor=QUIET,
        ),
        "sign": ParagraphStyle(
            "sign", fontName="Mono-XB", fontSize=18, leading=22, textColor=INK,
        ),
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


def _media_cell(item: dict, width: float, styles) -> list[Flowable]:
    cell: list[Flowable] = []
    if item["kind"] == "video":
        poster = media.view_ref(item["ref"])
        cell.append(
            _fitted(poster, width, width * 0.75)
            if media.path_for(poster)
            else _Missing(width, width * 0.56)
        )
        cell.append(Spacer(1, 1.5 * mm))
        cell.append(
            Paragraph(
                escape(f"VIDEO · {Path(item['ref']).name}"), styles["label"]
            )
        )
    else:
        cell.append(_fitted(item["ref"], width, width * 0.75))
    if item.get("caption"):
        cell.append(Spacer(1, 1.5 * mm))
        cell.append(_prose(item["caption"], styles["caption"]))
    return cell


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


def build(record: dict, target: Path) -> Path:
    _register_fonts()
    styles = _styles()
    n = record["instance"]
    frame_w = PAGE[0] - 2 * MARGIN

    doc = SimpleDocTemplate(
        str(target),
        pagesize=PAGE,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN + 6 * mm,
        title=f"Record {n}",
        author=f"Instance {n}",
        subject=record["day"],
    )

    story: list[Flowable] = []

    # Header: the number, the day, and the face that wrote it.
    selfie_w = 48 * mm
    # The day is the heading's label, as it is on the template: "Record" is
    # already what the body is called, and a page says a thing once.
    heading = [
        _label(_long_day(record["day"]), styles),
        Paragraph(f"Instance {n}", styles["title"]),
    ]
    header = Table(
        [[heading, _fitted(record["selfie"], selfie_w, selfie_w * 4 / 3)]],
        colWidths=[frame_w - selfie_w - 6 * mm, selfie_w + 6 * mm],
    )
    header.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ])
    )
    story += [header, Spacer(1, 10 * mm)]

    # Media: two across, captions under.
    items = record.get("media") or []
    if items:
        gap = 6 * mm
        cell_w = (frame_w - gap) / 2
        cells = [_media_cell(item, cell_w, styles) for item in items]
        rows = [cells[i : i + 2] for i in range(0, len(cells), 2)]
        if len(rows[-1]) == 1:
            rows[-1].append("")
        grid = Table(rows, colWidths=[cell_w + gap / 2] * 2)
        grid.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5 * mm),
            ])
        )
        story += [_label("Media", styles), grid, Spacer(1, 5 * mm)]

    story += [
        _label("Record", styles),
        _prose(record["body"], styles["body"]),
        Spacer(1, 9 * mm),
        KeepTogether([
            _label(f"What do you want {n + 1} to do?", styles),
            _prose(record["wish"], styles["body"]),
        ]),
        Spacer(1, 9 * mm),
        KeepTogether([
            _label("On a scale of 1 to 10, how do you feel?", styles),
            _mood_scale(int(record["mood"])),
            Spacer(1, 9 * mm),
            _label("Signed", styles),
            _prose(record["signature"], styles["sign"]),
        ]),
    ]

    def footer(canvas, _doc) -> None:
        canvas.saveState()
        canvas.setFont("Mono", 7)
        canvas.setFillColor(QUIET)
        canvas.drawString(MARGIN, MARGIN * 0.6, f"RECORD {n}  ·  {record['day']}")
        canvas.drawRightString(
            PAGE[0] - MARGIN, MARGIN * 0.6, f"{canvas.getPageNumber()}"
        )
        canvas.restoreState()

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".pdf.part")
    doc.filename = str(partial)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
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
    return build(record, path_of(instance))


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
