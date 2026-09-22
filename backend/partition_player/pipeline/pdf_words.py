"""The words a born-digital PDF already holds (ADR 0009, plan 0012, steps 4 and 5).

On an engraved page the syllables are text — cut where the engraver cut them, spelled as the author
spelled them — the hyphens are rectangles a quarter of a point thick, and the beams are filled
polygons. The camera path reads all of that back out of pixels and is measurably worse at it: 86.6 %
of syllables come out with the right text on the lead-sheet benchmark, and rows below twelve
interlines are not read at all.

So on a `digital` page the OCR is not run, and this module writes the words instead, into the same
`geometry.json` the OCR would have filled and in the same shape — `x_left`/`x_right` in the working
image's pixels, `y_units` below the staff's bottom line for a syllable, `y_units_above` over its top
line for a chord — so that `lyrics/align.py` and `chords/place.py` are untouched and cannot tell
where the words came from, except by the `source` each word now carries.

Three things decide what a span is, and all three are geometry:

* a span **below** a staff, within the lyric band, is a syllable of that staff's row;
* a span **above** a staff, within the chord band, is a chord symbol — unless it is only digits,
  which is how an engraver numbers a measure;
* everything else — the title, the composer, a page number, a rehearsal note in the margin — is
  dropped and listed, the way the OCR path already lists what it saw and did not use.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import pdf

# The bands, as the driver cuts them (`homr_driver.py`): a syllable sits between these many
# interlines below the bottom staff line, a chord symbol above the top one.
LYRICS_TOP_UNITS = 0.4
LYRICS_BOTTOM_UNITS = 12.0
CHORD_TOP_UNITS = 6.0
CHORD_BOTTOM_UNITS = 0.2
MARGIN_UNITS = 2.0        # how far past a staff's ends a word may still belong to it
HYPHEN_MAX_UNITS = 2.5    # a mark longer than this between two syllables is an extender line
DIGITS = re.compile(r"^\d+$")


@dataclass(frozen=True)
class TextLayer:
    """What one page of a PDF holds, in points, with the resolution it was rendered at."""
    spans: list[pdf.Span]
    marks: list[pdf.Mark]
    dpi: int

    @classmethod
    def of(cls, page, dpi: int) -> "TextLayer":
        return cls(spans=pdf.spans_of(page), marks=pdf.marks_of(page), dpi=dpi)


@dataclass(frozen=True)
class Placed:
    """A span in the working image's pixels: where the staves are measured."""
    text: str
    x_left: float
    x_right: float
    y_center: float
    height: float
    size: float


def to_working(chain: dict, dpi: int, x_pt: float, y_pt: float) -> tuple[float, float]:
    """Points on the page to pixels of the image the engine worked on.

    Two hops and no registration: points to the rendered page (`dpi / 72`, exact, because this
    application rendered it), then the preprocess chain the driver already records.
    """
    per_point = dpi / 72.0
    crop = chain.get("crop", [0, 0])
    resize = chain.get("resize", [1.0, 1.0])
    scale = chain.get("scale", 1.0)
    x = (x_pt * per_point * scale - crop[0]) * resize[0]
    y = (y_pt * per_point * scale - crop[1]) * resize[1]
    return x, y


def apply(geometry_file: Path, layer: TextLayer) -> dict:
    """Write the file's own words into `geometry.json`. Returns what was placed and what was not."""
    geometry = json.loads(geometry_file.read_text())
    chain = geometry.get("chain") or {}
    staves = geometry.get("staves") or []
    systems = geometry.get("systems") or []

    placed: list[Placed] = []
    for span in layer.spans:
        if not span.text.strip() or span.music:
            continue
        x0, y0 = to_working(chain, layer.dpi, span.x0, span.y0)
        x1, y1 = to_working(chain, layer.dpi, span.x1, span.y1)
        placed.append(Placed(text=span.text.strip(), size=span.size, x_left=x0, x_right=x1,
                             y_center=(y0 + y1) / 2, height=abs(y1 - y0)))
    marks = [
        (to_working(chain, layer.dpi, m.x0, m.y0), to_working(chain, layer.dpi, m.x1, m.y1))
        for m in layer.marks if m.kind == "thin"
    ]

    # Which staff a span belongs to is decided by **distance**, not by order: the gap between two
    # systems is under one staff and over the next at the same time, so a syllable of the upper row
    # and a measure number of the lower system both fall in both bands. The nearer edge wins, which
    # is what the eye does — and it is what keeps LilyPond's measure numbers out of the words.
    rows: dict[int, list[Placed]] = {i: [] for i in range(len(staves))}
    over: dict[int, list[Placed]] = {i: [] for i in range(len(systems))}
    dropped: list[dict] = []
    for p in placed:
        best: tuple[float, str, int] | None = None
        for i, staff in enumerate(staves):
            gap = _below(staff, p)
            if gap is not None and (best is None or gap < best[0]):
                best = (gap, "under", i)
        for i, system in enumerate(systems):
            gap = _above(system, p)
            if gap is not None and (best is None or gap < best[0]):
                best = (gap, "over", i)
        if best is None:
            dropped.append({"text": p.text, "reason": "not under or over a staff", "source": "file"})
        elif best[1] == "under":
            rows[best[2]].append(p)
        else:
            over[best[2]].append(p)

    syllables = 0
    for i, staff in enumerate(staves):
        unit = staff.get("unit") or 1.0
        row = [{"text": p.text, "confidence": 1.0, "x_left": p.x_left, "x_right": p.x_right,
                "y_units": (p.y_center - staff["bottom_y"]) / unit,
                "height_units": p.height / unit if p.height else 1.0,
                "extend": False, "source": "file"}
               for p in sorted(rows[i], key=lambda p: p.x_left)]
        row = _with_marks(row, marks, unit, staff["bottom_y"])
        staff["words"] = row
        syllables += sum(1 for w in row if w["text"] != "-")

    chords = 0
    for i, system in enumerate(systems):
        unit = system.get("unit") or 1.0
        tokens = []
        for p in sorted(over[i], key=lambda p: p.x_left):
            if DIGITS.match(p.text):     # a measure number, which the engraver prints and nobody sings
                dropped.append({"text": p.text, "reason": "a measure number", "source": "file"})
                continue
            tokens.append({"text": p.text, "confidence": 1.0, "x_left": p.x_left, "x_right": p.x_right,
                           "y_units_above": (system["top_y"] - p.y_center) / unit,
                           "raw": p.text, "framed": False, "source": "file"})
        system["tokens"] = tokens
        chords += len(tokens)

    geometry["text_source"] = "file"
    geometry["beams"] = [
        {"x0": a[0], "y0": a[1], "x1": b[0], "y1": b[1]}
        for a, b in ((to_working(chain, layer.dpi, m.x0, m.y0), to_working(chain, layer.dpi, m.x1, m.y1))
                     for m in layer.marks if m.kind == "beam")
    ]
    geometry_file.write_text(json.dumps(geometry, indent=1))
    return {"syllables": syllables, "chords": chords, "dropped": dropped, "beams": len(geometry["beams"])}


def _below(staff: dict, p: Placed) -> float | None:
    """How far under this staff's bottom line the span sits, or None when it is not in its band."""
    unit = staff.get("unit") or 1.0
    gap = (p.y_center - staff["bottom_y"]) / unit
    if not LYRICS_TOP_UNITS <= gap <= LYRICS_BOTTOM_UNITS:
        return None
    if p.x_left < staff["min_x"] - MARGIN_UNITS * unit or p.x_right > staff["max_x"] + MARGIN_UNITS * unit:
        return None
    return gap


def _above(system: dict, p: Placed) -> float | None:
    """How far over this system's top line the span sits, or None when it is not in its band."""
    unit = system.get("unit") or 1.0
    gap = (system["top_y"] - p.y_center) / unit
    if not CHORD_BOTTOM_UNITS <= gap <= CHORD_TOP_UNITS:
        return None
    if p.x_left < system["min_x"] - MARGIN_UNITS * unit or p.x_right > system["max_x"] + MARGIN_UNITS * unit:
        return None
    return gap


def _with_marks(row: list[dict], marks: list[tuple[tuple[float, float], tuple[float, float]]],
                unit: float, bottom_y: float) -> list[dict]:
    """The hyphens and extenders the engraver drew, put back between the syllables they join.

    The pixel path has to hunt for these in the ink (`lyrics/ocr.py`), and misses one on the page
    this was built for. Here they are objects: a thin mark lying in the gap between two syllables, at
    their own height, is a hyphen; a longer one is an extender, which is the same statement made over
    several notes.
    """
    if not row:
        return row
    out: list[dict] = []
    for i, word in enumerate(row):
        out.append(word)
        nxt = row[i + 1] if i + 1 < len(row) else None
        if nxt is None:
            continue
        gap_left, gap_right = word["x_right"], nxt["x_left"]
        if gap_right - gap_left <= 0:
            continue
        baseline = bottom_y + word["y_units"] * unit      # the row's own height, in working pixels
        for (x0, y0), (x1, y1) in marks:
            if x0 < gap_left - 0.3 * unit or x1 > gap_right + 0.3 * unit:
                continue
            if abs((y0 + y1) / 2 - baseline) > 1.2 * unit:
                continue
            if (x1 - x0) > HYPHEN_MAX_UNITS * unit:
                word["extend"] = True         # an extender line: the syllable is held over the notes
            else:
                out.append({"text": "-", "confidence": 1.0, "x_left": x0, "x_right": x1,
                            "y_units": word["y_units"], "height_units": 0.2, "extend": False, "source": "file"})
            break
    return out
