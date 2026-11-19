"""Render a MusicXML to OGG for listening: the same recipe as bench/make_audio.py (music21 to MIDI, timidity with
FluidR3_GM, ffmpeg to Vorbis; chord symbols removed so they are not played as block chords), as a function.

Needs music21 (bench/.venv-oemer has it), timidity, the soundfont and ffmpeg; returns None with a message when missing.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SOUNDFONT = "/usr/share/sounds/sf2/FluidR3_GM.sf2"


def render(musicxml: Path, ogg: Path) -> str | None:
    """Write `ogg`; returns None on success or the reason it was skipped."""
    for tool in ("timidity", "ffmpeg"):
        if not shutil.which(tool):
            return f"{tool} is not installed"
    try:
        from music21 import converter, harmony, instrument, tempo
    except ImportError:
        return "music21 is not installed (use bench/.venv-oemer/bin/python)"
    ogg.parent.mkdir(parents=True, exist_ok=True)
    s = converter.parse(str(musicxml))
    for cs in list(s.recurse().getElementsByClass(harmony.ChordSymbol)):
        cs.activeSite.remove(cs)
    p = s.parts[0]
    p.insert(0, instrument.Piano())
    p.insert(0, tempo.MetronomeMark(number=96))
    mid, wav = ogg.with_suffix(".mid"), ogg.with_suffix(".wav")
    s.write("midi", fp=str(mid))
    subprocess.run(["timidity", "-x", f"soundfont {SOUNDFONT}", "-Ow", "-o", str(wav), str(mid)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libvorbis", "-q:a", "3", str(ogg)], check=True)
    wav.unlink(missing_ok=True)
    return None
