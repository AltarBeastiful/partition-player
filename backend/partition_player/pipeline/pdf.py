"""The third door in (ADR 0009, plan 0012): a PDF, which is how a song actually reaches someone.

Three kinds of PDF arrive here and only the reading of them differs:

* **scan** — a photograph or a scanner's page, one image and nothing else. It is rasterized and goes
  down the camera path, which is what it is.
* **outlined** — engraved, then flattened: vector marks, but the words have become curves. Also
  rasterized; nothing can be read from it that the pixels do not say.
* **digital** — engraved and still holding its objects: the syllables are text, cut where the
  engraver cut them, the hyphens are rectangles a quarter of a point thick and the beams are filled
  four-sided polygons. Reading those off a raster is throwing away what is already written.

This module only *reads*. Coordinates stay in points, nothing here knows about the working image or
about staves; turning points into the pipeline's pixels is step 4's business.

Measured on the files this was built against (2026-09-22):

* *Dans le port de Lorient* (LilyPond 2.22.1, 1 page): 184 text spans — 110 of them music glyphs in
  `Emmentaler-20`, 66 lyric syllables in `C059-Roman` at 12.3 pt, 5 measure numbers at 8.7 pt, a
  bold title — and 277 drawings: 30 staff lines (one stroked line 538 pt wide), 44 barlines (20 pt
  tall), 87 stems, **28 hyphen rectangles** 0.25 pt thick, **8 beams** as filled four-segment
  polygons about 3 pt thick, 6 slurs as curve pairs.
* *Anton* (MuseScore export, 1 page): no music font at all — its noteheads are vector paths — and
  129 text spans in `NimbusRoman`, which is why a music font is evidence of a `digital` page but
  never a requirement.
* *Gymnopédie no. 1* (LilyPond, **2 pages**): the multi-page case.
* IMSLP scans: 78 pages, no text, one image a page.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

MAX_PAGES = 20          # a scanned hymnal is not what this app is; the cap is said in the message
MIN_RENDER_DPI = 72
MAX_RENDER_DPI = 400

# Music fonts put glyphs in the text layer: notes, clefs and rests as characters. They are read as
# evidence that the page was engraved, never as words.
MUSIC_FONTS = ("emmentaler", "feta", "bravura", "leland", "maestro", "opus", "sonata", "petaluma", "gonville")


class PdfError(ValueError):
    """The file cannot be opened as a PDF. The message is shown to the user as it is."""


@dataclass(frozen=True)
class Span:
    """A run of text with the font it is set in, and its box in points (y down from the page top)."""
    text: str
    font: str
    size: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def music(self) -> bool:
        return is_music_font(self.font)


@dataclass(frozen=True)
class Mark:
    """A vector mark of the page, in points. `kind` is what its shape makes of it."""
    kind: str          # "staff_line" | "barline" | "stem" | "thin" | "beam" | "curve"
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass(frozen=True)
class PdfPage:
    index: int         # 0-based, page order
    kind: str          # "digital" | "outlined" | "scan"
    width_pt: float
    height_pt: float


def looks_like_pdf(data: bytes) -> bool:
    """By the bytes, as the MusicXML door decides (plan 0010, decision 7)."""
    return data[:5] == b"%PDF-"


def open_document(src: Path) -> pymupdf.Document:
    """The document, or a sentence saying why it cannot be read."""
    try:
        doc = pymupdf.open(src)
    except Exception as e:  # pymupdf raises several types for a broken file
        raise PdfError(f"this PDF could not be opened: {e}") from e
    if doc.is_encrypted and not doc.authenticate(""):
        raise PdfError("this PDF is password-protected; open it and save a copy without the password")
    if doc.page_count == 0:
        raise PdfError("this PDF has no pages")
    if doc.page_count > MAX_PAGES:
        raise PdfError(f"this PDF has {doc.page_count} pages; {MAX_PAGES} is the most that can be read at once")
    return doc


def pages(src: Path) -> list[PdfPage]:
    """What is in the file, page by page, without rendering anything."""
    doc = open_document(src)
    try:
        return [
            PdfPage(index=i, kind=kind_of(page), width_pt=round(page.rect.width, 2), height_pt=round(page.rect.height, 2))
            for i, page in enumerate(doc)
        ]
    finally:
        doc.close()


def is_music_font(font: str) -> bool:
    name = (font or "").lower()
    return any(f in name for f in MUSIC_FONTS)


def kind_of(page: pymupdf.Page) -> str:
    """Which of the three kinds this page is.

    An engraved page carries vector marks in the hundreds: staff lines, stems, barlines. A scan
    carries one image and nothing else — and, when someone has run OCR over it, a text layer that
    sits on the ink and describes nothing this app can use. So the marks decide first, and text on a
    page without marks is never trusted.
    """
    drawings = len(page.get_drawings())
    images = page.get_images(full=True)
    words = [s for s in spans_of(page) if not s.music and s.text.strip()]
    if drawings < 20:
        # not engraved: a picture, with or without a text layer glued under it
        return "scan" if images else ("digital" if words else "scan")
    if not words:
        return "outlined"
    return "digital"


def spans_of(page: pymupdf.Page) -> list[Span]:
    """Every run of text on the page, in reading order, with its font and its box in points."""
    out: list[Span] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:  # 0 is text; 1 is an image
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                x0, y0, x1, y1 = span["bbox"]
                out.append(Span(text=span.get("text", ""), font=span.get("font", ""), size=round(span.get("size", 0), 2),
                                x0=round(x0, 2), y0=round(y0, 2), x1=round(x1, 2), y1=round(y1, 2)))
    return out


def marks_of(page: pymupdf.Page) -> list[Mark]:
    """The vector marks of the page, named by their shape.

    The shapes are the ones every engraver draws: a long horizontal stroke is a staff line, a short
    vertical one a barline or a stem, a rectangle a quarter of a point thick and a few points wide is
    a lyric hyphen or an extender, a filled four-segment polygon a few points thick is a beam. A page
    is drawn twice over in some files — once filled, once stroked — so marks that land in the same
    place are counted once.
    """
    seen: set[tuple[str, float, float, float, float]] = set()
    out: list[Mark] = []
    for path in page.get_drawings():
        ops = [op[0] for op in path["items"]]
        rect = path["rect"]
        box = (round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2))
        width, height = rect.width, rect.height
        kind = _kind_of_path(ops, width, height)
        if kind is None:
            continue
        key = (kind, *box)
        if key in seen:          # filled and stroked twice over, as LilyPond draws
            continue
        seen.add(key)
        out.append(Mark(kind=kind, x0=box[0], y0=box[1], x1=box[2], y1=box[3]))
    return out


def _kind_of_path(ops: list[str], width: float, height: float) -> str | None:
    """What a path's shape makes of it.

    The two op kinds matter as much as the box: an engraver draws a barline as a *stroke* and a stem
    as a filled *rectangle*, and both are thin and about as tall (a staff is four interlines, a stem
    three and a half), so nothing but the op tells them apart. A beam is the one filled polygon that
    is thick in both directions.
    """
    if not ops:
        return None
    if set(ops) == {"c"}:
        return "curve"                                       # a slur or a tie
    if len(ops) >= 3 and set(ops) <= {"l", "qu"} and min(width, height) > 1.0:
        return "beam"                                        # a filled polygon, thicker than a line
    if height <= 1.0 and width > 100:
        return "staff_line"
    if set(ops) == {"l"} and width <= 1.5 and height > 4:
        return "barline"                                     # a stroke down the staff
    if set(ops) == {"re"} and width <= 1.5 and height > 1:
        return "stem"                                        # a thin filled rectangle
    if height <= 1.5 and 1 < width <= 100:
        return "thin"                                        # a hyphen, an extender, a ledger line
    if width <= 1.5 and height > 4:
        return "barline"
    return None


def render(page: pymupdf.Page, dpi: int, out: Path) -> Path:
    """The page as an image the camera path can read. `dpi` is what the scale is built from."""
    dpi = max(MIN_RENDER_DPI, min(int(dpi), MAX_RENDER_DPI))
    pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    out.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(out)
    return out


def scale_of(dpi: int) -> float:
    """Points to pixels at this resolution: exact, no registration needed (ADR 0009)."""
    return dpi / 72.0
