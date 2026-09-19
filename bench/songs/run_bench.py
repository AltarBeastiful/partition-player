"""Run the pipeline on every song page and score the notes and the lyrics.

Pages: <out>/*.png (clean engraving) and *_photo.jpg (degraded like a phone photo), made by
bench/songs/make_pages.py, where <out> is bench/out/songs/leadsheets or .../voice_piano. The ground
truth is the transcription cut to the page, so the notes are scored against the sung line and the
syllables against the words printed under it. Results go to <out>/run/<name>/ and <out>/results.json,
which bench/songs/review.py turns into the side-by-side review page.

Usage: .venv-oemer/bin/python bench/songs/run_bench.py [--set leadsheets|voice_piano]
                                 [--only NAME] [--clean-only] [--scans] [--skip-run]
--scans runs the voice_piano set's second tier instead: the real IMSLP prints in <out>/scans/, whose
ground truth bench/songs/pin_scan.py cuts from the same transcriptions.
"""
import json, subprocess, sys, time
from pathlib import Path

# bench/lyrics has its own make_pages.py, so this directory has to come first on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lyrics"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chords"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_pages import out_dir, which_set  # noqa: E402
from score import align, tokens  # noqa: E402
from score_chords import score as score_chords  # noqa: E402
from score_lyrics import score as score_lyrics  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = out_dir(which_set(sys.argv))
RUN = OUT / "run"
CLI = ROOT / "backend" / ".venv" / "bin" / "partition-player"


def pages(clean_only: bool, scans: bool):
    if scans:
        for gt in sorted((OUT / "scans").glob("*.musicxml")):
            yield gt.stem + "_scan", OUT / "scans" / f"{gt.stem}_scan.png", gt, "scan"
        return
    for gt in sorted(OUT.glob("*.musicxml")):
        name = gt.stem
        yield name, OUT / f"{name}.png", gt, "clean"
        jpg = OUT / f"{name}_photo.jpg"
        if jpg.exists() and not clean_only:
            yield name + "_photo", jpg, gt, "photo"


def score_notes(gt: Path, cand: Path) -> dict:
    """Pitch and duration of the sung line, aligned by edit distance (bench/score.py)."""
    a, gm, _, _, _ = tokens(str(gt))
    b, cm, _, _, _ = tokens(str(cand))
    dist, pairs = align(a, b)
    both = sum(1 for x, y in pairs if x and y and x == y)
    pitch = sum(1 for x, y in pairs if x and y and x[0] == y[0])
    return {"events": len(a), "cand_events": len(b), "measures": (gm, cm), "pitch": pitch,
            "both": both, "error": round(dist / max(1, len(a)), 3)}


def main() -> None:
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    skip, clean_only, scans = "--skip-run" in sys.argv, "--clean-only" in sys.argv, "--scans" in sys.argv
    rows = []
    head = (f"{'page':46} {'kind':6} {'meas':>7} {'notes':>5} {'p+d':>6} {'syl':>4} {'placed':>6} "
            f"{'text':>5} {'verses':>6} {'false':>5} {'cer':>5} {'chrd':>5} {'right':>5} {'cfls':>4} {'s':>4}")
    print(head)
    for name, img, gt, kind in pages(clean_only, scans):
        if only and only not in name:
            continue
        out = RUN / name
        t0 = time.time()
        if not skip or not (out / "score.musicxml").exists():
            r = subprocess.run([str(CLI), "recognize", str(img), "-o", str(out)], capture_output=True, text=True)
            if r.returncode != 0:
                print(f"{name:46} {kind:6} FAILED: {(r.stderr or '').strip().splitlines()[-1:] }")
                continue
        secs = round(time.time() - t0, 1)
        cand = out / "score.musicxml"
        notes = score_notes(gt, cand)
        lyr = score_lyrics(str(gt), str(cand))
        ch = score_chords(str(gt), str(cand))
        stats = json.loads((out / "result.json").read_text())["stats"]
        row = {"name": name, "base": name[:-6] if name.endswith("_photo") else name, "kind": kind,
               "image": img.name, "notes": notes, "lyrics": lyr, "chords": ch, "seconds": secs,
               "seen": stats.get("lyrics_seen", []), "warnings": stats.get("lyric_warnings", [])}
        rows.append(row)
        placed = "-" if lyr["placed"] is None else f"{lyr['placed']}"
        print(f"{name:46} {kind:6} {notes['measures'][0]:3}/{notes['measures'][1]:<3} {notes['events']:5} "
              f"{notes['both']:6} {lyr['gt']:4} {placed:>6} {lyr['text']:5} "
              f"{lyr['verses_found']:2}/{lyr['verses_gt']:<3} {lyr['false']:5} {str(lyr['cer']):>5} "
              f"{ch['gt']:5} {ch['right']:5} {ch['false']:4} {secs:4.0f}")
    (OUT / ("results_scans.json" if scans else "results.json")).write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print()
    for kind in ("clean", "photo", "scan"):
        k = [r for r in rows if r["kind"] == kind]
        if not k:
            continue
        gt_syl = sum(r["lyrics"]["gt"] for r in k)
        placed = sum(r["lyrics"]["placed"] or 0 for r in k)
        text = sum(r["lyrics"]["text"] for r in k)
        ev = sum(r["notes"]["events"] for r in k)
        pct = lambda x, n: f"{100 * x / n:.1f}%" if n else "-"
        gt_ch = sum(r["chords"]["gt"] for r in k)
        print(f"{kind:6} pages={len(k)} | sung notes={ev} pitch={pct(sum(r['notes']['pitch'] for r in k), ev)} "
              f"pitch+duration={pct(sum(r['notes']['both'] for r in k), ev)} | syllables={gt_syl} "
              f"placed={pct(placed, gt_syl)} text={pct(text, gt_syl)} "
              f"verses={sum(r['lyrics']['verses_found'] for r in k)}/{sum(r['lyrics']['verses_gt'] for r in k)} "
              f"false={sum(r['lyrics']['false'] for r in k)} | chords={gt_ch} "
              f"right={pct(sum(r['chords']['right'] for r in k), gt_ch)} "
              f"false={sum(r['chords']['false'] for r in k)}")
    print(f"\nwrote {OUT / ('results_scans.json' if scans else 'results.json')}")


if __name__ == "__main__":
    main()
