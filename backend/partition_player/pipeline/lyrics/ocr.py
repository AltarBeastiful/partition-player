"""Read the words printed in the band below a staff (ADR 0004).

RapidOCR's full pipeline with word boxes, run twice (at full resolution and at half) because the two
scales make different mistakes; the detector's long side is capped so a 3000 px wide band is not
upsampled (its default working size made the bands 3x slower for the same text). The band is padded
vertically so RapidOCR does not switch to its single-line mode (anything wider than 8x its height).
An extender line (melisma) is looked for in the pixels after each word: a thin horizontal ink run on
the baseline that the OCR does not report.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

DET_MAX_SIDE_PX = 1600
PASSES = (1.0, 0.5)         # scales of the band given to the OCR
PAD_RATIO = 6               # pad the band so width / height <= this
HYPHENS = "-‐‑‒–—"


@dataclass
class Word:
    text: str
    confidence: float
    x_left: float     # band pixels
    x_right: float
    y_top: float
    y_bottom: float
    extend: bool = False   # an extender line follows the word

    @property
    def y_center(self) -> float:
        return (self.y_top + self.y_bottom) / 2


def make_lyrics_ocr():
    from rapidocr import RapidOCR

    return RapidOCR(params={"Det.limit_side_len": DET_MAX_SIDE_PX, "Det.limit_type": "max", "Global.use_cls": False})


def _pad(band: np.ndarray) -> tuple[np.ndarray, int]:
    h, w = band.shape[:2]
    pad = max(0, w // PAD_RATIO - h)
    if pad == 0:
        return band, 0
    return cv2.copyMakeBorder(band, pad // 2, pad - pad // 2, 0, 0, cv2.BORDER_CONSTANT, value=255), pad // 2


def _pass(ocr, band: np.ndarray, scale: float) -> list[Word]:
    img = band if scale == 1.0 else cv2.resize(band, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    img, top = _pad(img)
    res = ocr(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), return_word_box=True, use_det=True, use_rec=True)
    words: list[Word] = []
    for line in res.word_results or ():
        for item in line:
            if not isinstance(item, (tuple, list)) or len(item) != 3:   # RapidOCR gives an empty tuple, or a bare score, for a line it could not split
                continue
            text, conf, quad = item
            q = np.asarray(quad, dtype=float)
            text = text.strip()
            if not text:
                continue
            words.append(Word(text, float(conf), float(q[:, 0].min() / scale), float(q[:, 0].max() / scale),
                              float((q[:, 1].min() - top) / scale), float((q[:, 1].max() - top) / scale)))
    return words


def _same_row(a: Word, b: Word) -> bool:
    return abs(a.y_center - b.y_center) < 0.6 * max(a.y_bottom - a.y_top, b.y_bottom - b.y_top)


def _overlap(a: Word, b: Word) -> float:
    """Horizontal overlap as a fraction of the narrower word (0 when on different rows)."""
    if not _same_row(a, b):
        return 0.0
    ov = min(a.x_right, b.x_right) - max(a.x_left, b.x_left)
    return max(0.0, ov / max(1.0, min(a.x_right - a.x_left, b.x_right - b.x_left)))


def _better(a: Word, b: Word) -> Word:
    if abs(a.confidence - b.confidence) > 0.02:
        return a if a.confidence > b.confidence else b
    return a if (a.x_right - a.x_left) >= (b.x_right - b.x_left) else b


def merge_passes(passes: list[list[Word]]) -> list[Word]:
    """Printed words never overlap, so overlapping readings compete: the first pass is primary; a word
    of a later pass is added where the primary read nothing, replaces a primary word that spans the
    same place when it is surer, and loses to two or more finer primary words unless they are doubtful."""
    out: list[Word] = []
    for w in passes[0]:
        clash = [o for o in out if _overlap(w, o) > 0.3]
        if not clash:
            out.append(w)
        elif len(clash) == 1:
            out[out.index(clash[0])] = _better(clash[0], w)
    for words in passes[1:]:
        for w in words:
            clash = [o for o in out if _overlap(w, o) > 0.3]
            if not clash:
                out.append(w)
            elif len(clash) == 1:
                o = clash[0]
                same_span = _overlap(w, o) > 0.7 and abs((w.x_right - w.x_left) - (o.x_right - o.x_left)) < 0.5 * (o.x_right - o.x_left)
                if same_span and w.confidence > o.confidence + 0.02:
                    out[out.index(o)] = w
                elif not same_span and o.confidence < 0.7 < w.confidence:
                    out[out.index(o)] = w
            elif all(o.confidence < 0.7 for o in clash) and w.confidence > max(o.confidence for o in clash):
                for o in clash:
                    out.remove(o)
                out.append(w)
    out.sort(key=lambda w: (round(w.y_center / max(1.0, 0.8 * (w.y_bottom - w.y_top))), w.x_left))
    return out


def _extender_after(band: np.ndarray, w: Word, next_left: float, unit: float) -> bool:
    """A melisma line: ink at least one interline long, thinner than a fifth of it, on the word's
    baseline, in the gap between this word and the next (or the band's end)."""
    y0 = int(w.y_top + 0.55 * (w.y_bottom - w.y_top))
    y1 = int(w.y_bottom + 0.15 * (w.y_bottom - w.y_top))
    x0 = int(w.x_right + 0.15 * unit)
    x1 = int(min(next_left - 0.15 * unit, band.shape[1]))
    if x1 - x0 < unit or y1 <= y0:
        return False
    crop = band[max(0, y0):min(band.shape[0], y1), x0:x1]
    if crop.size == 0:
        return False
    ink = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1] > 0
    if ink.mean() < 0.02:
        return False
    rows = ink.sum(axis=1)
    best = int(rows.max())
    thick = int((rows > 0.5 * best).sum())
    return best >= unit and thick <= max(2, 0.2 * unit) and ink.any(axis=0)[: int(unit)].mean() > 0.5


def _hyphen_between(band: np.ndarray, a: Word, b: Word, unit: float) -> bool:
    """A printed hyphen the OCR dropped: a short thin horizontal ink run at mid x-height in the gap
    between two words on the same row, with nothing else in the gap."""
    gap = b.x_left - a.x_right
    if gap < 0.3 * unit or gap > 9.0 * unit:   # syllables sit under their notes, so gaps are wide
        return False
    y0 = int(a.y_top + 0.3 * (a.y_bottom - a.y_top))
    y1 = int(a.y_top + 0.8 * (a.y_bottom - a.y_top))
    x0, x1 = int(a.x_right + 0.1 * unit), int(b.x_left - 0.1 * unit)
    if x1 - x0 < 0.15 * unit or y1 <= y0:
        return False
    crop = band[max(0, y0):min(band.shape[0], y1), max(0, x0):x1]
    if crop.size == 0:
        return False
    ink = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1] > 0
    if not (0.004 < ink.mean() < 0.5):
        return False
    cols = ink.any(axis=0)
    runs, start = [], None
    for x, on in enumerate(cols):
        if on and start is None:
            start = x
        elif not on and start is not None:
            runs.append((start, x)); start = None
    if start is not None:
        runs.append((start, len(cols)))
    margin = 0.2 * unit   # serifs of the neighbouring letters poke into the crop's edges
    runs = [(a, b) for a, b in runs if b - a >= 0.1 * unit and a >= margin and b <= len(cols) - margin]
    if len(runs) != 1:
        return False
    length = runs[0][1] - runs[0][0]
    rows = ink[:, runs[0][0]:runs[0][1]].sum(axis=1)
    thick = int((rows > 0.5 * rows.max()).sum())
    return 0.3 * unit <= length <= 1.0 * unit and thick <= max(2, 0.25 * unit) and length >= 3 * thick and rows.max() >= 0.8 * length


def read_lyrics(ocr, band: np.ndarray, unit: float) -> list[Word]:
    """OCR one grayscale band (already straightened); coordinates in band pixels."""
    if band.size == 0 or band.shape[0] < 8 or band.shape[1] < 8:
        return []
    words = merge_passes([_pass(ocr, band, s) for s in PASSES])
    found: list[Word] = []
    for row in cluster_rows(words):
        row.sort(key=lambda w: w.x_left)
        for i, w in enumerate(row):
            if w.text and w.text[-1] in HYPHENS:
                continue
            next_left = row[i + 1].x_left if i + 1 < len(row) else band.shape[1]
            w.extend = _extender_after(band, w, next_left, unit)
            if w.extend:
                continue
            # a hyphen the OCR dropped, between this word and the next (or after the row's last word)
            nxt = row[i + 1] if i + 1 < len(row) else Word("", 1.0, min(band.shape[1], w.x_right + 3.0 * unit), band.shape[1], w.y_top, w.y_bottom)
            if (not nxt.text or nxt.text[0] not in HYPHENS) and _hyphen_between(band, w, nxt, unit):
                found.append(Word("-", 0.9, w.x_right + 0.1 * unit, nxt.x_left - 0.1 * unit, w.y_top, w.y_bottom))
    words += found
    return [w for row in cluster_rows(words) for w in sorted(row, key=lambda w: w.x_left)]


def cluster_rows(words: list[Word]) -> list[list[Word]]:
    """Words grouped into text rows by their vertical centre (rows are a text height apart)."""
    rows: list[list[Word]] = []
    for w in sorted(words, key=lambda w: w.y_center):
        if rows:
            centre = sum(x.y_center for x in rows[-1]) / len(rows[-1])
            height = max(x.y_bottom - x.y_top for x in rows[-1])
            if abs(w.y_center - centre) <= 0.6 * height:
                rows[-1].append(w)
                continue
        rows.append([w])
    return rows
