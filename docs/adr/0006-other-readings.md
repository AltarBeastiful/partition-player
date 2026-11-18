# ADR 0006: The other readings of a note, generated from the engine's known mistakes

Date: 2026-09-19
Status: Accepted

## Context

The editor (ADR 0005) lets the user fix a note, and the doubts say where to look, but choosing the
fix still needs music reading. The user's own account of what works: hearing that a measure is off,
seeing where two renderings of a measure differ, and comparing a rendering with the print. Choosing
"dotted quarter" in a toolbar of twenty operations does not.

The engine's mistakes are few in kind and measured (`bench/RESULTS.md`, "Doubts"): a duration a dot
or a flag off (dotted half read as whole 30 times over both sets, dotted quarter as half 12, eighth
as quarter 9, quarter as eighth 14), a rest read as a note or a note as a rest, a pitch one or two
steps off, an octave, a missing accidental, an extra note. The measure check says which of these
would make a short or long measure add up, and the padding rests the pipeline adds record how much
was missing.

## Decision

1. **Candidates come from a closed list of confusion kinds, in the browser, with no model.** For a
   selected note: the durations within two steps on the ladder from whole to thirty-second, the
   pitch one or two steps away, the other accidentals, an octave either way, note to rest and back,
   the note deleted, the note split in two. For a measure that does not add up or was padded: the
   one duration change on any of its events that makes it add up, and the deletion of an event of
   the excess length. Every candidate is an existing operation of `score/edit.ts` applied to a
   clone of the document and checked with `score/check.ts`; candidates that throw are dropped and
   candidates that produce the same measure are merged. Ranking: makes the measure add up, then
   the benchmark frequency of the kind, then the size of the change (`frontend/src/score/alternatives.ts`).
2. **Comparison is by eye and by ear against the print.** A dialog shows the strip of the photo
   framed on the measure, the measure as it stands, and the candidates each engraved on their own by
   OSMD with the changed note marked, a label in the toolbar's words, a play button (the previous
   measure as a run-up, then the measure as read this way, with the accompaniment when it is on),
   and Use, which applies the reading as an ordinary undoable edit and leaves the dialog open.
3. **Listening belongs in edit mode too.** A click in edit mode selects the note and leads the
   playback there, as outside it; after an edit re-renders the sheet, the playback position returns
   to the selected note. A double click on a note, in either mode, opens its readings.

## Alternatives considered

- **N-best output from homr's transformer.** The true second choice of the model, but the decoder
  is greedy per token, the intermediate files are deleted at the end of the job, and the readings
  would need the engine to run again; the closed list covers the same error kinds without it.
- **A language-model second opinion** (BACKLOG). Still to be benchmarked; a suggestion from it
  would be one more reading with a label and a rank, so the dialog is the place it would plug into.
- **Rendering the candidates on the main sheet** (swap the measure in place). Cheaper to build, but
  the comparison the user wants is side by side, and swapping the page's measure on every hover
  re-renders the whole sheet.

## Consequences

- The frontend gains one pure module with unit tests and one dialog; nothing changes on the server
  or in the stored files.
- Ten mini renders of one measure cost about a second; they are made one after another and
  disposed on close.
- The candidate list is only as good as the confusion list: an error of a kind not in it (a measure
  split in two, a wrong time signature) still needs the toolbar, and the dialog says so.
