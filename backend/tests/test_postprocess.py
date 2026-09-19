import xml.etree.ElementTree as ET
from pathlib import Path

from partition_player.pipeline.postprocess import postprocess

SHORT_MEASURE = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>4</divisions><time><beats>2</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration><type>eighth</type></note>
      <note><pitch><step>G</step><octave>4</octave></pitch><duration>2</duration><type>eighth</type></note>
    </measure>
    <measure number="2">
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
      <note><rest/><duration>4</duration><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
"""


def test_short_measure_is_padded(tmp_path: Path):
    src = tmp_path / "in.musicxml"; src.write_text(SHORT_MEASURE)
    dst = tmp_path / "out.musicxml"
    stats = postprocess(src, dst)
    assert stats.measures == 2 and stats.notes == 3 and stats.rests == 1
    assert stats.padded_measures == 1
    out = dst.read_text()
    assert out.count("<rest") == 2  # the original rest plus the padding rest
    assert "<duration>4</duration>" in out  # padding of one quarter (4 divisions)


def test_ground_truth_needs_no_padding(tmp_path: Path):
    from conftest import GROUND_TRUTH

    stats = postprocess(GROUND_TRUTH, tmp_path / "out.musicxml")
    assert (stats.measures, stats.notes, stats.rests, stats.padded_measures) == (19, 55, 15, 0)


SPLIT_ATTRIBUTES = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>4</divisions></attributes>
      <attributes><time><beats>2</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
      <note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
"""


def test_time_signature_in_second_attributes_block(tmp_path: Path):
    """homr writes divisions and time in separate <attributes> blocks; both must be read."""
    src = tmp_path / "in.musicxml"; src.write_text(SPLIT_ATTRIBUTES)
    stats = postprocess(src, tmp_path / "out.musicxml")
    assert stats.padded_measures == 0 and stats.warnings == []


REST_CHORD = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions><time><beats>3</beats><beat-type>4</beat-type></time></attributes>
      <note><rest/><duration>1</duration><voice>1</voice><type>quarter</type></note>
      <note><chord/><pitch><step>G</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type></note>
      <note><pitch><step>F</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type></note>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
"""


def test_rest_merged_into_chord_is_dropped(tmp_path: Path):
    """homr quirk: a rest followed by a <chord/> note. The note is real, the rest is not."""
    src = tmp_path / "in.musicxml"; src.write_text(REST_CHORD)
    dst = tmp_path / "out.musicxml"
    stats = postprocess(src, dst)
    out = dst.read_text()
    assert "<rest" not in out and "<chord" not in out
    assert stats.notes == 3 and stats.rests == 0 and stats.padded_measures == 0
    assert any("merged into a chord" in w for w in stats.warnings)


REPEATS = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions><time><beats>2</beats><beat-type>4</beat-type></time></attributes>
      <barline location="left"><bar-style>heavy-light</bar-style><repeat direction="forward"/></barline>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration><type>half</type></note>
      <barline location="right"><bar-style>light-heavy</bar-style><ending number="1" type="stop"/><repeat direction="backward"/></barline>
    </measure>
  </part>
</score-partwise>
"""


def test_repeats_are_kept_and_noted(tmp_path: Path):
    """Plan 0004: the signs stay in the document for the player, with an information doubt."""
    src = tmp_path / "in.musicxml"; src.write_text(REPEATS)
    dst = tmp_path / "out.musicxml"
    stats = postprocess(src, dst)
    out = dst.read_text()
    assert stats.repeat_signs == 2
    assert "<repeat" in out and "<ending" in out and "bar-style" in out
    [d] = [d for d in stats.doubts if d["kind"] == "repeat"]
    assert d["measure"] == 0 and d["info"] and d["directions"] == ["forward", "backward"]


def test_repeat_barlines_are_normalized(tmp_path: Path):
    """homr puts a forward repeat on a "right" barline at the start of the measure; it becomes a left
    barline, first in the measure, with the heavy-light style, so OSMD starts the repeat there."""
    src = tmp_path / "in.musicxml"
    src.write_text(REPEATS.replace('<barline location="left"><bar-style>heavy-light</bar-style><repeat direction="forward"/></barline>',
                                   '<barline location="right"><repeat direction="forward"/></barline>'))
    dst = tmp_path / "out.musicxml"
    postprocess(src, dst)
    measure = ET.parse(dst).getroot().find("part").find("measure")
    first = list(measure)[0]
    assert first.tag == "barline" and first.get("location") == "left"
    assert [c.tag for c in first] == ["bar-style", "repeat"] and first.find("bar-style").text == "heavy-light"
    last = list(measure)[-1]
    assert last.tag == "barline" and last.get("location") == "right" and last.find("repeat").get("direction") == "backward"


def test_short_first_measure_is_a_pickup(tmp_path):
    src = tmp_path / "in.musicxml"; dst = tmp_path / "out.musicxml"
    src.write_text(SHORT_MEASURE)
    stats = postprocess(src, dst)
    assert stats.pickup and stats.padded_measures == 1
    import xml.etree.ElementTree as ET
    m1 = ET.parse(dst).getroot().find("part").find("measure")
    assert m1.get("implicit") == "yes"
    tags = [el.tag for el in m1]
    assert tags[:2] == ["attributes", "note"] and m1.findall("note")[0].find("rest") is not None


UNEVEN = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>4</divisions><time><beats>3</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
      <note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
      <note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
    </measure>
    <measure number="2">
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>2</duration><type>eighth</type></note>
    </measure>
    <measure number="3">
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>8</duration><type>half</type></note>
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>6</duration><type>quarter</type><dot/></note>
    </measure>
  </part>
</score-partwise>
"""


def test_doubts_name_the_measures_that_do_not_add_up(tmp_path: Path):
    """ADR 0005: the padded and overfull measures are recorded per measure, in words."""
    src = tmp_path / "in.musicxml"; src.write_text(UNEVEN)
    stats = postprocess(src, tmp_path / "out.musicxml")
    kinds = [(d["measure"], d["kind"]) for d in stats.doubts]
    assert kinds == [(1, "padded"), (2, "overfull")]
    assert stats.doubts[0]["text"] == "shorter than 3/4 by a dotted quarter: a rest was added at the end"
    assert stats.doubts[1]["text"] == "longer than 3/4 by an eighth"
    assert stats.doubts[0]["gap"] == "3/2" and stats.doubts[1]["excess"] == "1/2"


def test_pickup_is_information_not_an_error(tmp_path: Path):
    src = tmp_path / "in.musicxml"; src.write_text(SHORT_MEASURE)
    stats = postprocess(src, tmp_path / "out.musicxml")
    assert [d["kind"] for d in stats.doubts] == ["pickup"] and stats.doubts[0]["info"] is True
    assert "shorter than 2/4 by a quarter" in stats.doubts[0]["text"]


def test_inspect_reports_without_changing(tmp_path: Path):
    """The live check the editor's save runs: the same measures, kinds underfull and overfull."""
    import xml.etree.ElementTree as ET
    from partition_player.pipeline.postprocess import describe, inspect
    from fractions import Fraction

    tree = ET.ElementTree(ET.fromstring(UNEVEN))
    before = ET.tostring(tree.getroot())
    stats = inspect(tree)
    assert ET.tostring(tree.getroot()) == before
    assert (stats.measures, stats.notes, stats.rests) == (3, 7, 0)
    assert [(d["measure"], d["kind"]) for d in stats.doubts] == [(1, "underfull"), (2, "overfull")]
    assert describe(Fraction(5, 2)) == "five eighths" and describe(Fraction(1, 3)) == "0.333333 quarters"
