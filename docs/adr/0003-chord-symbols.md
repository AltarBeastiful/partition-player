# ADR 0003: Chord symbol recognition and accompaniment

Date: 2026-09-18
Status: Accepted (reviewed 2026-09-18; the review's changes are folded in below)

## Context

The user's goal is to sing over the recognized music. On a lead sheet the melody line alone is thin;
the harmony is printed as chord symbols above the staff (Cm, Fm, G on the benchmark photo) and is
meant for an accompanying instrument. Today nothing reads them: homr 0.7 has no chord-symbol,
harmony or lyrics support in its sources, README or issue tracker (a lyrics PR, #65, was abandoned),
and Audiveris read 2 of 10 on the benchmark photo. The requirement is that whatever is played matches
what is printed: no invented harmony, and every printed chord at the right place.

Findings from the feasibility probe on the benchmark photo (`bench/samples/anton_yvan_boris_photo.jpg`):

- homr's staff detection exposes, per staff, the five staff lines as a function of x, the interline
  size, the staff extent, and detected barlines. The chord band is the strip above each staff; sampling
  it along the top staff line gives a straight strip even on a tilted photo.
- RapidOCR (already installed as homr's title OCR, ONNX, arm64 wheels) reads the chord names with
  confidence 0.8 to 1.0 once they are found. Its text detector misses most of them when given the
  whole strip, because it clamps the long side to 2000 px, so the 20 px tall names are never enlarged.
  Tiling the strip into windows about 30 interlines wide, scaled so an interline is 24 px, found 10 of
  10 names. Two known confusions: `G` read as `6`, and the top of the treble clef read as `A`.
- Tesseract 5 (system package) with a character whitelist was worse on the same crops, and hand-tuned
  blob detection failed on the photo's paper texture. Both are dropped.
- homr's detected barline count did not match the true measure count on one of four systems (one
  barline missed), so positions cannot rely on barlines alone.

## Decision

Add a **chord stage** to the recognition pipeline, deterministic and benchmark-driven:

1. **Geometry from homr.** Replace the `python -m homr.main` subprocess with our own driver
   subprocess (same isolation and timeout as before) that inlines homr's `detect_staffs_in_image` to
   keep the barline boxes, loops over the staves like `parse_staffs`, writes homr's MusicXML, and in
   addition writes `geometry.json` (per system: interline, x extent, barline and notehead x positions,
   measure count) and one straightened band PNG per system (6 interlines above the top staff line
   down to 0.4 above it). The chord OCR runs inside the same subprocess, after homr's title thread has
   finished, so it shares the process and the timeout. homr is pinned to `0.7.*`; the driver is about
   120 lines and the only place that touches its internals.
2. **OCR on the bands** with RapidOCR's detector on tiles about 30 interlines wide, scaled so one
   interline is 24 px, with the detector's working size lowered to 192 px (its default of 736 makes
   the text far larger than it likes: on the benchmark photo recall went from 7 to 10 of 10 and the
   detector time from 17 s to 0.4 s on a 16-core machine), then RapidOCR's recognizer on each box. The recognizer's output is not its top guess but its per-character probabilities, and
   these are decoded with a **grammar-constrained CTC beam search**: only strings of the chord grammar
   `root (accidental)? quality? extension? (/bass)?` can come out, and each grammar character accepts
   the glyphs the net may emit for it (`G` also `6` and `g`, `D` also `0` and `O`, flat also `♭`).
   The probability of the winning string is its confidence. This replaces any hand-written confusion
   table: a `6` never appears, because `G` is the best legal reading, and the same mechanism covers
   confusions not yet seen. On the benchmark photo the 10 chord names decode with confidence 0.88 to
   1.0 and the false detections (beams, clef top) with 0.37 or less; tokens under 0.6, or inside the
   clef zone (3 interlines past the staff start), are reported in the job's warnings with their text
   and position, never written to the score. If the benchmark later shows the general recognizer
   failing on music fonts, the fallback is a small recognizer trained on synthetic chord renders, not
   more rules; the synthetic generator already produces that training data.
3. **Placement.** The driver loops over the staves itself, so the measure count per system is the
   transformer's own barline count, not a guess from `<print new-system>`. Barlines closer than 1.5
   interlines are merged. A chord name starts at, or a little left of, the notehead it belongs to, so
   each token is anchored on the first detected notehead at or right of its left edge, and that
   notehead's measure is the chord's measure. When one barline is missing, the merged range is split
   where the score's note counts say the measure ends; when the counts disagree further, measures are
   spread evenly from the first notehead and a warning is recorded. Inside a measure the token snaps
   to a note onset when the noteheads match the score's note count, else to a half beat by position.
   Only the top staff of a system is read (below it is the upper staff's lyrics), tokens must sit in
   the band 0.8 to 5.5 interlines above the top line, and outliers off the common chord line are
   dropped. A short first measure is a pickup: it is padded at the front and marked implicit.
4. **Output** as standard MusicXML `<harmony>` elements (`root`, `kind`, `bass`, `degree`) inserted
   in the measure before the first note at or after the chosen beat. OpenSheetMusicDisplay renders
   these above the staff, so the sheet shows what was read and the user can compare with the paper.
5. **Playback.** The browser player reads the chord symbols from the loaded score and adds an
   accompaniment voice: bass note on the root plus a close voicing of the chord tones around C4, in a
   fixed pattern per time signature (2/4 and 4/4: bass on the strong beats, chord on every beat; 3/4:
   bass then two chords; 6/8: bass and chord on each dotted quarter), minus any weak pulse over a
   silence that lasts to the end of its measure: the comp is heard under the melody, and a pulse in
   the rests that end a song or a section sounded as a small extra note after the singing had
   stopped. Controls: accompaniment on or off, melody on or off, so the singer can rehearse against
   chords alone. Nothing is added when the
   score has no chord symbols (a piano score already has its accompaniment written out).
6. **Benchmark before merge.** `bench/chords/` renders 12 public-domain lead sheets with chord
   symbols (10 Nottingham folk tunes, Berlin's Alexander's Ragtime Band, Foster's Jeanie) as clean
   pages and as photo-like degraded pages, plus the real photo. The scorer compares the chord sequence
   (root, kind, bass) by edit distance and the measure placement where measure counts match.
   Acceptance: every chord right on the clean renders and on the real photo, at least 95 percent on
   the degraded renders, no false chords anywhere.

## Alternatives considered

- **Vision LLM reading the whole page.** Highest raw reading accuracy is plausible, but it cannot be
  held to "only what is printed" without a reference, and it needs a paid API and sends the user's
  photo out. Kept as a later second opinion on low-confidence tokens (backlog: LLM correction pass).
- **Audiveris with OCR on** as the chord reader: 2 of 10 on the photo, and its OCR mixed verse text
  into lyrics. Rejected.
- **Training or fine-tuning homr's transformer** to emit chord tokens: no training data pipeline,
  weeks of work, and the model's contamination with the public datasets would make evaluation
  unreliable. Rejected.
- **Tesseract** as the OCR engine: worse than RapidOCR on the crops, and a system dependency in the
  image. Rejected; RapidOCR is already shipped with homr.
- **Blob detection plus recognition-only OCR** instead of the neural text detector: brittle on
  photographed paper texture. Rejected.
- **Server-side accompaniment rendered into the MusicXML** as a second part: would make the
  downloaded score carry an invented piano part. Rejected; the accompaniment is a playback feature and
  the exported score stays what was printed.

## Consequences

- Recognition takes about a second longer per page on this machine (detector plus recognizer on
  four to eight bands); the measured cost on the ARM server is recorded in `bench/RESULTS.md`.
- The engine boundary changes from "run homr's CLI" to "run our driver as the subprocess"; the
  driver mirrors two homr functions, imports every name it needs at module level, and is pinned to
  homr 0.7.
- Job results gain `chords` and chord warnings in the stats; the score view shows the count and any
  token that was seen but not accepted, so a wrong or missing chord can be spotted.
- Chord symbols become part of the ground truth files in `bench/`, and the benchmark results table
  gets a chord row.
- The accompaniment is a fixed pattern; rhythm styles, inversions and voice leading are later work.
