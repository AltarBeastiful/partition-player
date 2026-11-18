"""A time signature that changes in the middle of the page (plan 0013).

homr reads the mark and then cannot write it down: the token carries only the beat-type, the
numerator it would use is the median bar of the whole part, and a repeated token is dropped as
redundant. So the driver keeps the place and `postprocess` takes the count from the bar. Two rules
are held here to exact numbers — what the bar has to look like before its meter is believed, and the
re-anchoring of voices that makes the bar measurable in the first place — because both of them move
notes on every recognized page, and the page they were written for is checked end to end at the
bottom.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

from partition_player.pipeline.postprocess import MeasureCtx, _relay, _time_from_bar, postprocess

HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
  <part id="P1">"""
FOOT = """
  </part>
</score-partwise>
"""


def note(step: str, duration: int, staff: int = 1, voice: int = 1, chord: bool = False) -> str:
    return (f'<note>{"<chord/>" if chord else ""}<pitch><step>{step}</step><octave>4</octave></pitch>'
            f"<duration>{duration}</duration><voice>{voice}</voice><staff>{staff}</staff></note>")


def measure(index: int, body: str, attributes: str = "") -> str:
    return f'<measure number="{index}">{attributes}{body}</measure>'


def one(body: str, attributes: str = "") -> ET.Element:
    return ET.fromstring(f"<measure number=\"1\">{attributes}{body}</measure>")


def ctx(measure_el: ET.Element, beats: int = 4, beat_type: int = 4, divisions: int = 1) -> MeasureCtx:
    return MeasureCtx(1, measure_el, divisions, beats, beat_type)


def held(measure_el: ET.Element) -> Fraction:
    """What a reader following backup and forward finds, which is what the checks measure."""
    from partition_player.pipeline.postprocess import _measure_filled
    return _measure_filled(measure_el, 1)


# ---- the re-anchoring ------------------------------------------------------------------------

def test_a_measure_written_correctly_is_left_exactly_as_it_is():
    m = one(note("C", 2) + "<backup><duration>2</duration></backup>" + note("E", 2, staff=2, voice=5))
    before = ET.tostring(m)
    assert _relay(m) is False
    assert ET.tostring(m) == before


def test_the_voices_are_put_back_on_their_own_beats():
    """The canon's measure 19: six quarters in each voice, written seven long because a half note in
    one staff spanning a quarter in the other makes homr's cursor overshoot."""
    m = one(
        note("D", 1) + "<backup><duration>1</duration></backup>"
        + note("F", 1, staff=2, voice=5)
        + note("F", 1) + "<backup><duration>1</duration></backup>"
        + note("A", 2, staff=2, voice=5) + "<backup><duration>1</duration></backup>"
        + note("F", 2)                      # here the stream loses a beat: no backup follows
        + note("A", 1, staff=2, voice=5)
        + note("E", 2) + "<backup><duration>2</duration></backup>"
        + note("G", 1, staff=2, voice=5) + note("A", 1, staff=2, voice=5))
    assert held(m) == 7
    assert _relay(m) is True
    assert held(m) == 6
    assert _relay(m) is False               # and it settles: running it again changes nothing


def test_a_chord_tone_keeps_its_head_s_beat():
    m = one(note("C", 4) + note("E", 4, chord=True) + "<backup><duration>4</duration></backup>" + note("G", 4, staff=2, voice=5))
    assert _relay(m) is False
    assert held(m) == 4


def test_what_stands_before_a_note_keeps_that_note_s_beat():
    """A chord symbol is placed on a beat by standing before the note on it — the canon's C7 stands
    exactly here — so the repair must not leave it on the wrong side of the backup it writes."""
    m = one(
        note("D", 1) + "<backup><duration>1</duration></backup>"
        + note("F", 1, staff=2, voice=5)
        + note("F", 1) + "<backup><duration>1</duration></backup>"
        + note("A", 2, staff=2, voice=5) + "<backup><duration>1</duration></backup>"
        + note("F", 2)
        + "<harmony><root><root-step>C</root-step></root><kind>dominant</kind></harmony>"
        + note("B", 1, staff=2, voice=5)
        + note("E", 2) + "<backup><duration>2</duration></backup>"
        + note("G", 1, staff=2, voice=5) + note("A", 1, staff=2, voice=5))
    assert _relay(m) is True
    tags = [el.tag for el in m]
    i = tags.index("harmony")
    assert tags[i - 1] == "backup" and tags[i + 1] == "note"
    assert list(m)[i + 1].findtext("pitch/step") == "B"   # still the note it was written before
    assert held(m) == 6


def test_a_gap_a_writer_left_inside_a_voice_is_not_closed():
    """The repair is made only where it shortens the bar. A voice that skips a beat without writing
    a rest leaves the bar as long as it was — six measures of the benchmark's songs do this — and a
    voice a second engine numbered like another would only make it longer."""
    m = one(note("C", 1) + note("D", 1) + note("E", 1) + note("F", 1)
            + "<backup><duration>4</duration></backup>"
            + note("G", 1, staff=2, voice=5)
            + "<backup><duration>1</duration></backup>" + "<backup><duration>0</duration></backup>"
            + note("A", 1, staff=2, voice=5))            # voice 5: a beat at 0, then one at 2
    assert held(m) == 4
    assert _relay(m) is False


def test_a_writer_that_places_a_voice_itself_is_left_alone():
    """A `forward` says the writer meant a voice to start late; no engine here emits one, and a
    document that does is not second-guessed."""
    m = one(note("C", 2) + "<backup><duration>2</duration></backup>"
            + "<forward><duration>2</duration></forward>" + note("E", 2, staff=2, voice=5))
    assert _relay(m) is False


# ---- the numerator ---------------------------------------------------------------------------

def test_two_voices_agreeing_on_six_quarters_in_a_four_four_bar_are_believed():
    m = one(note("D", 6) + "<backup><duration>6</duration></backup>" + note("F", 6, staff=2, voice=5))
    assert _time_from_bar(ctx(m)) == (6, 4)


def test_one_voice_is_never_enough():
    """A single staff holding five quarters is a misread duration far more often than a 5/4 bar."""
    m = one(note("D", 5))
    assert _time_from_bar(ctx(m)) is None


def test_voices_that_disagree_decide_nothing():
    m = one(note("D", 6) + "<backup><duration>6</duration></backup>" + note("F", 4, staff=2, voice=5))
    assert _time_from_bar(ctx(m)) is None


def test_a_bar_of_exactly_twice_the_meter_is_a_missed_barline_not_an_eight_four():
    m = one(note("D", 8) + "<backup><duration>8</duration></backup>" + note("F", 8, staff=2, voice=5))
    assert _time_from_bar(ctx(m)) is None


def test_a_length_that_is_not_a_whole_number_of_beats_decides_nothing():
    m = one(note("D", 5) + "<backup><duration>5</duration></backup>" + note("F", 5, staff=2, voice=5),
            "<attributes><divisions>2</divisions></attributes>")
    assert _time_from_bar(ctx(m, divisions=2)) is None      # two and a half quarters


def test_a_bar_that_already_agrees_with_the_time_in_force_says_nothing_new():
    m = one(note("D", 4) + "<backup><duration>4</duration></backup>" + note("F", 4, staff=2, voice=5))
    assert _time_from_bar(ctx(m)) is None


def test_the_beat_type_is_the_engine_s_and_only_the_count_is_ours():
    m = one(note("D", 3) + "<backup><duration>3</duration></backup>" + note("F", 3, staff=2, voice=5),
            "<attributes><divisions>2</divisions></attributes>")
    assert _time_from_bar(ctx(m, beats=2, beat_type=8, divisions=2)) == (3, 8)


# ---- the whole way through -------------------------------------------------------------------

def page(bodies: list[str]) -> str:
    head = '<attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>'
    return HEAD + "".join(measure(i + 1, b, head if i == 0 else "") for i, b in enumerate(bodies)) + FOOT


FOUR = note("C", 4) + "<backup><duration>4</duration></backup>" + note("E", 4, staff=2, voice=5)
SIX = note("D", 6) + "<backup><duration>6</duration></backup>" + note("F", 6, staff=2, voice=5)


def times_of(path: Path) -> list[tuple[str, str]]:
    out = []
    for m in ET.parse(path).getroot().find("part").findall("measure"):
        for attrs in m.findall("attributes"):
            if (t := attrs.find("time")) is not None:
                out.append((m.get("number"), f"{t.findtext('beats')}/{t.findtext('beat-type')}"))
    return out


def test_the_mark_says_where_and_the_bar_says_how_many(tmp_path: Path):
    src = tmp_path / "in.musicxml"; src.write_text(page([FOUR, SIX, FOUR]))
    dst = tmp_path / "out.musicxml"
    stats = postprocess(src, dst, times=[{"measure": 0, "beat_type": 4}, {"measure": 1, "beat_type": 4}, {"measure": 2, "beat_type": 4}])
    assert times_of(dst) == [("1", "4/4"), ("2", "6/4"), ("3", "4/4")]
    assert stats.padded_measures == 0
    assert [d["kind"] for d in stats.doubts] == ["time", "time"]
    assert all(d["level"] == "info" for d in stats.doubts)


def test_without_the_mark_the_long_bar_is_only_a_doubt(tmp_path: Path):
    """The position always comes from the page: a bar nobody marked is never renamed."""
    src = tmp_path / "in.musicxml"; src.write_text(page([FOUR, SIX, FOUR]))
    dst = tmp_path / "out.musicxml"
    stats = postprocess(src, dst)
    assert times_of(dst) == [("1", "4/4")]
    assert [(d["measure"], d["kind"]) for d in stats.doubts] == [(1, "overfull")]


def test_a_marked_bar_that_decides_nothing_says_so_in_its_doubt(tmp_path: Path):
    src = tmp_path / "in.musicxml"; src.write_text(page([FOUR, note("D", 5), FOUR]))
    dst = tmp_path / "out.musicxml"
    stats = postprocess(src, dst, times=[{"measure": 1, "beat_type": 4}])
    assert times_of(dst) == [("1", "4/4")]
    (d,) = [d for d in stats.doubts if d["kind"] == "overfull"]
    assert d["time_mark"] is True and "a time signature is printed here" in d["text"]


def test_an_authored_file_is_never_given_a_meter_it_did_not_write(tmp_path: Path):
    src = tmp_path / "in.musicxml"; src.write_text(page([FOUR, SIX, FOUR]))
    dst = tmp_path / "out.musicxml"
    postprocess(src, dst, repair=False, times=[{"measure": 1, "beat_type": 4}])
    assert times_of(dst) == [("1", "4/4")]
    assert dst.read_text().count("<backup>") == src.read_text().count("<backup>")
