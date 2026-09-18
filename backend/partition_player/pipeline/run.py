"""The recognition pipeline: preprocess -> engine (with optional fallback) -> postprocess."""
from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path

from ..config import Settings
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
            engine_xml = get_engine(name, **_engine_kwargs(settings, name)).recognize(pre, out_dir / name)
            info["engine"] = name
            break
        except EngineError as e:
            errors.append(f"{name}: {e}")
            (out_dir / f"{name}.error.log").write_text(f"{e}\n\n{e.log}")
    if engine_xml is None:
        raise EngineError("recognition failed: " + "; ".join(errors))

    notify("postprocessing", "Checking measures")
    final = out_dir / "score.musicxml"
    try:
        stats = postprocess(engine_xml, final)
    except PostprocessError as e:
        raise EngineError(f"{info.get('engine')} produced unusable output: {e}") from e
    info["stats"] = dataclasses.asdict(stats)
    (out_dir / "result.json").write_text(json.dumps(info, indent=2))
    return final
