"""The form of the benchmark songs (plan 0004, step 1, first part): what the truth prints (repeat
barlines, voltas, D.C./coda, stacked verses, form words) and how homr's repeat barlines compare
with it on the last song run. Run from `bench/`: `python -m songs.form`."""
from __future__ import annotations

import collections
import glob
import io
import os
import re
import xml.etree.ElementTree as ET
import zipfile

FORM_WORDS = re.compile(r"refrain|chorus|couplet|verse|strophe|x\s?\d|\d\s?x|fine|d\.?c\.?|d\.?s\.?|coda|bis|ritornello|estribillo", re.I)


def load(path: str) -> ET.Element:
    if path.endswith(".mxl"):
        z = zipfile.ZipFile(path)
        name = [n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF")][0]
        return ET.parse(io.BytesIO(z.read(name))).getroot()
    return ET.parse(path).getroot()


def repeats(root: ET.Element) -> set[tuple[int, str]]:
    return {(i, r.get("direction") or "") for i, m in enumerate(root.find("part").findall("measure")) for r in m.iter("repeat")}


def inventory() -> None:
    rows = []
    for path in sorted(glob.glob("songs/*/*.mxl") + glob.glob("samples/*.musicxml")):
        r = load(path)
        p = r.find("part")
        meas = p.findall("measure")
        endings = sum(1 for m in meas for _ in m.iter("ending"))
        jumps = sum(1 for s in r.iter("sound") if set(s.attrib) & {"dacapo", "dalsegno", "tocoda", "fine", "segno", "coda"})
        verses = max((len({l.get("number") or "1" for l in n.findall("lyric")}) for n in p.iter("note")), default=0)
        words = [w.text.strip() for w in r.iter("words") if w.text and FORM_WORDS.search(w.text)]
        rows.append((os.path.basename(path), len(meas), len(repeats(r)), endings, jumps, verses, words))
    print(f"{'song':40} {'meas':>4} {'rep':>3} {'volta':>5} {'jump':>4} {'verses':>6}  form words")
    for r in rows:
        print(f"{r[0]:40} {r[1]:4} {r[2]:3} {r[3]:5} {r[4]:4} {r[5]:6}  {r[6]}")
    n = len(rows)
    print(f"\n{n} songs: repeat barlines {sum(1 for r in rows if r[2])}, voltas {sum(1 for r in rows if r[3])}, "
          f"D.C./coda/fine {sum(1 for r in rows if r[4] or r[6] and any(re.search(r'fine|coda|d\.?c', w, re.I) for w in r[6]))}, "
          f"2+ verses {sum(1 for r in rows if r[5] >= 2)}, 3+ verses {sum(1 for r in rows if r[5] >= 3)}, form words {sum(1 for r in rows if r[6])}")


def repeat_recall() -> None:
    exact = collections.Counter()
    count = collections.Counter()
    for eng in sorted(glob.glob("out/songs/*/run/*/homr/engine.musicxml")):
        parts = eng.split("/")
        name, kind = parts[4], parts[2]
        base = name[:-6] if name.endswith("_photo") else name
        truth = f"songs/{kind}/{base}.mxl"
        if not os.path.exists(truth):
            continue
        t, e = repeats(load(truth)), repeats(load(eng))
        exact.update(tp=len(t & e), fp=len(e - t), fn=len(t - e))
        count.update(tp=min(len(t), len(e)), fp=max(0, len(e) - len(t)), fn=max(0, len(t) - len(e)))
        if t != e:
            print(f"  {name:40} truth {sorted(t)}  engine {sorted(e)}")
    for label, c in (("exact position and direction", exact), ("count per page", count)):
        p = c["tp"] / (c["tp"] + c["fp"] or 1)
        r = c["tp"] / (c["tp"] + c["fn"] or 1)
        print(f"repeat barlines, {label}: tp {c['tp']} fp {c['fp']} fn {c['fn']}  precision {p:.2f} recall {r:.2f}")


if __name__ == "__main__":
    inventory()
    print("\nhomr's repeat barlines against the truth (pages where they differ):")
    repeat_recall()
