"""Score chord symbols in a candidate MusicXML against ground truth.

Usage: python bench/chords/score_chords.py <ground_truth.musicxml> <candidate.musicxml> [--dump]

Each chord symbol becomes (measure, beat, root, kind, bass). Reported:
- sequence: edit distance between the (root, kind, bass) sequences, ignoring position;
- placement: chords whose (measure, beat) also match, when both files have the same measure count;
- false: candidate chords with no counterpart in the alignment (the number that must be 0).
Quarter-length positions are compared at half-beat resolution.
"""
import sys
from music21 import converter, harmony, pitch


def chords(path):
    s = converter.parse(path)
    p = s.parts[0]
    out = []
    measures = list(p.getElementsByClass("Measure"))
    for m in measures:
        for cs in m.getElementsByClass(harmony.ChordSymbol):
            root = cs.root().name if cs.root() else "?"
            bass = cs.bass().name if cs.bass() and cs.root() and cs.bass().name != cs.root().name else ""
            kind = cs.chordKind or "major"
            out.append((m.number, round(float(cs.offset) * 2) / 2, norm(root), kind, norm(bass)))
    return out, len(measures)


def norm(name):  # music21 spells flats as "B-"; use "Bb"
    return name.replace("-", "b")


def align(a, b):
    n, m = len(a), len(b)
    D = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1): D[i][0] = i
    for j in range(m + 1): D[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i][j] = min(D[i - 1][j] + 1, D[i][j - 1] + 1, D[i - 1][j - 1] + (0 if a[i - 1] == b[j - 1] else 1))
    i, j = n, m; pairs = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and D[i][j] == D[i - 1][j - 1] + (0 if a[i - 1] == b[j - 1] else 1):
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif i > 0 and D[i][j] == D[i - 1][j] + 1:
            pairs.append((i - 1, None)); i -= 1
        else:
            pairs.append((None, j - 1)); j -= 1
    return D[n][m], pairs[::-1]


def score(gt_path, cand_path, dump=False):
    gt, gt_m = chords(gt_path)
    cand, cand_m = chords(cand_path)
    key = lambda c: (c[2], c[3], c[4])
    dist, pairs = align([key(c) for c in gt], [key(c) for c in cand])
    right = sum(1 for i, j in pairs if i is not None and j is not None and key(gt[i]) == key(cand[j]))
    false = sum(1 for i, j in pairs if j is not None and (i is None or key(gt[i]) != key(cand[j])))
    placed = None
    if gt_m == cand_m:
        placed = sum(1 for i, j in pairs if i is not None and j is not None and key(gt[i]) == key(cand[j])
                     and gt[i][0] == cand[j][0] and abs(gt[i][1] - cand[j][1]) < 0.01)
    if dump:
        for i, j in pairs:
            print("  ", gt[i] if i is not None else "-" * 20, "|", cand[j] if j is not None else "-")
    return {"gt": len(gt), "found": len(cand), "right": right, "false": false, "placed": placed,
            "measures": (gt_m, cand_m), "edit": dist}


if __name__ == "__main__":
    r = score(sys.argv[1], sys.argv[2], dump="--dump" in sys.argv)
    print(f"chords gt={r['gt']} found={r['found']} right={r['right']} false={r['false']} "
          f"placed={r['placed']} measures={r['measures'][0]}/{r['measures'][1]} edit={r['edit']}")
