"""Several pages, one score (plan 0012, steps 2 and 3): the door, the page loop, and the join.

The join is where a two-page song either becomes one piece or becomes nonsense, so the arithmetic is
held to exact numbers here on hand-made pages — a restated key signature, a second page counting
quarters differently, a pickup mark that belongs to the piece and not to the sheet — and the door is
walked end to end with the fake engine on the repository's own two-page engraving.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ROOT
from partition_player.pipeline import pages
from test_api import wait_done

ENGRAVED = ROOT / "bench" / "samples" / "gymnopedie1" / "gymnopedie_1-a4.pdf"


def page(divisions: int = 1, *, key: int = 0, beats: str = "4/4", implicit: bool = False, note: str = "C") -> ET.ElementTree:
    """A one-measure page, stating what every engraved page states at its top."""
    beat, beat_type = beats.split("/")
    xml = f"""<score-partwise version="4.0">
      <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
      <part id="P1">
        <measure number="1"{' implicit="yes"' if implicit else ''}>
          <attributes><divisions>{divisions}</divisions><key><fifths>{key}</fifths></key>
            <time><beats>{beat}</beats><beat-type>{beat_type}</beat-type></time>
            <clef><sign>G</sign><line>2</line></clef></attributes>
          <note><pitch><step>{note}</step><octave>4</octave></pitch><duration>{4 * divisions}</duration><type>whole</type></note>
        </measure>
      </part></score-partwise>"""
    return ET.ElementTree(ET.fromstring(xml))


def measures(tree: ET.ElementTree) -> list[ET.Element]:
    return tree.getroot().find("part").findall("measure")


def test_the_pages_become_one_part_numbered_from_one():
    joined = pages.join_scores([page(note="C"), page(note="D"), page(note="E")])
    got = measures(joined)
    assert [m.get("number") for m in got] == ["1", "2", "3"]
    assert [m.find("note/pitch/step").text for m in got] == ["C", "D", "E"]


def test_what_is_in_force_is_not_restated_into_the_middle_of_the_music():
    joined = pages.join_scores([page(), page()])
    second = measures(joined)[1]
    assert second.find("attributes") is None      # same key, same time, same clef: nothing to say


def test_what_actually_changed_at_a_page_top_is_kept():
    joined = pages.join_scores([page(), page(key=-2, beats="3/4")])
    second = measures(joined)[1]
    attributes = second.find("attributes")
    assert attributes is not None
    assert attributes.find("key/fifths").text == "-2"
    assert attributes.find("time/beats").text == "3"
    assert attributes.find("clef") is None        # the clef did not change, so it is not restated


def test_a_second_page_that_counts_quarters_differently_is_scaled_to_the_common_count():
    joined = pages.join_scores([page(divisions=2), page(divisions=3)])
    got = measures(joined)
    # six divisions a quarter holds both pages exactly; every duration is scaled with it
    assert joined.getroot().find("part/measure/attributes/divisions").text == "6"
    assert [m.find("note/duration").text for m in got] == ["24", "24"]
    assert got[1].find("attributes") is None      # and the restated divisions say nothing new


def test_a_pickup_belongs_to_the_piece_and_not_to_a_sheet_of_paper():
    joined = pages.join_scores([page(implicit=True), page(implicit=True)])
    got = measures(joined)
    assert got[0].get("implicit") == "yes"        # the piece does begin on an upbeat
    assert got[1].get("implicit") is None         # but page 2 does not


def test_everything_measure_numbered_is_shifted_by_the_pages_before_it():
    results = [
        {"stats": {"measures": 4, "notes": 10, "doubts": [{"measure": 2, "kind": "overfull"}], "warnings": ["a"]}},
        {"stats": {"measures": 3, "notes": 7, "doubts": [{"measure": 0, "kind": "underfull"}], "warnings": ["b"]}},
    ]
    stats = pages.join_stats(results, [4, 3])
    assert stats["measures"] == 7 and stats["notes"] == 17
    assert [d["measure"] for d in stats["doubts"]] == [2, 4]
    assert stats["warnings"] == ["a", "b"]

    layouts = [
        {"width": 100, "height": 200, "systems": [{"index": 0, "measures": [{"index": 0}, {"index": 1}]}]},
        {"width": 100, "height": 200, "systems": [{"index": 0, "measures": [{"index": 0}]}]},
    ]
    layout = pages.join_layout(layouts, [4, 3])
    assert [s["page"] for s in layout["systems"]] == [0, 1]
    assert [s["index"] for s in layout["systems"]] == [0, 1]
    assert [m["index"] for s in layout["systems"] for m in s["measures"]] == [0, 1, 4]


def test_the_evidence_of_every_page_is_laid_end_to_end():
    joined = pages.join_evidence([{"heads": [["a"], ["b"]], "unit": 20}, {"heads": [["c"]], "unit": 21}])
    assert joined["heads"] == [["a"], ["b"], ["c"]]
    assert joined["unit"] == 20
    assert pages.join_evidence([None, None]) is None


def test_a_pdf_comes_in_through_the_door_and_is_read_page_by_page(settings):
    """The whole way: a two-page engraving posted as a PDF, read by the fake engine per page."""
    from partition_player.api import create_app

    with TestClient(create_app(settings)) as client:
        r = client.post("/api/jobs", files={"file": ("song.pdf", ENGRAVED.read_bytes(), "application/pdf")})
        assert r.status_code == 202, r.text
        job = wait_done(client, r.json()["id"], timeout=60)
        assert job["status"] == "done", job
        assert job["source"] == "pdf"
        # the fake engine answers the same 19 measures for each page, so the join is 38
        assert job["result"]["stats"]["measures"] == 38
        score = client.get(f"/api/jobs/{job['id']}/score.musicxml")
        assert score.status_code == 200
        assert len(ET.fromstring(score.content).find("part").findall("measure")) == 38
        assert client.get(f"/api/jobs/{job['id']}/thumb.jpg").status_code == 200

    out = Path(settings.jobs_dir) / job["id"]
    info = json.loads((out / "result.json").read_text())
    assert [p["index"] for p in info["pages"]] == [0, 1]
    assert all(p["kind"] == "digital" and p["dpi"] == 300 for p in info["pages"])
    assert [p["measures"] for p in info["pages"]] == [19, 19]
    assert (out / "review-1.webp").exists() and (out / "review-2.webp").exists()
    review = json.loads((out / "review.json").read_text())
    assert review["revision"] == 1 and review["lines"] == [] and review["unders"] == []


def test_a_pdf_that_cannot_be_read_fails_with_its_own_sentence(settings, tmp_path: Path):
    from partition_player.api import create_app

    broken = b"%PDF-1.4\nbut not really\n"
    with TestClient(create_app(settings)) as client:
        r = client.post("/api/jobs", files={"file": ("x.pdf", broken, "application/pdf")})
        assert r.status_code == 202          # it is taken in, and fails where it is read
        job = wait_done(client, r.json()["id"])
        assert job["status"] == "failed"
        assert "PDF" in (job["error"] or "") or "pdf" in (job["error"] or "")


def test_a_text_file_is_still_refused_at_the_door(settings):
    from partition_player.api import create_app

    with TestClient(create_app(settings)) as client:
        r = client.post("/api/jobs", files={"file": ("x.txt", b"hello", "text/plain")})
        assert r.status_code == 415 and "PDF" in r.json()["error"]


def test_a_piano_page_does_not_restate_its_braces_at_the_seam():
    """`staves` and `part-symbol` are restated at the top of page 2 exactly as the key is."""
    def grand(note: str) -> ET.ElementTree:
        return ET.ElementTree(ET.fromstring(f"""<score-partwise version="4.0">
          <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
          <part id="P1"><measure number="1">
            <attributes><divisions>1</divisions><key><fifths>0</fifths></key>
              <time><beats>3</beats><beat-type>4</beat-type></time><staves>2</staves>
              <part-symbol>brace</part-symbol><clef number="1"><sign>G</sign><line>2</line></clef>
              <clef number="2"><sign>F</sign><line>4</line></clef></attributes>
            <note><pitch><step>{note}</step><octave>4</octave></pitch><duration>3</duration><type>half</type><dot/></note>
          </measure></part></score-partwise>"""))

    joined = pages.join_scores([grand("C"), grand("D")])
    assert measures(joined)[1].find("attributes") is None
