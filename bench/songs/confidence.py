"""Does the decoder's own confidence know when it is wrong? (plan 0008, step 6.) **It does not.**

Measured 2026-09-21 on 40 lead-sheet pages, 1042 measures, 76 of them wrong (base rate 0.073). The
signal is real but lives entirely in the extreme tail, and it is far too small to pay for itself:

| confidence of the least sure note | measures marked | of which wrong | precision | catches what the arithmetic cannot | marks a perfect page |
|---|---|---|---|---|---|
| <= 0.50 |  9 | 5 | 0.56 | 0 | 1 |
| <= 0.60 | 13 | 9 | **0.69** | 1 | 1 |
| <= 0.70 | 18 | 9 | 0.50 | 1 | 2 |
| <= 0.85 | 37 | 10 | 0.27 | 2 | 5 |

0.69 against a base rate of 0.073 is nine times better than chance, and still worthless here: at its
best it finds **one** measure in 1042 that the arithmetic flag cannot already see, and it marks a
page that came back exactly right, which the rating is built not to do. As a corroborating second
reader — un-silencing a notehead finding a demotion had killed — it is 0.33 precision on 3 cases.

The reason is saturation. The model is certain of everything: the pitch head has median 1.000 and
minimum 0.973 over a whole page, lift, position, articulation and slur likewise, and the rhythm head
spans 0.871 to 0.910 outside the tail. A head that emits 1.000 for every token it reads cannot tell
you which pitch it read wrongly.

So the instrumentation is **not** in the driver: a monkeypatch wrapping a vendored ONNX decode loop
is a liability on every job, and this one buys a measure per thousand. To measure it again, put this
back in `homr_driver.py` and record its result per measure of each staff (the symbol stream contains
the barlines, so it needs no geometry to line up):

    from homr.transformer.decoder_inference import ScoreDecoder
    from homr.transformer.utils import softmax   # defined there, called by nothing

    class _WatchOutputs:          # wrap the session, never reimplement the decode loop
        def __init__(self, inner, sink): self._inner, self._sink = inner, sink
        def __getattr__(self, name): return getattr(self._inner, name)
        def run_with_iobinding(self, iobinding, *a, **kw):
            out = self._inner.run_with_iobinding(iobinding, *a, **kw)
            o = iobinding.get_outputs()   # heads 0 and 1 are rhythm and pitch
            self._sink.append(min(float(np.max(softmax(o[h].numpy()[:, -1, :], dim=-1))) for h in (0, 1)))
            return out
        # ... then in a wrapper around ScoreDecoder.generate, swap self.net for this, and afterwards
        # attach each probability to its EncodedSymbol (the class has no __slots__, so it carries).

    Key the result by (system index, voice): `parse()` runs voice-major while the geometry writer
    enumerates staves system-major, and the two agree only while there is one voice — which is why
    a single-voice page looks correct and a grand staff is scrambled.

Usage: .venv-oemer/bin/python bench/songs/confidence.py [--set leadsheets|voice_piano] --geo DIR
       (DIR holds <page>/geometry.json written by a driver instrumented as above)
"""
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
from partition_player.pipeline.evidence import emitted_by_measure  # noqa: E402
from partition_player.pipeline.layout import system_spans  # noqa: E402


def sureness_by_measure(geometry: dict, measure_count: int) -> list[float | None]:
    """Per measure of the final score, the lowest confidence any of its notes was read with."""
    out: list[float | None] = [None] * measure_count
    staves = geometry.get("staves", [])
    for i, first, n, _ in system_spans(geometry, measure_count):
        for st in staves:
            if st.get("system") != i:
                continue
            row = st.get("sureness") or []
            for k in range(n):
                if k >= len(row) or row[k] is None or first + k >= measure_count:
                    continue
                here = out[first + k]
                out[first + k] = row[k] if here is None else min(here, row[k])
    return out


def main() -> None:
    sets = [sys.argv[sys.argv.index("--set") + 1]] if "--set" in sys.argv else ["leadsheets"]
    geo = Path(sys.argv[sys.argv.index("--geo") + 1]) if "--geo" in sys.argv else None
    if geo is None:
        print(__doc__)
        return
    for s in sets:
        out = ROOT / "bench" / "out" / "songs" / s
        rows = []          # (confidence, wrong, invisible to the arithmetic flag, page came back perfect)
        for gt in sorted(out.glob("*.musicxml")):
            for run in [out / "run" / gt.stem, out / "run" / (gt.stem + "_photo")]:
                cand = run / "score.musicxml"
                geometry_file = geo / run.name / "geometry.json"
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
                sure = sureness_by_measure(json.loads(geometry_file.read_text()), len(emitted))
                for m, c in enumerate(sure):
                    if c is not None:
                        rows.append((c, m in bad, flags[m] == "ok", not bad))
        if not rows:
            print(f"\n== {s}: no geometry with `sureness` found under {geo}")
            continue
        wrong = sorted(c for c, w, _, _ in rows if w)
        right = sorted(c for c, w, _, _ in rows if not w)
        print(f"\n== {s}: {len(rows)} measures with a confidence, {len(wrong)} of them wrong")

        def q(v, f):
            return v[int(f * (len(v) - 1))] if v else float("nan")
        print(f"   confidence of the WRONG measures: min {q(wrong, 0):.4f}  p25 {q(wrong, .25):.4f}  "
              f"median {q(wrong, .5):.4f}  p75 {q(wrong, .75):.4f}  max {q(wrong, 1):.4f}")
        print(f"   confidence of the RIGHT measures: min {q(right, 0):.4f}  p25 {q(right, .25):.4f}  "
              f"median {q(right, .5):.4f}  p75 {q(right, .75):.4f}  max {q(right, 1):.4f}")
        base = len(wrong) / len(rows)
        print(f"   a measure taken at random is wrong {base:.2f} of the time — a threshold has to beat that")
        print("   marking every measure under a threshold:")
        allc = sorted(c for c, _, _, _ in rows)
        for f in (0.01, 0.02, 0.05, 0.10, 0.20, 0.30):
            t = allc[int(f * (len(allc) - 1))]
            sel = [r for r in rows if r[0] <= t]
            w = sum(1 for r in sel if r[1])
            inv = sum(1 for r in sel if r[1] and r[2])
            cry = sum(1 for r in sel if r[3])
            print(f"      lowest {f * 100:4.0f}%  (confidence <= {t:.4f})  marks {len(sel):5}  wrong {w:5}  "
                  f"precision {w / max(1, len(sel)):.2f}  adds {inv:4}  CRY WOLF {cry:4}")


if __name__ == "__main__":
    main()
