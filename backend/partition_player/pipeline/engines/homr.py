"""homr (https://github.com/liebharc/homr): the v1 engine. Writes <image stem>.musicxml next to the image."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from . import register
from .base import Engine, EngineError


@register
class HomrEngine(Engine):
    name = "homr"

    def recognize(self, image: Path, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        work_image = (out_dir / f"homr_input{image.suffix}").resolve()  # homr runs with cwd=out_dir
        shutil.copyfile(image, work_image)
        # Run through the current interpreter so the venv that has homr is the one used.
        log = self._run([sys.executable, "-m", "homr.main", str(work_image)], cwd=out_dir)
        (out_dir / "homr.log").write_text(log)
        produced = work_image.with_suffix(".musicxml")
        if not produced.exists():
            raise EngineError("homr finished without writing a MusicXML file", log)
        result = out_dir / "engine.musicxml"
        produced.replace(result)
        return result
