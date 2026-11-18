# Plan 0005: Listening in edit mode, and the other readings of a note

Status 2026-09-19: steps 1 to 5 done. Checked in the browser on two scores with a photo (a 16th in a 6/8
measure, a padded 3/4 measure whose fix ranks first), at desktop width and at 400 px; frontend 31
unit tests, build clean. Implementation notes: the mini sheets are keyed by reading id and document
version; the editing keys are held back while the dialog is open, except undo and redo (the dialog
has an Undo of its own); a close crop of the photo spans at least a system's worth of print.

## The problem

A wrong note is easy to hear and hard to fix. With the score playing, the ear catches the measure
that is off; the editor then offers a toolbar of twenty operations, and choosing among them needs
music reading the user does not have. What the user is good at: hearing that a measure sounds off,
comparing two renderings of a measure and seeing where they differ, and comparing a rendering with
the print. What the app knows and does not yet use: the kinds of mistake the engine makes are few and
measured (ADR 0005, `bench/RESULTS.md` "Doubts": a duration a dot or a flag off, a rest read as a note
or a note as a rest, a pitch one or two steps off, an octave, a missing accidental, an extra note),
and the measure check says which of these would make the measure add up.

Two gaps in the current editor:

1. **Listening while editing.** Outside edit mode a click leads the playback to the note; inside it a
   click only selects. To hear a passage again while correcting it, the user has to leave edit mode.
2. **No help choosing the correction.** The selected note and its measure are described in words, the
   photo strip shows the print, and the toolbar waits. Nothing says "it was probably one of these".

## Decision

1. **In edit mode a click selects the note and leads the playback there**, in every player state, as
   outside edit mode; Space then plays from the selected note. When an edit re-renders the sheet
   (which stops playback), the playback position goes back to the selected note, so Space replays
   the passage just changed. The two modes still differ in what a click *also* does (select) and in
   the frame colour.
2. **A note has a list of other readings**, generated in the browser from the benchmark's confusion
   kinds, no model: every duration within two steps on the ladder whole, dotted half, half, dotted
   quarter, quarter, dotted eighth, eighth, dotted sixteenth, sixteenth, thirty-second; a pitch one
   or two steps up or down; the other accidentals; an octave up or down; note to rest and rest to
   note; no note here (deleted); two notes of half the value instead of one. When the measure does
   not add up, or was padded by the pipeline, the readings that make it add up are generated for
   every event of the measure (the dotted quarter that was read as a quarter can be any note of the
   measure, not only the selected one) and ranked first. The ranking is: fixes the measure, then the
   benchmark's frequency of the kind, then the size of the change. Readings that produce the same
   measure are merged.
3. **The readings are compared by eye and by ear, against the print.** A dialog shows the strip of the
   photo framed on the measure, then one card per reading: the measure engraved on its own by OSMD
   with the changed note marked, a label in words ("dotted quarter instead of quarter", "measure adds
   up"), a play button (the previous measure for a run-up, then the measure as read this way, with the
   accompaniment of those measures if it is on) and a Use button. The first card is the measure as
   it stands. Use applies the reading as an ordinary edit (undoable, saved, the measure counts as
   checked) and the dialog stays open on the new state, so a second change can follow. The dialog
   opens from the toolbar ("Other readings", key `o`) and from a double click on a note in either
   mode (which enters edit mode).

What this is not: a second engine, a language model or an n-best list from the transformer. Those
remain in the backlog; the candidate list is the seam they would plug into (a model's suggestion is
a reading with a label and a rank).

## Validation of the plan

**Complexity.** One new pure module (`score/alternatives.ts`, the generator and the excerpt of a
measure as a standalone MusicXML, about 300 lines with tests), one small Player addition (preview of
a note list on the loaded sampler, about 60 lines), one dialog component (about 250 lines) and CSS,
and about 40 lines of wiring in ScoreView. Every candidate is an existing operation of `score/edit.ts`
applied to a clone of the document and checked with `score/check.ts`; nothing new is written to the
MusicXML and nothing changes on the server. Ten mini renders of one measure each cost about a second
on a laptop; they are made one after another so the page stays responsive, and disposed on close.

**UI/UX.** The dialog is a focused comparison task, so it is modal: the print at the top as the
reference, the current reading first, the candidates under it in the order of likelihood, six shown
and the rest behind "More". Each card has the same three affordances (look, play, use). The label
says the change in words the user has already met in the toolbar (whole, half, quarter, dot, ♯ ♭ ♮,
8va), never in theory terms. The change is marked on the mini sheet, since spotting a difference is
what the user does well. On a phone the cards stack in one column and the mini sheet scales to the
width. Escape and Close leave; Use keeps the dialog open because one measure often needs two fixes.
The double click gives the listening flow a direct path: hear it, double-click it, compare.

**Correctness.** Candidates are applied to a clone of the document, so a candidate that throws
(a rest has no pitch, an octave off the piano) is dropped, never shown. The reading that is chosen is
applied to the live document through `session.apply`, so undo, autosave, the checked mark and the
form remapping behave as for any edit. Keys are the ones the sheet already uses (measure, staff,
voice, onset, midi) and the list is regenerated whenever the document changes. The excerpt carries
the divisions, key, time and clef in force at the measure, so the mini sheet is engraved like the
page. The preview plays the measure as it is (a short measure plays short), chord tones together,
tied continuations extended, and stops the main playback first so two things never sound at once.
Unit tests cover the generator on the benchmark's confusion cases (a padded 3/4 measure, an
overfull one, a pitch, a rest, a grace note, a tuplet) and the excerpt's attributes.

## Steps

1. `frontend/src/score/alternatives.ts`: `excerpt`, `previewNotes`, `readings`; vitest tests.
2. `frontend/src/player.ts`: `preview` and `stopPreview`. `frontend/src/editor/sheet.ts`: `markNotes`.
3. `frontend/src/components/Readings.tsx`: the dialog; `PrintedStrip` framed on a measure; CSS.
4. `ScoreView`: click in edit mode seeks, re-seek after a re-render, the dialog's state, the toolbar
   button, the `o` key, the double click.
5. Check in the browser on a score with a photo, at desktop and phone widths; README, BACKLOG,
   ADR 0006; commit.
