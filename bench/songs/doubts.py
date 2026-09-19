"""How well the doubts point at the wrong measures (ADR 0005).

A measure of the engine's output that is shorter or longer than its time signature is a doubt. On
the pages whose measure count came back right, each measure is labelled wrong when the event
alignment of bench/score.py puts an error in it, and flagged when the engine's own output (before
padding) did not add up. Precision is the share of flagged measures that are wrong, recall the share
of wrong measures that are flagged.

Usage: .venv-oemer/bin/python bench/songs/doubts.py [--set leadsheets|voice_piano]   (needs run outputs)
"""
import collections
import sys
from fractions import Fraction
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench"))
sys.path.insert(0, str(ROOT / "backend"))
from score import align, tokens  # noqa: E402
from partition_player.pipeline.postprocess import _measure_filled, measures  # noqa: E402
from music21 import harmony  # noqa: E402


def fill_flags(engine_xml: Path) -> list[str]:
    part = ET.parse(engine_xml).getroot().find("part")
    out = []
    for ctx in measures(part):
        f = _measure_filled(ctx.measure, ctx.divisions)
        out.append("empty" if f == 0 else "under" if f < ctx.expected else "over" if f > ctx.expected else "ok")
    return out


def per_measure(meas) -> list[int]:
    idx = []
    for i, m in enumerate(meas):
        idx += [i] * sum(1 for e in m.recurse().notesAndRests if not isinstance(e, harmony.ChordSymbol))
    return idx


def main() -> None:
    sets = [sys.argv[sys.argv.index("--set") + 1]] if "--set" in sys.argv else ["leadsheets", "voice_piano"]
    print(f"{'set':14} {'measures':>8} {'flagged':>8} {'wrong':>6} {'precision':>9} {'errors':>7} {'found':>6} {'recall':>7} {'missed':>7}")
    for s in sets:
        out = ROOT / "bench" / "out" / "songs" / s
        c = collections.Counter()
        for gt in sorted(out.glob("*.musicxml")):
            for run in [out / "run" / gt.stem, out / "run" / (gt.stem + "_photo")]:
                cand, eng = run / "score.musicxml", run / "with_chords.musicxml"
                if not eng.exists():
                    eng = run / "homr" / "engine.musicxml"
                if not cand.exists() or not eng.exists():
                    continue
                A, gm, _, _, gmeas = tokens(str(gt))
                B, cm, _, _, cmeas = tokens(str(cand))
                if gm != cm:
                    c["skipped"] += 1
                    continue
                ai, bi = per_measure(gmeas), per_measure(cmeas)
                _, pairs = align(A, B)
                bad = set()
                ia = ib = 0
                for x, y in pairs:
                    mi = None
                    if x is not None:
                        mi = ai[ia]; ia += 1
                    if y is not None:
                        mj = bi[ib]; ib += 1
                        mi = mj if mi is None else mi
                    if not (x and y and x == y):
                        bad.add(mi)
                flags = fill_flags(eng)
                if len(flags) != cm:
                    c["skipped"] += 1
                    continue
                for i, f in enumerate(flags):
                    c[("flag" if f != "ok" else "clean", "wrong" if i in bad else "right")] += 1
        fw, fr, cw, cr = c[("flag", "wrong")], c[("flag", "right")], c[("clean", "wrong")], c[("clean", "right")]
        total = fw + fr + cw + cr
        print(f"{s:14} {total:8} {fw + fr:8} {fw:6} {fw / max(1, fw + fr):9.2f} {fw + cw:7} {fw:6} {fw / max(1, fw + cw):7.2f} {cw:7}   (pages skipped: {c['skipped']})")


if __name__ == "__main__":
    main()
