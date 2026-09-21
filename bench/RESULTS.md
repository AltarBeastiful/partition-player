# OMR engine benchmark, 2026-09-18

Input: `bench/samples/anton_yvan_boris_photo.jpg`, a 3072x4096 phone photo of a printed lead sheet
("Anton, Yvan, Boris et moi", Marie Laforêt). Single treble staff, C minor (3 flats), 2/4, 19 measures
in 4 systems, chord symbols, lyrics, and a block of verse text below the music. Ground truth in
`bench/ground_truth_anton.md`.

Machine: x86_64, 16 cores, 30 GB RAM. Target VPS is ARM with a few cores, so CPU time and peak RAM
matter more than wall time here.

## Engines

| Engine | Version | Runtime notes |
|---|---|---|
| Audiveris | 5.11.0 (Ubuntu deb, unpacked, bundled JRE) | Java. Ships x86_64 and arm64 native jars for Tesseract and Leptonica, so it runs on ARM with a system JRE 21 even though there is no arm64 package. |
| oemer | latest PyPI, Python 3.11 venv | ONNX models (110 MB). Needed `onnxruntime==1.22.1` (1.15 to 1.17 fail to load on this kernel, 1.30 rejects the model) and `opencv-python<5` (OpenCV 5 changed HoughLinesP output shape and oemer crashes). |
| homr | 0.7.0 PyPI, Python 3.11 venv, AGPL-3.0 | Segmentation net plus a TrOMR transformer per staff, ONNX (150 MB) plus RapidOCR for the title (30 MB). Installs and runs with current onnxruntime 1.30 and opencv. Resolves for aarch64 with uv (onnxruntime and opencv-python-headless publish arm64 wheels). |

## Cost

| Metric | Audiveris (1 sheet) | oemer | homr |
|---|---|---|---|
| Wall time | 1 min 57 s | 5 min 35 s | 11 s |
| CPU time | about 3 min | 34 min | about 80 s |
| Peak RAM | 1.45 GB | 6.0 GB | 1.27 GB |
| Input size sensitivity | none observed | none: same time at half resolution, it resizes internally | not tested |

Extrapolated to a 4-core ARM VPS: homr well under a minute per page, Audiveris roughly 2 to 4 min,
oemer 10 min or more and does not fit in a 4 GB VPS.

## Accuracy on the photo

Ground truth: `bench/samples/anton_yvan_boris_ground_truth.musicxml`, hand-encoded with
`bench/make_ground_truth.py` and rendered to `anton_yvan_boris_ground_truth.png` for visual comparison
with the photo. 19 measures, 55 notes, 15 rests (14 eighth, 1 quarter), 6 dotted rhythms, 3 naturals.
Scores come from `bench/score.py`, which aligns the event sequence by edit distance, so a merged or
missing measure does not shift everything after it.

| Metric | Audiveris | oemer | homr |
|---|---|---|---|
| Measures | 19 of 19, systems 4+5+5+5 | 18 of 19 (measures 2 and 3 merged) | 19 of 19 |
| Clef, time signature | correct | time signature missing | correct |
| Key signature | correct | flats read as naturals from system 3 on, output switches to 3 sharps | correct |
| Notes found | 52 of 55 | 55 of 55, two merged into a chord | 55 of 55 |
| Pitch correct | 51 of 55 | 38 of 55 (key signature) | 55 of 55 |
| Duration correct | 45 of 55 | 50 of 55 | 55 of 55 |
| Rests found, right duration | 7 of 15, 7 | 15 of 15, 4 (eighth rests read as whole rests) | 15 of 15, 15 |
| Event error rate | 0.21 | 0.24 | 0.00 |
| Fully correct measures | 9 of 19 | n/a | 19 of 19 |
| Chord symbols | 2 of 10 with OCR on | none | none |
| Lyrics | garbage: the verse block below the staves is attached as lyrics | none | none |

Three notes where my first hand reading disagreed with homr were re-checked on 2.5x crops; homr was
right each time (a natural sign belonging to the following note, and low notes engraved without ledger
lines). The ground truth was corrected accordingly.

## Observations

- homr is the only engine that produced a playable result from this photo with no manual fix, and it
  is 10x cheaper than Audiveris and 25x cheaper than oemer in CPU time.
- Audiveris errors are local and rhythmic (missing eighth rests, missed dots). Measure structure and
  key are right, so playback stays in tune and each measure can be padded to its time signature.
- oemer errors are structural (wrong key for half the piece, whole rests in a 2/4 bar) and would make
  the playback wrong. Its symbol classifier is better on dots and naturals, which is worth remembering
  for a later ensemble or correction pass.
- Audiveris treated the JPEG's embedded EXIF thumbnail as a second sheet. Preprocessing must re-encode
  the input (PNG) or we pass `-sheets 1`.
- Audiveris OCR (Tesseract, legacy engine, needs the full `tessdata` files, not `tessdata_fast`) is not
  useful on this layout: lyrics and verse text get mixed. Keep OCR off in v1; chord symbols and lyrics
  go to the backlog.
- Audiveris batch options that matter: `-batch -export -sheets 1 -output <dir> -- <image>`. Output is
  a compressed `.mxl` plus a `.omr` project file.

## Sample 2: Satie, Gymnopédie No. 1, page 1 (clean render, grand staff)

`bench/samples/gymnopedie1/`: Mutopia Project edition (public domain, typeset in LilyPond), page 1
rendered from the PDF at 300 dpi. 39 measures in 3/4, two staves, chords in both hands, two voices in
the right hand, a repeat with a first ending. The reference is Mutopia's own MIDI, generated from the
same LilyPond source, so it is independent of every engine and of any hand transcription.
`bench/score_midi.py` buckets the MIDI onsets into measures and compares each measure as a set of
(onset, pitch) events, which is chord-aware and immune to drift from a single wrong duration.

homr through the full pipeline (`partition-player recognize`), 14 s, 1.3 GB:

| Metric | homr, engine output | homr after post-processing |
|---|---|---|
| Measures | 39 of 39 | 39 of 39 |
| Note events | 241 for 234 in the reference | 234 |
| Precision / recall / F1 | 0.963 / 0.991 / 0.977 | 0.991 / 0.991 / 0.991 |
| Measures exact (pitch and onset) | 30 of 39 | 37 of 39 |
| Measures with the right pitch set | 32 of 39 | 39 of 39 |

Two error kinds only:

- In 7 measures the right hand has a quarter rest under the melody's first note; homr wrote the rest
  followed by the melody note flagged `<chord/>`, so parsers saw a chord of rest plus note and music21
  turned the rest into a C4. Now fixed in post-processing (`_fix_rest_chords`): the note is kept, the
  rest and the chord flag dropped.
- In measures 26 and 31 a D5 tied across the bar line is placed on beat 3 instead of beat 2, and the
  measure is one beat overfull. Left as is for now; overfull measures are reported as warnings.

Audiveris and oemer were not run on this sample.

## Limits of this benchmark

Two pages: one monophonic phone photo, one clean grand-staff render. Still missing: a phone photo of
a grand-staff page, and a screenshot of a digital score. Both engines' behaviour on dense piano
textures (fast runs, ornaments, cross-staff beaming) is unmeasured.

## Decision

homr is the v1 engine, Audiveris the fallback. See `docs/adr/0002-score-recognition.md`.

## Reproduce

```
uv venv --python 3.11 .venv-homr && uv pip install --python .venv-homr/bin/python homr
.venv-homr/bin/homr --init && .venv-homr/bin/homr bench/out/homr/anton.jpg   # writes anton.musicxml next to the image
.venv-oemer/bin/python bench/score_midi.py bench/samples/gymnopedie1/gymnopedie_1.mid <candidate.musicxml> [--dump]
uv venv --python 3.11 .venv-oemer
uv pip install --python .venv-oemer/bin/python oemer "onnxruntime==1.22.1" "opencv-python<5" verovio music21 cairosvg
.venv-oemer/bin/oemer bench/samples/anton_yvan_boris_photo.jpg -o bench/out/oemer_cv4
# Audiveris: download the 5.11.0 Ubuntu deb, dpkg-deb -x it, then
<unpacked>/opt/audiveris/bin/Audiveris -batch -export -sheets 1 -output bench/out/audiveris_raw -- bench/samples/anton_yvan_boris_photo.jpg
.venv-oemer/bin/python bench/make_ground_truth.py
.venv-oemer/bin/python bench/score.py bench/samples/anton_yvan_boris_ground_truth.musicxml <candidate.musicxml> [--dump]
.venv-oemer/bin/python bench/render.py <musicxml> <png>
```

## Chord symbols (ADR 0003), 2026-09-18

Pipeline: homr driver geometry, RapidOCR detector on tiles (working size 192 px), recognizer
probabilities decoded under the chord grammar, notehead-anchored placement, MusicXML `<harmony>`.
Set: the real lead-sheet photo; 15 synthetic pages (10 Nottingham folk tunes, Berlin's Alexander's
Ragtime Band, Foster's Jeanie, three jazz-vocabulary pages with sevenths, flats, dim, slash chords and
a key change), each as a clean verovio render and as a photo-like degraded copy; 5 negative pages with
no chord symbols (rehearsal letters, tempo text, lyrics, "Fine", and the Gymnopédie piano page).
Scorer: `bench/chords/score_chords.py` (sequence by edit distance on root, kind, bass; placement by
measure index and half beat).

| set | pages | chords printed | found | right | false | placed right |
|---|---|---|---|---|---|---|
| real photo | 1 | 10 | 10 | 10 | 0 | 10 of 10 |
| synthetic, clean | 15 | 389 | 365 | 365 | 0 | 317 of 357 scorable |
| synthetic, degraded | 15 | 389 | 374 | 374 | 0 | 335 of 389 |
| negatives | 5 | 0 | 0 | 0 | 0 | |

- Every chord that was written is a chord that was printed: 0 false in 36 pages, and every found
  chord had the right root, kind and bass.
- Misses (24 clean, 15 degraded): names that the engraver staggered higher or lower than the chord
  line, names run into the composer or title text above the first system, and one or two names per
  page on the folk tunes where the detector found no box. The clean renders do slightly worse than
  their blurred copies; the recognizer is run on a softened copy too and the surer reading kept.
- Placement: on the folk tunes and the real photo nearly every found chord is on its measure and
  beat. The three jazz pages lose about half their placements because verovio shifts wide names
  sideways to avoid collisions, so the name no longer starts above its note; the chord sequence is
  still right and a second name on the same beat is pushed to the next onset.
- Time: about 1 s per page on this machine for detection plus recognition on 4 to 8 bands; the
  server number is in `deploy/README.md`.

Reproduce:

```
.venv-oemer/bin/python bench/chords/make_synthetic.py <nottingham-dataset clone>   # writes bench/out/chords/
.venv-oemer/bin/python bench/chords/run_bench.py                                     # about 15 min
```

## Lyrics (ADR 0004)

Date: 2026-09-18. Pages: the real photo; 19 rendered pages (four French songs typed with two or
three verses on generated melodies, ten Nottingham lead sheets with synthetic French and English
verses of one to three verses with melismas and punctuation, Berlin's and Foster's lead sheets and
Luca's Gloria with their engraved lyrics), each clean and photo-degraded; two "paragraph" pages with
a verse paragraph pasted right under the last system, clean and degraded; the Gymnopédie piano page
as the negative. Scorer: `bench/lyrics/score_lyrics.py` (per note and verse: syllable placed on the
right note, text right up to case and punctuation, syllabic type right, false syllables; character
error rate of verse 1 in note order). A page whose measure count homr gets wrong (one of 17, a
24-measure page read as 23) cannot be scored by position and is scored by sequence for text only.

| set | pages | syllables | placed on the right note | text right | syllabic right | false | verses found |
|---|---|---|---|---|---|---|---|
| real photo | 1 | 55 | 55 (100 %) | 54 | 54 | 0 | 1 of 1 |
| rendered, clean | 16 scorable | 2180 | 2148 (98.5 %) | 96.2 % (of 2561) | 2066 | 2 | 32 of 32 |
| rendered, degraded | 16 scorable | 2180 | 2161 (99.1 %) | 96.9 % (of 2561) | 2076 | 1 | 32 of 32 |
| paragraph under the last system | 4 | 168 | 166 (98.8 %) | 154 | 164 | 0 | 4 of 4 |
| Gymnopédie (no words) | 1 | 0 | | | | 0 | 0 |

- Every verse row is found and no page gains a verse it does not have: the chord line of the next
  system, which sits inside the band of tight layouts, is rejected by its shape (it reads as chord
  symbols) or its place (the next staff's chord zone); the verse paragraphs are rejected by the row
  gap; the Gymnopédie's typesetting credits under its last system are rejected as prose (long words,
  no hyphenation) and as numbers. The ADR's "false lyrics = 0" is met for rows and verses; three
  single syllables in 5,100 (an OCR fragment matched to a free note) remain and are listed below.
- Placement misses are the two doubtful-token drops per page and the melisma notes of the Gloria
  (a Latin choral part with long melismas and no extender lines); text errors are OCR spelling
  (accents in tiny renders, "Jo" read as "To" on the photo), which the editor is for.
- The photo's dropped hyphens ("é - tions", "An - ton") were the main syllabic-type loss; they are
  recovered from the pixels between words, 54 of 55 syllabic types now.
- Time: recognition plus lyrics about 12 s per page on this machine; the server number is in
  `deploy/README.md`.

Reproduce:

```
.venv-oemer/bin/python bench/lyrics/make_pages.py       # writes bench/out/lyrics/ (needs bench/out/chords/nott_*.musicxml)
.venv-oemer/bin/python bench/lyrics/run_bench.py        # about 15 min
backend/.venv/bin/python bench/lyrics/replace.py        # re-place only, seconds, for tuning
```

## Songs: lead sheets, the page the product is for (bench/songs, `leadsheets`)

Date: 2026-09-19. Thirty songbook pages: one staff carrying the sung line, the chord names printed
above it, the verses stacked under it. Real songs — Brassens's *Chanson pour l'Auvergnat* and *Le
petit cheval*, *La Marche des Rois*, *Auprès de ma blonde*, *Alfonsina y el mar*, *Camptown Races*,
*Clementine*, *Home on the Range*, *Die Gedanken sind frei*, Brahms's *Wiegenlied*, *Mattinata*,
*Vieni sul mar*, *Kristallen den fina* — eleven French, eight English, four Spanish, four German,
two Italian, one Swedish. **5,819 syllables, 870 chord symbols, 3,240 sung notes**, one to eight
verses a page, engraved in five music fonts (Leipzig, Leland, Bravura, Gootville and the handwritten
Petaluma), each page also degraded into a phone photo.

Source: [PDMX](https://zenodo.org/records/15571083), 250K MuseScore scores. Kept: one part, one
staff, at least eight chord symbols, words, no chord noteheads, **one voice**. That last rule earned
itself: two Spanish scores with a second voice on the staff scored 0 of 294 syllables placed and 185
false, because neither scorer can pair a two-voice staff with what an engine reads, and one Italian
score wrote its chords in solfège display text (`MIm`, `RE`) over a root stuck at C, so all forty
printed as a bare "C". All three were replaced. The thirty `.mxl` files are vendored in
`bench/songs/leadsheets/` (216 KB, all public domain or CC0), so the set needs no download.

| set | pages | sung notes | pitch | pitch+duration | syllables | placed | text right | verses | false | chords | right | false |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| engraved | 30 | 3240 | 99.8 % | 99.5 % | 5819 | 90.5 % | 86.6 % | 94 of 104 | 76 | 870 | 83.7 % | 23 |
| degraded | 30 | 3240 | 99.9 % | 99.7 % | 5819 | 89.9 % | 86.2 % | 95 of 104 | 81 | 870 | 84.7 % | 38 |

"placed" is over the pages whose measure count came back right (28 of 30 clean, 29 of 30 degraded);
the other pages are scored for text by sequence only. The photo copy scores level with the clean
render throughout, so nothing here is an OCR-legibility problem.

- **The sung line is solved on this layout**: 99.8 % of notes right on pitch, 99.5 % on pitch and
  duration, and the measure count right on 57 of 60 pages. Against the voice-and-piano set's 86.6 %,
  the difference is the single staff.
- **Verses are found until the fifth, then lost.** Every page with four verses or fewer has all of
  them; from five up they start to go:

  | verses printed | pages | verses found |
  |---|---|---|
  | 1 to 4 | 15 | 46 of 46 |
  | 5 | 5 | 24 of 25 |
  | 6 | 3 | 15 of 18 |
  | 7 | 1 | 4 of 7 |
  | 8 | 1 | 5 of 8 |

  *Camptown Races* (8), *Clementine* (7), *My Grandfather's Clock* (6), *Le petit cheval* (6), *The
  First Noel* (6) and *Home on the Range* (5) are the pages that lose rows, and the cause is
  measurable in `geometry.json`: the lyric band runs from 1.5 to a fixed 12.0 interlines below the
  staff (`LYRICS_TOP_UNITS`, `LYRICS_BOTTOM_UNITS`), and the verse rows of these pages sit about 2.2
  interlines apart (2.5, 4.5, 7.0, 9.0, 11.0…). Five rows fit; the sixth would start near 13 and the
  eighth near 17, outside the band, so those rows are never in the image the OCR is given. A
  songbook stacks as many verses as the song has.
- **76 false syllables**, against the ADR's target of 0, and they are not spread out: *Les gens bien
  élevés* 35, *La Marche des Rois* 10, *My Grandfather's Clock* 8, *La nave del olvido* 6,
  *Wiegenlied* 6. Twenty of the thirty pages have none.
- **Chords 83.7 %**, with the misses concentrated the same way: *luna tucumana* 11 of 48, *Alfonsina
  y el mar* 30 of 46, *Votre divin Maître* 32 of 42. The first two are dense tango and folk sheets
  with a chord over almost every measure.
- Time: about 15 s per page on this machine, the three stages together.
- `bench/out/songs/leadsheets/review.html` puts each page beside the chords and syllables read from
  it, one row per verse, each syllable addressable as `<page> v2 #17`.

Reproduce:

```
.venv-oemer/bin/python bench/songs/make_pages.py     # engraves the 30 pages, no download
.venv-oemer/bin/python bench/songs/run_bench.py      # about 15 min
.venv-oemer/bin/python bench/songs/review.py         # writes .../leadsheets/review.html
```

## Songs, second set: voice and written-out piano (bench/songs, `voice_piano`)

Date: 2026-09-19. Not the product's target (that is the lead-sheet set below); this one is art song,
three staves to a system, and it is here because it is where the staff-grouping defect shows. Thirty
songs for voice and piano from the [OpenScore Lieder corpus](https://github.com/OpenScore/Lieder) (CC0, transcribed from IMSLP
scans), thirteen French, eight German, seven English, two Italian; sixteen pages with one verse,
nine with two, three with three, one with four and one with five; melismas held by extender lines,
real hyphenation, verse numbers printed in the first syllable, second verses in italic, and **three
staves to a system**. 2,602 syllables and 2,131 sung notes.

Two tiers, both scored against the same transcription, which is the ground truth for the notes and
for the syllables alike:

- **engraved**: one page per song rendered by verovio (the music font varies: Leipzig, Leland,
  Bravura, Gootville, Petaluma), the ground truth cut to exactly the measures verovio put on that
  page; plus a degraded copy of each, like a phone photo. 60 images.
- **IMSLP scan**: ten of the actual nineteenth- and twentieth-century prints the transcriptions
  were made from (Peters, Novello, Augener, Johann André and others, one carrying a library
  watermark), each pinned to its measures by finding its printed words in the transcription's
  syllable sequence. Independent check: the pipeline returned the pinned measure count exactly on
  all ten pages.

| set | pages | sung notes | pitch | pitch+duration | syllables | placed | text right | verses | false |
|---|---|---|---|---|---|---|---|---|---|
| engraved | 30 | 2131 | 88.2 % | 86.6 % | 2602 | 25.7 % | 25.6 % | 25 of 52 | 9 |
| engraved, degraded | 30 | 2131 | 87.4 % | 85.2 % | 2602 | 18.1 % | 16.2 % | 18 of 52 | 8 |
| IMSLP scan | 10 | 581 | 79.3 % | 73.8 % | 767 | 0.5 % | 0 % | 2 of 21 | 5 |

- The sung line survives: homr reads the voice staff at 86.6 % right on pitch and duration on the
  engravings and 73.8 % on the real prints, and gets the measure count right on 58 of 60 engraved
  pages and on all 10 scans. **The lyric stage is what collapses**, from 98.5 % on the synthetic set
  to 25.7 %, and to nothing at all on the scans.
- Cause, and it is the same on every page: **homr finds two staves per system where there are
  three**. On all 30 pages it merges the voice staff with the piano's upper staff into one staff
  whose interline comes out 1.7 to 2.9 times the true one. The lyric band is measured in interlines
  of that wrong unit and clipped one interline above the next staff, so it is squeezed to nothing,
  and the words are never in the image the OCR is given. What is left of the band predicts the
  result almost exactly:

  | band under the merged staff | pages | placed |
  |---|---|---|
  | under 1.1 interlines | 12 | 0 to 29 %, nine of them 0 % |
  | 1.1 to 2.5 | 6 | 0 to 75 %, two of them 0 % (one page unscored) |
  | over 2.5 | 12 | 19 to 100 %, none at 0 % |

  Where the engraving happens to leave vertical air, enough band survives and the words are read:
  Chausson's *Lassitude* 58 of 58 and Tosti's *Ideale* 57 of 57, both perfect. Where it does not,
  nothing is read at all: 11 of the 30 engraved pages place no syllable at all (a twelfth, Elgar's
  *Queen Mary's Song*, is the one page whose measure count came out wrong, so it is scored by
  sequence only). On the scans, which are set
  tighter than a modern render, no page has room and the whole tier reads nothing.
- Verses: 13 of 36 verses on the 14 multi-verse pages. Nothing yet handles two to five verse rows
  stacked under one staff.
- False syllables are 9 and 8 on the engraved tiers and 5 on the scans, against the ADR's target of
  0: the rows being read in the squeezed band are piano ink and dynamics ("25. dim. 3", "íl p 1 1"),
  not words.
- The photo copy sometimes scores *better* than the clean render it came from (Butterworth's
  *O Fair Enough* 0 to 29, Gounod's *Le soir* 37 to 70): the staff detection is unstable, not the
  OCR, which is another face of the same defect.
- Time: about 23 s per page on this machine, notes plus chords plus lyrics.
- `bench/out/songs/review.html` puts each page beside the syllables read from it, for the errors the
  numbers do not describe.

Reproduce:

```
S="--set voice_piano"
.venv-oemer/bin/python bench/songs/make_pages.py $S   # downloads the 30 scores
.venv-oemer/bin/python bench/songs/run_bench.py $S    # about 25 min
.venv-oemer/bin/python bench/songs/pin_scan.py --all  # ground truth for the scans (PDFs not downloaded by script)
.venv-oemer/bin/python bench/songs/run_bench.py $S --scans   # about 4 min
.venv-oemer/bin/python bench/songs/review.py $S       # writes .../voice_piano/review.html
```

## Doubts: where the wrong measures are (ADR 0005)

Date: 2026-09-19. The editor needs to say where to look. A measure of the engine's own output that is
shorter or longer than its time signature (what the post-processing pads or warns about) is a
*doubt*; here it is scored against the event alignment of `bench/score.py` on the song benchmark's
run outputs, per measure, on the pages whose measure count came back right (`bench/songs/doubts.py`).

| set | measures | flagged | of which wrong | precision | wrong measures | of which flagged | recall |
|---|---|---|---|---|---|---|---|
| lead sheets | 1505 | 106 | 95 | 0.90 | 98 | 95 | 0.97 |
| voice and piano | 1073 | 571 | 461 | 0.81 | 597 | 461 | 0.77 |

- On the product's page three wrong measures in 1505 carry no flag. The flag costs nothing and needs
  no model; it only has to be recorded before the padding hides it, which the pipeline now does
  (`review.json`). The padded pickup measure is counted as flagged and wrong here (the scorer sees the
  added rest as an extra event); the editor shows it as information.
- Two weaker signals were measured on the lead sheets and are not used as doubts: the detected
  barlines give the system's measure count on 277 of 302 systems (used to frame the measure on the
  photo, with an even split as the fallback), and the segmentation net's notehead count equals the
  transformer's note count on 256 of 302 systems.
- The kinds of error behind the flags, over all 120 pages (`bench/score.py` alignment): on lead
  sheets, after the padding rests, a duration a dot or a flag off (dotted half read as whole 30 times
  over both sets, dotted quarter as half 12, eighth as quarter 9, quarter as eighth 14), a rest read
  as a note or a note as a rest, a rest's duration; on the piano pages also extra and missing notes
  (staff grouping), pitches two steps off (25), one step off (20), an octave off (14) and a missing
  accidental (12). The editor's operations are these (ADR 0005, decision 4).

Reproduce:

```
.venv-oemer/bin/python bench/songs/doubts.py          # needs the run outputs of run_bench.py, both sets
```

## How sure: rating a second reading of the print (plan 0008)

Date: 2026-09-21. The doubt of ADR 0005 is arithmetic, so it cannot see an error that changes no
duration. The segmentation net's noteheads are an independent reading of the same ink; `evidence.py`
compares them with the notes the transformer emitted and rates the disagreement, marking only what
reaches `check`. Scored like the doubts above: against `bench/score.py`'s alignment, per measure, on
the pages whose measure count came back right (`bench/songs/rating.py`).

| set | pages | measures | findings | marked `check` | of which wrong | precision | wrong measures the arithmetic flag cannot see, caught | marks on pages that came back exactly right |
|---|---|---|---|---|---|---|---|---|
| lead sheets | 57 | 1505 | 116 | 2 | 2 | **1.00** | 0 | **0** |
| voice and piano | 58 | 1073 | 1022 | 76 | 58 | **0.76** | **14** | **0** |

### Can one reader be enough on its own? (`bench/songs/thresholds.py`)

Yes, and the threshold is not a magnitude. Sliced every way, **how far the counts differ does not
discriminate at all** — on the piano pages precision is 0.76, 0.76, 0.72, 0.70 at `|delta|` 1, 2, 3,
4. What separates a finding worth showing from one worth ignoring is whether anything argues against
it, so the rule is simply *readers that disagree, less the demotions, at least one*:

| rule | marks | precision | adds | cry wolf |
|---|---|---|---|---|
| lead sheets, nothing argues back | 2 | 1.00 | 0 | 0 |
| lead sheets, also allowing a sound measure | 33 | 0.09 | 1 | **15** |
| piano, nothing argues back | 76 | 0.76 | 14 | 0 |
| piano, also allowing a sound measure | 86 | 0.71 | 17 | 0 |

Both loosenings were rejected on the margin, not the total: the 18 extra marks that a sound measure
buys on the piano pages are right only **0.44** of the time, below the bar, and the same loosening
costs 15 cry-wolf marks on lead sheets. Going the other way, an earlier rule also demanded the
disagreement be of a "strong" kind; dropping that requirement is what lets a lead sheet speak at all,
and its increment is right 0.62 of the time on the piano pages and 2 times in 2 on the lead sheets.

Every demotion was checked this way. Three earn their keep. The fourth, "the measure's boundaries
were estimated", does **not** change precision on its own (0.56 against 0.58) but removes 30 of the
104 cry-wolf marks, so it is kept for that.

What each source is worth before the rating, so the rating's work is visible:

| set | source | fires | wrong | precision |
|---|---|---|---|---|
| lead sheets | notehead count, more | 78 | 11 | 0.14 |
| lead sheets | notehead count, fewer | 38 | 2 | 0.05 |
| voice and piano | notehead count, more | 989 | 558 | 0.56 |
| voice and piano | notehead count, fewer | 33 | 20 | 0.61 |

- **The rating is the whole of it.** On the piano pages it turns 1022 raw findings at 0.56 into 76
  marks at 0.76, and it catches 14 wrong measures that no arithmetic flag can reach. The price is
  recall: 122 wrong measures there stay silent. That is the trade the two levels ask for — a mark
  allowed to be wrong is a mark that cries wolf.
- **On lead sheets it says almost nothing, and should.** The raw sources are worth 0.05 to 0.14
  there, and the demotions silence 114 of the 116 findings: a lead sheet is monophonic, so a stacked
  head is ink, and a measure that adds up argues against a note gained in sequence. The two that
  survive are both on measures that really are wrong. There is also almost nothing left to find —
  the arithmetic flag already reaches 95 of the 98 wrong measures, and only 3 in 1505 are invisible
  to it.
- **Nothing lands on a page that came back right**, in either set: 0 of 19 perfect lead sheets and 0
  of 7 perfect piano pages carry a mark. This was the bar the plan set, and the page it was written
  for passes it — `anton`, where an ink blot makes the pixel stage read six heads in measure 8 where
  the score has four, ends with zero doubts, because the boundaries of that system were estimated,
  the page is monophonic, and the extra head sits 1.64 steps off the staff grid.
- **A source that was built, measured and removed.** The detected staff position of each head against
  the pitch the score gives should catch a wrong pitch, the commonest error the arithmetic cannot
  see. It does not: on a photographed page it is noise. Landing on a wrong measure 2 times in 36 with
  the position read off the staff lines, and **0 times in 8** with homr's own dewarped position (22
  lead-sheet pages re-run with a patched driver), at every normalisation tried — raw, one constant
  per staff, and the median of each head's nine nearest neighbours. It is out of the code; the
  position is still written to `evidence.json`, where it costs nothing.

Reproduce:

```
.venv-oemer/bin/python bench/songs/rating.py                  # needs the run outputs of run_bench.py
.venv-oemer/bin/python bench/songs/rating.py --geo DIR        # with geometry from a patched driver
```

## Form: repeats, verses and the order a song is sung in (plan 0004)

Date: 2026-09-19. A songbook page is not played in the order it is printed: verses are stacked under
one line of notes, the chorus is engraved once and sung after each. The app now plays a list of
passes derived from the repeat signs the engine read and the lyric rows it placed (`frontend/src/form.ts`),
and the user can replace it. The truth is the order each song is sung in, written by hand from the
print (`bench/songs/leadsheets/<song>.form.json`, 30 songs plus the sample); a machine expansion of
the truth's signs would give "verses N times, then the chorus once", which is not the song.

What the truth prints (`python -m songs.form`), 31 songs:

| structure | songs |
|---|---|
| repeat barlines | 15 |
| first and second endings | 8 |
| D.C., Fine or coda | 2 |
| two or more stacked verses | 25 |
| three or more stacked verses | 19 |

Repeat barlines read by homr on the 60 song pages, against the truth by measure index and direction:
precision 0.88, recall 0.74 (by count per page: 1.00 / 0.84). The misses: the implied forward repeat
at the first barline (4, harmless: OSMD defaults it), signs one measure early on pages whose measure
count is off by one (5), signs not read at all (6). Voltas are never read (0 of 8 songs).

The automatic form against the hand truth, on the 60 run outputs of the song benchmark
(`npm run bench:form` in `frontend/`, output in `bench/out/form.txt`):

| pages | exact pass list | same measure order | same pass count | verses sung / printed |
|---|---|---|---|---|
| 60 | 21 (35 %) | 23 (38 %) | 26 | 178 / 206 |

The rule that gets there ("the songbook rule" in `form.ts`): OSMD's expansion of the signs, each
repeat played once per lyric row under it; then, when the page has no repeat sign, or when three or
more verses are stacked and a single-lyric part follows them, the list is played in rounds, verse k
with the chorus after it. Two stacked rows under a repeat are taken literally (a first phrase sung
twice: *Kristallen den fina*).

Where the 37 other pages go wrong, by cause: verses under-read by the lyrics stage (*Camptown* 5 of
8, *Clementine* 4 of 7, *First Noel* 5 of 6, *Home on the range* 4 of 5, *Petit cheval* 5 of 6: the
order is right, the last verses are not sung); voltas not read, so the two endings play as one
(*Alfonsina*, *Luna tucumana*, *La nave*, *Mattinata*, *Marche des rois*); a measure count off by
one, which shifts every section (*Vieni sul mar*, *Home on the range*); a printed form no sign says
(*La clairière*'s "4 couplets, dernière fois coda", *Votre divin maître*, *Joyeux Noël*'s
forward-only repeat, the refrain-first *Probier's mal*); and the third ending of *Les gens bien
élevés*, whose single-lyric tail the rule takes for a chorus. All of these are one edit away in the
form panel; the under-read verses are the lyrics stage's problem, not the form's.

### How long the visit to the form panel is (plan 0007)

"One edit away" was optimistic, so the run now measures it: the passes to add, remove or change to
turn the automatic list into the truth, per page (`npm run bench:form`, second summary line).

| pages needing the panel | median pass edits | mean | worst | also need a section the app never proposed |
|---|---|---|---|---|
| 39 of 60 | 5 | 7.1 | 32 | 31 |

The worst page is *Chanson pour l'Auvergnat* (32 passes derived from its repeat signs against a truth
of 3). This is what plan 0007 works on: the panel writes a pass count (`Chorus ×2`), takes the whole
form as one line of words, and puts a section's edge on the note the user clicks, inside a measure
when the chorus starts on an upbeat. Building Anton's fourteen passes went from about 27 interactions
to 8, checked in the browser. The automatic form itself — the first summary line — is unchanged by
that work.
