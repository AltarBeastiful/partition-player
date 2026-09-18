"""Make engine output safe to play: validate, pad short measures with rests, collect statistics.

Works on the MusicXML tree directly (no music21 import cost on every job). Only score-partwise
documents are handled, which is what every engine here produces.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path


class PostprocessError(ValueError):
    pass


@dataclass
class ScoreStats:
    parts: int = 0
    measures: int = 0
    notes: int = 0
    rests: int = 0
    padded_measures: int = 0
    pickup: bool = False  # short first measure, padded at the front
    repeats_removed: int = 0
    warnings: list[str] = field(default_factory=list)
    chords: int = 0
    chord_warnings: list[str] = field(default_factory=list)
    chords_seen: list[dict] = field(default_factory=list)  # tokens read but not accepted
    lyrics_verses: int = 0
    lyrics_syllables: int = 0   # written under notes
    lyrics_read: int = 0        # read in accepted verse rows
    lyric_warnings: list[str] = field(default_factory=list)
    lyrics_seen: list[dict] = field(default_factory=list)   # rows and syllables read but not used


def _measure_filled(measure: ET.Element, divisions: int) -> Fraction:
    """Length of the longest voice in the measure, in divisions, following backup/forward."""
    pos = Fraction(0)
    end = Fraction(0)
    for el in measure:
        if el.tag == "note":
            dur_el = el.find("duration")
            if el.find("grace") is not None or dur_el is None:
                continue
            dur = Fraction(dur_el.text.strip())
            if el.find("chord") is None:
                pos += dur
            end = max(end, pos)
        elif el.tag == "backup":
            pos -= Fraction(el.findtext("duration", "0").strip())
        elif el.tag == "forward":
            pos += Fraction(el.findtext("duration", "0").strip())
            end = max(end, pos)
    return end


def _fix_rest_chords(measure: ET.Element) -> int:
    """homr sometimes emits a rest followed by a note flagged <chord/>, i.e. a "chord" of rest + note.

    The note is the real event; drop the rest and the chord flag. Returns the number of fixes."""
    fixes = 0
    notes = [el for el in measure if el.tag == "note"]
    for prev, cur in zip(notes, notes[1:]):
        if prev.find("rest") is not None and cur.find("chord") is not None and cur.find("rest") is None:
            cur.remove(cur.find("chord"))
            measure.remove(prev)
            fixes += 1
    return fixes


def _strip_repeats(measure: ET.Element) -> int:
    """Remove repeat signs and volta brackets. v1 plays the page straight through (BACKLOG: repeats)."""
    removed = 0
    for barline in measure.findall("barline"):
        for tag in ("repeat", "ending"):
            for el in barline.findall(tag):
                barline.remove(el)
                removed += 1
    return removed


def postprocess(src: Path, dst: Path) -> ScoreStats:
    try:
        tree = ET.parse(src)
    except ET.ParseError as e:
        raise PostprocessError(f"engine output is not well-formed XML: {e}") from e
    root = tree.getroot()
    if root.tag != "score-partwise":
        raise PostprocessError(f"expected score-partwise, got <{root.tag}>")

    stats = ScoreStats()
    for part in root.findall("part"):
        stats.parts += 1
        divisions = 1
        beats, beat_type = 4, 4
        for measure in part.findall("measure"):
            stats.measures += 1
            for attrs in measure.findall("attributes"):  # engines may split attributes over several blocks
                if (d := attrs.findtext("divisions")) is not None:
                    divisions = int(d.strip())
                if (t := attrs.find("time")) is not None:
                    beats = int(t.findtext("beats", "4").strip())
                    beat_type = int(t.findtext("beat-type", "4").strip())
            stats.repeats_removed += _strip_repeats(measure)
            fixed = _fix_rest_chords(measure)
            if fixed:
                stats.warnings.append(f"measure {measure.get('number')}: removed {fixed} rest(s) merged into a chord")
            for n in measure.findall("note"):
                if n.find("rest") is not None:
                    stats.rests += 1
                else:
                    stats.notes += 1
            expected = Fraction(beats * 4, beat_type) * divisions
            filled = _measure_filled(measure, divisions)
            if filled == 0:
                continue  # empty measure, leave it (OSMD renders it as a whole rest)
            if filled < expected:
                gap = expected - filled
                rest = ET.Element("note")
                ET.SubElement(rest, "rest")
                ET.SubElement(rest, "duration").text = str(int(gap))
                ET.SubElement(rest, "voice").text = "1"
                if measure is part.find("measure"):
                    # a short first measure is a pickup: the notes belong at its end, before the first full bar
                    first_note = next((i for i, el in enumerate(list(measure)) if el.tag in ("note", "harmony")), len(list(measure)))
                    measure.insert(first_note, rest)
                    measure.set("implicit", "yes")
                    stats.pickup = True
                else:
                    measure.append(rest)
                stats.padded_measures += 1
            elif filled > expected:
                stats.warnings.append(
                    f"measure {measure.get('number')} overfull: {float(filled / divisions):g} vs {float(expected / divisions):g} quarters"
                )
    if stats.parts == 0:
        raise PostprocessError("no <part> in engine output")
    if stats.notes == 0:
        raise PostprocessError("engine found no notes")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tree.write(dst, encoding="UTF-8", xml_declaration=True)
    return stats
