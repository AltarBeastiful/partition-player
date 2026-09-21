"""Is one reader ever enough on its own? (plan 0008, the threshold question.)

The rating counts readers: one disagreeing source is worth nothing unless something makes it strong.
This asks the other way round — whether a single source carries a *strength* such that below some
value it should stay silent and above it, alone, it is right often enough to speak.

For every finding the comparison makes, it prints the share that land on a measure the ground truth
says is wrong, sliced by each feature of the finding, and then the precision and the volume of every
threshold on the promising ones. A threshold is only worth taking if it clears the bar with enough
findings left to matter.

Usage: .venv-oemer/bin/python bench/songs/thresholds.py [--set leadsheets|voice_piano] [--geo DIR]
"""
import collections
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench"))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from doubts import fill_flags  # noqa: E402
from rating import wrong_measures  # noqa: E402
from partition_player.pipeline.evidence import collect, compare, emitted_by_measure  # noqa: E402


def rows_for(setname: str, geo: Path | None):
    out = ROOT / "bench" / "out" / "songs" / setname
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
            part = ET.parse(cand).getroot().find("part")
            if bad is None or part is None:
                continue
            emitted = emitted_by_measure(part)
            flags = fill_flags(eng)
            if len(flags) != len(emitted):
                continue
            evidence = collect(json.loads(geometry_file.read_text()), len(emitted))
            for f in compare(evidence, emitted, adds_up=[x == "ok" for x in flags]):
                yield run.name, f, f.measure in bad, flags[f.measure] == "ok", not bad


def share(label, wrong, total, extra=""):
    print(f"   {label:44} {total:5}  wrong {wrong:5}  precision {wrong / max(1, total):.2f} {extra}")


def main() -> None:
    sets = [sys.argv[sys.argv.index("--set") + 1]] if "--set" in sys.argv else ["leadsheets", "voice_piano"]
    geo = Path(sys.argv[sys.argv.index("--geo") + 1]) if "--geo" in sys.argv else None
    for s in sets:
        rows = list(rows_for(s, geo))
        print(f"\n== {s}: {len(rows)} findings")
        if not rows:
            continue
        by = collections.Counter()
        for _, f, bad, invisible, perfect in rows:
            ft = f.features
            keys = [
                ("kind", f.kind),
                ("delta", ft["delta"]),
                ("estimated", ft["estimated"]),
                ("measure adds up", ft["sound"]),
                ("monophonic page", ft["monophonic"]),
                ("stacked groups", ft["stacked"]),
                ("stack on the grid", ft["on_grid"]),
            ]
            for name, v in keys:
                by[(name, v, "n")] += 1
                by[(name, v, "w")] += bad
        for name in ["kind", "delta", "estimated", "measure adds up", "monophonic page", "stacked groups", "stack on the grid"]:
            print(f"  by {name}:")
            for (nm, v, k) in sorted({(a, b, c) for (a, b, c) in by if a == name and c == "n"}, key=lambda t: str(t[1])):
                share(f"{v}", by[(nm, v, "w")], by[(nm, v, "n")])

        # the question itself: one source, on its own. Which demotions earn their keep?
        names = ["the measure's boundaries were estimated", "the measure adds up",
                 "the page is monophonic everywhere else", "the extra head is not on the staff grid"]
        short = {names[0]: "estimated", names[1]: "adds up", names[2]: "monophonic", names[3]: "off grid"}
        print("  ONE SOURCE ALONE — what is left when only some demotions silence a finding:")
        import itertools
        best = []
        for k in range(len(names) + 1):
            for keep in itertools.combinations(names, k):
                sel = [r for r in rows if not (set(r[1].demotions) & set(keep))]
                if not sel:
                    continue
                w = sum(1 for r in sel if r[2])
                inv = sum(1 for r in sel if r[2] and r[3])
                cry = sum(1 for r in sel if r[4])
                best.append((w / len(sel), inv, len(sel), cry, [short[n] for n in keep]))
        for prec, inv, n, cry, keep in sorted(best, key=lambda t: (-t[1], -t[0]))[:12]:
            share("silenced by: " + (", ".join(keep) or "nothing"), round(prec * n), n,
                  f" adds {inv:4}  CRY WOLF {cry:4}")


if __name__ == "__main__":
    main()
