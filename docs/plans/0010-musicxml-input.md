# Plan 0010: MusicXML in

Status 2026-09-21: done, all six steps plus the *Duplicate as played* button asked for on the day.
Backend 100 tests (17 new: `tests/test_musicxml.py`, the API's two doors, the named upload, the
upbeat rules), frontend 88 (3 new), `tsc` clean.
Checked in the browser at 1375 px on three real files: the Anton export the user made in MuseScore
(19 measures, 10 chords, 55 syllables, the note names it carries as `<words>` drawn above the staff
where the file puts them, "Every measure adds up" in the editor and no photo strip offered);
`es_alfonsina_y_el_mar.mxl`, whose two voltas the automatic form expands into *m. 1–9, Verse 1,
Verse 2* with nothing entered by hand — 34 printed measures, 45 as played, the thing the camera door
cannot do; and a voice-and-piano page (`de_beethoven_mollys_abschied`, 2 parts, 5 stacked verses,
11 measures to 55), which renders with its brace, slurs and dynamics and plays with the cursor
crossing both staves.

What the building changed, from the decisions below:

- **The first measure needed a second shape.** "A short first measure is a pickup" was the rule until
  it silenced the live check on measure 1 for everyone, including the user who has just deleted a
  note there (an existing test caught it within the hour). So the first measure is excused only when
  the document says `implicit="yes"` (6 of the 20 pages that start short) or when the last measure
  completes it (12 more). Two pages of 60 are left saying "a quarter in a 4/4 measure", which is
  what they hold.
- **46 of the 48 short measures**, not 48: the two above are the difference between the rule as
  planned and the rule as built.
- **`postprocess` split in two.** `repair=False` is a different walk, not a flag inside the old one:
  `_read_part` counts, notes the repeat signs without moving a barline, and says what does not add
  up; `_repair_part` is the recognition path, unchanged line for line.
- **The upload's kind is decided twice**, once in the browser (`isScoreFile`, to say "Open the
  score" and skip the image preview) and once on the server by the bytes. The browser's content type
  is `application/octet-stream` for `.musicxml` and `.mxl` alike, so it is never trusted.

## The problem

Everything the app does after recognition — the sheet, the piano, the cursor, the loop, the note
names, the chords, the lyrics panel, the editor, the form, the written-out score of plan 0009 — works
on a MusicXML document. Only one door leads in, and it is a camera: `POST /api/jobs` takes a JPEG and
nothing else (`api.py:20`, `ALLOWED_TYPES`).

So a page that is *already* a file has to be printed and photographed to be played, and a page the
engine misreads has no better path: the user who fixes it in MuseScore cannot bring it back. The
thirty songbook pages of `bench/songs/leadsheets/` are `.mxl` files; the four Anton exports in the
repository root are `.musicxml` and `.mxl`; neither can be opened by the product they were made for.

What an imported file brings that a photographed one never had:

- **It is right.** No padding, no doubt, no second reading: the notes are the author's.
- **It has the signs the engine cannot read.** Voltas above all: 8 of the 30 benchmark songs have
  endings, all entered by hand today (`BACKLOG.md`), and every one of them is in the file. OSMD
  expands them, so `defaultPasses` (`form.ts:56`) gets the real form for free.
- **It is instant.** No engine, no queue worth the name: a page is ready in milliseconds.

## What is already built

| what | where | what it gives |
|---|---|---|
| measure arithmetic | `postprocess.py` `measures`, `_measure_filled` | the length of every measure against its time signature |
| the live check | `score/check.ts`, `postprocess.inspect` | the same arithmetic in the browser and on save |
| lyric placements from a document | `lyrics/inject.py` `read_placements` | the Lyrics panel, with no OCR involved |
| the editor's files | `run.py` `write_review` | `original.musicxml`, `review.json`, and (with a photo) `layout.json` |
| a score without a photo | `review.state`, `session.hasImage` | the editor already draws itself when there is no image |
| the job store | `jobs.py` | one input file per job, a worker, the library |

Measured before writing a line (`postprocess` run over both benchmark corpora, 60 authored files):

- **All 60 pass unchanged.** 30 lead sheets (817 measures) and 30 voice-and-piano pages (555
  measures) parse, hold notes, and come out of `postprocess` with no failure.
- **Short measures are upbeats, not mistakes.** 40 of the 817 lead-sheet measures and 8 of the 555
  piano ones are shorter than their time signature; 20 pages start on one. Every one of them is
  either a pickup (the file marks 6 of them `implicit="yes"`) or is completed exactly by the measure
  next to it, or by the page's other end (`en_clementine` m9+m10 = 2 + 1 = 3/4). Padding these would
  put a silent beat into the middle of every song. The rule as built excuses 46 of the 48 and leaves
  two unmarked pickups (`en_camptown_races`, `it_mattinata`) to say what they hold.
- **What is left after those rules is worth reading:** 2 overfull measures in 60 files, both in the
  source (`en_home_on_the_range` m29 holds 6 quarters of 3/4).
- **The same rule must not touch a recognized page.** In homr's own output it would explain 68 of
  100 short lead-sheet measures and 144 of 488 piano ones — because a missed barline splits one
  measure into two halves that add up perfectly. That is a doubt we want, and the measured precision
  of `bench/songs/doubts.py` rests on it.
- **Every file knows its name.** `credit-type` of `title` is present in 30 of 30 benchmark files, and
  in the Anton exports: "Anton, Yvan, Boris et moi" beats `anton_paroles_et_notes_fr`.

## Decisions

1. **An import is not a recognition.** No preprocess, no engine, no chord OCR, no lyric OCR, no
   evidence, no photo, no layout. The pipeline it runs is: unwrap, validate, check the arithmetic,
   read the placements that are already in the document.
2. **Nothing is repaired.** No rest is padded in, no rest-chord is unmerged, no barline is moved:
   those three repairs exist for what an engine does to a page, and doing them to an authored file
   is damage. The document is stored as it arrived.
3. **The arithmetic that survives is `info`, never `wrong`.** A measure of an imported page that does
   not add up is the author's business, so it is said once, quietly, in the same place recognition
   doubts are said. Repeat signs keep the `info` note they already get.
4. **The live check learns the two upbeat rules**, in `check.ts` and in `postprocess.inspect`, for
   every score whatever its origin. It is safe because the live check never sees raw engine output:
   `postprocess` has already padded a recognized page before anyone looks. Without this, opening the
   editor on an imported songbook page would light up four "places to check" that are all correct
   notation.
5. **The job says where it came from.** `Job.source` is `image` or `musicxml`; the UI stops offering
   a photo, the progress steps stop talking about reading notes, and the statistics line says
   *imported* instead of *read by homr in 11 s*.
6. **The name comes from the file, not the file name.**
7. **The type is decided by the bytes**, not by what the browser claims: `PK` plus a `.mxl` suffix is
   a container, a leading `<` is XML. Browsers send `application/octet-stream` for both.
8. **One page at a time, still.** A multi-part orchestral file is accepted if it survives the same
   validation — nothing here is part-aware — but nothing is promised beyond the one and two-staff
   pages the app is built for. PDF stays out (`BACKLOG.md`).

## Steps

1. **Read the file.** `pipeline/musicxml.py`: `read_document(path) -> bytes` unwraps a `.mxl`
   (`META-INF/container.xml` → rootfile, one entry, size-capped) or returns the XML bytes;
   `title_of(root)` picks `work-title`, then the `title` credit, then `movement-title`. Rejections
   are one sentence each: not XML, not `score-partwise` (a timewise file is named as such), no part,
   no note, an entity declaration, a container with no rootfile.
   *Check:* unit tests over the four Anton files and three benchmark `.mxl`s.
2. **The import path.** `ingest(src, out_dir, progress)` beside `recognize`: write `score.musicxml`
   and `original.musicxml`, the stats from `postprocess(..., repair=False)` (new flag: count, note,
   change nothing), `lyrics.json` from `read_placements`, `result.json` with
   `{"engine": "import", "source": "musicxml"}`, `review.json` with the info doubts.
   *Check:* a test that imports `anton_paroles_et_notes_fr.musicxml` and gets 19 measures, 56 notes,
   10 chords, 55 syllables and no `wrong` doubt.
3. **The door.** `api.py` classifies the upload (image by content type as today, MusicXML by bytes
   and suffix), `jobs.Job.source` records it, `Worker._process` branches, `PP_MAX_UPLOAD_MB` still
   caps the size, the 415 message names both kinds. `partition-player recognize` delegates to the
   import when handed a MusicXML file, so the CLI has one door too.
   *Check:* API tests for `.musicxml`, `.mxl`, a `.xml` that is not MusicXML, a timewise document,
   and the existing 415 for `text/plain`.
4. **The upbeat rules.** `postprocess.inspect` and `score/check.ts`: a short first measure is a
   pickup, and a short measure completed by its neighbour (or by the page's other end) is an upbeat
   pair; neither is a doubt. `bench/songs/doubts.py` is untouched — it reads `_measure_filled`
   directly — so the published precision figures still describe what ships.
   *Check:* unit tests both sides, with `en_clementine`'s four short measures as the case.
5. **The frontend.** `Upload.tsx` takes both (`accept="image/*,.musicxml,.xml,.mxl"`, drop or pick,
   a file card instead of an image preview, "Open the score" instead of "Read the score");
   `Progress.tsx` shows the import's two steps; `ScoreView.tsx` says *imported from …*;
   `Library.tsx` draws a tile for a score with no thumbnail; `api.ts` carries `source`.
   *Check:* `tsc` and the unit tests, then the real thing in the browser.
6. **The real check.** Import, in the browser: the two Anton exports (the played page matches the
   photographed one), a song with voltas (`es_alfonsina_y_el_mar`, 4 endings — the automatic form
   must play them without a hand-made section), and a two-staff piano page. Listen to each.
   Then `README.md` and `BACKLOG.md`.

## Duplicate as played (asked for while this was being built)

The written-out score of plan 0009 could only be downloaded. Now that a MusicXML file can come back
in, keeping it is one round trip: `ScoreView.duplicatePlayed` writes the expansion in the browser,
posts it through the same door, and opens the new score. Three things it needed:

- **A name the file cannot take back.** `POST /api/jobs` accepts an optional `name`, and the worker
  applies an imported file's own title only while the job's name is still the one its file name gave.
  Without it the copy came back called "Alfonsina y el mar", beside the original of the same name.
- **A pickup that survives being copied.** `expandScore` stamped `implicit="no"` on every measure it
  did not cut, which threw away the one mark that tells an upbeat from a mistake: the copy of
  Alfonsina opened saying "1 place to check" about its own first measure. A measure copied whole now
  keeps the source's mark. This is the one place where plan 0009's export and plan 0010's reading
  meet, and it was only visible once the export was read back.
- **The copy is of the score as saved**: a dirty session is saved first, so the duplicate cannot hold
  half an edit.

The copy is an ordinary imported score: no photo, no doubts, a form of its own, and no *duplicate*
button of its own, since a page already written out has nothing left to expand.

## What could go wrong

- **OSMD on a file it did not get from homr.** Page and system breaks, multiple voices, transposing
  parts, `<print>` blocks: all standard, all rendered by OSMD every day, but the editor's hit test
  (`editor/sheet.ts`) maps graphical notes back to the document by index. Step 6 is where that is
  found out; a piano page is in the check list for exactly this reason.
- **A file with no lyrics and no chords** should simply show neither panel; the Lyrics panel with
  zero verses is already the state of a photographed instrumental page.
- **Big files.** A 300-measure orchestral score will render slowly and may make the editor
  unpleasant. The upload cap (25 MB) and `MAX_DOCUMENT` (4 MB) are the only guards; anything beyond
  that is out of scope until someone tries it.
