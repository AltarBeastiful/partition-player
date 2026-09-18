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
