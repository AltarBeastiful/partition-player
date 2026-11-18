"""How well the rated second reading points at wrong notes (plan 0008).

`bench/songs/doubts.py` scores the arithmetic flag, which can only see a measure that does not add
up. This scores what the pixel stage adds: the noteheads it found against the notes the transformer
emitted, rated by `pipeline/evidence.py`, which only speaks when the disagreement is loud and
nothing on the page argues back.

Three things are printed, because three things decide whether it ships:

- **precision** of `check`, the share of the places it marks where the candidate really is wrong;
- **what it adds**, the wrong measures it catches that the arithmetic flag does not see at all;
- **the cry-wolf count**, how many marks land on pages that came back exactly right.

The last one is the one to watch. A mark on a perfect page is the failure this plan exists to avoid.

Usage: .venv-oemer/bin/python bench/songs/rating.py [--set leadsheets|voice_piano] [--verbose]
                                                    [--geo DIR]
       (needs the run outputs of run_bench.py, whose run/<page>/homr/geometry.json it reads;
        --geo DIR reads DIR/<page>/geometry.json instead, for geometry made by a patched driver)
"""
import collections
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench"))
sys.path.insert(0, str(ROOT / "backend"))
from score import align, tokens  # noqa: E402
from doubts import fill_flags, per_measure  # noqa: E402
from partition_player.pipeline.evidence import collect, compare, emitted_by_measure, rate  # noqa: E402


def wrong_measures(gt: Path, cand: Path) -> set[int] | None:
    """Which measures of the candidate hold an error, by the event alignment of bench/score.py."""
    A, gm, _, _, gmeas = tokens(str(gt))
    B, cm, _, _, cmeas = tokens(str(cand))
    if gm != cm:
        return None
    ai, bi = per_measure(gmeas), per_measure(cmeas)
    _, pairs = align(A, B)
    bad: set[int] = set()
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
    return bad


def main() -> None:
    sets = [sys.argv[sys.argv.index("--set") + 1]] if "--set" in sys.argv else ["leadsheets", "voice_piano"]
    verbose = "--verbose" in sys.argv
    geo = Path(sys.argv[sys.argv.index("--geo") + 1]) if "--geo" in sys.argv else None
    for s in sets:
        out = ROOT / "bench" / "out" / "songs" / s
        c = collections.Counter()
        kinds = collections.Counter()
        raw = collections.Counter()
        perfect_marks = []
        raised = []
        for gt in sorted(out.glob("*.musicxml")):
            for run in [out / "run" / gt.stem, out / "run" / (gt.stem + "_photo")]:
                cand = run / "score.musicxml"
                geometry_file = (geo / run.name / "geometry.json") if geo else (run / "homr" / "geometry.json")
                eng = run / "with_chords.musicxml"
                if not eng.exists():
                    eng = run / "homr" / "engine.musicxml"
                if not cand.exists() or not geometry_file.exists() or not eng.exists():
                    continue
                bad = wrong_measures(gt, cand)
                if bad is None:
                    c["skipped"] += 1
                    continue
                part = ET.parse(cand).getroot().find("part")
                if part is None:
                    c["skipped"] += 1
                    continue
                emitted = emitted_by_measure(part)
                flags = fill_flags(eng)
                if len(flags) != len(emitted):
                    c["skipped"] += 1
                    continue
                evidence = collect(json.loads(geometry_file.read_text()), len(emitted))
                adds_up = [f == "ok" for f in flags]
                findings = compare(evidence, emitted, adds_up=adds_up)
                marks = rate(findings)
                c["pages"] += 1
                c["measures"] += len(emitted)
                c["arith"] += sum(1 for f in flags if f != "ok")
                if not bad:
                    c["perfect_pages"] += 1
                    if marks:
                        perfect_marks.append((run.name, [m["measure"] + 1 for m in marks]))
                for f in findings:
                    raw[(f.kind, "wrong" if f.measure in bad else "right")] += 1
                    if f.measure in bad and flags[f.measure] == "ok":
                        raw[(f.kind, "adds")] += 1
                for m in marks:
                    i = m["measure"]
                    kinds[(m["kind"], "wrong" if i in bad else "right")] += 1
                    c[("check", "wrong" if i in bad else "right")] += 1
                    if i in bad and flags[i] == "ok":
                        c["added"] += 1   # a wrong measure the arithmetic flag cannot see
                    raised.append((run.name, i + 1, m["kind"], i in bad, flags[i] == "ok"))
                c["quiet_wrong"] += sum(1 for i in bad if flags[i] == "ok" and not any(m["measure"] == i for m in marks))
                c["findings"] += len(findings)

        cw, cr = c[("check", "wrong")], c[("check", "right")]
        print(f"\n== {s}: {c['pages']} pages, {c['measures']} measures, {c['perfect_pages']} of the pages exactly right")
        print(f"   findings before rating : {c['findings']}")
        print(f"   marked 'check'         : {cw + cr}   of which wrong {cw}   precision {cw / max(1, cw + cr):.2f}")
        print(f"   wrong measures the arithmetic flag cannot see, now caught : {c['added']}")
        print(f"   wrong measures still silent (arithmetic clean, no mark)   : {c['quiet_wrong']}")
        print(f"   CRY WOLF: marks on pages that came back exactly right     : {sum(len(m) for _, m in perfect_marks)}")
        for name, ms in perfect_marks:
            print(f"      {name}: measures {ms}")
        print("   by kind, as marked:")
        for (kind, verdict), n in sorted(kinds.items()):
            print(f"      {kind:12} {verdict:6} {n}")
        print("   by kind, every finding before the rating (what each source is worth on its own):")
        for kind in sorted({k for k, _ in raw}):
            w, r, a = raw[(kind, "wrong")], raw[(kind, "right")], raw[(kind, "adds")]
            print(f"      {kind:12} fires {w + r:5}  wrong {w:5}  precision {w / max(1, w + r):.2f}  "
                  f"of which the arithmetic flag cannot see {a}")
        if c["skipped"]:
            print(f"   (pages skipped, measure count came back different: {c['skipped']})")
        if verbose:
            for row in raised:
                print("     ", row)


if __name__ == "__main__":
    main()
