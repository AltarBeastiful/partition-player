"""PDF input (ADR 0009, plan 0012, step 1): what the file holds, before anything is rendered.

The fixture is the benchmark's own Gymnopédie, a two-page LilyPond engraving already in the
repository — born-digital, so the objects are all there, and two pages, which is the case a job
cannot hold today. The scanned and encrypted cases are made here from it rather than committed, so
no new binary joins the repository for them.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from partition_player.pipeline import pdf

ROOT = Path(__file__).resolve().parents[2]
ENGRAVED = ROOT / "bench" / "samples" / "gymnopedie1" / "gymnopedie_1-a4.pdf"


@pytest.fixture
def scanned(tmp_path: Path) -> Path:
    """The same page as a picture of itself: one image, no text, no vector marks."""
    out = tmp_path / "scan.pdf"
    with pymupdf.open(ENGRAVED) as src:
        image = src[0].get_pixmap(dpi=150)
        doc = pymupdf.open()
        page = doc.new_page(width=src[0].rect.width, height=src[0].rect.height)
        page.insert_image(page.rect, pixmap=image)
        doc.save(out)
        doc.close()
    return out


def test_an_engraved_pdf_is_read_as_the_objects_it_holds():
    pages = pdf.pages(ENGRAVED)
    assert len(pages) == 2
    assert [p.index for p in pages] == [0, 1]
    assert all(p.kind == "digital" for p in pages)
    assert (round(pages[0].width_pt), round(pages[0].height_pt)) == (595, 842)  # A4 in points


def test_the_marks_of_an_engraved_page_are_named_by_their_shape():
    with pymupdf.open(ENGRAVED) as doc:
        marks = pdf.marks_of(doc[0])
    kinds = collections.Counter(m.kind for m in marks)
    # every staff line is one long stroke, and a page of piano music has them in fives
    assert kinds["staff_line"] >= 10
    assert all(m.width > 100 and m.height <= 1 for m in marks if m.kind == "staff_line")
    # barlines and stems are both thin and upright; only the op that drew them tells them apart
    assert kinds["barline"] > 0 and kinds["stem"] > 0
    assert all(m.height > m.width for m in marks if m.kind in ("barline", "stem"))
    # a hyphen or a ledger line: thin, and short enough not to be a staff line
    assert all(1 < m.width <= 100 and m.height <= 1.5 for m in marks if m.kind == "thin")


def test_a_music_font_is_read_as_glyphs_and_never_as_words():
    with pymupdf.open(ENGRAVED) as doc:
        spans = pdf.spans_of(doc[0])
    music = [s for s in spans if s.music]
    words = [s for s in spans if not s.music and s.text.strip()]
    assert len(music) > 100                      # the notes themselves, as characters
    assert all(pdf.is_music_font(s.font) for s in music)
    assert any("Satie" in s.text for s in words)  # and the words are the words
    assert all(s.x1 >= s.x0 and s.y1 >= s.y0 for s in spans)


def test_a_scan_is_a_scan_however_it_was_made(scanned: Path):
    pages = pdf.pages(scanned)
    assert len(pages) == 1
    assert pages[0].kind == "scan"


def test_a_text_layer_over_a_picture_is_still_a_scan(scanned: Path, tmp_path: Path):
    """An OCR layer glued under a scan reads as nonsense; the marks decide, not the text."""
    out = tmp_path / "ocr.pdf"
    with pymupdf.open(scanned) as doc:
        doc[0].insert_text((72, 72), "Lorem ipsum dolor", fontsize=11)
        doc.save(out)
    assert pdf.pages(out)[0].kind == "scan"


def test_a_page_rendered_at_a_resolution_has_that_many_pixels(tmp_path: Path):
    with pymupdf.open(ENGRAVED) as doc:
        image = pdf.render(doc[0], 150, tmp_path / "page-1.png")
    assert image.exists()
    with Image.open(image) as rendered:
        assert abs(rendered.width - 595.28 * pdf.scale_of(150)) <= 1   # the renderer rounds up
    assert pdf.scale_of(300) == pytest.approx(300 / 72)

    # the resolution is bounded, so nothing asks for a page the size of a wall
    with pymupdf.open(ENGRAVED) as doc:
        huge = pdf.render(doc[0], 5_000, tmp_path / "huge.png")
    with Image.open(huge) as rendered:
        assert abs(rendered.width - 595.28 * pdf.scale_of(pdf.MAX_RENDER_DPI)) <= 1


def test_a_file_that_cannot_be_read_says_why(tmp_path: Path):
    not_a_pdf = tmp_path / "x.pdf"
    not_a_pdf.write_bytes(b"not a pdf at all")
    with pytest.raises(pdf.PdfError):
        pdf.pages(not_a_pdf)

    empty = tmp_path / "empty.pdf"
    empty.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF\n"
    )
    with pytest.raises(pdf.PdfError):   # no pages, however the reader phrases it
        pdf.pages(empty)

    locked = tmp_path / "locked.pdf"
    with pymupdf.open(ENGRAVED) as src:
        src.save(locked, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="secret")
    with pytest.raises(pdf.PdfError, match="password"):
        pdf.pages(locked)

    long = tmp_path / "long.pdf"
    doc = pymupdf.open()
    for _ in range(pdf.MAX_PAGES + 1):
        doc.new_page()
    doc.save(long)
    doc.close()
    with pytest.raises(pdf.PdfError, match=f"{pdf.MAX_PAGES} is the most"):
        pdf.pages(long)


def test_the_door_decides_by_the_bytes():
    assert pdf.looks_like_pdf(b"%PDF-1.7\n...")
    assert not pdf.looks_like_pdf(b"<score-partwise>")
    assert not pdf.looks_like_pdf(b"PK\x03\x04")


# ---- the words the file already holds (plan 0012, steps 4 and 5) ---------------------------------

from partition_player.pipeline import pdf_words   # noqa: E402


def span(text: str, x0: float, y0: float, width: float = 20, height: float = 8, font: str = "C059-Roman") -> pdf.Span:
    return pdf.Span(text=text, font=font, size=12.0, x0=x0, y0=y0, x1=x0 + width, y1=y0 + height)


def geometry(tmp_path: Path, *, staves: list[dict] | None = None, systems: list[dict] | None = None) -> Path:
    """A geometry file with an identity chain, so points and working pixels differ only by the dpi."""
    out = tmp_path / "geometry.json"
    out.write_text(json.dumps({
        "image": [1000, 1000],
        "chain": {"crop": [0, 0], "resize": [1.0, 1.0], "scale": 1.0, "k": 1.0},
        "systems": systems if systems is not None else [{"index": 0, "unit": 10.0, "min_x": 0, "max_x": 1000, "top_y": 100.0, "tokens": []}],
        "staves": staves if staves is not None else [{"index": 0, "system": 0, "unit": 10.0, "min_x": 0, "max_x": 1000,
                                                      "top_y": 100.0, "bottom_y": 140.0, "words": []}],
    }))
    return out


def test_points_become_the_working_image_s_pixels():
    chain = {"crop": [10, 20], "resize": [0.5, 0.5], "scale": 1.0}
    x, y = pdf_words.to_working(chain, 72, 100, 200)      # 72 dpi: a point is a pixel
    assert (x, y) == ((100 - 10) * 0.5, (200 - 20) * 0.5)
    x, _ = pdf_words.to_working({"crop": [0, 0], "resize": [1.0, 1.0], "scale": 1.0}, 300, 72, 72)
    assert x == pytest.approx(300.0)                       # an inch at 300 dpi


def test_the_syllables_under_a_staff_become_its_words(tmp_path: Path):
    file = geometry(tmp_path)
    layer = pdf_words.TextLayer(spans=[span("Dans", 100, 160), span("le", 140, 160), span("port", 180, 160)], marks=[], dpi=72)
    placed = pdf_words.apply(file, layer)
    assert placed["syllables"] == 3
    words = json.loads(file.read_text())["staves"][0]["words"]
    assert [w["text"] for w in words] == ["Dans", "le", "port"]
    assert all(w["source"] == "file" for w in words)
    assert words[0]["y_units"] == pytest.approx((164 - 140) / 10)   # units below the bottom staff line


def test_a_hyphen_the_engraver_drew_is_put_back_between_its_syllables(tmp_path: Path):
    file = geometry(tmp_path)
    layer = pdf_words.TextLayer(
        spans=[span("Lo", 100, 160, width=20), span("ri", 130, 160, width=20), span("ent", 160, 160, width=20)],
        marks=[pdf.Mark(kind="thin", x0=122, y0=163, x1=127, y1=163.3)],
        dpi=72)
    pdf_words.apply(file, layer)
    words = json.loads(file.read_text())["staves"][0]["words"]
    assert [w["text"] for w in words] == ["Lo", "-", "ri", "ent"]


def test_a_long_mark_holds_the_syllable_instead_of_joining_it(tmp_path: Path):
    file = geometry(tmp_path)
    layer = pdf_words.TextLayer(
        spans=[span("vent", 100, 160, width=20), span("Dans", 200, 160, width=20)],
        marks=[pdf.Mark(kind="thin", x0=122, y0=163, x1=195, y1=163.3)],   # an extender line
        dpi=72)
    pdf_words.apply(file, layer)
    words = json.loads(file.read_text())["staves"][0]["words"]
    assert [w["text"] for w in words] == ["vent", "Dans"]
    assert words[0]["extend"] is True


def test_a_measure_number_over_a_staff_is_dropped_and_said(tmp_path: Path):
    file = geometry(tmp_path)
    layer = pdf_words.TextLayer(spans=[span("17", 100, 80, width=8), span("Gm", 200, 80)], marks=[], dpi=72)
    placed = pdf_words.apply(file, layer)
    tokens = json.loads(file.read_text())["systems"][0]["tokens"]
    assert [t["text"] for t in tokens] == ["Gm"]
    assert {d["text"] for d in placed["dropped"]} == {"17"}
    assert placed["chords"] == 1


def test_a_span_in_the_gap_belongs_to_the_staff_it_is_nearest(tmp_path: Path):
    """The gap between two systems is under one staff and over the next; the nearer edge wins."""
    file = geometry(
        tmp_path,
        staves=[{"index": 0, "system": 0, "unit": 10.0, "min_x": 0, "max_x": 1000, "top_y": 100.0, "bottom_y": 140.0, "words": []},
                {"index": 1, "system": 1, "unit": 10.0, "min_x": 0, "max_x": 1000, "top_y": 240.0, "bottom_y": 280.0, "words": []}],
        systems=[{"index": 0, "unit": 10.0, "min_x": 0, "max_x": 1000, "top_y": 100.0, "tokens": []},
                 {"index": 1, "unit": 10.0, "min_x": 0, "max_x": 1000, "top_y": 240.0, "tokens": []}])
    layer = pdf_words.TextLayer(
        spans=[span("seau", 100, 160),     # 2 units under staff 1, 7.6 over system 2: a syllable
               span("Am", 100, 222)],      # 1.8 over system 2, 8.2 under staff 1: a chord
        marks=[], dpi=72)
    pdf_words.apply(file, layer)
    read = json.loads(file.read_text())
    assert [w["text"] for w in read["staves"][0]["words"]] == ["seau"]
    assert read["staves"][1]["words"] == []
    assert [t["text"] for t in read["systems"][1]["tokens"]] == ["Am"]
    assert read["systems"][0]["tokens"] == []


def test_the_beams_of_the_page_are_kept_for_when_they_are_wanted(tmp_path: Path):
    file = geometry(tmp_path)
    layer = pdf_words.TextLayer(spans=[], marks=[pdf.Mark(kind="beam", x0=100, y0=110, x1=130, y1=113)], dpi=72)
    placed = pdf_words.apply(file, layer)
    assert placed["beams"] == 1
    assert json.loads(file.read_text())["beams"][0]["x0"] == pytest.approx(100.0)


def test_a_span_holding_a_whole_line_is_cut_into_its_words(tmp_path: Path):
    """LilyPond hands a footer line as one object; the rules downstream were written against words."""
    file = geometry(tmp_path)
    prose = "Placed in the public domain by the typesetter free to distribute and perform"
    layer = pdf_words.TextLayer(spans=[span(prose, 100, 160, width=600)], marks=[], dpi=72)
    placed = pdf_words.apply(file, layer)
    words = json.loads(file.read_text())["staves"][0]["words"]
    assert len(words) == len(prose.split()) == placed["syllables"]
    assert words[0]["text"] == "Placed" and words[-1]["text"] == "perform"
    assert words[0]["x_left"] == pytest.approx(100.0)
    assert words[-1]["x_right"] == pytest.approx(700.0)
    assert all(a["x_right"] <= b["x_left"] + 1e-9 for a, b in zip(words, words[1:]))
