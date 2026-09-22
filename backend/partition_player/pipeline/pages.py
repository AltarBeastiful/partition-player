"""Several pages, one score (ADR 0009, plan 0012, step 3).

A job has held one page since the first day: one input file, one `review.webp`, one `layout.json`,
one `thumb.jpg`. A PDF is usually several. So a PDF job runs the ordinary pipeline once per page,
into `page-1/`, `page-2/`… under the job's own directory, and this module joins what comes back into
the single score the rest of the app expects.

The join is arithmetic, not recognition:

* **measures are appended in page order**, renumbered from 1, and a measure marked `implicit` on any
  page but the first loses the mark — a pickup is the beginning of a piece, not the beginning of a
  sheet of paper;
* **what is in force is carried across the seam**: page 2 restates its divisions, key, time and clef
  because it is a fresh page, and restating them into the middle of the music would draw a key change
  where the print has none. Only what actually changed is kept. Divisions are the one thing that
  cannot simply be dropped: where two pages count a quarter differently, every duration is scaled to
  the common count;
* **everything measure-numbered follows**: the doubts, the layout's systems and the pixel stage's
  evidence are shifted by the measures of the pages before them, and each layout system records the
  page it is on, so the editor's photo strip can show the right sheet.

The words are not joined: `lyrics.json` is read back from the joined document itself
(`read_placements`, the same call the MusicXML door uses in plan 0010), so nothing has to be shifted
twice.
"""
from __future__ import annotations

import json
import logging
import math
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from ..config import Settings
from . import pdf
from .lyrics import inject as lyrics_inject
from .pdf_words import TextLayer
from .run import Progress, recognize

log = logging.getLogger(__name__)

RENDER_DPI = 300           # what the camera path is measured on; the scale is exact (points * dpi / 72)
IN_FORCE = ("key", "time", "clef")   # restated at the top of every page, and dropped where unchanged


class PageError(ValueError):
    """The pages could not be joined. The message is shown to the user as it is."""


def read_pdf(src: Path, out_dir: Path, settings: Settings, progress: Progress | None = None) -> Path:
    """Every page of a PDF read by the ordinary pipeline, then joined into one score.

    A page that was engraved is rendered like any other — the notes can only be read from pixels —
    but its words are not: on a `digital` page the OCR is skipped and the syllables, the chord
    symbols and the hyphens are taken from the file's own objects (plan 0012, step 4).
    """
    notify = progress or (lambda stage, msg: None)
    out_dir.mkdir(parents=True, exist_ok=True)
    found = pdf.pages(src)
    doc = pdf.open_document(src)
    page_dirs: list[Path] = []
    try:
        for page in found:
            n = page.index + 1
            notify("preprocessing", f"Page {n} of {len(found)}: preparing" if len(found) > 1 else "Preparing the page")
            image = pdf.render(doc[page.index], RENDER_DPI, out_dir / f"page-{n}" / f"page-{n}.png")

            def page_progress(stage: str, message: str, n: int = n) -> None:
                notify(stage, f"Page {n} of {len(found)}: {message}" if len(found) > 1 else message)

            layer = TextLayer.of(doc[page.index], RENDER_DPI) if page.kind == "digital" else None
            recognize(image, out_dir / f"page-{n}", settings, page_progress, text_layer=layer)
            page_dirs.append(out_dir / f"page-{n}")
    finally:
        doc.close()
    notify("postprocessing", "Joining the pages")
    return join(page_dirs, out_dir, [page.__dict__ | {"dpi": RENDER_DPI, "scale": pdf.scale_of(RENDER_DPI)} for page in found])


def join(page_dirs: list[Path], out_dir: Path, pages_info: list[dict]) -> Path:
    """Join what each page's run left behind into the job's own files. Returns the joined score."""
    if not page_dirs:
        raise PageError("no page could be read from this PDF")
    scores = [ET.parse(d / "score.musicxml") for d in page_dirs]
    counts = [len(_measures_of(t.getroot(), 0)) for t in scores]
    joined = join_scores(scores)
    final = out_dir / "score.musicxml"
    joined.write(final, encoding="UTF-8", xml_declaration=True)

    results = [json.loads((d / "result.json").read_text()) for d in page_dirs]
    stats = join_stats(results, counts)
    info = dict(results[0])
    info["stats"] = stats
    info["pages"] = [
        {**page, "measures": count, "image": f"page-{i + 1}/page-{i + 1}.png"}
        for i, (page, count) in enumerate(zip(pages_info, counts, strict=False))
    ]
    (out_dir / "result.json").write_text(json.dumps(info, indent=2))

    # the editor's files: one review image per page, the first page's thumbnail for the library
    for i, d in enumerate(page_dirs, start=1):
        for name, target in (("review.webp", f"review-{i}.webp"), ("thumb.jpg", f"thumb-{i}.jpg")):
            if (d / name).exists():
                shutil.copyfile(d / name, out_dir / target)
    if (out_dir / "thumb-1.jpg").exists():
        shutil.copyfile(out_dir / "thumb-1.jpg", out_dir / "thumb.jpg")
    if (out_dir / "review-1.webp").exists():
        shutil.copyfile(out_dir / "review-1.webp", out_dir / "review.webp")

    layout = join_layout([_load(d / "layout.json") for d in page_dirs], counts)
    if layout is not None:
        (out_dir / "layout.json").write_text(json.dumps(layout))
    evidence = join_evidence([_load(d / "evidence.json") for d in page_dirs])
    if evidence is not None:
        (out_dir / "evidence.json").write_text(json.dumps(evidence))

    shutil.copyfile(final, out_dir / "original.musicxml")
    (out_dir / "review.json").write_text(json.dumps(
        {"doubts": stats["doubts"], "checked": [], "revision": 1, "form": None, "lines": [], "unders": []}, indent=1))
    placed = lyrics_inject.read_placements(final)
    lyrics_inject.save(out_dir / "lyrics.json", placed,
                       [w for r in results for w in (r.get("stats", {}).get("lyric_warnings") or [])],
                       [s for r in results for s in (r.get("stats", {}).get("lyrics_seen") or [])])
    return final


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def _measures_of(root: ET.Element, part_index: int) -> list[ET.Element]:
    parts = root.findall("part")
    if part_index >= len(parts):
        return []
    return parts[part_index].findall("measure")


def _divisions_of(root: ET.Element) -> int:
    for divisions in root.iter("divisions"):
        try:
            return int(float((divisions.text or "1").strip()))
        except ValueError:
            continue
    return 1


def _scale_durations(root: ET.Element, factor: int) -> None:
    if factor == 1:
        return
    # every <duration> of the page, wherever it hangs: a note's, a backup's, a forward's
    for el in root.iter("duration"):
        if not (el.text or "").strip():
            continue
        try:
            el.text = str(int(round(float(el.text) * factor)))
        except ValueError:
            continue
    for divisions in root.iter("divisions"):
        try:
            divisions.text = str(int(float((divisions.text or "1").strip()) * factor))
        except ValueError:
            continue


def join_scores(scores: list[ET.ElementTree]) -> ET.ElementTree:
    """One document out of several, part by part and measure after measure."""
    if not scores:
        raise PageError("no page could be read from this PDF")
    first = scores[0]
    root = first.getroot()
    target_divisions = math.lcm(*[_divisions_of(t.getroot()) for t in scores]) or 1
    for tree in scores:
        page_root = tree.getroot()
        own = _divisions_of(page_root)
        if own and target_divisions % own == 0:
            _scale_durations(page_root, target_divisions // own)
    parts = root.findall("part")
    if not parts:
        raise PageError("the first page holds no part")
    for part_index, part in enumerate(parts):
        in_force: dict[str, str] = {}
        for measure in part.findall("measure"):
            _remember(measure, in_force)
        for tree in scores[1:]:
            more = _measures_of(tree.getroot(), part_index)
            for i, measure in enumerate(more):
                if i == 0:
                    _drop_unchanged(measure, in_force)
                measure.attrib.pop("implicit", None)   # a pickup belongs to the piece, not to a sheet
                _remember(measure, in_force)
                part.append(measure)
    for part in parts:
        for number, measure in enumerate(part.findall("measure"), start=1):
            measure.set("number", str(number))
    return first


def _remember(measure: ET.Element, in_force: dict[str, str]) -> None:
    for attributes in measure.findall("attributes"):
        for tag in IN_FORCE:
            for el in attributes.findall(tag):
                in_force[_key(tag, el)] = _signature(el)
        for el in attributes.findall("divisions"):
            in_force["divisions"] = (el.text or "").strip()


def _drop_unchanged(measure: ET.Element, in_force: dict[str, str]) -> None:
    """The top of a page restates what is in force; only what changed is worth writing here."""
    for attributes in measure.findall("attributes"):
        for tag in (*IN_FORCE, "divisions"):
            for el in list(attributes.findall(tag)):
                key = "divisions" if tag == "divisions" else _key(tag, el)
                if key in in_force and in_force[key] == (_signature(el) if tag != "divisions" else (el.text or "").strip()):
                    attributes.remove(el)
        if len(attributes) == 0:
            measure.remove(attributes)


def _key(tag: str, el: ET.Element) -> str:
    return f"{tag}/{el.get('number', '1')}"


def _signature(el: ET.Element) -> str:
    return ET.tostring(el, encoding="unicode").strip()


def join_stats(results: list[dict], counts: list[int]) -> dict:
    """The pages' statistics added up, with everything measure-numbered shifted into the joined score."""
    out = dict(results[0].get("stats") or {})
    offsets = _offsets(counts)
    summed = ("measures", "notes", "rests", "padded_measures", "repeat_signs", "chords",
              "lyrics_verses", "lyrics_syllables", "lyrics_read")
    for key in summed:
        if key in out:
            out[key] = sum((r.get("stats") or {}).get(key) or 0 for r in results)
    for key in ("warnings", "chord_warnings", "lyric_warnings", "chords_seen", "lyrics_seen"):
        if key in out:
            out[key] = [item for r in results for item in ((r.get("stats") or {}).get(key) or [])]
    doubts = []
    for offset, r in zip(offsets, results, strict=False):
        for doubt in (r.get("stats") or {}).get("doubts") or []:
            shifted = dict(doubt)
            if isinstance(shifted.get("measure"), int):
                shifted["measure"] = shifted["measure"] + offset
            doubts.append(shifted)
    out["doubts"] = doubts
    out["pickup"] = bool((results[0].get("stats") or {}).get("pickup"))  # only the first page can hold one
    return out


def join_layout(layouts: list[dict | None], counts: list[int]) -> dict | None:
    """One layout for the score, every system saying which page it is on (plan 0012, step 3)."""
    if not any(layouts):
        return None
    offsets = _offsets(counts)
    systems: list[dict] = []
    width = height = 0
    for page, (layout, offset) in enumerate(zip(layouts, offsets, strict=False)):
        if layout is None:
            continue
        width = max(width, layout.get("width", 0))
        height = max(height, layout.get("height", 0))
        for system in layout.get("systems", []):
            moved = dict(system)
            moved["page"] = page
            moved["index"] = len(systems)
            moved["measures"] = [{**m, "index": m["index"] + offset} for m in system.get("measures", [])]
            systems.append(moved)
    return {"width": width, "height": height, "systems": systems}


def join_evidence(evidences: list[dict | None]) -> dict | None:
    """The pixel stage's noteheads, measure by measure, laid end to end like the measures they name."""
    kept = [e for e in evidences if e]
    if not kept:
        return None
    heads: list = []
    for e in kept:
        heads.extend(e.get("heads") or [])
    out = dict(kept[0])
    out["heads"] = heads
    return out


def _offsets(counts: list[int]) -> list[int]:
    offsets = []
    running = 0
    for count in counts:
        offsets.append(running)
        running += count
    return offsets
