"""The recognition pipeline: preprocess -> engine (with optional fallback) -> postprocess."""
from __future__ import annotations

import dataclasses
import json
import logging
import shutil
from collections.abc import Callable
from pathlib import Path

import xml.etree.ElementTree as ET

from ..config import Settings
from .chords.place import inject, place
from .lyrics import inject as lyrics_inject
from .lyrics.align import place_lyrics
from .lyrics.polish import polish
from .engines import EngineError, get_engine
from .evidence import collect, compare, emitted_by_measure, rate
from .layout import make_layout
from .postprocess import PostprocessError, postprocess
from .preprocess import preprocess, review_image, thumbnail

Progress = Callable[[str, str], None]  # (stage, message)
log = logging.getLogger(__name__)


def _engine_kwargs(settings: Settings, name: str) -> dict:
    kw: dict = {"timeout_s": settings.job_timeout_s}
    if name == "audiveris":
        kw["binary"] = settings.audiveris_bin
    return kw


def recognize(image: Path, out_dir: Path, settings: Settings, progress: Progress | None = None) -> Path:
    """Run the full pipeline on `image`; write files under `out_dir`; return the final MusicXML path."""
    notify = progress or (lambda stage, msg: None)
    out_dir.mkdir(parents=True, exist_ok=True)

    notify("preprocessing", "Preparing the image")
    pre = out_dir / "preprocessed.png"
    info = preprocess(image, pre, settings.max_side_px)
    try:
        thumbnail(image, out_dir / "thumb.jpg")
    except Exception:  # noqa: BLE001  (a missing thumbnail must not fail the job)
        pass
    review: dict | None = None
    try:
        review = review_image(image, out_dir / "review.webp")  # the copy the editor shows (ADR 0005)
    except Exception:  # noqa: BLE001  (the editor works without the photo)
        log.exception("review image failed")

    engines = [settings.engine] + ([settings.fallback_engine] if settings.fallback_engine != "none" else [])
    engine_xml: Path | None = None
    errors: list[str] = []
    for name in engines:
        notify("recognizing", f"Reading the score with {name}")
        try:
            engine = get_engine(name, **_engine_kwargs(settings, name))
            if name == "homr":  # the upload and its scale let the driver cut full-resolution lyric bands
                engine_xml = engine.recognize(pre, out_dir / name, original=image, scale=info["scale"])
            else:
                engine_xml = engine.recognize(pre, out_dir / name)
            info["engine"] = name
            break
        except EngineError as e:
            errors.append(f"{name}: {e}")
            (out_dir / f"{name}.error.log").write_text(f"{e}\n\n{e.log}")
    if engine_xml is None:
        raise EngineError("recognition failed: " + "; ".join(errors))

    notify("postprocessing", "Placing chord symbols")
    chord_info = add_chords(engine_xml, engine_xml.parent / "geometry.json", out_dir / "with_chords.musicxml")
    if chord_info is not None:
        engine_xml = out_dir / "with_chords.musicxml"

    notify("postprocessing", "Checking measures")
    final = out_dir / "score.musicxml"
    try:
        stats = postprocess(engine_xml, final)
    except PostprocessError as e:
        raise EngineError(f"{info.get('engine')} produced unusable output: {e}") from e
    if chord_info is not None:
        stats.chords = chord_info["chords"]
        stats.chord_warnings = chord_info["warnings"]
        stats.chords_seen = chord_info["seen"]

    notify("postprocessing", "Placing lyrics")
    lyrics_info = add_lyrics(final, out_dir / info["engine"] / "geometry.json", out_dir / "lyrics.json", settings.anthropic_api_key)
    if lyrics_info is not None:
        stats.lyrics_verses = lyrics_info["verses"]
        stats.lyrics_syllables = lyrics_info["syllables"]
        stats.lyrics_read = lyrics_info["read"]
        stats.lyric_warnings = lyrics_info["warnings"]
        stats.lyrics_seen = lyrics_info["seen"]
    notify("postprocessing", "Weighing what the pixel stage saw")
    add_evidence(out_dir, out_dir / info["engine"] / "geometry.json", final, stats)
    info["stats"] = dataclasses.asdict(stats)
    (out_dir / "result.json").write_text(json.dumps(info, indent=2))
    write_review(out_dir, info["engine"], stats, review)
    return final


def write_review(out_dir: Path, engine: str, stats, review: dict | None) -> None:
    """The editor's files (ADR 0005): the score as recognized, the doubts, and where each measure is
    on the review image."""
    final = out_dir / "score.musicxml"
    shutil.copyfile(final, out_dir / "original.musicxml")
    (out_dir / "review.json").write_text(json.dumps({"doubts": stats.doubts, "checked": [], "revision": 1}, indent=1))
    geometry_file = out_dir / engine / "geometry.json"
    if review is not None and geometry_file.exists():
        try:
            layout = make_layout(json.loads(geometry_file.read_text()), review, stats.measures)
            (out_dir / "layout.json").write_text(json.dumps(layout))
        except Exception:  # noqa: BLE001  (the strip is a convenience; the editor works without it)
            log.exception("layout failed")


ARITHMETIC = {"padded", "overfull", "underfull", "empty"}


def add_evidence(out_dir: Path, geometry_file: Path, final: Path, stats) -> None:
    """The pixel stage's own reading, kept as `evidence.json`, and the places where it disagrees
    loudly enough with the score to be worth saying (plan 0008). Never changes a note; a failure
    here costs the rating, not the score."""
    if not geometry_file.exists():
        return
    try:
        part = ET.parse(final).getroot().find("part")
        if part is None:
            return
        emitted = emitted_by_measure(part)
        evidence = collect(json.loads(geometry_file.read_text()), len(emitted))
        (out_dir / "evidence.json").write_text(json.dumps(evidence))
        unsound = {d["measure"] for d in stats.doubts if d.get("kind") in ARITHMETIC}
        adds_up = [m not in unsound for m in range(len(emitted))]
        stats.doubts.extend(rate(compare(evidence, emitted, adds_up=adds_up)))
    except Exception:  # noqa: BLE001  (the rating is a convenience; the score stands without it)
        log.exception("evidence failed")


def add_chords(engine_xml: Path, geometry_file: Path, dst: Path) -> dict | None:
    """Chord stage (ADR 0003): geometry.json from the driver + engine MusicXML -> MusicXML with <harmony>."""
    if not geometry_file.exists():
        return None
    geometry = json.loads(geometry_file.read_text())
    tree = ET.parse(engine_xml)
    result = place(tree, geometry)
    written = inject(tree, result.placed)
    tree.write(dst, encoding="unicode", xml_declaration=True)
    return {"chords": written, "warnings": result.warnings, "seen": result.seen}


def add_lyrics(score: Path, geometry_file: Path, lyrics_file: Path, api_key: str = "") -> dict | None:
    """Lyrics stage (ADR 0004): geometry.json (staves with words) + the final score -> <lyric> elements
    written into the score in place, and lyrics.json for the editor. With an API key, the texts are
    polished by a language model first (positions never move)."""
    if not geometry_file.exists():
        return None
    geometry = json.loads(geometry_file.read_text())
    if not geometry.get("staves"):
        return None
    tree = ET.parse(score)
    result = place_lyrics(tree, geometry)
    if api_key and result.placed:
        bands = {st["index"]: geometry_file.parent / st["band"] for st in geometry["staves"]}
        changed, warnings = polish(result.placed, bands, api_key)
        result.warnings.extend(warnings)
        if changed:
            result.warnings.append(f"{changed} syllable(s) corrected by the language model")
    written = lyrics_inject.rewrite(score, result.placed)
    lyrics_inject.save(lyrics_file, result.placed, result.warnings, result.seen)
    return {"verses": result.verses, "syllables": written, "read": result.read, "warnings": result.warnings, "seen": result.seen}
