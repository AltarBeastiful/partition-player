"""Find and read chord symbols in the straightened band above a staff (ADR 0003).

Detection: RapidOCR's text detector on tiles of the band scaled so one interline is `TARGET_UNIT_PX`,
with the detector's working size lowered to `DET_SIDE_PX` (its default 736 upsamples the text far past
what it likes and finds fewer names). Recognition: the recognizer's per-character probabilities decoded
under the chord grammar (`grammar.constrained_decode`).
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .grammar import constrained_decode

TARGET_UNIT_PX = 24
DET_SIDE_PX = 192
TILE_UNITS = 30
OVERLAP_UNITS = 6


@dataclass
class Token:
    text: str          # best legal chord string, "" when none
    confidence: float
    x_left: float      # band coordinates (pixels of the band image)
    x_right: float
    y: float
    raw: str           # unconstrained greedy reading, for the warnings


def make_ocr():
    from rapidocr import RapidOCR

    return RapidOCR(params={"Det.limit_side_len": DET_SIDE_PX, "Det.limit_type": "min", "Global.use_cls": False})


def _greedy(probs: np.ndarray, chars: list[str]) -> str:
    out, last = [], 0
    for i in probs.argmax(1):
        if i != 0 and i != last:
            out.append(chars[i])
        last = i
    return "".join(out)


def _detect(ocr, band: np.ndarray, unit: float) -> list[tuple[float, float, float, float]]:
    h, w = band.shape
    scale = TARGET_UNIT_PX / unit
    tw, ov = int(TILE_UNITS * unit), int(OVERLAP_UNITS * unit)
    boxes = []
    x = 0
    while True:
        x1 = min(w, x + tw)
        up = cv2.resize(band[:, x:x1], None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        pad = max(0, int(up.shape[1] / 4) - up.shape[0])
        up = cv2.copyMakeBorder(up, pad // 2, pad - pad // 2, 0, 0, cv2.BORDER_CONSTANT, value=255)
        res = ocr.text_det(cv2.cvtColor(up, cv2.COLOR_GRAY2BGR))
        for b in res.boxes if res.boxes is not None else []:
            xs = [p[0] / scale + x for p in b]
            ys = [(p[1] - pad // 2) / scale for p in b]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
        if x1 >= w:
            break
        x = x1 - ov
    boxes.sort()
    merged: list[tuple[float, float, float, float]] = []
    for b in boxes:
        for i, m in enumerate(merged):
            overlap = min(b[2], m[2]) - max(b[0], m[0])
            if overlap > 0.5 * min(b[2] - b[0], m[2] - m[0]):
                merged[i] = (min(b[0], m[0]), min(b[1], m[1]), max(b[2], m[2]), max(b[3], m[3]))
                break
        else:
            merged.append(b)
    return merged


def read_band(ocr, band: np.ndarray, unit: float) -> list[Token]:
    """OCR one band (grayscale, already straightened). Returns every detected box, decoded."""
    rec = ocr.text_rec
    chars = rec.postprocess_op.character
    tokens = []
    for x0, y0, x1, y1 in _detect(ocr, band, unit):
        pad = unit * 0.3
        crop = band[max(0, int(y0 - pad)):int(y1 + pad), max(0, int(x0 - pad)):int(x1 + pad)]
        if crop.size == 0 or crop.shape[0] < 4 or crop.shape[1] < 4:
            continue
        bgr = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
        ratio = max(rec.rec_image_shape[2] / rec.rec_image_shape[1], bgr.shape[1] / bgr.shape[0])
        norm = rec.resize_norm_img(bgr, ratio)
        probs = rec.session(norm[np.newaxis].astype(np.float32))[0]
        text, conf = constrained_decode(probs, chars)
        tokens.append(Token(text, round(conf, 3), x0, x1, (y0 + y1) / 2, _greedy(probs, chars)))
    return tokens
