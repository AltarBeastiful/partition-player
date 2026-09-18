# ADR 0003: Chord symbol recognition and accompaniment

Date: 2026-09-18
Status: Proposed

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

1. **Geometry from homr.** Replace the `python -m homr.main` subprocess with a small driver script
   that runs homr's own steps (`detect_staffs_in_image`, `parse_staffs`, `generate_xml`) and, in
   addition, writes `geometry.json` (per staff: x extent, interline, barline x positions, system
   index) and one straightened strip PNG per staff (from 6 interlines above the top line down to 0.4
   interline above it). homr is pinned to `0.7.*`; the driver is the only place that touches its
   internals.
2. **OCR on the strips** with RapidOCR, detection plus recognition, on overlapping tiles scaled to a
   fixed interline height, two passes offset by half a tile, results merged by position. Tokens are
   kept only if, after a small confusion map (`6`→`G`, `0`→`D`, `l`→`1`, `rn`→`m`), they match the
   chord grammar `root (accidental)? quality? extension? (/bass)?`, lie to the right of the clef zone
   (3 interlines past the staff start), and score at least 0.6. Anything else is reported in the job's
   warnings with its text and position, never written to the score.
3. **Placement.** For each system, the measure count comes from the final MusicXML (`<print
   new-system>` marks). If the detected barlines agree with it (count equal to measures minus one, or
   to measures when the closing barline was detected), they give the measure boundaries; otherwise
   measures are assumed equal-width across the staff and a warning is recorded. The beat inside the
   measure is the token's fractional position times the beats of the time signature, snapped to the
   nearest half beat, with the first 15 percent of a measure snapped to beat one.
4. **Output** as standard MusicXML `<harmony>` elements (`root`, `kind`, `bass`, `degree`) inserted
   in the measure before the first note at or after the chosen beat. OpenSheetMusicDisplay renders
   these above the staff, so the sheet shows what was read and the user can compare with the paper.
5. **Playback.** The browser player reads the chord symbols from the loaded score and adds an
   accompaniment voice: bass note on the root plus a close voicing of the chord tones around C4, in a
   fixed pattern per time signature (2/4 and 4/4: bass on the strong beats, chord on every beat; 3/4:
   bass then two chords; 6/8: bass and chord on each dotted quarter). Controls: accompaniment on or
   off, melody on or off, so the singer can rehearse against chords alone. Nothing is added when the
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

- Recognition takes a few seconds longer per page (OCR on four to eight strips, two passes each).
- The engine boundary changes from "run homr's CLI" to "run our driver in the same interpreter";
  the driver is 60 lines that mirror `homr.main.process_image`, pinned to homr 0.7.
- Job results gain `chords` and chord warnings in the stats; the score view shows the count and any
  token that was seen but not accepted, so a wrong or missing chord can be spotted.
- Chord symbols become part of the ground truth files in `bench/`, and the benchmark results table
  gets a chord row.
- The accompaniment is a fixed pattern; rhythm styles, inversions and voice leading are later work.
