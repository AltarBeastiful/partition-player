"""Test engine: returns a fixed MusicXML file (PP_FAKE_MUSICXML) without looking at the image."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import register
from .base import Engine, EngineError


@register
class FakeEngine(Engine):
    name = "fake"

    def recognize(self, image: Path, out_dir: Path) -> Path:
        src = os.environ.get("PP_FAKE_MUSICXML")
        if not src or not Path(src).exists():
            raise EngineError("fake engine needs PP_FAKE_MUSICXML pointing at a MusicXML file")
        out_dir.mkdir(parents=True, exist_ok=True)
        result = out_dir / "engine.musicxml"
        shutil.copyfile(src, result)
        return result
