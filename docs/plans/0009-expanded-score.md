# Plan 0009: The score as played — writing the form out

Status 2026-09-21: done, all five steps, written and built the same day. Asked for after plan 0007
shipped the form panel: once the verses and the chorus have been picked out, offer the page written
out in the order it is sung. Frontend 85 unit tests (14 new, `score/expand.test.ts`), `tsc` clean.
Checked on Anton's real form in the browser at 1280×800 and at 400 px: the link reads *as played (145
measures)*, the file is written in 25 ms and 148 KB of it lands in `~/Downloads`, and OSMD reads it
back as 145 measures whose eleventh is one beat of "relles." and whose twelfth is one beat of "An"
under a Cm — the worked example below, confirmed by a reader that knows nothing of forms. The same
file engraves in verovio and parses in music21 without one warning, and so does a two-staff piano
page (Gymnopédie 1, 39 measures to 54). MuseScore Studio is not installed on this machine, so those
two readers stood in for it; it is the one check of step 5 not made.

What the building changed, from the decisions below:

- **The slice arithmetic lives in `form.ts`, not in `player.ts`.** It is arithmetic about ranges and
  onsets with no sound in it, and putting it there is what keeps `score/expand.ts` clear of Tone.
  `Slice` gained one recorded field, `cut`, because "the section is left here" cannot be recomputed
  from `to` alone: a whole measure at the end of a range ends on the same beat and does *not* cut a
  note that rings past it.
- **A measure is as long as what it holds**, `filledQuarters` — the length `previewNotes` reads back —
  rather than what its time signature asks for. It is the only measurement a pure module has, and on
  the page this plan is named after OSMD agrees with it: the last measure of Anton was read short by
  the engine, and the player and the export both give it one beat, ten times over.
- **Three rules the plan did not foresee**, each of them a reader complaining: the double bar that
  closed the printed page would have closed this one fifteen times, so it is written once at the end;
  a tie whose next measure is no longer next door is dropped at both ends; and a slur cut in two by a
  pass edge is pruned (music21 and verovio both warn about half a slur, and the piano page had four).
  Beams come off a measure cut in two, since half a beam group is not a beam group.

## The problem

The form is now known exactly. The panel of plan 0007 holds sections over measure ranges with
beat-precise edges, `expandForm` turns it into a pass list, and `layPasses` lays the passes end to
end on one timeline — the app knows, to the beat, that Anton is sung verse, chorus, chorus, verse,
chorus, chorus, five times over.

Everything you can **take away** is still the printed page. `Download MusicXML`
(`ScoreView.tsx:368`) serves the server's copy of the score: 19 measures, the words of one verse
under the notes, and the order implied by signs that are mostly not in the file at all — the engine
reads no volta (`BACKLOG.md`: 8 of the 30 benchmark songs have them, all entered by hand), and
D.C./Fine/Coda are neither read nor editable. So the one artefact that leaves the app is the one
that does not know the form.

Three things want the written-out version, in the order they matter:

1. **Reading while singing.** A songbook stacks verses to save paper. A player following the notes
   on verse 3 wants verse 3's words under them, once, in order, with the chorus where it is sung.
2. **Checking the form you just entered.** Today the only proof that a form is right is the ear,
   over the whole song. Written out, a wrong pass is visible in a second: the sections are in front
   of you with their names and their verse numbers.
3. **Getting it into another tool.** A flat score is what MuseScore and friends import best, and it
   is precisely the repeat structure — voltas, D.C., segno — that round-trips worst and that we
   cannot write anyway.

## What is already built

| what | where | what it gives |
|---|---|---|
| the pass list | `form.ts` `expandForm` | ranges + verse per pass, `times` expanded (capped at `MAX_TIMES` = 50) |
| the slice arithmetic | `player.ts` `layPasses` | per measure of a pass: `[from, to)` inside it, a note cut where a section is left early, a note still sounding re-attacked at the edge, an empty slice skipped |
| a measure range as a standalone score | `alternatives.ts` `excerpt`, `inForce`, `putAttributes`, `stripLayout` | the attributes in force written into the first measure, the page layout dropped, a `<part-list>` built |
| notation of an arbitrary length | `edit.ts` `splitQuarters`, `typeFor` | a duration as a list of notatable values, for a clipped note or a short measure |
| measure numbers, divisions | `edit.ts` `renumber`, `ensureDivisions` | |
| which words belong to a pass | `verses.ts` | the rule the dimming layer already uses: keep verse *n*; a note with a single lyric keeps it; a note with several but none numbered *n* keeps them all |
| an OSMD-free reading of a document | `alternatives.ts` `previewNotes` | (time, midi, length) per sounding note, measure lengths as **filled**, ties joined |

The expansion is therefore not new arithmetic. It is the arithmetic the player already does, applied
to XML elements instead of oscillators.

## The worked example: Anton

The form saved with the score (`data/jobs/7d4220e9900e/review.json`) is not the easy case, and that
is why it is the one to build against:

```
Verse   measures 1–11, left on beat 2 of measure 11   (to: 10, toOnset: 0.25)
Chorus  measures 11–19, entered on beat 2 of measure 11 (from: 10, fromOnset: 0.25)
passes  Verse 1 · Chorus ×2 · Verse 2 · Chorus ×2 · … · Verse 5 · Chorus ×2
```

**Measure 11 belongs to both.** Written out at 2/4 with divisions 4, it holds a `<harmony>` Cm at
its head, a quarter C4 carrying the verse's last syllable ("relles."), an eighth G4 carrying the
chorus's first ("An"), and an eighth rest. The section edge at 0.25 whole notes falls exactly
between the first and second note — as it must, since the panel takes an edge from a clicked note.

So the expansion must:

- end the verse with a **one-beat measure** holding the quarter and "relles.";
- start the chorus with a **one-beat measure** holding the eighth, "An", and the eighth rest;
- **re-emit the Cm** at the head of that chorus measure, because the `<harmony>` sits before the
  quarter that was cut away, and the player goes on sounding it there (`layPasses` keeps an
  accompaniment pulse that straddles the edge).

The size, exactly: 15 passes (5 verse, 10 chorus) of 11 and 9 measure elements, **19 printed
measures become 145**, of which **15 are partial**. The file goes from 22.7 KB to roughly 170 KB.

One more thing this page shows: its lyrics are 55 syllables, every one of them `number="1"`, while
the form asks for five verses — the lyrics stage under-reads verse rows on 6 of 25 songs
(`BACKLOG.md`). The expanded page will therefore print the same words under all five verse passes.
That is the right outcome: it is what the app shows and sings today, and it makes a known gap
visible instead of inventing words to fill it.

## Decision

1. **An export, never a document.** The expanded score is generated, downloaded, and forgotten. It
   never becomes the score being edited, because everything in the review stage keys off *printed*
   measure indexes — `layout.systems` and the photo strips, the doubts and their levels, the checked
   set, the form's own ranges. A 145-measure page has no photograph behind it.

2. **The sound is the specification.** The page must be what the player plays, to the beat. The
   slice arithmetic is therefore **extracted from `layPasses` into one pure function** that both the
   player and the exporter call, rather than written a second time: a slice is `{measure, from, to}`,
   an empty slice is skipped, a note is cut where a section is left early, and a note still sounding
   at a slice start is written **as a note there**, which is exactly what the player does when it
   re-attacks it.

3. **A partial measure is written as a partial measure**, `implicit="yes"`, its notes summing to
   `to - from`. Not padded with rests (that would gain a beat, and the page would no longer match
   the sound), not merged with its neighbour (the two halves of Anton's measure 11 are six measures
   apart in the expansion). This is the ordinary notation of a pickup and of a short final measure,
   and OSMD and MuseScore both read it. Where an edge does not land on a note boundary, the clipped
   remainder is notated with `splitQuarters`, tied.

4. **The words of the pass.** For a pass with verse *n*, keep `<lyric number="n">`, drop the others,
   renumber what is kept to 1 — by the same rule as the dimming layer of `verses.ts`, so that the
   printed page says what the app shows and sings. A pass with no verse keeps the lyrics it has.

5. **The order is written, so the signs come off.** `<barline>` repeats and `<ending>` are stripped
   from every emitted measure; a reader that obeyed them would sing the chorus four times. Each pass
   begins on a new system (`<print new-system="yes">`) with a rehearsal mark naming it — "Verse 3",
   "Chorus" — which is the only thing that makes 145 measures navigable.

6. **Attributes are re-emitted only where they change.** `inForce` is evaluated at each slice start
   and written into the measure only where it differs from what is in force at the end of the
   measure just emitted — otherwise a key signature would be printed fifteen times.

7. **It lives in the frontend, and touches no endpoint.** `score/expand.ts`, pure, taking the
   session's document and its pass list and returning MusicXML; the download is a Blob. The
   document expanded is the one on screen, including edits not yet saved, and there is no second
   implementation in Python to drift from the player.

8. **The link says how big it will be** — "as played (145 measures)". It is one number, it costs
   nothing, and it is a second look at the form before the file is written.

## Steps

1. **Extract the slices.** Pull the per-measure `[from, to)` arithmetic out of `layPasses` into
   `sliceRanges(passes, measureDuration, measureCount): Slice[]`, and have `layPasses` call it. No
   behaviour changes; the existing player tests must pass untouched.

2. **`score/expand.ts`.** For each slice: import the measure, drop what falls outside `[from, to)`,
   clip a straddling note, mark it `implicit` when it is short, re-emit the harmony in force and the
   attributes that changed, strip repeats, endings and layout. Then `renumber`, and the pass
   headings. Multi-part scores get the same slices in every part, so the parts stay aligned.

3. **The property test, which is the point of step 1.** For a set of forms — Anton's real one, a
   plain two-verse page, a section entered and left mid-measure, a pass with `times` — read the
   expanded document with `previewNotes` and compare it, note for note, with the concatenation of
   `previewNotes` over the source slices: same count, same time, midi and length within 1e-9. The
   page and the sound then agree by construction rather than by inspection. Plus unit tests for the
   lyric selection, the stripped repeats, and the attribute rule.

4. **The UI.** The pair of links in the controls row: `Download MusicXML — as printed · as played
   (N measures)`, the second one shown only when the form makes the page longer than it is printed
   (a page played once, straight through, has nothing to expand).

5. **Check it for real.** On Anton at 1280×800 and at phone width: the file downloads, measure 11
   comes out as a one-beat ending and a one-beat pickup with its Cm, the five verses carry their
   rehearsal marks. Open it in MuseScore Studio and in a fresh tab of the app to confirm both read
   it; play it against the app's own playback and listen for a beat gained or lost at a section
   edge. Then a piano page from the benchmark, for the two-staff case.

## Rejected

- **Expanding on the server.** The form and the score are both saved, so it could be done in Python
  — and then the sound and the page would be two implementations of one rule, and would drift the
  first time a slice edge changed. The player owns that rule; the exporter borrows it.
- **Making the expansion the document you edit.** It would double or quintuple the page, cut it
  loose from the photo it was read from, and break every doubt, check and section range, all of
  which are indexed by printed measure. The compact page is the score; this is a rendering of it.
- **Rendering the expanded score in the app.** The sheet is already the slowest thing on the page
  and this makes it 7.6× longer on Anton. It is a print artefact first; if it is wanted on screen
  later it should be its own read-only route, not a mode of the editor.
- **Padding a partial measure to a full one.** It would add a beat that nobody sings and silently
  break the correspondence with the timeline — the one property this feature has to keep.
- **Writing proper repeats and voltas instead.** That is the opposite feature: it needs structure
  the engine never reads and the editor cannot enter (`BACKLOG.md`, the volta editor). Writing the
  order out is precisely how we avoid needing signs we do not have.

## Non-goals

Nothing here changes a note of the recognition, the form, or the playback. It adds one file format
of one thing the app already knows. No new endpoint, no new stored file, nothing kept on the server.
