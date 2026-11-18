"""Run homr on one image and also export the geometry the chord and lyrics stages need (ADR 0003, 0004).

Inlines `homr.main.detect_staffs_in_image` for the CPU path (no cache, no debug, no GPU) so the
detected barline boxes stay available, and wraps homr's own `parse_staffs` to watch it. Writes, in the working directory:

- `engine.musicxml`: homr's output (same as `python -m homr.main` would write);
- `geometry.json`: per system (top staff of each connected staff group): interline, x extent, barline
  and notehead x positions, the transformer's measure count, and the chord tokens read above it;
  plus `times`, the measures where a time signature was printed (plan 0013);
  per staff (`staves`): the same plus the bottom line, noteheads as (x, y), and the lyric words read
  below it;
- `band_<n>.png`: the straightened band above each system (chords);
- `lyrics_<n>.png`: the straightened band below each staff, cut from the original upload at full
  resolution when `--original` is given (lyrics need the resolution homr throws away).

Coordinates in geometry.json are homr's working image: the input autocropped (`homr.autocrop`) and
resized to 1920 px wide. `chain` records how to map them back to the upload.

Pinned to homr 0.7.1: every imported name is used, so an API change fails at import time.
Usage: python -m partition_player.pipeline.engines.homr_driver <image> <out_dir> [--original <upload> --scale <s>]
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from homr.autocrop import autocrop_with_offset
from homr.bar_line_detection import detect_bar_lines
from homr.brace_dot_detection import find_braces_brackets_and_grand_staff_lines, prepare_brace_dot_image
from homr.bounding_boxes import create_rotated_bounding_boxes
from homr.debug import Debug
from homr.main import download_weights, load_and_preprocess_predictions, predict_symbols
from homr.music_xml_generator import XmlGeneratorArguments, generate_xml
from homr.note_detection import add_notes_to_staffs, combine_noteheads_with_stems
from homr.staff_detection import break_wide_fragments, detect_staff, estimate_unit_size_from_clefs
from homr import staff_parsing
from homr.staff_parsing import parse_staffs
from homr.system_repair import repair_systems
from homr.title_detection import detect_title, download_ocr_weights
from homr.transformer.configs import Config
from homr.transformer.vocabulary import EncodedSymbol
from PIL import Image, ImageOps

from ..chords.ocr import make_ocr, read_band
from ..lyrics.ocr import make_lyrics_ocr, read_lyrics

BAND_ABOVE_UNITS = 6.0   # band spans from this far above the top staff line ...
BAND_BELOW_UNITS = -0.4  # ... down to this far above it (negative: stays above the line)
BAND_MARGIN_UNITS = 2.0
LYRICS_TOP_UNITS = 1.5    # lyric band: from this far below the bottom staff line ...
LYRICS_BOTTOM_UNITS = 12.0  # ... to this far below it, or one interline above the next staff
LYRICS_GAP_UNITS = 1.0


def log(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def detect(image_path: str):
    """`homr.main.detect_staffs_in_image`, keeping the barline boxes."""
    predictions, debug, _ = load_and_preprocess_predictions(image_path, False, False, False)
    symbols = predict_symbols(debug, predictions)
    symbols.staff_fragments = break_wide_fragments(symbols.staff_fragments)
    noteheads_with_stems = combine_noteheads_with_stems(symbols.noteheads, symbols.stems_rest)
    if noteheads_with_stems:
        avg_head = float(np.median([n.notehead.size[1] for n in noteheads_with_stems]))
    else:
        unit = estimate_unit_size_from_clefs(symbols.staff_fragments, symbols.clefs_keys)
        if unit is None:
            raise RuntimeError("No noteheads or clefs found")
        avg_head = unit
    heads = [n.notehead for n in noteheads_with_stems]
    stems = [n.stem for n in noteheads_with_stems if n.stem is not None]
    candidates = [b for b in symbols.bar_lines if not b.is_overlapping_with_any(heads) and not b.is_overlapping_with_any(stems)]
    bar_lines = detect_bar_lines(candidates, avg_head)
    staffs = detect_staff(debug, predictions.staff, symbols.staff_fragments, symbols.clefs_keys, bar_lines, predictions.symbols)
    if not staffs:
        raise RuntimeError("No staffs found")
    title_future = detect_title(debug, staffs[0])
    brace_dot = create_rotated_bounding_boxes(prepare_brace_dot_image(predictions.symbols, predictions.staff), skip_merging=True, max_size=(100, -1))
    add_notes_to_staffs(staffs, noteheads_with_stems, predictions.symbols, predictions.notehead)
    multi_staffs = find_braces_brackets_and_grand_staff_lines(debug, staffs, brace_dot)
    multi_staffs.sort(key=lambda ms: ms.staffs[0].min_y)
    multi_staffs = repair_systems(debug, multi_staffs)
    return multi_staffs, bar_lines, predictions.preprocessed, debug, title_future


def parse(debug, multi_staffs, image) -> tuple[list[list[EncodedSymbol]], list[int], list, list[dict]]:
    """`homr.staff_parsing.parse_staffs`, also returning the measure count the transformer saw per
    system, the staff groups it actually parsed (it may drop or split groups), and where a time
    signature was printed.

    homr's own function does the parsing; this only watches it. Each staff goes through
    `parse_staff_image`, which is wrapped to keep its raw token stream (by staff, not by index, so hidden staffs cannot shift it), and the staff groups homr
    settles on reach `StaffRegions`, which is wrapped to keep them. The raw stream is why (plan
    0013): homr reads a time-signature mark in the right bar but cannot say how many beats it has
    (the token carries only the beat-type), and `remove_duplicated_symbols` then drops the mark
    whenever that token repeats, which is every change of numerator. The position is thrown away
    there and nowhere else, so it is kept there.
    """
    raw: dict[int, list[EncodedSymbol]] = {}   # id of the Staff object -> its raw stream
    groups: list = []

    original_parse_staff_image = staff_parsing.parse_staff_image
    original_regions = staff_parsing.StaffRegions

    def recording_parse_staff_image(debug, index, staff, *args, **kwargs):
        result = original_parse_staff_image(debug, index, staff, *args, **kwargs)
        raw[id(staff)] = list(result)   # parse_staffs appends a "newline" to this very list
        return result

    class RecordingRegions(original_regions):
        def __init__(self, staffs):
            super().__init__(staffs)
            groups[:] = staffs

    config = Config()
    config.use_gpu_inference = False
    staff_parsing.parse_staff_image = recording_parse_staff_image
    staff_parsing.StaffRegions = RecordingRegions
    try:
        voices = parse_staffs(debug, multi_staffs, image, config)
    finally:
        staff_parsing.parse_staff_image = original_parse_staff_image
        staff_parsing.StaffRegions = original_regions

    measures_per_system: list[int] = []
    marks: dict[tuple[int, int], int] = {}   # (system, bar within it) -> beat type
    for system, group in enumerate(groups):
        # Staffs homr hides in a system have no stream; the first one it parsed gives the count
        # (the same as voice 0 when nothing is hidden).
        streams = [raw[id(staff)] for staff in group.staffs if id(staff) in raw]
        counted = False
        for result in streams:
            if len(result) == 0:
                continue
            seen = 0
            for s in result:
                if is_barline(s.rhythm):
                    seen += 1
                elif s.rhythm.startswith("timeSignature"):
                    marks.setdefault((system, seen), int(s.rhythm.split("/")[1]))
            if not counted:
                counted = True
                last_is_bar = is_barline(result[-1].rhythm)
                measures_per_system.append(seen + (0 if last_is_bar else 1))
        if not counted:
            measures_per_system.append(0)
    times = [{"measure": sum(measures_per_system[:system]) + bar, "beat_type": beat_type}
             for (system, bar), beat_type in sorted(marks.items())]
    return voices, measures_per_system, groups, times


def is_barline(rhythm: str) -> bool:
    """What ends a measure in the token stream, counted exactly as `build_measures` counts it."""
    return "barline" in rhythm or "repeat" in rhythm


# ---- coordinate chain -----------------------------------------------------------------------------

def autocrop_offset(image: np.ndarray) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the crop `homr.autocrop` takes."""
    cropped, (x, y) = autocrop_with_offset(image)
    return x, y, cropped.shape[1], cropped.shape[0]


class Chain:
    """Working coordinates (homr's autocropped, 1920 px wide image) <-> upload pixels."""

    def __init__(self, engine_input: str, working_shape: tuple[int, int], scale: float):
        img = cv2.imread(engine_input)
        x, y, w, h = autocrop_offset(img)
        self.crop = (x, y)
        self.resize = (working_shape[1] / w, working_shape[0] / h)   # working px per input px
        self.scale = scale                                            # input px per upload px
        self.k = 1.0 / (self.resize[0] * scale)                       # upload px per working px (x)
        self.ky = 1.0 / (self.resize[1] * scale)

    def to_upload(self, x: float, y: float) -> tuple[float, float]:
        return (x / self.resize[0] + self.crop[0]) / self.scale, (y / self.resize[1] + self.crop[1]) / self.scale

    def as_dict(self) -> dict:
        return {"crop": list(self.crop), "resize": list(self.resize), "scale": self.scale, "k": self.k}


def load_upload(path: str) -> np.ndarray:
    """The upload as grayscale, EXIF-oriented like the preprocess step did."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("L")
        return np.asarray(im)


# ---- bands ----------------------------------------------------------------------------------------

def band_above(gray: np.ndarray, staff) -> tuple[np.ndarray, int]:
    """Straightened band above the staff: each column sampled relative to the top staff line."""
    unit = staff.average_unit_size
    x0 = max(0, int(staff.min_x - BAND_MARGIN_UNITS * unit))
    x1 = min(gray.shape[1], int(staff.max_x + BAND_MARGIN_UNITS * unit))
    h = int((BAND_ABOVE_UNITS + BAND_BELOW_UNITS) * unit)
    band = np.full((h, x1 - x0), 255, np.uint8)
    for x in range(x0, x1):
        pt = staff.get_at(min(max(x, staff.min_x), staff.max_x))
        top = min(pt.y) if pt else staff.min_y
        ys = max(0, int(top - BAND_ABOVE_UNITS * unit))
        col = gray[ys:ys + h, x]
        band[:len(col), x - x0] = col
    return band, x0


def band_below(upload: np.ndarray, staff, chain: Chain, bottom_units: float) -> tuple[np.ndarray, int, float]:
    """Straightened band below the staff, cut from the upload: each column sampled relative to the
    bottom staff line. Returns (band, x0 in working coordinates, interline in upload pixels)."""
    unit = float(staff.average_unit_size)
    x0 = max(0, int(staff.min_x - BAND_MARGIN_UNITS * unit))
    x1 = int(staff.max_x + BAND_MARGIN_UNITS * unit)
    unit_px = unit * chain.ky
    width = int((x1 - x0) * chain.k)
    h = int((bottom_units - LYRICS_TOP_UNITS) * unit_px)
    band = np.full((max(h, 1), max(width, 1)), 255, np.uint8)
    if h <= 0 or width <= 0:
        return band, x0, unit_px
    for j in range(width):
        xw = x0 + j / chain.k
        pt = staff.get_at(min(max(xw, staff.min_x), staff.max_x))
        bottom = max(pt.y) if pt else staff.max_y
        ux, uy = chain.to_upload(xw, bottom)
        ux = int(round(ux))
        if not 0 <= ux < upload.shape[1]:
            continue
        ys = int(uy + LYRICS_TOP_UNITS * unit_px)
        if ys >= upload.shape[0]:
            continue
        col = upload[max(0, ys):ys + h, ux]
        band[:len(col), j] = col
    return band, x0, unit_px


def dedup_bars(xs: list[float], unit: float) -> list[float]:
    out: list[float] = []
    for x in sorted(xs):
        if out and x - out[-1] < 1.5 * unit:
            out[-1] = (out[-1] + x) / 2
        else:
            out.append(x)
    return out


def main(image_path: str, out_dir: str, original: str | None = None, scale: float = 1.0, read_text: bool = True) -> None:
    ort.set_default_logger_severity(3)
    download_weights(False, False, False)
    download_ocr_weights()   # the title reader is no longer set up on first use
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    xml_file = out / "engine.musicxml"
    debug = None
    try:
        multi_staffs, bar_lines, image, debug, title_future = detect(image_path)
        gray = cv2.cvtColor(debug.original_image, cv2.COLOR_BGR2GRAY) if debug.original_image.ndim == 3 else debug.original_image
        voices, measures_per_system, multi_staffs, times = parse(debug, multi_staffs, image)
        title = title_future.result(60)
        log("Found title:", title)
        xml = generate_xml(XmlGeneratorArguments(False, None, None), voices, title)
        ET.ElementTree(xml).write(str(xml_file), encoding="unicode", xml_declaration=True)

        chain = Chain(image_path, gray.shape, scale)
        upload = load_upload(original) if original else None
        if upload is None:
            # no upload given (tests, bench of the working image): use the working image itself
            chain = Chain(image_path, gray.shape, 1.0)
            chain.crop, chain.resize, chain.k, chain.ky = (0, 0), (1.0, 1.0), 1.0, 1.0
            upload = gray
        # On a page whose words are read from the file itself (plan 0012, step 4) no OCR is run at
        # all: the models are not even loaded, which is most of a page's time on a small machine.
        ocr = make_ocr() if read_text else None  # after the title thread, so the OCR does not compete with it
        lyrics_ocr = make_lyrics_ocr() if read_text else None
        systems, staves = [], []
        all_staffs = [(i, v, staff) for i, ms in enumerate(multi_staffs) for v, staff in enumerate(ms.staffs)]
        for i, ms in enumerate(multi_staffs):
            staff = ms.staffs[0]
            unit = float(staff.average_unit_size)
            band, x0 = band_above(gray, staff)
            band_file = out / f"band_{i}.png"
            cv2.imwrite(str(band_file), band)
            bars = [float(b.center[0]) for b in bar_lines
                    if staff.min_x - 2 * unit <= b.center[0] <= staff.max_x + 2 * unit and staff.y_distance_to((b.center[0], b.center[1])) < 2 * unit]
            tokens = read_band(ocr, band, unit) if ocr is not None else []
            systems.append({
                "index": i, "unit": unit, "min_x": float(staff.min_x), "max_x": float(staff.max_x),
                "top_y": float(staff.min_y), "staffs": len(ms.staffs),
                "bars": dedup_bars(bars, unit),
                "notes": sorted(float(n.center[0]) for n in staff.get_notes()),
                "measures": measures_per_system[i] if i < len(measures_per_system) else 0,
                "band": band_file.name, "band_x0": x0, "band_above_units": BAND_ABOVE_UNITS,
                "tokens": [{"text": t.text, "confidence": float(t.confidence), "x_left": float(t.x_left + x0), "x_right": float(t.x_right + x0),
                            "y_units_above": float((band.shape[0] - t.y) / unit - BAND_BELOW_UNITS), "raw": t.raw, "framed": bool(t.framed)} for t in tokens],
            })
        for n, (i, v, staff) in enumerate(all_staffs):
            unit = float(staff.average_unit_size)
            below = [s for _, _, s in all_staffs if s.min_y > staff.max_y]
            bottom_units = LYRICS_BOTTOM_UNITS
            if below:
                nxt = min(s.min_y for s in below)
                bottom_units = min(bottom_units, (nxt - staff.max_y) / unit - LYRICS_GAP_UNITS)
            band, x0, unit_px = band_below(upload, staff, chain, bottom_units)
            band_file = out / f"lyrics_{n}.png"
            cv2.imwrite(str(band_file), band)
            words = read_lyrics(lyrics_ocr, band, unit_px) if lyrics_ocr is not None and bottom_units > LYRICS_TOP_UNITS + 1 else []
            staves.append({
                "index": n, "system": i, "voice": v, "unit": unit, "min_x": float(staff.min_x), "max_x": float(staff.max_x),
                "top_y": float(staff.min_y), "bottom_y": float(staff.max_y),
                # x, y, the notehead's height in pixels, and the staff position the detector read
                # (half interlines above the staff's reference line): the pixel stage's own reading
                # of this note, kept so a doubt can be rated rather than raised (plan 0008).
                "noteheads": sorted([float(nt.center[0]), float(nt.center[1]),
                                     round(float(nt.box.size[1]), 2), int(nt.position)] for nt in staff.get_notes()),
                "band": band_file.name, "band_x0": x0, "band_top_units": LYRICS_TOP_UNITS, "band_bottom_units": bottom_units, "unit_px": unit_px,
                "words": [{"text": w.text, "confidence": round(w.confidence, 3),
                           "x_left": x0 + w.x_left / chain.k, "x_right": x0 + w.x_right / chain.k,
                           "y_units": LYRICS_TOP_UNITS + w.y_center / unit_px,   # below the bottom line
                           "height_units": (w.y_bottom - w.y_top) / unit_px, "extend": bool(w.extend)} for w in words],
            })
        (out / "geometry.json").write_text(json.dumps({"image": [int(gray.shape[1]), int(gray.shape[0])], "chain": chain.as_dict(),
                                                        "systems": systems, "staves": staves, "times": times}, indent=1))
        log("Result was written to", xml_file)
    except BaseException:
        if xml_file.exists():
            xml_file.unlink()
        raise
    finally:
        if debug is not None:
            debug.clean_debug_files_from_previous_runs()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("out_dir")
    ap.add_argument("--original", default=None, help="the upload, for full-resolution lyric bands")
    ap.add_argument("--scale", type=float, default=1.0, help="preprocess scale: input px per upload px")
    ap.add_argument("--no-text-ocr", action="store_true",
                    help="skip the chord and lyric OCR: the words come from the file itself (plan 0012)")
    a = ap.parse_args()
    main(a.image, a.out_dir, a.original, a.scale, read_text=not a.no_text_ocr)
