"""Score an OMR MusicXML output against the ground truth MusicXML.

Usage: python bench/score.py <ground_truth.musicxml> <candidate.musicxml> [--dump]
Tokens are (pitch-or-rest, quarterLength) events of the first part, in order. Chords are reduced to
their lowest note. Alignment is by edit distance, so a missing measure or a merged one shifts nothing.
"""
import sys
from music21 import converter, note, chord, harmony

def tokens(path):
    s = converter.parse(path)
    p = s.parts[0]
    toks = []; measures = list(p.getElementsByClass('Measure'))
    for m in measures:
        for e in m.recurse().notesAndRests:   # recurse: a measure split into <voice>s nests them
            if isinstance(e, harmony.ChordSymbol): continue
            ql = float(e.duration.quarterLength)
            if isinstance(e, note.Rest): toks.append(('r', ql))
            elif isinstance(e, note.Note): toks.append((e.pitch.nameWithOctave, ql))
            elif isinstance(e, chord.Chord): toks.append((min(e.pitches).nameWithOctave, ql))
    ks = p.flatten().getElementsByClass('KeySignature'); ts = p.flatten().getElementsByClass('TimeSignature')
    return toks, len(measures), [k.sharps for k in ks], [t.ratioString for t in ts], measures

def align(a, b):
    # Levenshtein with backtrace; substitution cost 1 if pitch differs OR duration differs (partial 0.5 each)
    n, m = len(a), len(b)
    D = [[0.0]*(m+1) for _ in range(n+1)]
    for i in range(n+1): D[i][0] = i
    for j in range(m+1): D[0][j] = j
    def sub(x, y): return (0 if x[0]==y[0] else 0.5) + (0 if abs(x[1]-y[1])<1e-6 else 0.5)
    for i in range(1,n+1):
        for j in range(1,m+1):
            D[i][j] = min(D[i-1][j]+1, D[i][j-1]+1, D[i-1][j-1]+sub(a[i-1],b[j-1]))
    i, j = n, m; pairs = []
    while i>0 or j>0:
        if i>0 and j>0 and abs(D[i][j] - (D[i-1][j-1]+sub(a[i-1],b[j-1])))<1e-9: pairs.append((a[i-1], b[j-1])); i-=1; j-=1
        elif i>0 and abs(D[i][j]-(D[i-1][j]+1))<1e-9: pairs.append((a[i-1], None)); i-=1
        else: pairs.append((None, b[j-1])); j-=1
    return D[n][m], pairs[::-1]

def main():
    gt, cand = sys.argv[1], sys.argv[2]
    A, gm, gks, gts, gmeas = tokens(gt); B, cm, cks, cts, cmeas = tokens(cand)
    dist, pairs = align(A, B)
    gnotes = [t for t in A if t[0]!='r']; grests = [t for t in A if t[0]=='r']
    matched = [(x,y) for x,y in pairs if x and y]
    notes_ok = sum(1 for x,y in matched if x[0]!='r' and x[0]==y[0])
    dur_ok = sum(1 for x,y in matched if x[0]!='r' and abs(x[1]-y[1])<1e-6)
    both_ok = sum(1 for x,y in matched if x[0]!='r' and x[0]==y[0] and abs(x[1]-y[1])<1e-6)
    rests_ok = sum(1 for x,y in matched if x[0]=='r' and y[0]=='r' and abs(x[1]-y[1])<1e-6)
    rests_found = sum(1 for x,y in matched if x[0]=='r' and y[0]=='r')
    missing_notes = sum(1 for x,y in pairs if x and not y and x[0]!='r')
    extra = sum(1 for x,y in pairs if y and not x)
    print(f"candidate: {cand}")
    print(f"  measures: {cm} (truth {gm})   key sigs: {cks} (truth {gks})   time sigs: {cts} (truth {gts})")
    print(f"  notes: {len(gnotes)} truth, {missing_notes} missing, {extra} extra events")
    print(f"  pitch correct: {notes_ok}/{len(gnotes)}   duration correct: {dur_ok}/{len(gnotes)}   pitch+duration: {both_ok}/{len(gnotes)}")
    print(f"  rests: {rests_found}/{len(grests)} found, {rests_ok}/{len(grests)} with right duration")
    print(f"  event error rate (edit distance / truth events): {dist/len(A):.2f}")
    if cm == gm:
        ok = 0
        for gmm, cmm in zip(gmeas, cmeas):
            g = [(e.pitch.nameWithOctave if isinstance(e, note.Note) else ('r' if isinstance(e, note.Rest) else min(e.pitches).nameWithOctave), float(e.duration.quarterLength)) for e in gmm.recurse().notesAndRests if not isinstance(e, harmony.ChordSymbol)]
            c = [(e.pitch.nameWithOctave if isinstance(e, note.Note) else ('r' if isinstance(e, note.Rest) else min(e.pitches).nameWithOctave), float(e.duration.quarterLength)) for e in cmm.recurse().notesAndRests if not isinstance(e, harmony.ChordSymbol)]
            ok += (g == c)
        print(f"  fully correct measures: {ok}/{gm}")
    else:
        print(f"  fully correct measures: n/a (measure count differs)")
    if '--dump' in sys.argv:
        for x,y in pairs:
            flag = '' if (x and y and x==y) else '  <--'
            print(f"    {str(x):16} | {str(y):16}{flag}")
if __name__ == "__main__":
    main()
