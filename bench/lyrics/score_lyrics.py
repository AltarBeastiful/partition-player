"""Score the lyrics of a candidate MusicXML against ground truth.

Usage: python bench/lyrics/score_lyrics.py <ground_truth.musicxml> <candidate.musicxml> [--dump]

Notes are identified by (measure index, onset index among the measure's sounding notes), which both
files share when they have the same measure count. Per verse: placed (a candidate syllable sits on
the note the ground truth has one on), text exact, text right up to case and punctuation, syllabic
type right, and false (candidate syllables on notes the ground truth leaves empty, or in verses the
ground truth does not have). Character error rate over the verse text in note order.
"""
import sys, unicodedata
import xml.etree.ElementTree as ET


def sounding(measure):
    return [n for n in measure.findall("note") if n.find("rest") is None and n.find("grace") is None and n.find("chord") is None]


def lyrics(path):
    """{(measure, onset): {verse: (text, syllabic, extend)}}, measure count."""
    part = ET.parse(path).getroot().find("part")
    out = {}
    measures = part.findall("measure")
    for mi, m in enumerate(measures):
        for oi, n in enumerate(sounding(m)):
            for ly in n.findall("lyric"):
                verse = int(ly.get("number") or 1)
                text = "".join(t.text or "" for t in ly.findall("text"))
                out.setdefault((mi, oi), {})[verse] = (text, ly.findtext("syllabic") or "single", ly.find("extend") is not None)
    return out, len(measures)


def norm(text):
    t = unicodedata.normalize("NFC", text).casefold()
    return "".join(c for c in t if c.isalnum() or c in "'’")


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def lcs(a, b):
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0]
        for j, cb in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if ca == cb else max(prev[j], cur[j - 1]))
        prev = cur
    return prev[-1]


def score(gt_path, cand_path, dump=False):
    gt, gt_m = lyrics(gt_path)
    cand, cand_m = lyrics(cand_path)
    r = {"gt": 0, "placed": 0, "exact": 0, "text": 0, "syllabic": 0, "false": 0, "verses_gt": 0, "verses_found": 0, "cer": None, "measures": (gt_m, cand_m)}
    gt_verses = {v for d in gt.values() for v in d}
    cand_verses = {v for d in cand.values() for v in d}
    r["verses_gt"], r["verses_found"] = len(gt_verses), len(cand_verses)
    if gt_m != cand_m:
        # measures cannot be paired by index: score the text by sequence alignment, leave placement unscored
        r["gt"] = sum(len(d) for d in gt.values())
        r["placed"] = None
        for verse in gt_verses:
            a = [norm(d[verse][0]) for k, d in sorted(gt.items()) if verse in d]
            b = [norm(d[verse][0]) for k, d in sorted(cand.items()) if verse in d]
            r["text"] += lcs(a, b)
        r["note"] = f"measures {gt_m} vs {cand_m}: placement not scored"
        return r
    gt_text, cand_text = [], []
    for key in sorted(set(gt) | set(cand)):
        g, c = gt.get(key, {}), cand.get(key, {})
        for verse, (text, syl, ext) in g.items():
            r["gt"] += 1
            if verse in c:
                r["placed"] += 1
                ct, cs, ce = c[verse]
                r["exact"] += ct == text
                r["text"] += norm(ct) == norm(text)
                r["syllabic"] += cs == syl
            if verse == 1:
                gt_text.append(norm(text)); cand_text.append(norm(c[verse][0]) if verse in c else "")
            if dump:
                print(f"  m{key[0] + 1}.{key[1]} v{verse}: {text!r:14} {syl:6} | {c.get(verse, ('-', '', False))[0]!r}")
        for verse in c:
            if verse not in g:
                r["false"] += 1
                if dump:
                    print(f"  m{key[0] + 1}.{key[1]} v{verse}: FALSE {c[verse][0]!r}")
    if gt_text:
        a, b = " ".join(gt_text), " ".join(cand_text)
        r["cer"] = round(edit_distance(a, b) / max(1, len(a)), 3)
    return r


if __name__ == "__main__":
    res = score(sys.argv[1], sys.argv[2], dump="--dump" in sys.argv)
    print(res)
