"""Re-run only the lyrics placement on a finished benchmark run (no recognition), for quick tuning.

Usage: backend/.venv/bin/python bench/lyrics/replace.py [--only NAME]
Reads bench/out/lyrics/run/<name>/homr/geometry.json and the score, strips its lyrics, places them again
with the current code, writes <name>/score.musicxml back and prints the same table as run_bench.
"""
import json, re, subprocess, sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from partition_player.pipeline.lyrics import inject  # noqa: E402
from partition_player.pipeline.lyrics.align import place_lyrics  # noqa: E402

RUN = ROOT / "bench" / "out" / "lyrics" / "run"
only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
for d in sorted(RUN.iterdir()):
    geo = d / "homr" / "geometry.json"
    score = d / "score.musicxml"
    if not geo.exists() or not score.exists() or (only and only not in d.name):
        continue
    geometry = json.loads(geo.read_text())
    tree = ET.parse(score)
    part = tree.getroot().find("part")
    inject.strip_lyrics(part)
    result = place_lyrics(tree, geometry)
    inject.inject(part, result.placed)
    tree.write(score, encoding="UTF-8", xml_declaration=True)
    inject.save(d / "lyrics.json", result.placed, result.warnings, result.seen)
    r = json.loads((d / "result.json").read_text())
    r["stats"].update(lyrics_verses=result.verses, lyrics_syllables=len(result.placed), lyrics_read=result.read, lyric_warnings=result.warnings, lyrics_seen=result.seen)
    (d / "result.json").write_text(json.dumps(r, indent=2))
subprocess.run([str(ROOT / ".venv-oemer" / "bin" / "python"), str(ROOT / "bench" / "lyrics" / "run_bench.py"), "--skip-run"] + (["--only", only] if only else []))
