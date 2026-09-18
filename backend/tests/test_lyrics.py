"""Lyrics stage (ADR 0004): grammar, alignment, injection, OCR on the real bands, the correction round trip."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from partition_player.pipeline.lyrics import inject as inj
from partition_player.pipeline.lyrics.align import Onset, Placement, align_row, place_lyrics
from partition_player.pipeline.lyrics.grammar import Row, Syllable, link_systems, rows, syllables

DATA = Path(__file__).parent / "data"


def word(text, x0, x1, y=3.4, conf=0.99, extend=False, h=1.3):
    return {"text": text, "confidence": conf, "x_left": x0, "x_right": x1, "y_units": y, "height_units": h, "extend": extend}


# ---- grammar --------------------------------------------------------------------------------------

def test_syllables_from_hyphens_attached_and_detached():
    row = Row(1, 3.4, [word("Lors", 0, 40), word("-", 45, 50), word("que", 55, 90), word("bru-", 100, 140), word("Re-bec", 150, 220), word("-", 225, 230), word("ca,", 235, 260)])
    s = syllables(row)
    assert [x.text for x in s] == ["Lors", "que", "bru", "Re", "bec", "ca,"]
    assert [x.syllabic for x in s] == ["begin", "end", "begin", "begin", "middle", "end"]
    assert s[3].x_left == 150 and s[4].x_left > 150 and s[4].x_right <= 220


def test_syllables_punctuation_extender_and_verse_number():
    r, rejected = rows([word("1.", 0, 10), word("la", 20, 40), word(",", 41, 44), word("fants_", 50, 90), word("sur", 100, 130, extend=True)], (0, 200))
    assert r[0].label == "1." and not rejected
    s = syllables(r[0])
    assert [(x.text, x.extend) for x in s] == [("la,", False), ("fants", True), ("sur", True)]


def test_rows_order_gap_and_coverage():
    verse1 = [word("a", 100, 120, y=3.4), word("b", 300, 320, y=3.5), word("c", 900, 920, y=3.4)]
    verse2 = [word("d", 100, 120, y=5.0), word("e", 900, 920, y=5.1)]
    chords = [word("Cm", 100, 130, y=11.3), word("G", 600, 615, y=11.4)]
    short = [word("x", 100, 110, y=6.6)]
    r, rejected = rows(verse1 + verse2 + chords + short, (100, 920))
    assert [x.verse for x in r] == [1, 2] and [len(x.words) for x in r] == [3, 2]
    assert {x.reason for x in rejected} == {"too far below the verses", "does not span the notes"}


def test_link_systems_continues_a_cut_word():
    a = Row(1, 3, []); a.syllables = [Syllable("bru", 0, 10, 1.0, joins_next=True)]
    b = Row(1, 3, []); b.syllables = [Syllable("yère", 0, 10, 1.0)]
    link_systems([[a], [b]])
    assert b.syllables[0].syllabic == "end"


# ---- alignment ------------------------------------------------------------------------------------

def onsets(xs):
    return [Onset(0, i, x, 0) for i, x in enumerate(xs)]


def test_align_row_follows_order_despite_drift():
    unit = 10.0
    xs = [100, 200, 300, 400, 500, 600]
    # syllables drift right by up to 2.5 interlines along the line: nearest-note would fail at the end
    syls = [Syllable(t, x + 5 * i, x + 5 * i + 30, 1.0) for i, (t, x) in enumerate(zip("abcdef", xs))]
    cost, assign = align_row(syls, onsets(xs), unit)
    assert assign == [0, 1, 2, 3, 4, 5]


def test_align_row_skips_melisma_and_drops_doubtful_token():
    unit = 10.0
    xs = [100, 200, 300, 400]
    syls = [Syllable("a", 95, 130, 1.0, extend=True), Syllable("zz", 250, 260, 0.3), Syllable("b", 295, 330, 1.0), Syllable("c", 395, 430, 1.0)]
    cost, assign = align_row(syls, onsets(xs), unit)
    assert assign == [0, None, 2, 3]


def test_align_row_starts_mid_system_for_free():
    unit = 10.0
    xs = [100, 200, 300, 400, 500]
    syls = [Syllable("d", 398, 430, 1.0), Syllable("e", 498, 530, 1.0)]
    cost, assign = align_row(syls, onsets(xs), unit)
    assert assign == [3, 4] and cost < 1


# ---- the real page --------------------------------------------------------------------------------

GT = ("Lors que nous é tions en core en fants sur le che min de bru yère, tout le long de la ri vière on cueil lait "
      "la mi ra belle. Sous le nez des tour te relles. An ton, Y van, Bo ris et moi. Re bec ca, Pau la, Jo han na et moi.").split()


def test_anton_lyrics_placed_on_every_note():
    geometry = json.loads((DATA / "anton_geometry.json").read_text())
    tree = ET.parse(DATA / "anton_score.musicxml")
    result = place_lyrics(tree, geometry)
    part = tree.getroot().find("part")
    order = [(mi, k) for mi, m in enumerate(part.findall("measure")) for k in range(len(inj.sounding_notes(m)))]
    assert len(order) == 55 and result.verses == 1
    placed = {(p.measure, p.onset): p for p in result.placed}
    assert len(placed) == 55
    right = sum(1 for i, key in enumerate(order) if placed[key].text == GT[i])
    assert right >= 52  # OCR misreads a letter or a comma now and then; the notes are all right
    assert placed[order[0]].syllabic == "begin" and placed[order[1]].syllabic == "end"
    # the chord names of the next system, 11 interlines down, were seen and rejected, never written
    assert any("too far below" in s["reason"] for s in result.seen)
    assert inj.inject(part, result.placed) == 55


@pytest.mark.slow
def test_anton_bands_read_every_syllable():
    import cv2
    from partition_player.pipeline.lyrics.ocr import make_lyrics_ocr, read_lyrics

    geometry = json.loads((DATA / "anton_geometry.json").read_text())
    ocr = make_lyrics_ocr()
    texts = []
    for st in geometry["staves"]:
        band = cv2.imread(str(DATA / f"anton_lyrics_{st['index']}.png"), cv2.IMREAD_GRAYSCALE)
        words = [w for w in read_lyrics(ocr, band, st["unit_px"]) if w.y_center / st["unit_px"] < 6]
        texts += [p for w in words for p in w.text.replace("-", " ").split() if p]
    assert len(texts) == 55 and sum(1 for t in texts if t in GT) >= 52


# ---- injection and the correction round trip ------------------------------------------------------

def test_inject_after_notations_and_rewrite_keeps_harmony(tmp_path):
    xml = """<?xml version="1.0"?><score-partwise><part id="P1"><measure number="1">
    <attributes><divisions>1</divisions></attributes>
    <harmony><root><root-step>C</root-step></root><kind>major</kind></harmony>
    <note><rest/><duration>1</duration></note>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><notations/></note>
    <note><pitch><step>E</step><octave>4</octave></pitch><duration>1</duration><notations/></note>
    <note><chord/><pitch><step>G</step><octave>4</octave></pitch><duration>1</duration></note>
    </measure></part></score-partwise>"""
    score = tmp_path / "s.musicxml"
    score.write_text(xml)
    placed = [Placement(1, 0, 0, "Lors", "begin", False, 1.0), Placement(1, 0, 1, "que", "end", True, 1.0), Placement(2, 0, 0, "Deux", "single", False, 1.0)]
    assert inj.rewrite(score, placed) == 3
    tree = ET.parse(score)
    notes = inj.sounding_notes(tree.getroot().find("part").find("measure"))
    first = [c.tag for c in notes[0]]
    assert first.index("lyric") > first.index("notations") and len(notes[0].findall("lyric")) == 2
    assert notes[1].find("lyric/extend") is not None and notes[1].find("lyric/syllabic").text == "end"
    assert tree.getroot().find("part/measure/harmony") is not None
    # rewriting again replaces, never duplicates
    assert inj.rewrite(score, placed[:1]) == 1
    assert sum(1 for _ in ET.parse(score).getroot().iter("lyric")) == 1
    assert inj.onset_counts(score) == [2]


# ---- the editor's text convention -------------------------------------------------------------------

def test_verse_text_round_trip_with_holds_and_skips():
    from partition_player.pipeline.lyrics.edit import deal, parse_verse, verse_text

    order = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0)]
    placed = [Placement(1, 0, 1, "Lors", "begin", False, 1.0), Placement(1, 0, 2, "que", "end", False, 1.0),
              Placement(1, 1, 0, "nous", "single", True, 1.0), Placement(1, 1, 2, "é", "begin", False, 1.0),
              Placement(1, 2, 0, "tions", "end", False, 1.0)]
    text = verse_text(placed, 1, order)
    assert text == "* Lors-que nous_ é-tions"
    again = deal([text], order, [])
    assert [(p.measure, p.onset, p.text, p.syllabic) for p in again] == [(p.measure, p.onset, p.text, p.syllabic) for p in placed]
    assert [it.text for it in parse_verse("a-b-c d_ e") if not it.skip] == ["a", "b", "c", "d", "e"]


def test_deal_keeps_positions_when_counts_match_and_deals_otherwise():
    from partition_player.pipeline.lyrics.edit import deal

    order = [(0, 0), (0, 1), (0, 2), (1, 0)]
    old = [Placement(1, 0, 1, "la", "single", False, 0.9), Placement(1, 1, 0, "mi", "single", False, 0.9)]
    fixed = deal(["Pau-la,"], order, old)   # same count: texts replaced, positions kept
    assert [(p.measure, p.onset, p.text, p.syllabic) for p in fixed] == [(0, 1, "Pau", "begin"), (1, 0, "la,", "end")]
    dealt = deal(["a b c", "x"], order, old)  # different count: from the first note, in order
    assert [(p.verse, p.measure, p.onset, p.text) for p in dealt] == [(1, 0, 0, "a"), (1, 0, 1, "b"), (1, 0, 2, "c"), (2, 0, 0, "x")]


# ---- the optional language-model polish ---------------------------------------------------------

def test_polish_keeps_structure_and_rejects_changed_counts(tmp_path):
    from partition_player.pipeline.lyrics.polish import polish, verse_string

    band = tmp_path / "lyrics_0.png"
    band.write_bytes(b"\x89PNG fake")
    placed = [Placement(1, 0, 0, "Lors", "begin", False, 1.0, 0), Placement(1, 0, 1, "que", "end", False, 1.0, 0),
              Placement(1, 0, 2, "To", "begin", False, 0.7, 0), Placement(1, 1, 0, "han", "middle", False, 1.0, 0), Placement(1, 1, 1, "na", "end", False, 1.0, 0)]
    assert verse_string(placed) == "Lors-que To-han-na"

    class Reply:
        def __init__(self, text): self._t = text
        def raise_for_status(self): pass
        def json(self): return {"content": [{"type": "text", "text": self._t}]}

    class Client:
        def __init__(self, text): self.text, self.calls = text, 0
        def post(self, *a, **k): self.calls += 1; return Reply(self.text)

    changed, warnings = polish(placed, {0: band}, "key", client=Client("Lors-que Jo-han-na"))
    assert changed == 1 and placed[2].text == "Jo" and not warnings
    changed, warnings = polish(placed, {0: band}, "key", client=Client("Lorsque Johanna et moi"))
    assert changed == 0 and placed[2].text == "Jo" and "structure" in warnings[0]
