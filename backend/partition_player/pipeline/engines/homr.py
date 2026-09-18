"""homr (https://github.com/liebharc/homr): the v1 engine, run through our driver so the chord stage gets
the staff geometry (ADR 0003). The driver writes engine.musicxml and geometry.json into out_dir."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from . import register
from .base import Engine, EngineError


@register
class HomrEngine(Engine):
    name = "homr"

    def recognize(self, image: Path, out_dir: Path, original: Path | None = None, scale: float = 1.0) -> Path:
        """`image` is the preprocessed page; `original` the upload and `scale` the preprocess factor,
        so the driver can cut full-resolution lyric bands (ADR 0004)."""
        out_dir.mkdir(parents=True, exist_ok=True)
        work_image = (out_dir / f"homr_input{image.suffix}").resolve()  # homr runs with cwd=out_dir
        shutil.copyfile(image, work_image)
        # Run through the current interpreter so the venv that has homr is the one used.
        cmd = [sys.executable, "-m", "partition_player.pipeline.engines.homr_driver", str(work_image), str(out_dir.resolve())]
        if original is not None:
            cmd += ["--original", str(original.resolve()), "--scale", str(scale)]
        log = self._run(cmd, cwd=out_dir)
        (out_dir / "homr.log").write_text(log)
        result = out_dir / "engine.musicxml"
        if not result.exists():
            raise EngineError("homr finished without writing a MusicXML file", log)
        return result
