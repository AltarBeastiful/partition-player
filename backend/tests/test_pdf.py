"""PDF input (ADR 0009, plan 0012, step 1): what the file holds, before anything is rendered.

The fixture is the benchmark's own Gymnopédie, a two-page LilyPond engraving already in the
repository — born-digital, so the objects are all there, and two pages, which is the case a job
cannot hold today. The scanned and encrypted cases are made here from it rather than committed, so
no new binary joins the repository for them.
"""
from __future__ import annotations

import collections
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
