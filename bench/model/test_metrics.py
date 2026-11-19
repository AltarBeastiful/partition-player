"""Seam 1: the counting of notes fixed and notes broken (the gate). Run: backend/.venv/bin/python -m pytest bench/model"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics import compare, lyric_compare  # noqa: E402


def score(measures: list[list[str]], lyrics: dict | None = None) -> ET.Element:
    """measures: per measure a list of "C4:1" (step octave : quarters) or "r:1"."""
    out = ['<score-partwise><part id="P1">']
    for i, m in enumerate(measures):
        out.append(f'<measure number="{i + 1}">' + ('<attributes><divisions>1</divisions></attributes>' if i == 0 else ""))
        for k, ev in enumerate(m):
            name, dur = ev.split(":")
            pitch = "<rest/>" if name == "r" else f"<pitch><step>{name[0]}</step><octave>{name[1]}</octave></pitch>"
            lyr = ""
            if lyrics and (i, k) in lyrics:
                lyr = f"<lyric number=\"1\"><syllabic>single</syllabic><text>{lyrics[(i, k)]}</text></lyric>"
            out.append(f"<note>{pitch}<duration>{dur}</duration>{lyr}</note>")
        out.append("</measure>")
    out.append("</part></score-partwise>")
    return ET.fromstring("".join(out))


GT = score([["C4:1", "D4:1"], ["E4:2"]])


def test_a_wrong_note_put_right_is_fixed():
    before = score([["C4:1", "E4:1"], ["E4:2"]])
    r = compare(GT, before, GT, 0, 1)
    assert (r.fixed, r.broken, r.wrong_before) == (1, 0, 1)


def test_a_right_note_made_wrong_is_broken():
    after = score([["C4:1", "D4:1"], ["F4:2"]])
    r = compare(GT, GT, after, 0, 1)
    assert (r.fixed, r.broken) == (0, 1)


def test_a_wrong_note_changed_to_another_wrong_one_is_neither():
    before = score([["C4:1", "E4:1"], ["E4:2"]])
    after = score([["C4:1", "F4:1"], ["E4:2"]])
    r = compare(GT, before, after, 0, 1)
    assert (r.fixed, r.broken, r.wrong_before, r.wrong_after) == (0, 0, 1, 1)


def test_a_duration_counts_as_part_of_the_note():
    after = score([["C4:1", "D4:2"], ["E4:2"]])
    assert compare(GT, GT, after, 0, 1).broken == 1


def test_only_the_span_is_counted():
    after = score([["C4:1", "D4:1"], ["F4:2"]])
    assert compare(GT, GT, after, 0, 0).broken == 0


def test_a_note_pushed_off_by_an_insert_is_broken():
    after = score([["C4:1", "C4:1", "D4:1"], ["E4:2"]])
    assert compare(GT, GT, after, 0, 0).broken == 1  # slot 1 now holds C where D was right


def test_measure_count_mismatch_is_reported_not_guessed():
    short = score([["C4:1", "D4:1"]])
    assert compare(GT, short, short, 0, 1).comparable is False


def test_lyric_syllables_fixed_and_broken():
    gt = score([["C4:1", "D4:1"]], {(0, 0): "la", (0, 1): "li"})
    before = score([["C4:1", "D4:1"]], {(0, 0): "la", (0, 1): "xx"})
    after = score([["C4:1", "D4:1"]], {(0, 0): "xx", (0, 1): "li"})
    assert lyric_compare(gt, before, after, 0, 0) == (1, 1)
