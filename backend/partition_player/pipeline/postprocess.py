"""Make engine output safe to play: validate, pad short measures with rests, collect statistics, and
record the doubts (ADR 0005): the measures where the engine's own output did not add up, which is
where its mistakes are (97 % of the wrong measures on the lead-sheet benchmark).

Works on the MusicXML tree directly (no music21 import cost on every job). Only score-partwise
documents are handled, which is what every engine here produces.

A file the user brings already written (plan 0010) comes through the same door with `repair=False`:
it is counted and checked but never changed, since every repair here answers something an engine
does to a page and an author does not.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterator
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
    repeat_signs: int = 0  # repeat barlines kept in the document (plan 0004)
    warnings: list[str] = field(default_factory=list)
    doubts: list[dict] = field(default_factory=list)  # per measure, see `doubt`
    chords: int = 0
    chord_warnings: list[str] = field(default_factory=list)
    chords_seen: list[dict] = field(default_factory=list)  # tokens read but not accepted
    lyrics_verses: int = 0
    lyrics_syllables: int = 0   # written under notes
    lyrics_read: int = 0        # read in accepted verse rows
    lyric_warnings: list[str] = field(default_factory=list)
    lyrics_seen: list[dict] = field(default_factory=list)   # rows and syllables read but not used


def doubt(measure: int, kind: str, text: str, part: int = 0, **detail) -> dict:
    """One thing to check. `measure` is the 0-based index in its part; kinds: padded, overfull,
    rest_chord, pickup (information, not an error), underfull and empty (the live check, and the
    reading of an imported file, which never says more than `info`; recognition raises neither).

    The level (plan 0008) says how sure we are that something is wrong: `wrong` for these, because a
    measure that does not add up cannot be right, `info` for what is only worth knowing. The rating
    of a second reading adds `check` from `evidence.py`; there is deliberately no quieter level."""
    return {"measure": measure, "part": part, "kind": kind, "text": text,
            "level": "info" if detail.get("info") else "wrong", **detail}


NAMES = {Fraction(4): "a whole note", Fraction(3): "a dotted half", Fraction(2): "a half note", Fraction(3, 2): "a dotted quarter",
         Fraction(1): "a quarter", Fraction(3, 4): "a dotted eighth", Fraction(1, 2): "an eighth", Fraction(1, 4): "a sixteenth",
         Fraction(1, 8): "a thirty-second"}
WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


def describe(quarters: Fraction) -> str:
    """A length in words a musician reads: 'a dotted quarter', 'five eighths', '2.5 quarters'."""
    if quarters in NAMES:
        return NAMES[quarters]
    for unit, name in ((Fraction(1), "quarters"), (Fraction(1, 2), "eighths"), (Fraction(1, 4), "sixteenths")):
        n = quarters / unit
        if n.denominator == 1 and 2 <= n <= 12:
            return f"{WORDS[int(n)]} {name}"
    return f"{float(quarters):g} quarters"


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


def _repeat_signs(measure: ET.Element) -> list[str]:
    """The repeat signs on a measure's barlines, "forward" and "backward", kept in the document: the
    player follows them and the user sees what was read (plan 0004). homr writes both on a barline
    marked "right" at the start of the measure, which renderers ignore for a forward sign: the
    location and the bar style are set from the direction, and the left barline moved first."""
    signs = []
    for barline in list(measure.findall("barline")):
        directions = [el.get("direction") or "backward" for el in barline.findall("repeat")]
        if not directions:
            continue
        direction = directions[0]
        for el in barline.findall("repeat")[1:]:
            barline.remove(el)
        location = "left" if direction == "forward" else "right"
        barline.set("location", location)
        for style in barline.findall("bar-style"):
            barline.remove(style)
        style = ET.Element("bar-style")
        style.text = "heavy-light" if location == "left" else "light-heavy"
        barline.insert(0, style)
        measure.remove(barline)
        if location == "left":
            measure.insert(0, barline)
        else:
            measure.append(barline)
        signs.append(direction)
    return signs


@dataclass
class MeasureCtx:
    index: int
    measure: ET.Element
    divisions: int
    beats: int
    beat_type: int

    @property
    def expected(self) -> Fraction:
        return Fraction(self.beats * 4, self.beat_type) * self.divisions

    @property
    def time(self) -> str:
        return f"{self.beats}/{self.beat_type}"

    def quarters(self, divs: Fraction) -> Fraction:
        return divs / self.divisions


def measures(part: ET.Element) -> Iterator[MeasureCtx]:
    """Every measure with the divisions and time signature in force (engines may split attributes)."""
    divisions, beats, beat_type = 1, 4, 4
    for index, measure in enumerate(part.findall("measure")):
        for attrs in measure.findall("attributes"):
            if (d := attrs.findtext("divisions")) is not None:
                divisions = int(d.strip())
            if (t := attrs.find("time")) is not None:
                beats = int(t.findtext("beats", "4").strip())
                beat_type = int(t.findtext("beat-type", "4").strip())
        yield MeasureCtx(index, measure, divisions, beats, beat_type)


def part_lengths(part: ET.Element) -> list[tuple[Fraction, Fraction]]:
    """Every measure of a part as (what it holds, what its time signature asks for), in quarters."""
    return [(ctx.quarters(_measure_filled(ctx.measure, ctx.divisions)), ctx.quarters(ctx.expected)) for ctx in measures(part)]


def upbeats(part: ET.Element) -> set[int]:
    """The short measures of a part that are an upbeat and not a mistake (plan 0010), by index.

    Two shapes, both counted over the 60 authored files of the song benchmarks, 20 of which start on
    a short measure:

    - a first measure the document marks `implicit="yes"`, which is how MusicXML writes a pickup
      (6 of the 20);
    - a short measure completed exactly by a short neighbour — or, for the page's first and last
      measures, by each other: one bar written in two pieces, which is how a songbook writes a
      section that begins mid-bar (`en_clementine` holds 2 + 1 quarters over its measures 9 and 10 of
      3/4). This covers 12 of the remaining 14 first measures, and every short measure that is not
      the first one.

    Two pages of the 60 are left saying "a quarter in a 4/4 measure", which is what they hold. In
    homr's own output the pairing would explain 68 of 100 short measures, because a missed barline
    splits one measure into two halves that add up perfectly — a doubt well worth keeping. So this
    excuses measures only where the document was authored (`postprocess(repair=False)`) or has
    already been repaired (`inspect`, the live check), never in the repair of a recognized page.
    """
    lengths = part_lengths(part)
    n = len(lengths)
    first = part.find("measure")
    out: set[int] = set()
    for i, (filled, expected) in enumerate(lengths):
        if not 0 < filled < expected:
            continue
        if i == 0 and first is not None and first.get("implicit") == "yes":
            out.add(i)
            continue
        ends = ({n - 1} if i == 0 else set()) | ({0} if i == n - 1 else set())
        for j in ({i - 1, i + 1} | ends) - {i}:
            if 0 <= j < n:
                other, other_expected = lengths[j]
                if 0 < other < other_expected and filled + other == expected:
                    out.add(i)
                    break
    return out


def _count(stats: ScoreStats, measure: ET.Element) -> None:
    for n in measure.findall("note"):
        if n.find("rest") is not None:
            stats.rests += 1
        else:
            stats.notes += 1


def _check_root(root: ET.Element) -> None:
    if root.tag != "score-partwise":
        raise PostprocessError(f"expected score-partwise, got <{root.tag}>")


def inspect(tree: ET.ElementTree) -> ScoreStats:
    """Statistics and the live check of a document, without changing it: the measures that are
    shorter or longer than their time signature become doubts of kind underfull / overfull.

    An upbeat is not one of them (plan 0010): a recognized page reaches this already padded, so a
    short measure here is either the user's own edit or an authored file's upbeat pair."""
    root = tree.getroot()
    _check_root(root)
    stats = ScoreStats()
    for p, part in enumerate(root.findall("part")):
        stats.parts += 1
        excused = upbeats(part)
        for ctx in measures(part):
            stats.measures += 1
            _count(stats, ctx.measure)
            filled = _measure_filled(ctx.measure, ctx.divisions)
            if filled == 0 or filled == ctx.expected or ctx.index in excused:
                continue
            if filled < ctx.expected:
                gap = ctx.quarters(ctx.expected - filled)
                stats.doubts.append(doubt(ctx.index, "underfull", f"shorter than {ctx.time} by {describe(gap)}", p, gap=str(gap)))
            else:
                excess = ctx.quarters(filled - ctx.expected)
                stats.warnings.append(f"measure {ctx.measure.get('number')} overfull: {float(ctx.quarters(filled)):g} vs {float(ctx.quarters(ctx.expected)):g} quarters")
                stats.doubts.append(doubt(ctx.index, "overfull", f"longer than {ctx.time} by {describe(excess)}", p, excess=str(excess)))
    if stats.parts == 0:
        raise PostprocessError("no <part> in the document")
    if stats.notes == 0:
        raise PostprocessError("the document has no notes")
    return stats


def postprocess(src: Path, dst: Path, repair: bool = True) -> ScoreStats:
    """Read `src`, write `dst`, return what the document holds.

    `repair` is what an engine's output needs and an authored file must not get (plan 0010): with it
    off nothing is padded, unmerged or moved, and a measure that does not add up is recorded as
    information rather than as a doubt."""
    try:
        tree = ET.parse(src)
    except ET.ParseError as e:
        raise PostprocessError(f"engine output is not well-formed XML: {e}") from e
    root = tree.getroot()
    _check_root(root)

    stats = ScoreStats()
    for p, part in enumerate(root.findall("part")):
        stats.parts += 1
        (_repair_part if repair else _read_part)(part, p, stats)
    if stats.parts == 0:
        raise PostprocessError("no <part> in the document")
    if stats.notes == 0:
        raise PostprocessError("the document has no notes")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tree.write(dst, encoding="UTF-8", xml_declaration=True)
    return stats


def _read_part(part: ET.Element, p: int, stats: ScoreStats) -> None:
    """An authored part: counted and noted, never touched. Only the repeat signs the player will
    obey and the measures that do not add up after the upbeat rules are worth saying, both as
    information (plan 0010)."""
    lengths = part_lengths(part)
    excused = upbeats(part)
    for ctx in measures(part):
        stats.measures += 1
        _count(stats, ctx.measure)
        signs = [el.get("direction") or "backward" for bl in ctx.measure.findall("barline") for el in bl.findall("repeat")]
        if signs:
            stats.repeat_signs += len(signs)
            words = " and ".join("goes back to here" if d == "forward" else "goes back from here" for d in signs)
            stats.doubts.append(doubt(ctx.index, "repeat", f"a repeat sign is written here: playback {words}", p, info=True, directions=signs))
        filled, expected = lengths[ctx.index]
        if ctx.index == 0 and 0 < filled < expected:
            stats.pickup = True
        if filled == expected or ctx.index in excused:
            continue
        if filled == 0:
            stats.doubts.append(doubt(ctx.index, "empty", "this measure holds nothing", p, info=True))
        elif filled < expected:
            stats.doubts.append(doubt(ctx.index, "underfull", f"{describe(filled)} in a {ctx.time} measure", p, info=True, gap=str(expected - filled)))
        else:
            stats.doubts.append(doubt(ctx.index, "overfull", f"{describe(filled)} in a {ctx.time} measure", p, info=True, excess=str(filled - expected)))


def _repair_part(part: ET.Element, p: int, stats: ScoreStats) -> None:
    """An engine's part: made safe to play, and every repair recorded as a doubt (ADR 0005)."""
    for ctx in measures(part):
        measure = ctx.measure
        stats.measures += 1
        signs = _repeat_signs(measure)
        if signs:
            stats.repeat_signs += len(signs)
            words = " and ".join("goes back to here" if d == "forward" else "goes back from here" for d in signs)
            stats.doubts.append(doubt(ctx.index, "repeat", f"a repeat sign was read: playback {words}", p, info=True, directions=signs))
        fixed = _fix_rest_chords(measure)
        if fixed:
            stats.warnings.append(f"measure {measure.get('number')}: removed {fixed} rest(s) merged into a chord")
            stats.doubts.append(doubt(ctx.index, "rest_chord", f"a rest merged into a chord was removed ({fixed}); check the beat", p, fixed=fixed))
        _count(stats, measure)
        filled = _measure_filled(measure, ctx.divisions)
        if filled == 0:
            continue  # empty measure, leave it (OSMD renders it as a whole rest)
        if filled < ctx.expected:
            gap = ctx.expected - filled
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
                stats.doubts.append(doubt(ctx.index, "pickup", f"first measure is shorter than {ctx.time} by {describe(ctx.quarters(gap))}: treated as a pickup, a rest was added at the front",
                                          p, gap=str(ctx.quarters(gap)), info=True))
            else:
                measure.append(rest)
                stats.doubts.append(doubt(ctx.index, "padded", f"shorter than {ctx.time} by {describe(ctx.quarters(gap))}: a rest was added at the end", p, gap=str(ctx.quarters(gap))))
            stats.padded_measures += 1
        elif filled > ctx.expected:
            stats.warnings.append(
                f"measure {measure.get('number')} overfull: {float(ctx.quarters(filled)):g} vs {float(ctx.quarters(ctx.expected)):g} quarters"
            )
            excess = ctx.quarters(filled - ctx.expected)
            stats.doubts.append(doubt(ctx.index, "overfull", f"longer than {ctx.time} by {describe(excess)}", p, excess=str(excess)))
