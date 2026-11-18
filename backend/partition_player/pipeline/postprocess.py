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


ATTRIBUTES_ORDER = ["footnote", "level", "divisions", "key", "time", "staves", "part-symbol", "instruments", "clef",
                    "staff-details", "transpose", "directive", "measure-style"]


def _key_of(note: ET.Element) -> str:
    """The voice a note belongs to. MusicXML numbers voices per part and not per staff, which is how
    piano writing puts one hand's voice on the other's staff for a few notes — 7 measures of the
    benchmark's two-staff songs do — so the staff must not come into it. homr numbers its voices
    apart per staff already (`get_xml_voice`)."""
    return note.findtext("voice", "1").strip()


def _onsets(measure: ET.Element) -> list[tuple[ET.Element, Fraction, Fraction]]:
    """Every note of the measure as (element, where the written stream puts it, where its own voice
    says it belongs). The second is what a reader follows; the third has every voice entering where
    its first note is written and its notes following one another from there.

    The entry is taken and not assumed: a second voice on a staff may well begin in the middle of the
    bar and say so by the backup that positions it. Starting every voice at the bar line instead, and
    keying it by (staff, voice), moved notes in 16 of the benchmark's 1946 authored measures, all in
    the two-staff songs — those two mistakes together. What no writer means is a gap inside a voice:
    that is what a cursor laid by duration alone produces when a long note in one staff spans a
    shorter note in the other."""
    written = Fraction(0)          # a reader's cursor through backup/forward
    at: dict[str, Fraction] = {}
    head_written = head_meant = Fraction(0)
    out: list[tuple[ET.Element, Fraction, Fraction]] = []
    for el in measure:
        if el.tag == "backup":
            written -= Fraction(el.findtext("duration", "0").strip())
            continue
        if el.tag == "forward":
            written += Fraction(el.findtext("duration", "0").strip())
            continue
        if el.tag != "note":
            continue
        key = _key_of(el)
        dur_el = el.find("duration")
        grace = el.find("grace") is not None or dur_el is None
        chord = el.find("chord") is not None
        dur = Fraction(0) if grace else Fraction(dur_el.text.strip())
        if chord or grace:
            out.append((el, head_written, head_meant))
            continue
        meant = at.setdefault(key, written)
        out.append((el, written, meant))
        head_written, head_meant = written, meant
        written += dur
        at[key] = meant + dur
    return out


def _ends_at(places: list[tuple[ET.Element, Fraction, Fraction]]) -> Fraction:
    """Where the last voice ends once every voice follows its own notes, in divisions."""
    end = Fraction(0)
    for el, _, meant in places:
        dur_el = el.find("duration")
        if dur_el is None or el.find("chord") is not None or el.find("grace") is not None:
            continue
        end = max(end, meant + Fraction(dur_el.text.strip()))
    return end


def _relay(measure: ET.Element) -> bool:
    """Put every note where its own voice says it belongs, by rewriting backup and forward (plan 0013).

    homr's generator lays chords one after another by duration and keeps no absolute onset, so a long
    note in one staff spanning a shorter note in the other makes the cursor overshoot and everything
    after it in the bar lands late — the canon's measure 19 holds six quarters in each voice and is
    written seven long, with a beat of silence in the middle. So the repair is made only where it
    **shortens** the bar, which is what closing a hole does and what nothing else does: a voice whose
    writer really did leave a gap, and two voices an engine numbered alike, both leave the bar as long
    as it was and are left alone. Over the benchmark's 61 authored scores (1946 measures) this moves
    nothing at all; over homr's own output on the pages in this repository it moves 14 measures, 13 of
    them into their time signature and none out of it. Returns whether anything moved.

    Whatever is not a note and not a backup keeps the note it stands before, so a chord symbol or a
    direction keeps its beat."""
    if measure.find("forward") is not None:
        return False   # a writer that positions a voice itself is trusted to mean it
    places = _onsets(measure)
    if all(written == meant for _, written, meant in places):
        return False
    if _ends_at(places) >= _measure_filled(measure, 1):
        return False   # the bar is no shorter for it, so nothing here was a hole: leave it written
    meant = {id(el): m for el, _, m in places}
    cursor = Fraction(0)
    out: list[ET.Element] = []
    pending: list[ET.Element] = []
    for el in list(measure):
        if el.tag in ("backup", "forward"):
            continue                      # rebuilt below from the notes themselves
        if el.tag != "note":
            pending.append(el)
            continue
        onset = meant[id(el)]
        if onset != cursor:
            move = ET.Element("backup" if onset < cursor else "forward")
            ET.SubElement(move, "duration").text = str(int(abs(onset - cursor)))
            out.append(move)
            cursor = onset
        out.extend(pending)
        pending = []
        out.append(el)
        dur_el = el.find("duration")
        if dur_el is not None and el.find("grace") is None and el.find("chord") is None:
            cursor += Fraction(dur_el.text.strip())
    out.extend(pending)
    for el in list(measure):
        measure.remove(el)
    measure.extend(out)
    return True


def _voice_lengths(measure: ET.Element) -> list[Fraction]:
    """What each voice of the measure holds from its own notes alone, in divisions."""
    ends: dict[str, Fraction] = {}
    for el, _, meant in _onsets(measure):
        if el.find("chord") is not None or el.find("grace") is not None:
            continue
        dur_el = el.find("duration")
        if dur_el is None:
            continue
        ends[_key_of(el)] = meant + Fraction(dur_el.text.strip())
    return list(ends.values())


def _time_from_bar(ctx: "MeasureCtx") -> tuple[int, int] | None:
    """The numerator a bar with a time-signature mark says about itself (plan 0013), or None.

    homr reads the mark but never its numerator, so the page gives the place and the bar gives the
    count. Conditions, all of them needed to keep this from renaming a misread bar: two voices at
    least, agreeing exactly, on a length that is not the one in force, that is a whole number of
    beats, and that is not twice the bar — a missed barline joins two bars far more often than a
    page doubles its meter."""
    lengths = _voice_lengths(ctx.measure)
    if len(lengths) < 2 or len(set(lengths)) != 1 or lengths[0] <= 0:
        return None
    held = lengths[0]
    if held == ctx.expected or held == 2 * ctx.expected:
        return None
    beats = ctx.quarters(held) * ctx.beat_type / 4
    if beats.denominator != 1 or not 1 <= beats <= 32:
        return None
    return int(beats), ctx.beat_type


def _set_time(measure: ET.Element, beats: int, beat_type: int) -> None:
    """Write a time signature into the measure, making its <attributes> if it has none."""
    attrs = measure.find("attributes")
    if attrs is None:
        attrs = ET.Element("attributes")
        first = next((i for i, el in enumerate(list(measure)) if el.tag in ("note", "harmony", "direction", "backup", "forward")), len(measure))
        measure.insert(first, attrs)
    for old in attrs.findall("time"):
        attrs.remove(old)
    time = ET.Element("time")
    ET.SubElement(time, "beats").text = str(beats)
    ET.SubElement(time, "beat-type").text = str(beat_type)
    after = ATTRIBUTES_ORDER[:ATTRIBUTES_ORDER.index("time")]
    place = max([i for i, el in enumerate(list(attrs)) if el.tag in after], default=-1) + 1
    attrs.insert(place, time)


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


_BARLINE_ORDER = ["bar-style", "editorial", "wavy-line", "segno", "coda", "fermata", "ending", "repeat"]
_PLAYED = ("note", "forward", "backup", "harmony")


def _merge_barline(into: ET.Element, source: ET.Element) -> None:
    """Add what `source` says to `into`, keeping what `into` already says, in schema order."""
    have = {c.tag for c in into}
    for child in list(source):
        if child.tag not in have:
            into.append(child)
    into[:] = sorted(list(into), key=lambda c: _BARLINE_ORDER.index(c.tag) if c.tag in _BARLINE_ORDER else len(_BARLINE_ORDER))


def _give_barline(source: ET.Element, target: ET.Element, location: str) -> None:
    existing = next((b for b in target.findall("barline") if b.get("location") == location), None)
    if existing is None:
        source.set("location", location)
        target.append(source) if location == "right" else target.insert(0, source)
    else:
        _merge_barline(existing, source)


def drop_empty_measures(root: ET.Element) -> list[tuple[int, int]]:
    """Remove the measures nobody plays in, in every part, and say which: [(original index, system)].

    homr 0.7.1 closes the measure at a forward repeat, and at a volta that stops, whether or not
    anything was played since the barline before it, so a repeat that opens a page or a system leaves
    a measure that holds attributes and a barline and no note (Camptown Races 17 -> 18, La marche des
    rois 20 -> 23). It is not a measure of the page: what it carries goes to the neighbour it belongs
    with, so nothing is lost: attributes, directions and a new-system mark forward; a left barline
    forward; a right barline back. A rest is a note here, so a bar of silence stays. The system is
    counted from the new-system marks, because the driver's per-system counts must follow."""
    parts = root.findall("part")
    if not parts:
        return []
    count = min(len(p.findall("measure")) for p in parts)
    empty = [i for i in range(count) if all(not any(c.tag in _PLAYED for c in p.findall("measure")[i]) for p in parts)]
    if not empty:
        return []
    systems, system = [], 0
    for i, m in enumerate(parts[0].findall("measure")):
        if i > 0 and m.find("print[@new-system='yes']") is not None:
            system += 1
        systems.append(system)
    for part in parts:
        ms = part.findall("measure")
        for i in empty:
            m = ms[i]
            target_next = next((ms[j] for j in range(i + 1, len(ms)) if j not in empty), None)
            target_prev = next((ms[j] for j in range(i - 1, -1, -1) if j not in empty), None)
            forward = target_next if target_next is not None else target_prev
            carried = []
            for child in list(m):
                if child.tag == "barline":
                    loc = child.get("location", "right")
                    if loc == "right" and target_prev is not None:
                        _give_barline(child, target_prev, "right")
                    elif forward is not None:
                        _give_barline(child, forward, loc)
                else:
                    carried.append(child)
            if forward is not None:
                at = 0
                for child in carried:
                    forward.insert(at, child)
                    at += 1
        for i in empty:
            part.remove(ms[i])
        for n, m in enumerate(part.findall("measure"), 1):
            m.set("number", str(n))
    return [(i, systems[i]) for i in empty]


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


def _in_force(measure: ET.Element, state: tuple[int, int, int]) -> tuple[int, int, int]:
    """(divisions, beats, beat type) after this measure's own attributes, which engines may split."""
    divisions, beats, beat_type = state
    for attrs in measure.findall("attributes"):
        if (d := attrs.findtext("divisions")) is not None:
            divisions = int(d.strip())
        if (t := attrs.find("time")) is not None:
            beats = int(t.findtext("beats", "4").strip())
            beat_type = int(t.findtext("beat-type", "4").strip())
    return divisions, beats, beat_type


def measures(part: ET.Element) -> Iterator[MeasureCtx]:
    """Every measure with the divisions and time signature in force (engines may split attributes)."""
    state = (1, 4, 4)
    for index, measure in enumerate(part.findall("measure")):
        state = _in_force(measure, state)
        yield MeasureCtx(index, measure, *state)


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


def postprocess(src: Path, dst: Path, repair: bool = True, times: list[dict] | None = None) -> ScoreStats:
    """Read `src`, write `dst`, return what the document holds.

    `repair` is what an engine's output needs and an authored file must not get (plan 0010): with it
    off nothing is padded, unmerged or moved, and a measure that does not add up is recorded as
    information rather than as a doubt.

    `times` is the driver's list of the measures where a time signature is printed (plan 0013), which
    the engine reads and then cannot write down."""
    try:
        tree = ET.parse(src)
    except ET.ParseError as e:
        raise PostprocessError(f"engine output is not well-formed XML: {e}") from e
    root = tree.getroot()
    _check_root(root)

    stats = ScoreStats()
    for p, part in enumerate(root.findall("part")):
        stats.parts += 1
        if repair:
            marks = {int(t["measure"]): int(t["beat_type"]) for t in (times or [])}
            _read_meter(part, marks, p, stats)
            _repair_part(part, p, stats, marks)
        else:
            _read_part(part, p, stats)
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


def _mark_note(ctx: "MeasureCtx", marks: dict[int, int]) -> str:
    """What to add to a doubt on a bar where a time signature is printed and could not be read from
    the bar itself: the page said the meter changes here, so say so rather than only the arithmetic."""
    return "; a time signature is printed here, so the meter may change on this bar" if ctx.index in marks and ctx.index > 0 else ""


def _mark_detail(ctx: "MeasureCtx", marks: dict[int, int]) -> dict:
    return {"time_mark": True} if ctx.index in marks and ctx.index > 0 else {}


def _read_meter(part: ET.Element, marks: dict[int, int], p: int, stats: ScoreStats) -> None:
    """Where the engine read a time-signature mark, take the numerator from the bar (plan 0013).

    Its own pass, before anything is measured: `measures` carries the time in force forward, so a
    measure whose meter changes must be written before the measure after it is looked at. Measure 0
    is skipped — the engine already wrote the meter the page opens with, and its numerator, being the
    median bar of the page, is right far more often than not."""
    if not marks:
        return
    state = (1, 4, 4)
    for index, measure in enumerate(part.findall("measure")):
        state = _in_force(measure, state)
        if index == 0 or index not in marks:
            continue
        found = _time_from_bar(MeasureCtx(index, measure, *state))
        if found is None:
            continue
        beats, beat_type = found
        _set_time(measure, beats, beat_type)
        state = (state[0], beats, beat_type)   # in force from here, for the measures still to come
        stats.warnings.append(f"measure {measure.get('number')}: time signature read as {beats}/{beat_type} (the mark was seen, the count comes from the bar)")
        stats.doubts.append(doubt(index, "time", f"a time signature is printed here: read as {beats}/{beat_type}, the count taken from what the bar holds",
                                  p, info=True, beats=beats, beat_type=beat_type))


def _repair_part(part: ET.Element, p: int, stats: ScoreStats, marks: dict[int, int]) -> None:
    """An engine's part: made safe to play, and every repair recorded as a doubt (ADR 0005)."""
    for ctx in measures(part):
        measure = ctx.measure
        stats.measures += 1
        if _relay(measure):
            stats.warnings.append(f"measure {measure.get('number')}: the voices were put back on their own beats")
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
                stats.doubts.append(doubt(ctx.index, "padded", f"shorter than {ctx.time} by {describe(ctx.quarters(gap))}: a rest was added at the end{_mark_note(ctx, marks)}",
                                          p, gap=str(ctx.quarters(gap)), **_mark_detail(ctx, marks)))
            stats.padded_measures += 1
        elif filled > ctx.expected:
            stats.warnings.append(
                f"measure {measure.get('number')} overfull: {float(ctx.quarters(filled)):g} vs {float(ctx.quarters(ctx.expected)):g} quarters"
            )
            excess = ctx.quarters(filled - ctx.expected)
            stats.doubts.append(doubt(ctx.index, "overfull", f"longer than {ctx.time} by {describe(excess)}{_mark_note(ctx, marks)}",
                                      p, excess=str(excess), **_mark_detail(ctx, marks)))
