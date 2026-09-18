"""Chord stage (ADR 0003): grammar, constrained decoding, OCR on real bands, placement, injection."""
import json
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from partition_player.pipeline.chords.grammar import constrained_decode, parse_chord
from partition_player.pipeline.chords.place import Placed, inject, place

DATA = Path(__file__).parent / "data"


@pytest.mark.parametrize("text,root,alter,kind,bass", [
    ("C", "C", 0, "major", ""), ("Cm", "C", 0, "minor", ""), ("F#m7", "F", 1, "minor-seventh", ""),
    ("Bb", "B", -1, "major", ""), ("G7/B", "G", 0, "dominant", "B"), ("Cdim", "C", 0, "diminished", ""),
    ("Dsus4", "D", 0, "suspended-fourth", ""), ("D/F#", "D", 0, "major", "F"), ("Cmaj7", "C", 0, "major-seventh", ""),
    ("Ebmaj7", "E", -1, "major-seventh", ""), ("Bdim7", "B", 0, "diminished-seventh", ""), ("C6", "C", 0, "major-sixth", ""),
])
def test_grammar_accepts_chords(text, root, alter, kind, bass):
    c = parse_chord(text)
    assert c is not None and (c.root, c.root_alter, c.kind, c.bass) == (root, alter, kind, bass)


@pytest.mark.parametrize("text", ["", "6", "Marie", "H7", "C/", "Cm/H", "Allegro", "Fine", "sing", "la"])
def test_grammar_rejects_non_chords(text):
    assert parse_chord(text) is None


def test_add9_is_major_with_a_degree():
    c = parse_chord("Cadd9")
    assert c.kind == "major" and c.degrees == ((9, 0, "add"),)


def _probs(seq, chars, p=0.9):
    """A (T, V) matrix that spells `seq` (None = blank) with probability p at each step."""
    V = len(chars); idx = {c: i for i, c in enumerate(chars)}
    out = np.full((len(seq), V), (1 - p) / (V - 1), dtype=np.float32)
    for t, s in enumerate(seq):
        out[t, 0 if s is None else idx[s]] = p
    return out


def test_constrained_decode_prefers_legal_reading():
    chars = ["blank", "6", "G", "C", "m", "a", " "]
    # the net is sure it sees "6": the only legal reading is "G", and the mass on "6" carries over
    probs = _probs([None, "6", "6", None], chars, p=0.8)
    text, conf = constrained_decode(probs, chars)
    assert text == "G" and conf > 0.4
    probs = _probs([None, "C", None, "m", "m", None], chars)
    assert constrained_decode(probs, chars)[0] == "Cm"
    # "a" alone is not a chord: "A" is (glyph variant), so it decodes to A; "am" -> Am
    probs = _probs(["a", "m"], chars)
    assert constrained_decode(probs, chars)[0] == "Am"


def test_constrained_decode_returns_nothing_for_blank():
    chars = ["blank", "x", "y"]
    text, conf = constrained_decode(_probs([None, None, None], chars, p=0.99), chars)
    assert text == "" or conf < 0.05


@pytest.mark.slow
def test_read_bands_from_photo():
    """The four bands above the staves of the benchmark photo: 10 chord names, nothing else accepted."""
    from partition_player.pipeline.chords.ocr import make_ocr, read_band
    import cv2

    geometry = json.loads((DATA / "anton_geometry.json").read_text())
    ocr = make_ocr()
    expected = [["Cm"], ["Fm", "Cm", "Fm", "G"], ["Cm", "G"], ["Cm", "G", "Cm"]]
    for system, want in zip(geometry["systems"], expected):
        band = cv2.imread(str(DATA / f"anton_band_{system['index']}.png"), cv2.IMREAD_GRAYSCALE)
        tokens = read_band(ocr, band, system["unit"])
        good = [t.text for t in sorted(tokens, key=lambda t: t.x_left) if t.confidence >= 0.6]
        assert good == want, [(t.text, t.confidence, t.raw) for t in tokens]


SCORE = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>2</divisions><time><beats>2</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration><type>quarter</type></note>
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>2</duration><type>quarter</type></note>
    </measure>
    <measure number="2">
      <note><pitch><step>E</step><octave>4</octave></pitch><duration>1</duration><type>eighth</type></note>
      <note><pitch><step>F</step><octave>4</octave></pitch><duration>1</duration><type>eighth</type></note>
      <note><pitch><step>G</step><octave>4</octave></pitch><duration>2</duration><type>quarter</type></note>
    </measure>
    <measure number="3">
      <note><rest/><duration>2</duration><type>quarter</type></note>
      <note><pitch><step>A</step><octave>4</octave></pitch><duration>2</duration><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
"""


def _geometry(tokens, bars, notes, measures=3, unit=20.0):
    return {"systems": [{"index": 0, "unit": unit, "min_x": 100.0, "max_x": 1000.0, "top_y": 300.0, "staffs": 1,
                         "bars": bars, "notes": notes, "measures": measures,
                         "tokens": [{"text": t, "confidence": c, "x_left": x, "x_right": x + 40, "y_units_above": 2.5, "raw": t} for t, c, x in tokens]}]}


def _tok(text, x, conf=0.95):
    return (text, conf, x)


def test_place_with_matching_barlines_and_noteheads():
    tree = ET.ElementTree(ET.fromstring(SCORE))
    notes = [220.0, 330.0, 470.0, 530.0, 620.0, 860.0]
    geo = _geometry([_tok("C", 210), _tok("G7", 525), _tok("F", 850)], bars=[400.0, 700.0, 1000.0], notes=notes)
    r = place(tree, geo)
    assert not r.warnings
    assert [(p.measure, p.offset, p.chord.text) for p in r.placed] == [(0, Fraction(0), "C"), (1, Fraction(1, 2), "G7"), (2, Fraction(1), "F")]


def test_place_repairs_one_missing_barline_from_note_counts():
    tree = ET.ElementTree(ET.fromstring(SCORE))
    notes = [220.0, 330.0, 470.0, 530.0, 620.0, 860.0]
    geo = _geometry([_tok("C", 210), _tok("G", 455), _tok("F", 850)], bars=[700.0, 1000.0], notes=notes)  # 400 missing
    r = place(tree, geo)
    assert any("one barline" in w for w in r.warnings)
    assert [(p.measure, p.chord.text) for p in r.placed] == [(0, "C"), (1, "G"), (2, "F")]


def test_place_rejects_low_confidence_clef_zone_and_non_chords():
    tree = ET.ElementTree(ET.fromstring(SCORE))
    geo = _geometry([_tok("A", 120), _tok("D", 500, conf=0.2), _tok("", 700), _tok("C", 210)], bars=[400.0, 700.0, 1000.0], notes=[220.0, 330.0, 470.0, 530.0, 620.0, 860.0])
    geo["systems"][0]["tokens"][2]["raw"] = "Marie"
    r = place(tree, geo)
    assert [p.chord.text for p in r.placed] == ["C"]
    reasons = sorted(s["reason"] for s in r.seen)
    assert reasons == ["above the clef", "low confidence 0.20", "not a chord"]


def test_place_falls_back_to_proportion_when_barlines_are_off():
    tree = ET.ElementTree(ET.fromstring(SCORE))
    geo = _geometry([_tok("C", 210), _tok("F", 850)], bars=[300.0, 500.0, 600.0, 800.0, 1000.0], notes=[])
    r = place(tree, geo)
    assert any("by proportion" in w for w in r.warnings)
    assert [p.measure for p in r.placed] == [0, 2]


def test_inject_writes_harmony_before_the_right_note():
    tree = ET.ElementTree(ET.fromstring(SCORE))
    c = parse_chord("G7/B")
    n = inject(tree, [Placed(1, Fraction(1, 2), c, 0.9, 0.0), Placed(2, Fraction(0), parse_chord("F"), 0.9, 0.0)])
    assert n == 2
    m2 = tree.getroot().find("part").findall("measure")[1]
    tags = [el.tag for el in m2]
    assert tags == ["note", "harmony", "note", "note"]
    h = m2.find("harmony")
    assert h.findtext("root/root-step") == "G" and h.findtext("kind") == "dominant" and h.findtext("bass/bass-step") == "B"
    m3 = tree.getroot().find("part").findall("measure")[2]
    assert [el.tag for el in m3] == ["harmony", "note", "note"]  # offset 0 goes before the rest


def test_recognize_end_to_end_keeps_chords(settings, tmp_path):
    """The fake engine writes no geometry, so the stage is a no-op and stats say 0 chords."""
    from partition_player.pipeline.run import add_chords

    assert add_chords(tmp_path / "x.musicxml", tmp_path / "geometry.json", tmp_path / "y.musicxml") is None
