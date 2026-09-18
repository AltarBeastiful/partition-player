"""Run the pipeline on every lyrics benchmark page and score the lyrics.

Usage: .venv-oemer/bin/python bench/lyrics/run_bench.py [--only NAME] [--skip-run]
Pages: bench/out/lyrics/*.png (clean), *_photo.jpg (degraded), the real photo, and negatives
(Gymnopédie: an instrument page with no words). Outputs go to bench/out/lyrics/run/<name>/.
"""
import json, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from score_lyrics import score  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "bench" / "out" / "lyrics"
RUN = OUT / "run"
ANTON = (ROOT / "bench" / "samples" / "anton_yvan_boris_photo.jpg", ROOT / "bench" / "samples" / "anton_yvan_boris_ground_truth.musicxml")
GYMNO = ROOT / "bench" / "samples" / "gymnopedie1" / "page-1.png"


def pages():
    yield "anton_photo", ANTON[0], ANTON[1], "real"
    for png in sorted(OUT.glob("*.png")):
        base = png.stem
        gt = OUT / f"{base}.musicxml"
        kind = "paragraph" if base.startswith("para_") else "clean"
        yield base, png, gt, kind
        jpg = OUT / f"{base}_photo.jpg"
        if jpg.exists():
            yield base + "_photo", jpg, gt, "paragraph" if kind == "paragraph" else "photo"
    if GYMNO.exists():
        yield "gymnopedie", GYMNO, None, "negative"


def main():
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    skip = "--skip-run" in sys.argv
    totals = {}
    print(f"{'page':28} {'kind':9} {'gt':>4} {'placed':>6} {'text':>5} {'exact':>5} {'syl':>5} {'false':>5} {'verses':>6} {'cer':>5} {'meas':>7}  notes")
    for name, img, gt, kind in pages():
        if only and only not in name:
            continue
        out = RUN / name
        if not skip or not (out / "score.musicxml").exists():
            r = subprocess.run([str(ROOT / "backend" / ".venv" / "bin" / "partition-player"), "recognize", str(img), "-o", str(out)], capture_output=True, text=True)
            if r.returncode != 0:
                print(f"{name:28} {kind:9} FAILED: {r.stderr.strip().splitlines()[-1] if r.stderr else ''}")
                continue
        stats = json.loads((out / "result.json").read_text())["stats"]
        if gt is None:
            res = {"gt": 0, "placed": 0, "text": 0, "exact": 0, "syllabic": 0, "false": stats.get("lyrics_syllables", 0), "verses_gt": 0,
                   "verses_found": stats.get("lyrics_verses", 0), "cer": None, "measures": (0, stats["measures"])}
        else:
            res = score(str(gt), str(out / "score.musicxml"))
        t = totals.setdefault(kind, {"pages": 0, "gt": 0, "placed": 0, "text": 0, "exact": 0, "syllabic": 0, "false": 0, "cer": [], "verses_gt": 0, "verses_found": 0})
        t["pages"] += 1
        for k in ("gt", "placed", "text", "exact", "syllabic", "false", "verses_gt", "verses_found"):
            t[k] += res[k] or 0
        if res["cer"] is not None:
            t["cer"].append(res["cer"])
        if res["placed"] is None:
            t["unscored"] = t.get("unscored", 0) + 1
        seen = "; ".join(f"{s['text'][:20]} ({s['reason'][:22]})" for s in stats.get("lyrics_seen", [])[:2])
        print(f"{name:28} {kind:9} {res['gt']:4} {str(res['placed']):>6} {res['text']:5} {res['exact']:5} {res['syllabic']:5} {res['false']:5} "
              f"{res['verses_found']:2}/{res['verses_gt']:<3} {str(res['cer']):>5} {res['measures'][0]:3}/{res['measures'][1]:<3}  {seen[:60]}")
    print()
    for kind, t in totals.items():
        cer = round(sum(t["cer"]) / len(t["cer"]), 3) if t["cer"] else "-"
        pct = lambda k: f"{100 * t[k] / t['gt']:.1f}%" if t["gt"] else "-"
        print(f"{kind:9} pages={t['pages']} syllables={t['gt']} placed={t['placed']} ({pct('placed')}) text={t['text']} ({pct('text')}) "
              f"exact={t['exact']} syllabic={t['syllabic']} false={t['false']} verses={t['verses_found']}/{t['verses_gt']} cer={cer}"
              + (f" unscored_pages={t['unscored']}" if t.get("unscored") else ""))


if __name__ == "__main__":
    main()
