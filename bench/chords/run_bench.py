"""Run the pipeline on every chord benchmark page and score the chord symbols.

Usage: .venv-oemer/bin/python bench/chords/run_bench.py [--only NAME] [--skip-run]
Pages: bench/out/chords/*.png (clean), *_photo.jpg (degraded), bench/samples/anton_yvan_boris_photo.jpg
(real), and the negative pages (no chords printed). Outputs go to bench/out/chords/run/<name>/.
Ground truth for a page is bench/out/chords/<base>.musicxml, or the Anton ground truth.
"""
import subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from score_chords import score  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "bench" / "out" / "chords"
RUN = OUT / "run"
ANTON = (ROOT / "bench" / "samples" / "anton_yvan_boris_photo.jpg", ROOT / "bench" / "samples" / "anton_yvan_boris_ground_truth.musicxml")
GYMNO = ROOT / "bench" / "samples" / "gymnopedie1" / "page-1.png"


def pages():
    yield "anton_photo", ANTON[0], ANTON[1], "real"
    for png in sorted(OUT.glob("*.png")):
        base = png.stem
        gt = OUT / f"{base}.musicxml"
        kind = "negative" if base.startswith("neg_") else "clean"
        yield base, png, gt, kind
        jpg = OUT / f"{base}_photo.jpg"
        if jpg.exists():
            yield base + "_photo", jpg, gt, "negative" if kind == "negative" else "photo"
    if GYMNO.exists():
        yield "gymnopedie", GYMNO, None, "negative"


def main():
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    skip = "--skip-run" in sys.argv
    totals = {}
    print(f"{'page':32} {'kind':9} {'gt':>3} {'found':>5} {'right':>5} {'false':>5} {'placed':>6} {'meas':>7}  warnings")
    for name, img, gt, kind in pages():
        if only and only not in name:
            continue
        out = RUN / name
        if not skip or not (out / "score.musicxml").exists():
            r = subprocess.run([str(ROOT / "backend" / ".venv" / "bin" / "partition-player"), "recognize", str(img), "-o", str(out)], capture_output=True, text=True)
            if r.returncode != 0:
                print(f"{name:32} {kind:9} FAILED: {r.stderr.strip().splitlines()[-1] if r.stderr else ''}")
                continue
        import json
        stats = json.loads((out / "result.json").read_text())["stats"]
        if gt is None:
            res = {"gt": 0, "found": stats["chords"], "right": 0, "false": stats["chords"], "placed": None, "measures": (0, stats["measures"])}
        else:
            res = score(str(gt), str(out / "score.musicxml"))
        t = totals.setdefault(kind, {"gt": 0, "found": 0, "right": 0, "false": 0, "placed": 0, "placeable": 0, "pages": 0})
        t["pages"] += 1
        for k in ("gt", "found", "right", "false"):
            t[k] += res[k]
        if res["placed"] is not None:
            t["placed"] += res["placed"]; t["placeable"] += res["gt"]
        warn = "; ".join(stats["chord_warnings"])[:70]
        print(f"{name:32} {kind:9} {res['gt']:3} {res['found']:5} {res['right']:5} {res['false']:5} {str(res['placed']):>6} {res['measures'][0]:3}/{res['measures'][1]:<3}  {warn}")
    print()
    for kind, t in totals.items():
        placed = f"{t['placed']}/{t['placeable']}" if t["placeable"] else "-"
        print(f"{kind:9} pages={t['pages']} chords={t['gt']} found={t['found']} right={t['right']} false={t['false']} placed={placed}")


if __name__ == "__main__":
    main()
