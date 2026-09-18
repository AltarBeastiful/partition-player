"""Place chord tokens on measures and beats, and write them as MusicXML <harmony> (ADR 0003).

Inputs: the engine's MusicXML (ElementTree) and the driver's geometry.json. Per system, the measure
count the transformer saw assigns a run of XML measures to the system; barlines (deduplicated) give
the measure boundaries in x, with one-missing-barline repair and an equal-width fallback; inside a
measure, the token snaps to a note onset when the detected noteheads match the score's note count,
else to a beat by fractional position. Tokens below the confidence floor, in the clef zone, outside
the chord band, or off the common baseline are reported, never written.
"""
from __future__ import annotations

import statistics
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fractions import Fraction

from .grammar import Chord, parse_chord

MIN_CONFIDENCE = 0.6
CLEF_ZONE_UNITS = 3.0
BAND_MIN_UNITS, BAND_MAX_UNITS = 0.8, 4.5
BASELINE_TOLERANCE_UNITS = 0.7


@dataclass
class Placed:
    measure: int          # 0-based index over the part's measures
    offset: Fraction      # quarter lengths from the measure start
    chord: Chord
    confidence: float
    x_left: float


@dataclass
class MeasureInfo:
    length: Fraction                  # quarter lengths
    onsets: list[Fraction]            # note onsets (rests excluded), quarter lengths, for chord-tone groups once


@dataclass
class Result:
    placed: list[Placed] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    seen: list[dict] = field(default_factory=list)  # rejected tokens, for the UI


# ---- reading the score --------------------------------------------------------------------------

def measure_infos(part: ET.Element) -> list[MeasureInfo]:
    divisions = 1
    beats, beat_type = 4, 4
    infos = []
    for m in part.findall("measure"):
        for attrs in m.findall("attributes"):
            d = attrs.find("divisions")
            if d is not None and d.text:
                divisions = int(d.text)
            t = attrs.find("time")
            if t is not None:
                beats = int(t.findtext("beats") or beats)
                beat_type = int(t.findtext("beat-type") or beat_type)
        pos = Fraction(0)
        onsets: list[Fraction] = []
        for el in m:
            if el.tag == "note":
                dur = int(el.findtext("duration") or 0)
                q = Fraction(dur, divisions)
                if el.find("chord") is not None:
                    continue
                if el.find("grace") is not None:
                    continue
                if el.find("rest") is None:
                    onsets.append(pos)
                pos += q
            elif el.tag == "backup":
                pos -= Fraction(int(el.findtext("duration") or 0), divisions)
            elif el.tag == "forward":
                pos += Fraction(int(el.findtext("duration") or 0), divisions)
        infos.append(MeasureInfo(Fraction(beats * 4, beat_type), sorted(set(onsets))))
    return infos


def system_runs(part: ET.Element, counts: list[int]) -> tuple[list[tuple[int, int]], str | None]:
    """(start, end) measure index per system from the transformer's counts, else from <print new-system>."""
    measures = part.findall("measure")
    total = len(measures)
    if counts and sum(counts) == total and all(c > 0 for c in counts):
        runs, c = [], 0
        for n in counts:
            runs.append((c, c + n)); c += n
        return runs, None
    starts = [i for i, m in enumerate(measures) if i == 0 or any(p.get("new-system") == "yes" for p in m.findall("print"))]
    runs = [(s, (starts[i + 1] if i + 1 < len(starts) else total)) for i, s in enumerate(starts)]
    return runs, f"measure counts per system {counts} do not add up to {total}; using system breaks from the score"


# ---- geometry -------------------------------------------------------------------------------------

def boundaries(system: dict, n_measures: int, warnings: list[str], note_counts: list[int] | None = None) -> list[float]:
    unit, min_x, max_x = system["unit"], system["min_x"], system["max_x"]
    bars = [b for b in system["bars"] if b > min_x + CLEF_ZONE_UNITS * unit]
    edges = [min_x] + bars
    if not bars or bars[-1] < max_x - 2 * unit:
        edges.append(max_x)
    notes = system["notes"]
    # a barline with no note before it (a repeat sign after the key signature) or an empty sliver is not a measure
    while notes and len(edges) - 1 > n_measures:
        empty = next((k for k in range(len(edges) - 1) if not any(edges[k] <= x < edges[k + 1] for x in notes)), None)
        if empty is None:
            break
        del edges[empty + 1 if empty + 1 < len(edges) - 1 else empty]
    if len(edges) - 1 == n_measures:
        return edges
    if len(edges) - 1 == n_measures - 1 and n_measures >= 2:
        widths = [edges[i + 1] - edges[i] for i in range(len(edges) - 1)]
        i = max(range(len(widths)), key=lambda k: widths[k])
        inside = [x for x in notes if edges[i] < x < edges[i + 1]]
        left = note_counts[i] if note_counts and i < len(note_counts) else None
        right = note_counts[i + 1] if note_counts and i + 1 < len(note_counts) else None
        if left and right and len(inside) == left + right and left >= 1:
            split = (inside[left - 1] + inside[left]) / 2  # the score says where the measure ends
        elif len(inside) >= 2:
            gaps = [(inside[k + 1] - inside[k], (inside[k + 1] + inside[k]) / 2) for k in range(len(inside) - 1)]
            split = max(gaps)[1]
        else:
            split = (edges[i] + edges[i + 1]) / 2
        warnings.append(f"system {system['index'] + 1}: one barline not detected, measure boundary estimated")
        return edges[:i + 1] + [split] + edges[i + 1:]
    start = (notes[0] - unit) if notes else min_x + 8 * unit
    warnings.append(f"system {system['index'] + 1}: {len(edges) - 1} measures from barlines but {n_measures} in the score; chords placed by proportion")
    return [start + (max_x - start) * k / n_measures for k in range(n_measures + 1)]


def beat_in_measure(x_left: float, edges: tuple[float, float], notes_in_measure: list[float], info: MeasureInfo, unit: float) -> Fraction:
    anchor = x_left + 0.3 * unit
    if len(notes_in_measure) == len(info.onsets) and info.onsets:
        k = next((i for i, nx in enumerate(notes_in_measure) if nx >= x_left - 1.0 * unit), len(info.onsets) - 1)
        return info.onsets[k]
    start = notes_in_measure[0] - 0.5 * unit if notes_in_measure else edges[0]
    span = max(edges[1] - start, unit)
    frac = (anchor - start) / span
    if frac < 0.15:
        return Fraction(0)
    beats = info.length * 2  # half-beat grid in quarters
    return min(Fraction(round(frac * beats), 2), info.length - Fraction(1, 2))


# ---- placement ------------------------------------------------------------------------------------

def place(tree: ET.ElementTree, geometry: dict) -> Result:
    result = Result()
    part = tree.getroot().find("part")
    if part is None:
        return result
    infos = measure_infos(part)
    systems = geometry.get("systems", [])
    runs, warn = system_runs(part, [s.get("measures", 0) for s in systems])
    if warn:
        result.warnings.append(warn)
    for system, (start, end) in zip(systems, runs):
        unit = system["unit"]
        accepted = []
        for t in system["tokens"]:
            chord = parse_chord(t["text"]) if t["text"] else None
            why = None
            if chord is None:
                why = "not a chord"
            elif t["confidence"] < MIN_CONFIDENCE:
                why = f"low confidence {t['confidence']:.2f}"
            elif t["x_left"] < system["min_x"] + CLEF_ZONE_UNITS * unit:
                why = "above the clef"
            elif not (BAND_MIN_UNITS <= t["y_units_above"] <= BAND_MAX_UNITS):
                why = "outside the chord band"
            elif t.get("framed"):
                why = "boxed text, a rehearsal mark"
            if why:
                if t["raw"].strip() and (t["confidence"] >= 0.2 or len(t["raw"].strip()) >= 2):  # skip detector noise
                    result.seen.append({"system": system["index"] + 1, "text": t["raw"] or t["text"], "reading": t["text"], "confidence": t["confidence"], "reason": why})
                continue
            accepted.append((t, chord))
        if len(accepted) >= 3:
            base = statistics.median(t["y_units_above"] for t, _ in accepted)
            keep = []
            for t, chord in accepted:
                if abs(t["y_units_above"] - base) > BASELINE_TOLERANCE_UNITS:
                    result.seen.append({"system": system["index"] + 1, "text": t["raw"] or t["text"], "reading": t["text"], "confidence": t["confidence"], "reason": "off the chord line"})
                else:
                    keep.append((t, chord))
            accepted = keep
        n = end - start
        if n <= 0 or not accepted:
            continue
        edges = boundaries(system, n, result.warnings, [len(infos[start + k].onsets) for k in range(n)])
        for t, chord in sorted(accepted, key=lambda a: a[0]["x_left"]):
            # a chord name starts at (or a little left of) the notehead it belongs to
            anchor = next((x for x in system["notes"] if x >= t["x_left"] - 1.0 * unit), t["x_left"] + 0.3 * unit)
            i = max(0, min(n - 1, next((k for k in range(n) if anchor < edges[k + 1]), n - 1)))
            info = infos[start + i]
            notes_in = [x for x in system["notes"] if edges[i] <= x < edges[i + 1]]
            offset = beat_in_measure(t["x_left"], (edges[i], edges[i + 1]), notes_in, info, unit)
            result.placed.append(Placed(start + i, offset, chord, t["confidence"], t["x_left"]))
    # two readings of the same chord at the same spot (overlapping boxes) collapse to one
    dedup: dict[tuple[int, Fraction], Placed] = {}
    for p in result.placed:
        key = (p.measure, p.offset)
        if key not in dedup or p.confidence > dedup[key].confidence:
            if key in dedup and dedup[key].chord.text != p.chord.text:
                result.warnings.append(f"measure {p.measure + 1}: two chords read at the same beat ({dedup[key].chord.text}, {p.chord.text}); kept the surer one")
            dedup[key] = p
    result.placed = sorted(dedup.values(), key=lambda p: (p.measure, p.offset))
    return result


# ---- writing --------------------------------------------------------------------------------------

def harmony_element(chord: Chord) -> ET.Element:
    h = ET.Element("harmony")
    root = ET.SubElement(h, "root")
    ET.SubElement(root, "root-step").text = chord.root
    if chord.root_alter:
        ET.SubElement(root, "root-alter").text = str(chord.root_alter)
    ET.SubElement(h, "kind").text = chord.kind
    if chord.bass:
        bass = ET.SubElement(h, "bass")
        ET.SubElement(bass, "bass-step").text = chord.bass
        if chord.bass_alter:
            ET.SubElement(bass, "bass-alter").text = str(chord.bass_alter)
    for value, alter, kind in chord.degrees:
        d = ET.SubElement(h, "degree")
        ET.SubElement(d, "degree-value").text = str(value)
        ET.SubElement(d, "degree-alter").text = str(alter)
        ET.SubElement(d, "degree-type").text = kind
    return h


def inject(tree: ET.ElementTree, placed: list[Placed]) -> int:
    """Insert each chord before the first note at or after its offset (chord-tone notes skipped)."""
    part = tree.getroot().find("part")
    if part is None:
        return 0
    measures = part.findall("measure")
    divisions = 1
    written = 0
    per_measure: dict[int, list[Placed]] = {}
    for p in placed:
        per_measure.setdefault(p.measure, []).append(p)
    for mi, m in enumerate(measures):
        for attrs in m.findall("attributes"):
            d = attrs.find("divisions")
            if d is not None and d.text:
                divisions = int(d.text)
        todo = sorted(per_measure.get(mi, []), key=lambda p: p.offset)
        if not todo:
            continue
        # onset of every child, so we know where to insert
        pos = Fraction(0)
        onsets: list[tuple[int, Fraction]] = []
        for idx, el in enumerate(list(m)):
            if el.tag == "note":
                if el.find("chord") is None:
                    onsets.append((idx, pos))
                if el.find("chord") is None and el.find("grace") is None:
                    pos += Fraction(int(el.findtext("duration") or 0), divisions)
            elif el.tag == "backup":
                pos -= Fraction(int(el.findtext("duration") or 0), divisions)
            elif el.tag == "forward":
                pos += Fraction(int(el.findtext("duration") or 0), divisions)
        # insert from the last to the first so indices stay valid
        for p in reversed(todo):
            target = next((idx for idx, on in onsets if on >= p.offset), None)
            if target is None:
                last_note = max((idx for idx, _ in onsets), default=-1)
                target = last_note + 1 if last_note >= 0 else len(list(m))
            m.insert(target, harmony_element(p.chord))
            written += 1
    return written
