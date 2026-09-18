"""Run homr on one image and also export the geometry the chord stage needs (ADR 0003).

Mirrors `homr.main.process_image` for the CPU path (no cache, no debug, no GPU) and inlines
`detect_staffs_in_image` so the detected barline boxes stay available. Writes, in the working directory:

- `engine.musicxml`: homr's output (same as `python -m homr.main` would write);
- `geometry.json`: per system (top staff of each connected staff group): interline, x extent, barline
  and notehead x positions, the transformer's measure count, and the chord tokens read above it;
- `band_<n>.png`: the straightened band above each system, for debugging and tests.

Pinned to homr 0.7: every imported name is used, so an API change fails at import time.
Usage: python -m partition_player.pipeline.engines.homr_driver <image> <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from homr.bar_line_detection import detect_bar_lines
from homr.brace_dot_detection import find_braces_brackets_and_grand_staff_lines, prepare_brace_dot_image
from homr.bounding_boxes import create_rotated_bounding_boxes
from homr.debug import Debug
from homr.main import download_weights, load_and_preprocess_predictions, predict_symbols
from homr.music_xml_generator import XmlGeneratorArguments, generate_xml
from homr.note_detection import add_notes_to_staffs, combine_noteheads_with_stems
from homr.staff_detection import break_wide_fragments, detect_staff
from homr.staff_parsing import _ensure_same_number_of_staffs, _get_number_of_voices, parse_staff_image
from homr.staff_regions import StaffRegions
from homr.title_detection import detect_title
from homr.transformer.configs import Config
from homr.transformer.vocabulary import EncodedSymbol, remove_duplicated_symbols

from ..chords.ocr import make_ocr, read_band

BAND_ABOVE_UNITS = 6.0   # band spans from this far above the top staff line ...
BAND_BELOW_UNITS = -0.4  # ... down to this far above it (negative: stays above the line)
BAND_MARGIN_UNITS = 2.0


def log(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def detect(image_path: str):
    """`homr.main.detect_staffs_in_image`, keeping the barline boxes."""
    predictions, debug = load_and_preprocess_predictions(image_path, False, False, False)
    symbols = predict_symbols(debug, predictions)
    symbols.staff_fragments = break_wide_fragments(symbols.staff_fragments)
    noteheads_with_stems = combine_noteheads_with_stems(symbols.noteheads, symbols.stems_rest)
    if not noteheads_with_stems:
        raise RuntimeError("No noteheads found")
    avg_head = float(np.median([n.notehead.size[1] for n in noteheads_with_stems]))
    heads = [n.notehead for n in noteheads_with_stems]
    stems = [n.stem for n in noteheads_with_stems if n.stem is not None]
    candidates = [b for b in symbols.bar_lines if not b.is_overlapping_with_any(heads) and not b.is_overlapping_with_any(stems)]
    bar_lines = detect_bar_lines(candidates, avg_head)
    staffs = detect_staff(debug, predictions.staff, symbols.staff_fragments, symbols.clefs_keys, bar_lines)
    if not staffs:
        raise RuntimeError("No staffs found")
    title_future = detect_title(debug, staffs[0])
    brace_dot = create_rotated_bounding_boxes(prepare_brace_dot_image(predictions.symbols, predictions.staff), skip_merging=True, max_size=(100, -1))
    add_notes_to_staffs(staffs, noteheads_with_stems, predictions.symbols, predictions.notehead)
    multi_staffs = find_braces_brackets_and_grand_staff_lines(debug, staffs, brace_dot)
    multi_staffs.sort(key=lambda ms: ms.staffs[0].min_y)
    return multi_staffs, bar_lines, predictions.preprocessed, debug, title_future


def parse(debug, multi_staffs, image) -> tuple[list[list[EncodedSymbol]], list[int]]:
    """`homr.staff_parsing.parse_staffs`, also returning the measure count the transformer saw per system."""
    multi_staffs = _ensure_same_number_of_staffs(multi_staffs, image)
    regions = StaffRegions(multi_staffs)
    config = Config()
    config.use_gpu_inference = False
    voices, measures_per_system = [], []
    i = 0
    for voice in range(_get_number_of_voices(multi_staffs)):
        result_for_voice: list[EncodedSymbol] = []
        for ms in multi_staffs:
            staff = ms.staffs[voice]
            result = parse_staff_image(debug, i, staff, image, regions, config)
            i += 1
            if len(result) == 0:
                log("Skipping empty staff", i - 1)
                if voice == 0:
                    measures_per_system.append(0)
                continue
            if voice == 0:
                bars = sum(1 for s in result if "barline" in s.rhythm or "repeat" in s.rhythm)
                last_is_bar = "barline" in result[-1].rhythm or "repeat" in result[-1].rhythm
                measures_per_system.append(bars + (0 if last_is_bar else 1))
            result.append(EncodedSymbol("newline"))
            result_for_voice.extend(result)
        voices.append(remove_duplicated_symbols(result_for_voice))
    return voices, measures_per_system


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


def dedup_bars(xs: list[float], unit: float) -> list[float]:
    out: list[float] = []
    for x in sorted(xs):
        if out and x - out[-1] < 1.5 * unit:
            out[-1] = (out[-1] + x) / 2
        else:
            out.append(x)
    return out


def main(image_path: str, out_dir: str) -> None:
    ort.set_default_logger_severity(3)
    download_weights(False, False, False)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    xml_file = out / "engine.musicxml"
    debug = None
    try:
        multi_staffs, bar_lines, image, debug, title_future = detect(image_path)
        gray = cv2.cvtColor(debug.original_image, cv2.COLOR_BGR2GRAY) if debug.original_image.ndim == 3 else debug.original_image
        voices, measures_per_system = parse(debug, multi_staffs, image)
        title = title_future.result(60)
        log("Found title:", title)
        xml = generate_xml(XmlGeneratorArguments(False, None, None), voices, title)
        xml.write(str(xml_file))

        ocr = make_ocr()  # after the title thread is done, so the OCR does not compete with it
        systems = []
        for i, ms in enumerate(multi_staffs):
            staff = ms.staffs[0]
            unit = float(staff.average_unit_size)
            band, x0 = band_above(gray, staff)
            band_file = out / f"band_{i}.png"
            cv2.imwrite(str(band_file), band)
            bars = [float(b.center[0]) for b in bar_lines
                    if staff.min_x - 2 * unit <= b.center[0] <= staff.max_x + 2 * unit and staff.y_distance_to((b.center[0], b.center[1])) < 2 * unit]
            tokens = read_band(ocr, band, unit)
            systems.append({
                "index": i, "unit": unit, "min_x": float(staff.min_x), "max_x": float(staff.max_x),
                "top_y": float(staff.min_y), "staffs": len(ms.staffs),
                "bars": dedup_bars(bars, unit),
                "notes": sorted(float(n.center[0]) for n in staff.get_notes()),
                "measures": measures_per_system[i] if i < len(measures_per_system) else 0,
                "band": band_file.name, "band_x0": x0, "band_above_units": BAND_ABOVE_UNITS,
                "tokens": [{"text": t.text, "confidence": float(t.confidence), "x_left": float(t.x_left + x0), "x_right": float(t.x_right + x0),
                            "y_units_above": float((band.shape[0] - t.y) / unit - BAND_BELOW_UNITS), "raw": t.raw, "framed": t.framed} for t in tokens],
            })
        (out / "geometry.json").write_text(json.dumps({"image": [int(gray.shape[1]), int(gray.shape[0])], "systems": systems}, indent=1))
        log("Result was written to", xml_file)
    except BaseException:
        if xml_file.exists():
            xml_file.unlink()
        raise
    finally:
        if debug is not None:
            debug.clean_debug_files_from_previous_runs()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
