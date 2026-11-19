"""A model pass over a span without words: notes and chords (ADR 0010, decisions 1, 4, 7, plan 0016 steps 8-10).

The answer is a list of operations in the score editor's vocabulary (`frontend/src/score/edit.ts`), each naming
a note by `measure` and `event` (0-based; the event is the note's place among the measure's <note> elements,
rests, grace notes and chord tones included, as the prompt lists them). Both indices refer to the score as the
model was shown it: a note stays addressable after an earlier operation of the answer moved others.

    {"op": "stepPitch", "measure": 3, "event": 2, "delta": 1}        one step up the staff (-1: down)
    {"op": "setAlter", ..., "alter": -1}                              flat; 0 natural; 1 sharp
    {"op": "shiftOctave", ..., "delta": -1}
    {"op": "setDuration", ..., "type": "quarter", "dots": 1}          type: whole half quarter eighth 16th 32nd
    {"op": "toRest", ...}  {"op": "deleteEvent", ...}  {"op": "toggleTie", ...}
    {"op": "insertEvent", ..., "where": "after", "kind": "note"}      next to a note; a rest next to anything
    {"op": "setChord", ..., "text": "Am7"}                            "" takes the chord symbol away

This module applies the operations to the MusicXML (a port of the editor's functions, kept in step by the tests
of both sides on the same case) and is the validator: operations that do not apply are dropped one by one with
their reason; the operations on one measure form one change, kept only if no measure that added up stops adding
up, no broken one gets worse, and nothing outside the span or in the clef, key and time moved.
"""
from __future__ import annotations

import copy
import json
import re
import xml.etree.ElementTree as ET
from fractions import Fraction
from math import floor

from ..pipeline.chords import grammar as chord_grammar
from ..pipeline.chords import place as chord_place
from ..pipeline.postprocess import _measure_filled
from .route import Route

STEPS = "CDEFGAB"
SHARPS, FLATS = "FCGDAEB", "BEADGCF"
SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
TYPE_QUARTERS = {"breve": Fraction(8), "whole": Fraction(4), "half": Fraction(2), "quarter": Fraction(1), "eighth": Fraction(1, 2),
                 "16th": Fraction(1, 4), "32nd": Fraction(1, 8), "64th": Fraction(1, 16)}
TYPES = ["whole", "half", "quarter", "eighth", "16th", "32nd"]
NOTE_ORDER = ["grace", "cue", "chord", "pitch", "unpitched", "rest", "duration", "tie", "instrument", "footnote", "level",
              "voice", "type", "dot", "accidental", "time-modification", "stem", "notehead", "notehead-text", "staff", "beam",
              "notations", "lyric", "play", "listen"]
STRIP_ON_REST = ["pitch", "tie", "accidental", "stem", "notehead", "notations", "lyric", "chord"]
CHORD_SUFFIXES = ("", "m", "7", "maj7", "m7", "dim", "dim7", "aug", "6", "m6", "9", "sus4", "sus2", "5")  # what both grammars read alike
CHORD_TEXT = re.compile(r"^[A-G][#b]?(" + "|".join(re.escape(s) for s in CHORD_SUFFIXES if s) + r")?(/[A-G][#b]?)?$")
MAX_OPS = 60
MAX_NOTE = 500

PROMPT = (
    "Below is a stretch of a melody as a music-recognition program read it from a photo. Some of what it read may be "
    "wrong: a note with the wrong pitch or length, a note that is not there or is missing, a wrong chord symbol. "
    "{why}Correct only what you are fairly sure is wrong; if nothing is, reply [].\n\n{score}\n\n"
    "Reply with a JSON array of operations only, in the order they apply. Every operation names a note by `measure` and "
    "`event`, the numbers shown above (they keep their meaning after earlier operations). Operations:\n"
    '  {{"op": "stepPitch", "measure": 3, "event": 2, "delta": 1}}   one step up the staff (-1 down)\n'
    '  {{"op": "setAlter", "measure": 3, "event": 2, "alter": -1}}   -1 flat, 0 natural, 1 sharp\n'
    '  {{"op": "shiftOctave", "measure": 3, "event": 2, "delta": -1}}\n'
    '  {{"op": "setDuration", "measure": 3, "event": 2, "type": "quarter", "dots": 0}}   type: whole half quarter eighth 16th 32nd\n'
    '  {{"op": "toRest", "measure": 3, "event": 2}}   {{"op": "deleteEvent", "measure": 3, "event": 2}}   {{"op": "toggleTie", "measure": 3, "event": 2}}\n'
    '  {{"op": "insertEvent", "measure": 3, "event": 2, "where": "after", "kind": "note"}}   a new note of the same length next to a note; "kind": "rest" next to anything\n'
    '  {{"op": "setChord", "measure": 3, "event": 2, "text": "Am7"}}   the chord symbol over that beat; "" takes it away. Symbols: '
    "C, Cm, C7, Cmaj7, Cm7, Cdim, Cdim7, Caug, C6, Cm6, C9, Csus4, Csus2, C5, with an optional /bass.\n"
    "Every measure must still add up to its time signature after your operations; changes outside measures {first} to {last}, "
    "and of clef, key or time, are not possible."
)


class OpError(ValueError):
    pass


# ---- reading the score ----------------------------------------------------------------------------------

def _text(el: ET.Element | None, tag: str, default: str = "") -> str:
    found = el.find(tag) if el is not None else None
    return (found.text or "").strip() if found is not None and found.text else default


def _is_rest(n): return n.find("rest") is not None
def _is_grace(n): return n.find("grace") is not None
def _in_chord(n): return n.find("chord") is not None


def measure_states(part: ET.Element) -> list[dict]:
    """Every measure with the attributes in force: divisions, beats, beat type, fifths."""
    divisions, beats, beat_type, fifths = 1, 4, 4, 0
    out = []
    for i, m in enumerate(part.findall("measure")):
        for attrs in m.findall("attributes"):
            if _text(attrs, "divisions"):
                divisions = int(_text(attrs, "divisions")) or divisions
            t = attrs.find("time")
            if t is not None:
                beats, beat_type = int(_text(t, "beats", "4") or 4), int(_text(t, "beat-type", "4") or 4)
            k = attrs.find("key")
            if k is not None:
                fifths = int(_text(k, "fifths", "0") or 0)
        out.append({"index": i, "el": m, "divisions": divisions, "beats": beats, "beat_type": beat_type, "fifths": fifths})
    return out


def onsets(m: ET.Element) -> list[int]:
    """The place of each <note> of the measure in divisions, following backup and forward (the editor's `events`)."""
    pos, last, out = 0, 0, []
    for el in m:
        if el.tag == "backup":
            pos -= int(_text(el, "duration", "0") or 0)
        elif el.tag == "forward":
            pos += int(_text(el, "duration", "0") or 0)
        elif el.tag == "note":
            grace, chord = _is_grace(el), _in_chord(el)
            duration = 0 if grace else int(_text(el, "duration", "0") or 0)
            out.append(last if chord else pos)
            if not chord and not grace:
                last = pos
                pos += duration
            elif not chord:
                last = pos
    return out


def pitch_of(note: ET.Element) -> tuple[str, int, int] | None:
    p = note.find("pitch")
    if p is None:
        return None
    return _text(p, "step", "C"), int(_text(p, "alter", "0") or 0), int(_text(p, "octave", "4") or 4)


def _name(p: tuple[str, int, int]) -> str:
    step, alter, octave = p
    return step + ("#" * alter if alter > 0 else "b" * -alter) + str(octave)


def describe_note(n: ET.Element) -> str:
    kind = _text(n, "type", "?")
    dots = "." * len(n.findall("dot"))
    head = "rest" if _is_rest(n) else (_name(pitch_of(n)) if pitch_of(n) else "?")
    tied = "~" if any(t.get("type") == "start" for t in n.findall("tie")) else ""
    return ("grace " if _is_grace(n) else "+" if _in_chord(n) else "") + f"{head} {kind}{dots}{tied}"


def summarise(m: ET.Element) -> list[str]:
    """One string per <note> of the measure: the old and new values of a notes change, and what a conflict compares."""
    return [describe_note(n) for n in m.findall("note")]


_SUFFIX: dict[tuple[str, tuple], str] = {}
for (_q, _e), (_kind, _deg) in chord_grammar.KINDS.items():
    _SUFFIX.setdefault((_kind, _deg), _q + _e)


def harmony_text(h: ET.Element) -> str:
    root = h.find("root")
    if root is None:
        return ""
    degrees = tuple((int(_text(d, "degree-value", "0")), int(_text(d, "degree-alter", "0") or 0), _text(d, "degree-type", "add")) for d in h.findall("degree"))
    kind = _text(h, "kind", "major") or "major"
    suffix = _SUFFIX.get((kind, degrees), _SUFFIX.get((kind, ()), ""))
    alt = int(_text(root, "root-alter", "0") or 0)
    text = _text(root, "root-step", "C") + ("#" * alt if alt > 0 else "b" * -alt) + suffix
    bass = h.find("bass")
    if bass is not None:
        balt = int(_text(bass, "bass-alter", "0") or 0)
        text += "/" + _text(bass, "bass-step", "C") + ("#" * balt if balt > 0 else "b" * -balt)
    return text


def harmony_at(m: ET.Element, position: int) -> ET.Element | None:
    pos, found = 0, None
    for el in m:
        if el.tag == "harmony":
            if pos == position:
                found = el
        elif el.tag == "note":
            if not _in_chord(el) and not _is_grace(el):
                pos += int(_text(el, "duration", "0") or 0)
        elif el.tag == "backup":
            pos -= int(_text(el, "duration", "0") or 0)
        elif el.tag == "forward":
            pos += int(_text(el, "duration", "0") or 0)
    return found


def chord_at(m: ET.Element, event: int) -> str:
    where = onsets(m)
    h = harmony_at(m, where[event]) if 0 <= event < len(where) else None
    return harmony_text(h) if h is not None else ""


def fill(state: dict) -> tuple[Fraction, Fraction]:
    """(filled, expected) of a measure in divisions."""
    return Fraction(_measure_filled(state["el"], state["divisions"])), Fraction(state["beats"] * 4 * state["divisions"], state["beat_type"])


def current_text(part: ET.Element, change: dict) -> str | None:
    """What the score holds now at the place a change names, in the words of its old/new values."""
    measures = part.findall("measure")
    if not 0 <= change["measure"] < len(measures):
        return None
    if change["kind"] == "chord":
        return chord_at(measures[change["measure"]], change["event"])
    return ", ".join(summarise(measures[change["measure"]]))


# ---- the editor's operations, ported -----------------------------------------------------------------------

def _insert_ordered(parent: ET.Element, el: ET.Element, order: list[str] = NOTE_ORDER) -> None:
    rank = order.index(el.tag) if el.tag in order else -1
    for i, c in enumerate(list(parent)):
        if (order.index(c.tag) if c.tag in order else -1) > rank:
            parent.insert(i, el)
            return
    parent.append(el)


def _set_child(parent: ET.Element, tag: str, value: str, order: list[str] = NOTE_ORDER) -> ET.Element:
    c = parent.find(tag)
    if c is None:
        c = ET.Element(tag)
        _insert_ordered(parent, c, order)
    c.text = value
    return c


def _remove_all(parent: ET.Element, tag: str) -> None:
    for c in parent.findall(tag):
        parent.remove(c)


def key_alter(step: str, fifths: int) -> int:
    if fifths > 0:
        return 1 if step in SHARPS[:fifths] else 0
    if fifths < 0:
        return -1 if step in FLATS[:-fifths] else 0
    return 0


def write_pitch(note: ET.Element, step: str, alter: int, octave: int) -> None:
    pe = note.find("pitch")
    if pe is None:
        pe = ET.Element("pitch")
        _insert_ordered(note, pe)
    for c in list(pe):
        pe.remove(c)
    ET.SubElement(pe, "step").text = step
    if alter:
        ET.SubElement(pe, "alter").text = str(alter)
    ET.SubElement(pe, "octave").text = str(octave)
    _remove_all(note, "accidental")


def nominal(kind: str, dots: int) -> Fraction:
    return TYPE_QUARTERS[kind] * (2 - Fraction(1, 2 ** dots))


def type_for(quarters: Fraction) -> tuple[str, int] | None:
    for kind in TYPE_QUARTERS:
        for dots in range(3):
            if nominal(kind, dots) == quarters:
                return kind, dots
    return None


def tuplet_ratio(note: ET.Element) -> Fraction:
    tm = note.find("time-modification")
    if tm is None:
        return Fraction(1)
    return Fraction(int(_text(tm, "normal-notes", "1") or 1), int(_text(tm, "actual-notes", "1") or 1))


class Ctx:
    """The part an answer is applied to, the notes as the model was shown them, and the measures it may touch."""

    def __init__(self, part: ET.Element, first: int, last: int, origs: list[list[ET.Element]] | None = None):
        self.part, self.first, self.last = part, first, last
        self.origs = origs if origs is not None else [m.findall("note") for m in part.findall("measure")]

    def measures(self) -> list[dict]:
        return measure_states(self.part)

    def where(self, note: ET.Element) -> int:
        for i, m in enumerate(self.part.findall("measure")):
            if any(n is note for n in m.findall("note")):
                return i
        raise OpError("that note is no longer in the score")

    def target(self, measure: int, event: int) -> ET.Element:
        if not 0 <= measure < len(self.origs) or not 0 <= event < len(self.origs[measure]):
            raise OpError(f"there is no note {event} in measure {measure}")
        note = self.origs[measure][event]
        if not any(n is note for n in self.part.findall("measure")[measure].findall("note")):
            raise OpError(f"note {event} of measure {measure} is gone: an earlier operation took it away")
        return note

    def allowed(self, note: ET.Element) -> None:
        if not self.first <= self.where(note) <= self.last:
            raise OpError("that reaches a note outside the span")

    def group(self, note: ET.Element) -> list[ET.Element]:
        notes = self.part.findall("measure")[self.where(note)].findall("note")
        head = next(i for i, n in enumerate(notes) if n is note)
        while head > 0 and _in_chord(notes[head]):
            head -= 1
        out = [notes[head]]
        for n in notes[head + 1:]:
            if not _in_chord(n):
                break
            out.append(n)
        return out

    def divisions_all(self) -> set[int]:
        return {int(_text(a, "divisions")) for m in self.part.findall("measure") for a in m.findall("attributes") if _text(a, "divisions")}

    def write_duration(self, note: ET.Element, kind: str, dots: int, measure: dict) -> None:
        quarters = nominal(kind, dots) * tuplet_ratio(note)
        if any((quarters * d).denominator != 1 for d in self.divisions_all()):
            raise OpError("that length needs finer divisions than this score has")
        _set_child(note, "duration", str(int(quarters * measure["divisions"])))
        _set_child(note, "type", kind)
        _remove_all(note, "dot")
        for _ in range(dots):
            _insert_ordered(note, ET.Element("dot"))


def _set_tie(note: ET.Element, kind: str, on: bool) -> None:
    for t in note.findall("tie"):
        if t.get("type") == kind:
            note.remove(t)
    n = note.find("notations")
    if n is not None:
        for t in n.findall("tied"):
            if t.get("type") == kind:
                n.remove(t)
    if not on:
        return
    _insert_ordered(note, ET.Element("tie", {"type": kind}))
    if n is None:
        n = ET.Element("notations")
        _insert_ordered(note, n)
    ET.SubElement(n, "tied", {"type": kind})


def _same_voice(a: ET.Element, b: ET.Element) -> bool:
    return _text(a, "staff", "1") == _text(b, "staff", "1") and _text(a, "voice", "1") == _text(b, "voice", "1") and not _in_chord(b) and not _is_grace(b)


def _neighbour(ctx: Ctx, note: ET.Element, step: int) -> ET.Element | None:
    flat = [n for m in ctx.part.findall("measure") for n in m.findall("note")]
    at = next(i for i, n in enumerate(flat) if n is note)
    i = at + step
    while 0 <= i < len(flat):
        if _same_voice(note, flat[i]):
            return flat[i]
        i += step
    return None


def _tied_to_next(note: ET.Element) -> bool:
    return any(t.get("type") == "start" for t in note.findall("tie"))


def _untie(ctx: Ctx, note: ET.Element) -> None:
    if _tied_to_next(note):
        nxt = _neighbour(ctx, note, 1)
        if nxt is not None:
            ctx.allowed(nxt)
            _set_tie(nxt, "stop", False)
    if any(t.get("type") == "stop" for t in note.findall("tie")):
        prev = _neighbour(ctx, note, -1)
        if prev is not None:
            ctx.allowed(prev)
            _set_tie(prev, "start", False)


def _int(op: dict, key: str, low: int, high: int) -> int:
    v = op.get(key)
    if not isinstance(v, int) or isinstance(v, bool) or not low <= v <= high:
        raise OpError(f"`{key}` must be a whole number from {low} to {high}")
    return v


def apply_op(ctx: Ctx, op: dict) -> None:
    """One operation, in place; OpError (with a sentence) when it does not apply. Chord symbols are `setChord`."""
    name = op.get("op")
    if name not in OPS:
        raise OpError(f"unknown operation {name!r}")
    m, e = op.get("measure"), op.get("event")
    if not isinstance(m, int) or not isinstance(e, int) or isinstance(m, bool) or isinstance(e, bool):
        raise OpError("`measure` and `event` must be whole numbers")
    if not ctx.first <= m <= ctx.last:
        raise OpError(f"measure {m} is outside the span (measures {ctx.first} to {ctx.last})")
    note = ctx.target(m, e)
    state = ctx.measures()[m]
    OPS[name](ctx, op, note, state)


def _step_pitch(ctx, op, note, state):
    delta = _int(op, "delta", -7, 7)
    p = pitch_of(note)
    if p is None or _is_rest(note):
        raise OpError("a rest has no pitch")
    step, alter, octave = p
    explicit = alter != key_alter(step, state["fifths"])
    idx = STEPS.index(step) + delta
    new_step, new_octave = STEPS[idx % 7], octave + floor(idx / 7)
    if not 0 <= new_octave <= 9:
        raise OpError("that is off the piano")
    write_pitch(note, new_step, alter if explicit else key_alter(new_step, state["fifths"]), new_octave)


def _set_alter(ctx, op, note, state):
    alter = _int(op, "alter", -2, 2)
    p = pitch_of(note)
    if p is None or _is_rest(note):
        raise OpError("a rest has no pitch")
    write_pitch(note, p[0], alter, p[2])


def _shift_octave(ctx, op, note, state):
    delta = _int(op, "delta", -2, 2)
    p = pitch_of(note)
    if p is None or _is_rest(note):
        raise OpError("a rest has no pitch")
    if not 0 <= p[2] + delta <= 9:
        raise OpError("that octave is off the piano")
    write_pitch(note, p[0], p[1], p[2] + delta)


def _set_duration(ctx, op, note, state):
    kind, dots = op.get("type"), _int(op, "dots", 0, 2)
    if kind not in TYPES:
        raise OpError(f"`type` must be one of {', '.join(TYPES)}")
    if _is_grace(note):
        raise OpError("a grace note has no length")
    for n in ctx.group(note):
        ctx.write_duration(n, kind, dots, state)


def _to_rest(ctx, op, note, state):
    if _is_rest(note):
        return
    if len(ctx.group(note)) > 1:
        return _delete(ctx, op, note, state)
    for tag in STRIP_ON_REST:
        _remove_all(note, tag)
    _insert_ordered(note, ET.Element("rest"))  # the editor unties after stripping the <tie>s, which leaves nothing to untie; so does this


def _delete(ctx, op, note, state):
    group = ctx.group(note)
    _untie(ctx, note)
    measure = ctx.part.findall("measure")[ctx.where(note)]
    if len(group) > 1 and group[0] is note:
        nxt = group[1]
        _remove_all(nxt, "chord")
        for lyric in note.findall("lyric"):
            _insert_ordered(nxt, lyric)
    measure.remove(note)


def _toggle_tie(ctx, op, note, state):
    if _is_rest(note):
        raise OpError("a rest cannot be tied")
    nxt = _neighbour(ctx, note, 1)
    on = not _tied_to_next(note)
    if on:
        if nxt is None or _is_rest(nxt):
            raise OpError("there is no note after this one to tie to")
        if pitch_of(nxt) != pitch_of(note):
            raise OpError("a tie joins two notes of the same pitch")
    if nxt is not None:
        ctx.allowed(nxt)
    _set_tie(note, "start", on)
    if nxt is not None:
        _set_tie(nxt, "stop", on)


def _insert(ctx, op, note, state):
    where, kind = op.get("where"), op.get("kind")
    if where not in ("before", "after") or kind not in ("note", "rest"):
        raise OpError("`where` is before or after, `kind` is note or rest")
    if kind == "note" and (_is_rest(note) or _is_grace(note)):
        raise OpError("a new note goes next to a note")
    group = ctx.group(note)
    quarters_now = Fraction(int(_text(note, "duration", "0") or 0), state["divisions"]) / tuplet_ratio(note)
    t = (_text(note, "type") if _text(note, "type") in TYPE_QUARTERS else None)
    pair = (t, len(note.findall("dot"))) if t else type_for(quarters_now)
    kind_type, dots = pair or ("quarter", 0)
    el = ET.Element("note")
    if kind == "rest":
        ET.SubElement(el, "rest")
    ET.SubElement(el, "duration").text = "1"
    ET.SubElement(el, "voice").text = _text(note, "voice", "1")
    ET.SubElement(el, "type").text = kind_type
    tm = note.find("time-modification")
    if tm is not None:
        _insert_ordered(el, copy.deepcopy(tm))
    if note.find("staff") is not None:
        _insert_ordered(el, _staff(note))
    anchor = group[0] if where == "before" else group[-1]
    measure = ctx.part.findall("measure")[ctx.where(note)]
    kids = list(measure)
    at = next(i for i, c in enumerate(kids) if c is anchor)
    measure.insert(at if where == "before" else at + 1, el)
    ctx.write_duration(el, kind_type, dots, state)
    if kind == "note":
        p = pitch_of(note)
        write_pitch(el, *p)


def _staff(note: ET.Element) -> ET.Element:
    s = ET.Element("staff")
    s.text = _text(note, "staff", "1")
    return s


def _set_chord(ctx, op, note, state):
    text = op.get("text")
    if not isinstance(text, str):
        raise OpError("`text` must be the chord symbol")
    text = text.strip().replace("♭", "b").replace("♯", "#")
    measure = state["el"]
    group = ctx.group(note)
    position = onsets(measure)[list(measure.findall("note")).index(note)]
    existing = harmony_at(measure, position)
    if not text:
        if existing is not None:
            measure.remove(existing)
        return
    chord = chord_grammar.parse_chord(text) if CHORD_TEXT.match(text) else None
    if chord is None:
        raise OpError(f"{text!r} is not a chord symbol this app knows")
    fresh = chord_place.harmony_element(chord)
    if existing is not None:
        kids = list(measure)
        measure.remove(existing)
        measure.insert(next(i for i, c in enumerate(kids) if c is existing), fresh)
    else:
        kids = list(measure)
        measure.insert(next(i for i, c in enumerate(kids) if c is group[0]), fresh)


OPS = {"stepPitch": _step_pitch, "setAlter": _set_alter, "shiftOctave": _shift_octave, "setDuration": _set_duration,
       "toRest": _to_rest, "deleteEvent": _delete, "toggleTie": _toggle_tie, "insertEvent": _insert, "setChord": _set_chord}


# ---- transactions and the validator ----------------------------------------------------------------------

def _snapshot(part: ET.Element) -> list:
    return [(m, [(el, copy.deepcopy(el)) for el in list(m)]) for m in part.findall("measure")]


def _restore(part: ET.Element, snap: list) -> None:
    """Put the part back as it was, element for element, so the notes the answer names stay the same objects."""
    for m, kids in snap:
        for el in list(m):
            m.remove(el)
        for el, saved in kids:
            el.attrib.clear()
            el.attrib.update(saved.attrib)
            el.text, el.tail = saved.text, saved.tail
            el[:] = list(saved)
            m.append(el)


def _fixed(root: ET.Element) -> list[str]:
    """What a pass never touches: per measure of every part the clef, key, time and divisions."""
    return ["".join(ET.tostring(c, encoding="unicode") for att in m.findall("attributes") for c in att if c.tag in ("clef", "key", "time", "divisions"))
            for p in root.findall("part") for m in p.findall("measure")]


def _outside(root: ET.Element, span: dict) -> list[str]:
    parts = root.findall("part")
    out = []
    for pi, p in enumerate(parts):
        for i, m in enumerate(p.findall("measure")):
            if pi != 0 or not span["from"] <= i <= span["to"]:
                out.append(ET.tostring(m, encoding="unicode"))
    return out


def arithmetic(part: ET.Element) -> list[tuple[Fraction, Fraction]]:
    return [fill(s) for s in measure_states(part)]


def broken_by(before: tuple[Fraction, Fraction], after: tuple[Fraction, Fraction]) -> str | None:
    """Why a measure's new length is not acceptable, or None: one that added up must still, a short or long one may not get worse."""
    b, a = abs(before[0] - before[1]), abs(after[0] - after[1])
    if b == 0 and a != 0:
        return "a measure that added up no longer does"
    if a > b:
        return "a measure that was already wrong gets worse"
    return None


def _group_changes(ops: list[dict]) -> list[tuple[str, int, list[dict]]]:
    """The operations as units a user can tick: chord operations alone, the note operations of one measure together."""
    units: list[tuple[str, int, list[dict]]] = []
    for op in ops:
        if op["op"] == "setChord":
            units.append(("chord", op["measure"], [op]))
        else:
            found = next((u for u in units if u[0] == "notes" and u[1] == op["measure"]), None)
            if found:
                found[2].append(op)
            else:
                units.append(("notes", op["measure"], [op]))
    return units


def _unit_text(ctx: Ctx, kind: str, measure: int, ops: list[dict]) -> str:
    m = ctx.part.findall("measure")[measure]
    if kind == "notes":
        return ", ".join(summarise(m))
    note = ctx.target(measure, ops[0]["event"])
    return chord_at(m, list(m.findall("note")).index(note))


def apply_changes(root: ET.Element, changes: list[dict]) -> list[str]:
    """Write score changes (kind notes or chord) into the first part, each as a transaction that is undone when it
    fails: an operation that does not apply, a measure that stops adding up, a hand outside its span. Returns the ids applied."""
    part = root.find("part")
    done: list[str] = []
    if part is None:
        return done
    origs = [m.findall("note") for m in part.findall("measure")]   # one numbering for the whole answer
    for c in changes:
        span = c["span"]
        ctx = Ctx(part, span["from"], span["to"], origs)
        before, outside, fixed, snap = arithmetic(part), _outside(root, span), _fixed(root), _snapshot(part)
        try:
            for op in c["ops"]:
                apply_op(ctx, op)
            after = arithmetic(part)
            if len(after) != len(before) or any(broken_by(b, a) for b, a in zip(before, after)):
                raise OpError("a measure no longer adds up")
            if _outside(root, span) != outside or _fixed(root) != fixed:
                raise OpError("it reaches outside the span")
        except OpError:
            _restore(part, snap)
            continue
        done.append(c["id"])
    return done


# ---- asking the model -----------------------------------------------------------------------------------

def is_notes_span(span: dict) -> bool:
    """A span with no words, typed or pictured, is asked for notes and chords; one whose picture could not be read is not."""
    return not (span.get("lyrics_source") or "").strip() and not span.get("lyrics_picture") and not span.get("unreadable")


def score_text(root: ET.Element, span: dict) -> str:
    part = root.find("part")
    states = measure_states(part)
    lines = []
    for i in range(span["from"], span["to"] + 1):
        s = states[i]
        filled, expected = fill(s)
        if filled == expected:
            adds = "adds up"
        else:
            adds = f"{'short' if filled < expected else 'long'} by {float(abs(filled - expected) / s['divisions']):g} quarter notes"
        notes = s["el"].findall("note")
        where = onsets(s["el"])
        row = []
        for k, n in enumerate(notes):
            h = harmony_at(s["el"], where[k]) if not _in_chord(n) else None
            row.append((f"[{harmony_text(h)}] " if h is not None else "") + f"{k}: {describe_note(n)}")
        lines.append(f"measure {i} ({s['beats']}/{s['beat_type']}, {adds}): " + "; ".join(row))
    return "\n".join(lines)


def prompt_for(root: ET.Element, span: dict) -> str:
    note = (span.get("note") or "").strip()[:MAX_NOTE]
    why = f"What is known: {note}. " if note else ""
    return PROMPT.format(why=why, score=score_text(root, span), first=span["from"], last=span["to"])


def estimate(root: ET.Element, spans: list[dict]) -> tuple[int, int, int]:
    """(calls, tokens in, tokens out) for the notes spans."""
    calls = tin = tout = 0
    for span in spans:
        calls += 1
        tin += len(prompt_for(root, span)) // 3
        tout += 120
    return calls, tin, tout


def parse_answer(reply: str) -> list[dict]:
    """The operations of a reply, or OpError when it is not a list of objects."""
    start, end = reply.find("["), reply.rfind("]")
    try:
        ops = json.loads(reply[start:end + 1])
    except ValueError as e:
        raise OpError("the answer is not a list of operations") from e
    if not isinstance(ops, list) or not all(isinstance(o, dict) for o in ops):
        raise OpError("the answer is not a list of operations")
    if len(ops) > MAX_OPS:
        raise OpError(f"the answer holds more than {MAX_OPS} operations")
    return ops


def vet(root: ET.Element, span: dict, ops: list[dict]) -> tuple[list[dict], list[str]]:
    """Apply the operations to a copy of the score and keep what holds: (changes without ids, reasons dropped).

    An operation that does not apply is dropped alone. The rest are grouped (the note operations of a measure are one
    change) and a group is kept only if, applied, no measure that added up stops adding up and none that was wrong
    gets worse; otherwise the whole group goes, with the reason."""
    where = {"staff": span["staff"], "from": span["from"], "to": span["to"]}
    dropped: list[str] = []
    probe = copy.deepcopy(root).find("part")
    pctx = Ctx(probe, span["from"], span["to"])
    live: list[dict] = []
    for op in ops:
        snap = _snapshot(probe)
        try:
            apply_op(pctx, op)
        except OpError as e:
            _restore(probe, snap)
            dropped.append(f"{op.get('op')} on measure {op.get('measure')}, event {op.get('event')}: {e}")
            continue
        live.append(op)
    work = copy.deepcopy(root)
    part = work.find("part")
    ctx = Ctx(part, span["from"], span["to"])
    kept: list[dict] = []
    for kind, measure, unit in _group_changes(live):
        c = {"kind": kind, "span": where, "measure": measure, "ops": unit}
        if kind == "chord":
            c["event"] = unit[0]["event"]
        old = _unit_text(ctx, kind, measure, unit)
        snap, before = _snapshot(part), arithmetic(part)
        try:
            for op in unit:
                apply_op(ctx, op)
            for b, a in zip(before, arithmetic(part)):
                if (why := broken_by(b, a)):
                    raise OpError(why)
        except OpError as e:
            _restore(part, snap)
            dropped.append(f"measure {measure}: {e}" if kind == "notes" else f"chord at measure {measure}: {e}")
            continue
        new = _unit_text(ctx, kind, measure, unit)
        if old == new:
            continue
        c["old"], c["new"] = {"text": old}, {"text": new}
        if kind == "notes":
            a, b = old.split(", "), new.split(", ")
            c["marks"] = [i for i in range(max(len(a), len(b))) if (a[i] if i < len(a) else None) != (b[i] if i < len(b) else None)]
        kept.append(c)
    return kept, dropped


def ask(route: Route, prompt: str, root: ET.Element, span: dict, client=None) -> tuple[list[dict], list[str]]:
    """One call and its vetting; OpError when the reply is not a list of operations."""
    ops = parse_answer(route.complete(prompt, max_tokens=2000, client=client))
    kept, dropped = vet(root, span, ops)
    if ops and not kept and dropped:
        raise OpError("; ".join(dropped))   # nothing of the answer held: the caller may try the larger model
    return kept, dropped


def run_span(root: ET.Element, span: dict, route: Route, client=None) -> dict:
    """The changes, dropped reasons and escalation of one notes span."""
    where = {"staff": span["staff"], "from": span["from"], "to": span["to"]}
    out = {"changes": [], "dropped": [], "escalated": []}
    if span["staff"] != 0:
        out["dropped"].append({"span": where, "verse": 0, "kind": "notes", "reason": "notes and chords are checked on the first part only"})
        return out
    prompt = prompt_for(root, span)
    try:
        kept, dropped = ask(route, prompt, root, span, client)
    except OpError as e:
        bigger = route.larger()
        if bigger is None:
            out["dropped"].append({"span": where, "verse": 0, "kind": "notes", "reason": str(e)})
            return out
        try:
            kept, dropped = ask(bigger, prompt, root, span, client)
        except OpError as e2:
            out["dropped"].append({"span": where, "verse": 0, "kind": "notes", "reason": f"{e}; the larger model ({bigger.model}) failed too: {e2}"})
            return out
        except Exception as e2:  # noqa: BLE001
            out["dropped"].append({"span": where, "verse": 0, "kind": "notes", "reason": f"{e}; the larger model could not be asked: {e2.__class__.__name__}"})
            return out
        out["escalated"].append({"span": where, "verse": 0, "model": bigger.model})
    except Exception as e:  # noqa: BLE001
        out["dropped"].append({"span": where, "verse": 0, "kind": "notes", "reason": f"the model could not be asked: {e.__class__.__name__}"})
        return out
    out["changes"] = kept
    out["dropped"] += [{"span": where, "verse": 0, "kind": "notes", "reason": r} for r in dropped]
    return out
