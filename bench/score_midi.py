"""Compare an OMR MusicXML output against a reference MIDI, measure by measure.

Usage: python bench/score_midi.py <reference.mid> <candidate.musicxml> [--measures N] [--dump]

The reference MIDI has no bar lines, so onsets are bucketed into measures using the time signature of
the candidate (assumed constant). Each measure is compared as a set of (onset within measure, MIDI
pitch) events over all staves and voices. This makes the comparison immune to cumulative drift when
one measure's duration is wrong, and chord-aware.
"""
import sys
from fractions import Fraction
from music21 import converter, note, chord, meter

def events_from_musicxml(path):
    s = converter.parse(path)
    ts = s.recurse().getElementsByClass(meter.TimeSignature).first()
    mlen = Fraction(ts.barDuration.quarterLength) if ts else Fraction(4)
    measures = {}
    nmeas = 0
    for p in s.parts:
        for m in p.getElementsByClass('Measure'):
            nmeas = max(nmeas, m.number)
            ev = measures.setdefault(m.number, set())
            for e in m.recurse().notes:
                off = Fraction(e.offset).limit_denominator(64)
                pitches = [e.pitch] if isinstance(e, note.Note) else list(e.pitches)
                for pch in pitches:
                    ev.add((off, pch.midi))
    return measures, mlen, nmeas

def events_from_midi(path, mlen, nmeas):
    s = converter.parse(path)
    measures = {i: set() for i in range(1, nmeas + 1)}
    for e in s.flatten().notes:
        onset = Fraction(e.offset).limit_denominator(64)
        mnum = int(onset // mlen) + 1
        if mnum > nmeas: continue
        off = onset - (mnum - 1) * mlen
        pitches = [e.pitch] if isinstance(e, note.Note) else list(e.pitches)
        for pch in pitches:
            measures[mnum].add((off, pch.midi))
    return measures

def main():
    ref, cand = sys.argv[1], sys.argv[2]
    dump = '--dump' in sys.argv
    nlimit = int(sys.argv[sys.argv.index('--measures') + 1]) if '--measures' in sys.argv else None
    cm, mlen, nmeas = events_from_musicxml(cand)
    if nlimit: nmeas = min(nmeas, nlimit)
    rm = events_from_midi(ref, mlen, nmeas)
    tp = fp = fn = 0; full = 0; pitch_only = 0
    rows = []
    for i in range(1, nmeas + 1):
        r, c = rm.get(i, set()), cm.get(i, set())
        hit = r & c
        tp += len(hit); fp += len(c - r); fn += len(r - c)
        full += (r == c)
        rp, cp = sorted(p for _, p in r), sorted(p for _, p in c)
        pitch_only += (rp == cp)
        if r != c:
            rows.append((i, sorted(r - c), sorted(c - r)))
    prec = tp / (tp + fp) if tp + fp else 0; rec = tp / (tp + fn) if tp + fn else 0
    print(f"candidate: {cand}")
    print(f"  measures compared: {nmeas}   measure length: {mlen} quarters")
    print(f"  note events: {tp + fn} in reference, {tp + fp} in candidate")
    print(f"  precision {prec:.3f}   recall {rec:.3f}   F1 {2*prec*rec/(prec+rec) if prec+rec else 0:.3f}")
    print(f"  measures exact (pitch and onset): {full}/{nmeas}   measures with right pitch multiset: {pitch_only}/{nmeas}")
    if dump:
        from music21 import pitch as m21pitch
        nm = lambda p: m21pitch.Pitch(midi=p).nameWithOctave
        for i, missing, extra in rows:
            print(f"    m{i}: missing {[(str(o), nm(p)) for o, p in missing]}  extra {[(str(o), nm(p)) for o, p in extra]}")
main()
