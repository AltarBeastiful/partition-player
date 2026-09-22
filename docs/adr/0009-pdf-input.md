# ADR 0009: PDF in — the kind of page decided by its objects, the notes still read from the pixels, the words taken from the file

Date: 2026-09-22
Status: Proposed (plan 0012)

## Context

Two doors lead in: a photograph, which an engine reads (ADR 0002), and a MusicXML file, which is
opened as it is (plan 0010). A PDF is neither, and is rejected with 415: `ALLOWED_TYPES` holds five
image types (`api.py:22`), `looks_like_musicxml` holds three suffixes (`musicxml.py:21`), the picker
offers `image/*,.musicxml,.xml,.mxl` (`Upload.tsx:59`), and the string "pdf" appears nowhere in
`backend/partition_player` or `frontend/src`. `BACKLOG.md:54` has asked for it twice: several photos
merged into one MusicXML, and multi-page PDF input split server-side.

It is the obvious next file. A song that reaches someone reaches them as a PDF far more often than
as a `.mxl`, and a PDF that was engraved rather than scanned is not a picture of a page — it is the
page's objects, with the text the engraver wrote still in it. So the question this decision answers
is not whether to accept a PDF. It is **which reader a PDF deserves**, and in particular whether the
OCR that reads words off pixels should be replaced by one that handles PDFs better.

What was measured on 2026-09-22 — on the file the user brought (*Dans le port de Lorient*, LilyPond
2.22.1 through Ghostscript 9.21, A4, one page, 46 KB), and against `bench/RESULTS.md`:

- **Nothing on that page is pixels.** Three embedded subset fonts: C059-Bold for the title,
  C059-Roman for the words, Emmentaler-20 for the music. The music is *named glyphs*:
  `noteheads.s2` x61, `noteheads.s1` x12, `dots.dot` x10, `flags.u3` x8 (eighth, stem up),
  `clefs.G` x6, `accidentals.flat` x6, `rests.2` x3, the two digits of the 2/4, one breath mark.
  The staff is 30 stroked lines, six systems of five, interline 4.98 pt; 44 vertical strokes of
  exactly staff height (19.9 pt = four interlines) are the barlines.
- **The words are text, already cut into syllables**, each with a box: `Lo` `ri` `ent,`. Six rows,
  66 syllables.
- **The marks the OCR has to guess at are objects.** The lyric hyphen is a filled rectangle 0.25 pt
  tall and 1.6 to 3 pt wide — 28 of them on the page. The eight beams are four-point polygons
  2.9 pt thick (0.58 interline), 24 to 30 pt wide, each drawn twice, filled and then stroked.
- **The existing path already reads this page correctly.** Rasterized at 300 dpi and run through
  `partition-player recognize`: 73 notes, 3 rests, 40 measures, one repeat sign, 66 syllables, one
  doubt. The PDF's own objects say 73 noteheads and 3 rests. Every pitch agrees with the pitch
  derived from the glyph positions (the derivation missed the key's B-flat on three notes; the
  pipeline had them right). The 66 syllables are the 66 in the file, spelled the same.
- **What that page lost is exactly what the objects hold.** One hyphen: the second verse line came
  back `Lo ri- ent` where the first got `Lo- ri- ent`, because the extender is looked for in the
  pixels after each word (`lyrics/ocr.py`). No beams: the score carries zero `<beam>` elements
  against eight in the print. And LilyPond's measure numbers (6, 11, 16, 21, 31) arrived at the
  lyric stage as candidate syllables, rejected by geometry and recorded in `lyrics_seen` ("does not
  span the notes", "in the chord band of the next system").
- **Crispness is not what is missing.** On the thirty lead sheets the clean engraved render and its
  phone-photo copy score level: pitch 99.8 % against 99.9 %, pitch and duration 99.5 % against
  99.7 %, syllables placed 90.5 % against 89.9 %, text right 86.6 % against 86.2 %, chords 83.7 %
  against 84.7 % (`RESULTS.md:230`, "nothing here is an OCR-legibility problem"). Rendering a PDF at
  300 dpi into the existing path is worth approximately nothing in accuracy — and is still worth
  building, because today that page cannot come in at all.
- **Where the lead-sheet loss actually is.** Of 5,819 syllables, 90.5 % land on a note and 86.6 %
  land with the right text; the gap is OCR spelling ("accents in tiny renders, *Jo* read as *To*",
  `RESULTS.md:195`). 76 syllables are false. 10 verses of 104 are never read, and the cause is
  measured: the lyric band runs to a fixed 12.0 interlines below the staff while the verse rows of
  those pages sit 2.2 apart, so a sixth verse starts near 13, outside the image the OCR is given
  (`RESULTS.md:246`). 870 chord symbols come back 83.7 % right with 23 false.
- **The engines were surveyed once already** (ADR 0004 survey, section 3): Tesseract weaker than
  PP-OCR on photos, docTR a solid fallback at 60 to 100 MB a model, EasyOCR no advantage, Surya and
  Florence-2 too heavy for the box, vision LLMs "excellent on accents and verse structure, boxes
  unreliable" — which is why the language model fixes words and never moves them
  (`lyrics/polish.py`).
- **The substitution point already exists.** RapidOCR runs inside the driver
  (`homr_driver.py:243-289`) and its words are serialized per staff into `geometry.json`;
  `place_lyrics(tree, geometry)` and the chord `place(tree, geometry)` read nothing else.
- **The page and its raster are related by a known number.** Rendered at R dpi, an upload pixel is a
  PDF point times R/72, and the driver already maps upload pixels to working pixels. Nothing has to
  be registered or estimated.
- **Not measured, and it matters**: what share of real score PDFs are born-digital rather than scans
  or outlined vectors. There is no MuseScore and no LilyPond on this machine (found twice today,
  once by the session writing ADR 0008), so the thirty benchmark `.mxl` lead sheets cannot be
  engraved into a PDF set here: verovio's SVG carries glyph outlines, not text, so cairosvg would
  manufacture the wrong kind of PDF and flatter the raster path.

## Decision

1. **The door takes a PDF, and the kind of page is decided by its objects.** Per page, three kinds:
   a **scan** (an image and nothing else), an **outlined vector** (paths, no text), and a
   **born-digital** page (text spans, and usually a music font). The test is what the page yields,
   not the producer string, not the suffix, not the content type. Scans and outlined pages take the
   raster path unchanged. Born-digital pages take the raster path *and* their own text. Every
   uncertainty falls back to the raster path, so a misjudged PDF is never worse than a photograph of
   the same page.
2. **A PDF is a recognition, not an import.** Plan 0010's rule — "an import is not a recognition",
   nothing repaired, arithmetic only `info` — belongs to a document whose author wrote the notes. A
   PDF's notes are being read off a picture by a model, so the whole recognition applies: padding,
   repairs, doubts, evidence, the review image, the layout. The upbeat rules stay where they are, on
   the import path only.
3. **The notes are read from pixels by homr, at a fixed dpi.** Not by a second, glyph-level engine.
   The notes are not where the loss is (99.8 % and 99.5 % on lead sheets), and a vector reader would
   be an engine per engraver family — Emmentaler names, SMuFL code points, Maestro, Opus — each with
   its own stem, beam, dot and voice rules, to maintain beside homr. Revisit when the lead-sheet
   numbers stop being 99.8 %, or for the piano pages (87.4 % pitch), and not before.
4. **On a born-digital page the words come from the file, and RapidOCR is not run on it.** This is a
   substitution inside `geometry.json`, not an engine swap: the lyric `words` per staff and the
   chord band tokens are written from the PDF's text spans, and `place_lyrics` and the chord `place`
   never learn where they came from. RapidOCR keeps the pixel door and stays exactly as it is —
   changing it would chase the ~4 points of spelling that the language-model polish already
   addresses, at 60 to 100 MB and a slower page.
5. **What a piece of text is, is decided by font, size and place — and there is no band.** Rows
   below a staff in the page's lyric font are verses, ordered by y; a row above in the chord font is
   chord symbols; the small italic or smaller-size numbers at the left of a system are measure
   numbers and are dropped; the first page's largest text is the title and its right-aligned
   neighbour the composer. Dropping the fixed band is what recovers the sixth and eighth verses,
   which no recogniser can read because they are never in the image today.
6. **The marks that are objects are taken as objects.** A hyphen or an extender between two
   syllables is a thin filled rectangle on the lyric baseline, so the syllabic type is read, not
   inferred from ink. A beam is a thick quadrilateral meeting two stems, which is what ADR 0007's
   pixel rule reconstructs; when ADR 0007 lands, the PDF door feeds it groups instead of finding
   them, and until then it records them and does nothing.
7. **Certainty is not a confidence.** A word taken from the file carries `source: "file"`, not
   `confidence: 1.0`. The doubts and the evidence rating (plan 0008) weigh readings against each
   other, and a 1.0 poured into that arithmetic would silently outvote every measurement. A syllable
   from the file can still be doubted for *where* it was placed; it is never doubted for its
   spelling.
8. **A PDF is several pages, so a score becomes several pages.** One job is still one score, and the
   score is the pages in order: measures appended, attributes carried across the seam, a pickup only
   on page 1, measures renumbered. `layout.json` entries gain a page index, `review.webp` and
   `thumb.jpg` become one per page, `result.json` gains a `pages` list. `review.json` does not
   change. A cap (`PP_MAX_PAGES`, default 20) refuses a whole songbook with a sentence that says how
   many pages it holds. This is the same work `BACKLOG.md:54` wants for several photos of one piece,
   and the PDF is what forces it.
9. **One dependency, no system package.** PyMuPDF: rasterizing (`get_pixmap(dpi=…)`), text with font
   name, size and box (`get_text("rawdict")`) and the vector drawings (`get_drawings()`) in one
   wheel, AGPL-3.0, which is this project's licence. The Docker image gains nothing to `apt-get`.

## Alternatives considered

- **Move to an OCR that reads PDFs better.** A category error worth naming, because it is the
  question that started this: `pdftotext` and PyMuPDF are not recognisers, they copy out objects.
  For a born-digital page the right number of OCR engines is zero, and for a scan the survey's
  comparison (ADR 0004 survey, section 3) plus "the photo scores level with the clean render" say
  the recogniser is not the bottleneck. RapidOCR stays.
- **A glyph-level reader for born-digital pages** (pitch from notehead y against the staff lines,
  duration from glyph names, flags, beams and dots). Tempting — the probe above got all 73 pitches
  of the user's page from the glyphs alone — and it is the only path that would move the piano
  pages. It is also a second OMR engine, per engraver family, to keep correct against homr's. Not
  now; decision 3 says when.
- **Send PDFs to Audiveris**, which takes them natively. It is the fallback engine, not deployed
  (`README.md`), and it would bring its own note reading, which cannot be laid onto homr's notes —
  the same reason ADR 0007 rejected its beams.
- **Treat every PDF as a scan** (rasterize page 1, done, about twenty lines). This is genuinely
  worth shipping and is step 1 of plan 0012 — but stopping there leaves the text layer, the
  hyphens, the beams and the lost verses on the table for exactly the pages where they are free.
- **Ask for a MusicXML export instead.** Plan 0010's door, already open, always better when it
  exists. It usually does not: the PDF is what the user has.
- **An external PDF-to-MusicXML service.** Cost, latency, and a page of someone's music leaving the
  box. Against ADR 0001.

## Consequences

- One Python dependency and no system package; homr stays at 0.7, RapidOCR at 3.9, OSMD at 1.9.x.
- Jobs gain a page dimension. A PDF of N pages runs the pipeline N times: about 15 s a page on a
  development machine (`RESULTS.md:265`) but **36 s on the server**, measured, with the container
  capped at 3 GB and running one job at a time (`deploy/README.md:26`). Six pages is around 216 s
  against a 300 s `PP_JOB_TIMEOUT_S`, so the timeout must scale per page and the cap of decision 8
  is load-bearing — a twenty-page PDF is twelve minutes of one core, not a detail.
- `geometry.json` grows a `source` on each word (`ocr` or `file`) and, on born-digital pages, the
  hyphen and beam objects. The lyric and chord stages are untouched.
- The editor shows the page a measure lives on; `ScoreView.tsx` gains a line in the statistics. The
  per-line work of ADR 0008 touches the same file and `review.json`, which this decision leaves
  alone.
- **The benchmark cannot follow yet.** There is no PDF set and no engraver here to make an honest
  one, so the first numbers come from real files, one at a time, and the claim "the text layer is
  exact" is true by construction rather than measured. What can be measured here without an
  engraver is the negative: that a rasterized PDF scores what the equivalent render scores today.
- Not covered, and said so: PDFs with a text layer that lies (a scan with a bad OCR layer glued
  under it — detected by text boxes that do not sit on the ink, and treated as a scan), encrypted
  PDFs, pages rotated by `/Rotate`, two songs on one page, and PDFs whose lyrics are drawn as
  outlines while the chord symbols are text (the classifier is per row, so this works out).
