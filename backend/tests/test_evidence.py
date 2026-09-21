"""The second reading and its rating (plan 0008).

The rule under test is a refusal as much as a detection: one reader disagreeing on its own, or
disagreeing about something the rest of the page argues against, must come to nothing. The page
that prompted the plan — `anton`, where an ink blot over a notehead made the pixel stage see two
heads where the print has one and the transformer was right — is the last test here, and it must
stay silent.
"""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from partition_player.pipeline.evidence import (
    CHECK, Emitted, clef_base, collect, compare, emitted_by_measure, heads_by_measure, off_grid,
    rate, stacks,
)

DATA = Path(__file__).parent / "data"
UNIT = 10.0


def geometry(heads_per_system, *, bars_ok=True):
    """Two systems of two measures each, staff lines 10 px apart, bottom line at y=340/740."""
    systems, staves = [], []
    for i, _ in enumerate(heads_per_system):
        inner = [600.0] if bars_ok else []
        systems.append({"index": i, "unit": UNIT, "min_x": 100.0, "max_x": 1100.0,
                        "top_y": 300.0 + 400 * i, "bars": [100.0, *inner, 1100.0], "measures": 2})
        staves.append({"index": i, "system": i, "unit": UNIT, "min_x": 100.0, "max_x": 1100.0,
                       "top_y": 300.0 + 400 * i, "bottom_y": 340.0 + 400 * i,
                       "noteheads": sorted(heads_per_system[i])})
    return {"systems": systems, "staves": staves}


def head(x, y, size=8.0, position=0):
    return [x, y, size, position]


def test_heads_land_in_the_measure_the_review_strip_would_frame():
    g = geometry([[head(200, 330), head(400, 330), head(800, 330)], [head(300, 730), head(900, 730)]])
    per = heads_by_measure(g, 4)
    assert [len(m) for m in per] == [2, 1, 1, 1]
    assert per[0][0]["x"] == 200 and per[2][0]["x"] == 300


def test_heads_of_a_system_whose_barlines_were_missed_are_marked_estimated():
    g = geometry([[head(200, 330)], [head(300, 730)]], bars_ok=False)
    ev = collect(g, 4)
    assert ev["estimated"] == [0, 1, 2, 3]  # both systems were split evenly
    assert collect(geometry([[head(200, 330)], [head(300, 730)]]), 4)["estimated"] == []


def test_collect_round_trips_what_the_rating_needs():
    g = geometry([[head(200, 330, 9.5, 3)], [head(300, 730)]])
    ev = collect(g, 4)
    assert json.loads(json.dumps(ev)) == ev  # it is written to disk as it stands
    assert ev["heads"][0] == [[200.0, 330.0, 9.5, 3, 0]]


def test_stacks_group_the_noteheads_that_share_a_stem():
    heads = [{"x": 100.0, "y": 330.0}, {"x": 103.0, "y": 340.0}, {"x": 300.0, "y": 330.0}]
    assert [len(g) for g in stacks(heads, UNIT)] == [2, 1]
    assert [len(g) for g in stacks(heads, 1.0)] == [1, 1, 1]  # a tiny interline: nothing shares an x


def test_off_grid_tells_ink_from_a_chord():
    on = [{"y": 330.0}, {"y": 340.0}]        # two interlines apart: a fifth, engraved
    assert not off_grid(on, UNIT)
    assert off_grid([{"y": 330.0}, {"y": 338.2}], UNIT)   # 1.64 steps: the Anton blot
    assert off_grid([{"y": 330.0}, {"y": 330.0}], UNIT)   # the same place twice is not a chord
    assert not off_grid([{"y": 330.0}], UNIT)


def test_clef_base_puts_the_bottom_line_where_the_clef_says():
    def part(sign, line):
        return ET.fromstring(f"<part><measure><attributes><clef><sign>{sign}</sign><line>{line}</line></clef></attributes></measure></part>")
    assert clef_base(part("G", 2)) == 4 * 7 + 2   # E4
    assert clef_base(part("F", 4)) == 2 * 7 + 4   # G2
    assert clef_base(ET.fromstring("<part><measure/></part>")) == 4 * 7 + 2  # treble by default


def test_emitted_counts_noteheads_and_places_them_on_the_staff():
    part = ET.fromstring(
        "<part><measure><attributes><clef><sign>G</sign><line>2</line></clef></attributes>"
        "<note><pitch><step>E</step><octave>4</octave></pitch></note>"
        "<note><chord/><pitch><step>G</step><octave>4</octave></pitch></note>"
        "<note><rest/></note>"
        "<note><grace/><pitch><step>A</step><octave>4</octave></pitch></note></measure></part>")
    e = emitted_by_measure(part)[0]
    assert (e.count, e.chords, e.steps) == (2, 1, [0, 2])  # E4 on the bottom line, G4 two steps up


# --- the rating -----------------------------------------------------------------------------------


def test_a_lone_disagreement_on_a_sound_measure_says_nothing():
    g = geometry([[head(200, 330), head(203, 335)], [head(300, 730)]])  # two heads where the score has one
    ev = collect(g, 4)
    emitted = [Emitted(1, 0, [0]), Emitted(0, 0, []), Emitted(1, 0, [0]), Emitted(0, 0, [])]
    found = compare(ev, emitted, adds_up=[True] * 4)
    assert [f.kind for f in found] == ["heads_more"]
    assert found[0].score < CHECK and rate(found) == []


def test_an_on_grid_extra_head_on_a_page_that_has_chords_is_worth_a_check():
    g = geometry([[head(200, 330), head(200, 340)], [head(300, 730)]])
    ev = collect(g, 4)
    emitted = [Emitted(1, 0, [0]), Emitted(2, 1, [0, 2]), Emitted(1, 0, [0]), Emitted(0, 0, [])]
    found = compare(ev, emitted, adds_up=[False, False, False, False])
    out = rate(found)
    assert [d["kind"] for d in out] == ["heads_more"]
    assert out[0]["level"] == "check" and out[0]["measure"] == 0
    assert "2 noteheads were detected here, the score has 1" in out[0]["text"]


def test_adding_up_silences_a_note_gained_in_sequence_but_says_nothing_about_a_stack():
    """A head on its own stem would have changed the arithmetic; a head stacked on an existing one
    adds no duration, so a measure that adds up is no evidence against it. Demoting on it anyway
    left the rating speaking only where the arithmetic flag already spoke (plan 0008, step 4)."""
    emitted = [Emitted(1, 0, [0]), Emitted(2, 1, [0, 2]), Emitted(1, 0, [0]), Emitted(0, 0, [])]
    apart = geometry([[head(200, 330), head(500, 340)], [head(300, 730)]])
    assert rate(compare(collect(apart, 4), emitted, adds_up=[True, False, False, False])) == []

    stacked = geometry([[head(200, 330), head(200, 340)], [head(300, 730)]])
    out = rate(compare(collect(stacked, 4), emitted, adds_up=[True, False, False, False]))
    assert [d["measure"] for d in out] == [0]
def test_a_notehead_short_speaks_too_when_nothing_argues_back():
    """A head fewer than the score has: the transformer may have invented a note. One reader is
    enough here, because nothing demotes it — measured at 0.62 precision on the increment it buys,
    with no mark on any page that came back right (plan 0008, the threshold question)."""
    g = geometry([[head(200, 330)], [head(300, 730)]])
    emitted = [Emitted(2, 1, [0, 2]), Emitted(0, 0, []), Emitted(1, 0, [0]), Emitted(0, 0, [])]
    out = rate(compare(collect(g, 4), emitted, adds_up=[False] * 4))
    assert [d["kind"] for d in out] == ["heads_fewer"]
    assert (out[0]["heads"], out[0]["notes"]) == (1, 2)
    assert out[0]["text"] == "1 notehead was detected here, the score has 2"

    # ... but a measure that adds up argues a note lost in sequence back down to silence
    assert rate(compare(collect(g, 4), emitted, adds_up=[True] * 4)) == []


def test_estimated_boundaries_silence_a_count_that_cannot_be_trusted():
    g = geometry([[head(200, 330), head(200, 340)], [head(300, 730)]], bars_ok=False)
    emitted = [Emitted(1, 0, [0]), Emitted(2, 1, [0, 2]), Emitted(1, 0, [0]), Emitted(0, 0, [])]
    assert rate(compare(collect(g, 4), emitted, adds_up=[False] * 4)) == []


def test_a_measure_where_nothing_was_detected_is_not_evidence_of_anything():
    g = geometry([[head(200, 330)], [head(300, 730)]])
    emitted = [Emitted(1, 0, [0]), Emitted(4, 0, [0, 1, 2, 3]), Emitted(1, 0, [0]), Emitted(0, 0, [])]
    assert compare(collect(g, 4), emitted, adds_up=[False] * 4) == []


# --- the page the plan is named after -------------------------------------------------------------

ANTON_EVIDENCE = DATA / "anton_evidence.json"


@pytest.mark.skipif(not ANTON_EVIDENCE.exists(), reason="needs the recorded evidence of the anton page")
def test_anton_says_nothing_although_the_pixel_stage_disagrees_on_measure_8():
    """The blot on '-ra-': the pixel stage reads two heads, the print has one and we read it right."""
    ev = json.loads(ANTON_EVIDENCE.read_text())
    part = ET.parse(DATA / "anton_score.musicxml").getroot().find("part")
    emitted = emitted_by_measure(part)
    found = compare(ev, emitted, adds_up=[True] * len(emitted))

    m8 = [f for f in found if f.measure == 7]
    # six heads, not five: the system's barlines were short by one, so the even split also pulled in
    # the last head of measure 7 — which is exactly why an estimated boundary demotes the count.
    assert m8 and m8[0].kind == "heads_more" and m8[0].detail == {"heads": 6, "notes": 4}
    assert set(m8[0].demotions) >= {"the measure's boundaries were estimated",
                                    "the page is monophonic everywhere else",
                                    "the extra head is not on the staff grid"}
    assert m8[0].score < CHECK
    assert rate(found) == []  # nothing at all on the whole page
