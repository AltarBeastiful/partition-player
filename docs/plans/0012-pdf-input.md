# Plan 0012: PDF in, and a score that is several pages

Status 2026-09-22: proposed, nothing built. Decisions in ADR 0009. Numbering agreed with the session
writing ADR 0008 / plan 0011 (per-line instruments), which touches `review.json` and
`ScoreView.tsx`; this plan leaves `review.json` alone and keeps its `ScoreView.tsx` diff to one line
of statistics.

## The problem

`POST /api/jobs` takes a photo or a MusicXML file. A PDF — the form a song actually reaches someone
in — is rejected with 415, and the user has to print it and photograph it to play it. The BACKLOG
has asked twice (`BACKLOG.md:54`): several photos merged into one MusicXML, and multi-page PDF
input split server-side.

Two things make this more than a file-type check.

**A PDF that was engraved is not a picture.** The file the user brought (*Dans le port de Lorient*,
LilyPond 2.22.1) holds its words as text already cut into syllables, its noteheads as named glyphs,
its lyric hyphens as 0.25 pt rectangles and its eight beams as four-point polygons. Reading those
off a raster, as the app does today, is throwing away what is already written and then guessing it
back — and the guesses are exactly where the lead sheets lose: 10 verses of 104 never read, 76 false
syllables, 23 false chords, and the gap between 90.5 % of syllables placed and 86.6 % with the right
text.

**A PDF is usually several pages, and a score is one page today.** One job holds one input file, one
`review.webp`, one `layout.json`, one `thumb.jpg`. A two-page song has nowhere to go.

## What is already built

| what | where | what it gives |
|---|---|---|
| the raster door | `api.py`, `jobs.py`, `pipeline/run.py` | a photo to MusicXML with chords, lyrics, doubts, evidence, layout |
| the file door | `pipeline/musicxml.py` `ingest` | the precedent: the door picks the reader, and the UI says which |
| the only consumer of read words | `geometry.json` -> `lyrics/align.place_lyrics`, `chords/place.place` | one substitution point for both stages |
| upload pixels <-> working pixels | `homr_driver.py` `Mapping` | half of the points-to-working-pixels chain; the other half is R/72 |
| measure arithmetic | `postprocess.py`, `score/check.ts` | what will catch a bad join between two pages |
| expansion over every part | `score/expand.ts:329` | as-played export already walks every `<part>` and slices them alike |
| part-0 assumptions, mapped | `session.ts:95`, `edit.ts:91/393/567`, `review.py:150` | the list to watch when a PDF brings a two- or three-staff page |

The last two rows come from the session writing ADR 0008, which walked that ground this morning.

## Measured before writing a line (2026-09-22)

On the user's file, and on `bench/RESULTS.md`:

- **The page as objects**: 6 systems of 5 staff lines, interline 4.98 pt, 44 barline strokes,
  73 noteheads by name (61 black, 12 half), 3 rests, 8 eighth flags, **8 beam quadrilaterals**
  (2.9 pt thick), 66 syllables of text in 6 rows, **28 lyric hyphens as filled rectangles**.
- **The page as pixels, through the existing pipeline** (rendered at 300 dpi, `partition-player
  recognize`): 73 notes, 3 rests, 40 measures, 1 repeat sign, 66 syllables, 1 doubt, 0 `<beam>`.
  Every pitch matches the objects. The losses against the objects: one hyphen (`Lo ri-` where the
  print has `Lo- ri-`), all eight beams, and LilyPond's measure numbers arriving at the lyric stage
  as candidates (rejected, logged in `lyrics_seen`).
- **Crispness buys nothing**: clean render vs phone photo on thirty lead sheets is 99.8/99.9 pitch,
  86.6/86.2 text right, 83.7/84.7 chords (`RESULTS.md:230`). The reason to accept a PDF is that the
  page cannot come in at all today, not that it will read better as a raster.
- **No PDF benchmark can be engraved here**: no MuseScore, no LilyPond; verovio's SVG carries
  outlines, not text, so cairosvg would make the wrong kind of PDF.

## Steps

1. **Read a PDF.** New `pipeline/pdf.py` over PyMuPDF: `pages(path)` (refuses encrypted, zero-page,
   and more than `PP_MAX_PAGES` = 20 with a sentence naming the count); `kind_of(page)` returning
   `scan` | `outlined` | `digital`; `render(page, dpi) -> Path`; `spans_of(page)` giving text with
   font, size and box in points; `marks_of(page)` giving thin rectangles and thick quadrilaterals
   from `get_drawings()`. Coordinates stay in points here; nothing knows about pixels yet.
   *Check:* unit tests on the Lorient file — 6 systems' worth of staff lines, 66 syllable spans,
   28 hyphen rectangles, 8 beam quadrilaterals, `kind_of` = `digital`. Plus a fixture made by
   rasterizing that same file into an image-only PDF, which must come back `scan`.
2. **The door, and the raster path.** `api.py` accepts a PDF by its magic bytes (`%PDF-`, never the
   content type); `jobs.Job.source` gains `pdf`; the worker renders each page at 300 dpi and calls
   `recognize()` per page, unchanged. This step alone is shippable and useful: a scanned songbook
   page stops needing a screenshot.
   *Check:* API tests for a born-digital PDF, a scanned one, an encrypted one, a 30-page one, and
   the existing 415 for `text/plain`. An end-to-end test asserting the rasterized Lorient page still
   gives 73 notes and 66 syllables.
3. **Several pages, one score.** `pipeline/pages.py` `join(results) -> tree`: measures appended in
   page order, `<attributes>` carried across each seam (a page that restates key, time and clef must
   not restate them into the music), `implicit="yes"` allowed only on page 1, measures renumbered.
   `result.json` gains `pages` (count, dpi, kind per page); `layout.json` entries gain `page`;
   `review.webp` and `thumb.jpg` become `review-1.webp`, … . `review.json` is untouched.
   *Check:* a two-page case built from the benchmark (a song whose verovio render runs to two pages),
   joined and scored against the ground truth cut to those measures; and a one-page PDF asserted to
   produce byte-identical files to today apart from `pages`.
4. **The text layer becomes the words.** `pipeline/pdf/words.py`: classify every text row by font,
   size and place — verses below a staff ordered by y, chord symbols above, measure numbers and
   page furniture dropped, title and composer to `result.json`; map points to working pixels
   (`pt * dpi / 72`, then the driver's `Mapping`); write them into `geometry.json` in place of the
   OCR's words, each with `source: "file"`. RapidOCR is not run on a `digital` page. No change in
   `align.py` or `chords/place.py`.
   *Check:* the 66 syllables land as 66 words with boxes within a pixel of the glyphs; the five
   measure numbers are dropped; the pipeline's syllables are the file's, spelled identically. Then
   the case this is really for: a PDF of a page with six or more verses, where the raster path loses
   the rows below 12 interlines and this path must not.
5. **The marks.** Hyphens and extenders from the thin rectangles between two syllable boxes, giving
   the syllabic type outright instead of the pixel probe in `lyrics/ocr.py`. Beams from the thick
   quadrilaterals: recorded per staff in `geometry.json` in ADR 0007's shape, placed on notes when
   plan 0006 lands, ignored until then.
   *Check:* `Lo- ri- ent` on both verse lines of the Lorient page (the defect the raster path has
   today); 8 beam groups recorded, 0 false.
6. **The frontend.** `Upload.tsx` accepts `application/pdf` and says "Read the PDF" with a page
   count once it is known; `Progress.tsx` counts pages ("page 2 of 4"); `ScoreView.tsx` gains one
   statistics line (*read from the file's own text* vs *read from the page*); the editor's review
   strip shows the page a measure lives on; `Library.tsx` tiles a multi-page score with its first
   page.
   *Check:* `tsc`, unit tests, then the browser at 1375 px and on the phone.
7. **The real check.** The user's own file, end to end, listened to. A scan of a songbook page. A
   multi-page song. A born-digital PDF with six verses. Then `README.md`, `BACKLOG.md:54-56` (both
   entries close), and a `bench/RESULTS.md` section that says honestly what was and was not
   measured.

## What could go wrong

- **A text layer that lies.** A scan with an OCR layer glued underneath it looks `digital` and reads
  as nonsense. Guard: the text boxes of a real engraving sit on ink and line up in rows with a
  consistent baseline; where they do not, treat the page as a scan. Worth a test with a
  Tesseract-layered scan if one can be made here.
- **The classifier meeting a page it was not measured on.** Chords printed below the staff, verses
  above it, a second song on the same page, fingerings, rehearsal marks. Every misclassification
  costs a row, so a row that cannot be placed is dropped and logged in `lyrics_seen`, which is where
  the same class of decision is already visible.
- **A join that hides a miscount.** If the engine loses a barline on page 2, the seam makes it look
  like a long measure rather than a missing one. `postprocess` will say the measure does not add up,
  which is the existing doubt — but the page index has to be in the doubt, or the user will look on
  the wrong sheet.
- **Time and memory.** N pages is N runs of the pipeline, and the server's number is 36 s a page at
  1.1 GB peak in a 3 GB container (`deploy/README.md:26`), not the 15 s of a development machine.
  Six pages is 216 s against a 300 s `PP_JOB_TIMEOUT_S`: the timeout scales per page, pages run one
  at a time, progress reports the page being read, and the 20-page cap is what keeps a scanned
  hymnal from taking the box down. Worth measuring on the server before step 7 is called done.
- **PyMuPDF.** AGPL-3.0, which matches this project, and one wheel with MuPDF inside it — the image
  grows by that much. If the licence ever becomes awkward, pypdfium2 renders and gives text but no
  drawings, which costs steps 5 and half of 4.
- **Multi-part pages.** A PDF makes a two- or three-staff page much more likely than the camera did.
  `expandScore` already handles every part; `session.ts:95`, `edit.ts:91/393/567` and
  `review.py:150` assume part 0. Measured on 2026-09-22 by the session building plan 0011: a
  photographed two-staff canon page comes back from homr as **one part with two staves** (20
  measures, 87 notes, 5 chords, about 40 s on this box), so the engine itself does not produce the
  second part — the risk arrives with imported files and with a PDF that was engraved from one.
  None of it is this plan's to fix, but step 7 is where it will be found out.
