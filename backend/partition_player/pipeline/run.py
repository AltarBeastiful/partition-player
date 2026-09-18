"""The recognition pipeline: preprocess -> engine (with optional fallback) -> postprocess."""
from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path

import xml.etree.ElementTree as ET

from ..config import Settings
from .chords.place import inject, place
from .lyrics import inject as lyrics_inject
from .lyrics.align import place_lyrics
from .engines import EngineError, get_engine
from .postprocess import PostprocessError, postprocess
from .preprocess import preprocess, thumbnail

Progress = Callable[[str, str], None]  # (stage, message)


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
    lyrics_info = add_lyrics(final, out_dir / info["engine"] / "geometry.json", out_dir / "lyrics.json")
    if lyrics_info is not None:
        stats.lyrics_verses = lyrics_info["verses"]
        stats.lyrics_syllables = lyrics_info["syllables"]
        stats.lyrics_read = lyrics_info["read"]
        stats.lyric_warnings = lyrics_info["warnings"]
        stats.lyrics_seen = lyrics_info["seen"]
    info["stats"] = dataclasses.asdict(stats)
    (out_dir / "result.json").write_text(json.dumps(info, indent=2))
    return final


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


def add_lyrics(score: Path, geometry_file: Path, lyrics_file: Path) -> dict | None:
    """Lyrics stage (ADR 0004): geometry.json (staves with words) + the final score -> <lyric> elements
    written into the score in place, and lyrics.json for the editor."""
    if not geometry_file.exists():
        return None
    geometry = json.loads(geometry_file.read_text())
    if not geometry.get("staves"):
        return None
    tree = ET.parse(score)
    result = place_lyrics(tree, geometry)
    written = lyrics_inject.rewrite(score, result.placed)
    lyrics_inject.save(lyrics_file, result.placed, result.warnings, result.seen)
    return {"verses": result.verses, "syllables": written, "read": result.read, "warnings": result.warnings, "seen": result.seen}
