"""The cases from the song benchmark's outputs (bench/out/songs/<set>/, made by bench/songs/run_bench.py, untracked).

Per page: ground truth `<set>/<name>.musicxml`, the pipeline's score `<set>/run/<name>[_photo]/score.musicxml`, and the
engine's own output (`with_chords.musicxml` or `homr/engine.musicxml`) whose measures that do not add up are the
engine-flagged ones, as in bench/songs/doubts.py. A span is a run of flagged measures with one measure of context each
side. With `lyrics` a span that holds ground-truth syllables also carries them as the typed lyrics source.
"""
from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("BENCH_OUT", ROOT / "bench" / "out"))   # the untracked outputs may live in another checkout
sys.path.insert(0, str(ROOT / "backend"))
from partition_player.model import notes_pass  # noqa: E402

from harness import Case  # noqa: E402
from metrics import lyrics as lyric_map  # noqa: E402


def flagged(engine: ET.Element) -> list[int]:
    return [s["index"] for s in notes_pass.measure_states(engine.find("part")) if (lambda f: f[0] != f[1])(notes_pass.fill(s))]


def spans_of(flags: list[int], count: int, context: int = 1) -> list[dict]:
    spans: list[list[int]] = []
    for i in flags:
        lo, hi = max(0, i - context), min(count - 1, i + context)
        if spans and lo <= spans[-1][1] + 1:
            spans[-1][1] = max(spans[-1][1], hi)
        else:
            spans.append([lo, hi])
    return [{"staff": 0, "from": a, "to": b} for a, b in spans]


def source_for(truth: ET.Element, first: int, last: int) -> str:
    """The ground-truth verses of a span as typed text, one verse per paragraph, syllables joined with hyphens."""
    verses: dict[int, list[str]] = {}
    for (verse, m, o), v in sorted(lyric_map(truth).items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        if first <= m <= last:
            text, syl = v.rsplit("/", 1)
            verses.setdefault(verse, []).append(text + ("-" if syl in ("begin", "middle") else " "))
    return "\n\n".join("".join(parts).strip() for _, parts in sorted(verses.items()))


def load(sets: list[str], lyrics: bool, limit: int | None = None) -> list[Case]:
    cases: list[Case] = []
    for s in sets:
        base = OUT / "songs" / s
        for gt in sorted(base.glob("*.musicxml")):
            for run in [base / "run" / gt.stem, base / "run" / (gt.stem + "_photo")]:
                score = run / "score.musicxml"
                eng = run / "with_chords.musicxml"
                if not eng.exists():
                    eng = run / "homr" / "engine.musicxml"
                if not score.exists() or not eng.exists():
                    continue
                truth, final, raw = (ET.parse(p).getroot() for p in (gt, score, eng))
                count = len(final.find("part").findall("measure"))
                if len(raw.find("part").findall("measure")) != count or len(truth.find("part").findall("measure")) != count:
                    continue   # the measure count is wrong: nothing to compare slot by slot
                spans = spans_of(flagged(raw), count)
                if not spans:
                    continue
                if lyrics:
                    for sp in list(spans):   # a words span is asked beside the notes span, never instead of it
                        text = source_for(truth, sp["from"], sp["to"])
                        if text:
                            spans.append({**sp, "lyrics_source": text})
                cases.append(Case(f"{s}/{run.name}", final, truth, spans))
    return cases[:limit] if limit else cases
