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
