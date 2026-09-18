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
