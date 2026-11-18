# ADR 0005: Correcting the recognized score: doubts on the sheet and a note editor

Date: 2026-09-19
Status: Accepted

## Context

Recognition is now three stages (notes, chord symbols, lyrics) and the lyrics have a correction
panel (ADR 0004). The notes and the chords have none: a wrong note stays wrong, and the user cannot
see where the pipeline was unsure. The uploaded photo is deleted when the job ends (ADR 0001, to
keep a score at about 50 KB), so there is nothing to compare the sheet against either.

What goes wrong, measured on the song benchmark (`bench/songs`, 60 lead-sheet pages and 70
voice-and-piano pages, `bench/RESULTS.md`), scored event by event against the transcription:

- On the **lead sheets**, the product's page, 99.5 % of sung notes are right on pitch and duration.
  The remaining errors are few and local: a duration read a flag or a dot off (dotted half read as a
  whole, dotted quarter as a half or a quarter, eighth as a quarter or a sixteenth), a rest read as
  a note or a note as a rest, a rest's duration, a pitch one or two steps off, a missing accidental,
  and once in thirty pages a time signature (2/4 read as 4/4) or a merged or split measure (3 of 60
  pages have the wrong measure count). No key signature was wrong.
- On the **piano pages** the errors are ten times denser (86.6 % right) and of the same kinds, plus
  extra notes from the staff-grouping defect, missing notes in chords, and octaves (ledger lines).
- homr writes no ties, no beams and no `<accidental>` elements (alterations only), so a note tied
  across a bar line comes out as two notes or as one overfull measure.

The pipeline already has a signal that says where to look. The post-processing pads every measure
that is shorter than its time signature and warns about every longer one. Scored per measure on the
pages whose measure count came back right:

| set | measures | flagged (short or long) | of which really wrong | wrong measures | of which flagged |
|---|---|---|---|---|---|
| lead sheets | 1505 | 106 | 95 (90 %) | 98 | 95 (97 %) |
| voice and piano | 1073 | 571 | 461 (81 %) | 597 | 461 (77 %) |

On lead sheets, three wrong measures in 1505 are not flagged. The flag is cheap, needs no ground
truth and no model, and it is computed before the padding hides it, so it has to be recorded at
recognition time. (The count includes the padded pickup measure, which the scorer sees as an extra
rest; the editor shows it as an information flag, not a doubt.)

Other signals were measured and are weaker: the detected barlines give the system's measure count
on 92 % of systems (useful to locate a measure on the photo, not as a doubt), and the segmentation
net's notehead count equals the transformer's note count on 85 % of systems (too noisy for a flag
on its own; kept for the review page of the benchmark).

The sum of the transformer's measure counts per system equals the number of measures in the XML on
all 60 pages, so every measure can be placed on its system of the photo.

## Decision

1. **Doubts are recorded at recognition time and drawn on the sheet.** `postprocess` returns, per
   measure, whether it was padded (and by how much), overfull (filled against expected), had a rest
   merged into a chord, or is the pickup. The pipeline writes them to `review.json` with the
   revision number and the list of measures the user has marked as checked. The score page tints
   these measures on the rendered sheet (a layer under the notes, like the note names), lists them
   in a review bar ("4 places to check", previous, next, mark checked), and explains each in words
   ("shorter than 3/4 by an eighth: a rest was added at the end"). A measure edited by the user
   counts as checked; a check can be undone.

2. **The photo stays, small.** The pipeline keeps a copy of the upload as `review.webp`, longest side
   2400 px, quality lowered until the file is under 300 KB (the benchmark photo, 3072 × 4096, comes
   to about 240 KB; grayscale saves 2 % and is not worth losing a highlighter mark). Next to it,
   `layout.json` gives every system's box and every measure's x range in review-image pixels,
   mapped through the driver's coordinate chain: measure boundaries come from the detected barlines
   when their count matches the transformer's measure count, else the system is split evenly. When a
   measure is selected, the editor shows the strip of the photo it was read from, with the measure
   framed, and the whole photo on request. Scores recognized before this change have no photo and
   no layout; the editor works without them.

3. **The editor edits the MusicXML in the browser and saves the document.** The score is parsed
   into a DOM, every operation is a pure function on that DOM (`frontend/src/score/`), the sheet is
   re-rendered from the serialized string, and undo is a stack of strings. Nothing round-trips to
   the server per keystroke. Saving sends the whole document with the checked list and the base
   revision (`PUT /api/jobs/{id}/score`); the server validates it (well-formed, score-partwise,
   notes present, durations integral, size), recomputes the statistics and the measure check,
   re-reads the lyric placements from the document so the lyrics panel stays right, and bumps the
   revision; a stale base revision is refused with 409 so two browsers cannot silently overwrite
   each other. Saving is automatic, a second after the last edit, with the state shown; leaving with
   unsaved changes asks first.

4. **Operations are the ones the benchmark errors need, and no more.** On a selected note or rest:
   pitch up or down a step (an accidental that was explicit travels with the note; one that came from
   the key follows the new step's key alteration), flat, natural, sharp, octave up or down, duration
   (whole to thirty-second, dot), tie to the next note of the same pitch, note to rest and back,
   insert a note or rest before or after, delete. On a measure: fill the gap with a rest, split at the
   selected event, merge with the next, insert an empty measure, delete. On the score: time
   signature and key signature from a measure onward, clef per staff, revert to the recognized
   version (the pipeline keeps `original.musicxml`). Chord symbols: the text of the chord on the
   selected event (grammar of ADR 0003, parsed in the browser with the same kinds), add, remove.
   Tuplets, grace notes and beams are preserved, not edited. Lyrics keep the existing panel; a
   syllable stays on its note through pitch and duration edits and is lost with a deleted note,
   which the panel then shows.

5. **Selection is by clicking the sheet**, on a phone as on a desktop. The click is mapped to OSMD's
   graphical model (nearest note within a tolerance, else nearest staff entry, else the measure), and
   the graphical note is mapped to its XML element by measure index, staff, voice, onset and pitch.
   The selected note is coloured through its SVG group; the keyboard drives the common operations
   (arrows for pitch and selection, digits for durations, dot, r, t, Delete, n for the next doubt,
   c for checked, Ctrl+Z / Ctrl+Y). On a phone the tools are a bottom bar with large targets and the
   photo strip above it.

## Alternatives considered

- **Operations applied on the server** (one request per edit, server owns the document). Simpler
  validation and a natural history, but a step of pitch would cost a round trip from a phone to the
  VPS plus a render, and offline edits would be impossible. The whole-document save keeps the
  validation and the concurrency control with none of the latency.
- **A general notation editor** (MuseScore-like input, voices, beaming, articulation). Out of
  proportion: the errors are local and few, and the sheet is a means to play and sing, not an
  engraving. The operation list is closed on the benchmark's error kinds.
- **Keeping the full-resolution upload.** 3 to 8 MB per score against a 500-score cap on a small
  VPS; 300 KB reads well enough to check a note against the print, and the strips are cut from it
  at the size they are shown.
- **A language-model second opinion** on the doubts (BACKLOG). Still worth benchmarking; the flags
  and the editor are what it would need to plug into, and they are useful without it.
- **Flags from a second engine's disagreement** (Audiveris). Two to four minutes per page on the
  server for a signal the measure check already gives on the target layout.

## Consequences

- A finished score grows from about 50 KB to about 350 KB (photo, layout, original, review record).
  500 scores are 175 MB; the deploy notes are updated.
- `postprocess` and `run.py` change shape (per-measure detail, four more kept files); the fake
  engine path has no geometry, so tests cover the no-layout case as the pre-editor scores do.
- The frontend gains a `score/` module with unit tests (vitest, jsdom) for the DOM operations and
  the measure check, which the app did not have before; the bundle grows by the editor code only,
  OSMD and Tone.js are already there.
- The measure check exists twice, in Python for the stored statistics and in TypeScript for the live
  flags; both are tested on the same cases.

## Validation

- The flag precision and recall above, reproduced by `bench/songs/doubts.py`, recorded in
  `bench/RESULTS.md`.
- Backend tests: doubts and pickup on the benchmark photo, review image under 300 KB, layout boxes
  (checked visually once on the photo), save round trip with validation errors and stale revision,
  revert, lyrics placements re-read after a note is deleted.
- Frontend unit tests on the operations (pitch step across the octave and with key alterations,
  durations with a divisions change, tie, split and merge, time signature from a measure, chord
  text round trip) and the measure check against the Python one.
- In the browser, on the benchmark photo and on the Gymnopédie page: every flagged measure can be
  selected, shown on the photo, fixed with the toolbar and the keyboard, saved, reloaded and played;
  the lyrics panel still round-trips after a note edit; the page works at phone width.
