"""Audiveris 5.x in batch mode, kept as an optional fallback (ADR 0002). Needs PP_AUDIVERIS_BIN."""
from __future__ import annotations

import zipfile
from pathlib import Path

from . import register
from .base import Engine, EngineError


@register
class AudiverisEngine(Engine):
    name = "audiveris"

    def __init__(self, timeout_s: int = 600, binary: str = "Audiveris"):
        super().__init__(timeout_s)
        self.binary = binary

    def recognize(self, image: Path, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        log = self._run(
            [self.binary, "-batch", "-export", "-sheets", "1", "-output", str(out_dir), "--", str(image)]
        )
        (out_dir / "audiveris.log").write_text(log)
        mxls = sorted(out_dir.glob("*.mxl"))
        if not mxls:
            raise EngineError("Audiveris finished without writing an .mxl file", log)
        with zipfile.ZipFile(mxls[0]) as z:
            names = [n for n in z.namelist() if n.endswith(".xml") and not n.startswith("META-INF")]
            if not names:
                raise EngineError("Audiveris .mxl contains no MusicXML", log)
            data = z.read(names[0])
        result = out_dir / "engine.musicxml"
        result.write_bytes(data)
        return result
