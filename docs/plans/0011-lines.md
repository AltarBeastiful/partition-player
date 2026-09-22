# Plan 0011: An instrument for each line, and a line that goes on underneath

Status 2026-09-22: **done**, all eight steps. Frontend 122 tests (14 new: `lines.test.ts`,
`voices.test.ts`, the player's lines and under-line cases, the expansion's loop part), backend 100
(the sound round trip and its six rejections inside the editor's API test), `tsc` clean.
Checked in the browser on the page that asked for it — the photograph of *Auprès du ruisseau*, read
by homr as one part with two staves, 20 measures, 87 notes, 5 chords. With the top staff set to
flute over measures 1–8 and piano after, and the flute told to go on from measure 9, the timeline
holds 22 flute events in the printed eight measures, 36 more under the voices, and 245 piano ones;
both sample sets load from the CDN with no failure; the choice survives a reload (the panel comes
back reading *Top staff: flute, then piano · Bottom staff: piano · flute goes on under m. 9*), and
*Duplicate as played* writes a second part, `Top staff, going on`, of exactly the main part's twenty
measures.

What the building changed, from the decisions below:

- **The loop had to be re-barred.** Written as its own tiles, the loop part came out with 21 measures
  against the page's 20 — because the tiles are laid on time and this page's measure 19 holds seven
  quarters. A part with its own bar count is not a score any reader can lay out, so the export lays
  the tiles **into the form's own measures**: one measure here for one measure there, of the same
  length, holding the pieces of the loop that fall in it, and a measure rest before it comes in.
  Nothing is tied across a piece boundary, because a note is only cut where the loop wraps, and what
  follows a wrap is the loop beginning again.
- **The as-played export hid itself.** It is offered only when the form writes more measures than the
  page has, which is exactly false for a page played straight through — the canon page. With a line
  going on underneath, the file differs from the printed page whatever the form does, so the button
  now appears for that too.
- **An under-line has its own switch.** It carries the index of its record, not just the staff it is
  printed on: silencing the top staff to hear the lower voice alone must not take the flute away,
  since on this page they are the same staff.
- **`review.load()` names the new keys in the same commit that writes them**, and the round trip
  asserts they come back — the lesson of plan 0008, and the other session working on plan 0012
  flagged the same trap from its side the same hour.

Decisions in ADR 0008.

## The problem

*Auprès du ruisseau* (photographed 2026-09-22) is a canon for two voices with a flute. The flute has
measures 1 to 8 to itself; from measure 9 the same two staves are *Vx. 1* and *Vx. 2* and sing the
tune against itself, a measure apart, with a 6/4 bar near the end. Played by the app as it stands,
the page is a piano playing eight measures of tune and then twelve of two-part writing, and the
flute — which in performance keeps going under the singing — falls silent at measure 9 and never
comes back.

Two lacks, one small and one structural:

- Every line sounds the same, because there is one sampler for the page (`player.ts:364`) and
  `collect()` flattens every staff into one list of notes (`player.ts:202`).
- There is one order of play for the page (`Pass[]`, one timeline, `layPasses`), so nothing can run
  beside it on its own clock.

## What is already built

| what | where | what it gives |
|---|---|---|
| a voice that is not on the page | `chords.ts` `accompaniment()`, merged in `layPasses` | the exact pattern an under-line follows: own events, own switch, own velocity, one timeline |
| slicing a range of measures onto time | `form.ts` `sliceRanges` | the tiling arithmetic, cuts and onsets included |
| the line of a note, at collect time | OSMD `ParentSourceStaffEntry.ParentStaff` | `idInMusicSheet` and `ParentInstrument.Name` |
| a written-out score per part | `score/expand.ts:329-401` | every `<part>` written from a slice list; only the list is shared today |
| the form saved and validated | `review.py` `validate_form`, `save` | where `lines` and `unders` go, and the shape to copy |
| a sampler and a scheduler | `player.ts` | `triggerAttackRelease` on one instrument; nothing about it is piano-specific |

Measured on 2026-09-22 (fully in ADR 0008): the `tonejs-instruments` collection has 20 sets, samples
CC-BY 3.0 and code MIT, pinned at `622c2f1` (untouched since 2022-05-07), served by jsDelivr —
flute 10 files / 1.7 MB (C4 to C7), clarinet 11 / 2.6 MB, violin 15 / 4.6 MB, organ 21 / 5.9 MB,
harmonium 38 / 8.2 MB, against the piano's 21 files of about 80 KB. No voice or choir set exists in
it. `review.load()` drops any key it does not name literally (`review.py:42`).

## Steps

1. **The lines of the sheet.** `frontend/src/lines.ts`: `linesOf(osmd): Line[]` with
   `{ id, name, index }` — `idInMusicSheet`, the instrument name when the document has one, else
   *Top staff* / *Bottom staff* / *Staff n* — and the per-note line read in `collect()` from the
   voice entry's parent staff.
   *Check:* unit tests over a one-staff lead sheet fixture and a two-staff fixture; a one-line page
   gives exactly one line, named *Melody*, so nothing downstream has to special-case it.

2. **The voice bank.** `frontend/src/voices.ts`: a committed table, one entry per offered instrument
   (`piano`, `flute`, `clarinet`, `violin`, `cello`, `organ`, `harmonium`, `guitar-nylon`, `harp`,
   `trumpet`, `xylophone`), each with its pinned base URL, its sample map after thinning (every
   second above 16, every fourth above 32), its written range and its gain in dB; `voiceFor(name)`
   returns a `Tone.Sampler`, made once and kept, the piano on failure. The table is generated once by
   `scripts/sample-table.mjs` from the repository listing and committed as data — the app never lists
   a CDN at runtime.
   *Check:* a test that every entry's keys are note names Tone accepts, that no map exceeds 16
   samples, and that every instrument named by the table exists in the picker's list.

3. **The player routes by line.** `NoteEvent` gains `line: number`; the player keeps a sampler per
   instrument in play and picks it per event from the instrument ranges of decision 2;
   `setLine(id, on)` beside `setTrack`; the accompaniment keeps its own switch and plays on the
   piano. A page with one line behaves exactly as before.
   *Check:* `player.test.ts` — a two-line timeline whose events carry their lines; a range that
   changes instrument at a measure puts the right sampler on either side of it; the existing tests
   stay green untouched.

4. **The line that goes on underneath.** `form.ts` gains
   `Under { staff, from, to, startAt, instrument }` and a pure `underSlices(under, measureDuration,
   total, slices)` that tiles the source measures on time from the first stretch of `startAt` to the
   end, cutting the last tile; `layPasses` takes `unders` and merges their events into the timeline
   with the line's own velocity.
   *Check:* `form.test.ts` — eight measures tiled under twelve gives one and a half rounds, the cut
   falls where the form ends, a 6/4 measure in the middle shifts the tiles off the barlines and the
   arithmetic still adds up, an `Under` whose `startAt` is never reached produces nothing.

5. **Saved with the form.** `review.py`: `validate_lines` and `validate_unders` (a staff that is on
   the page, measures inside it, an instrument from the table, a small cap on how many), `load()`
   naming both keys, `save()` writing them; `api.ts` carries them; the session sends them on
   autosave as the form is sent.
   *Check:* backend tests for each rejection, and a round trip through `PUT /score` that asserts
   `lines` and `unders` come back unchanged — the assertion plan 0008 had to add for the form.

6. **The controls.** `ScoreView.tsx`: a *Lines* row, one line per line — name, on/off, an instrument
   picker that says when the line goes below the set's written range, and *changes at measure…* to
   split the range; in the form panel, *… goes on playing measures a–b, from measure c* with its own
   instrument picker. The footer credits the two sample collections.
   *Check:* `tsc`, the unit tests, then the browser at 1375 px and on the phone width the BACKLOG
   cares about.

7. **The written-out score.** `expand.ts`: the per-part loop takes a slice list per part instead of
   one for all; an under-line is written as an extra `<part>` with a `part-name`, its measures the
   tiles, a cut tile `implicit="yes"`.
   *Check:* `expand.test.ts` — the existing cases unchanged (a page with no under-line exports what
   it exports today, asserted byte for byte against the current output), plus the canon page's flute
   part written out and read back through the import door, which is `Duplicate as played` end to end.

8. **The real check, by ear.** The canon page: read it from the photo, or import a hand-written
   MusicXML of its twenty measures if homr does not give two usable staves (there is no MuseScore and
   no LilyPond on this box, so the fixture is written by hand and lives in the frontend tests either
   way). Set line 1 to flute over measures 1 to 8 and to piano after, set the flute to go on from
   measure 9, listen: the canon must still be a canon, the flute must be in step at the 6/4 bar, and
   the chords must still be under the voices. Then a lead sheet and the Anton page, to hear that
   nothing moved for a page that uses none of this. Then `README.md` and `BACKLOG.md`.

## What could go wrong

- **The photo may not read as two staves.** homr is a lead-sheet and piano reader; a two-staff
  choral page with the staff labels changing mid-page is not what it was measured on, and the flute
  system's lower staff is eight bars of whole rests. Step 8 says what to do about it, and nothing
  else in the plan depends on the reading: the feature is playback over a document, wherever the
  document came from.
- **Third-party sounds over a third-party CDN.** A set that fails to load costs the timbre and not
  the app (decision 3), but an offline user gets the piano and should be told once, not per note.
- **Polyphony on a phone.** Three samplers, each with its own voices, on a two-line page with an
  accompaniment. Measure it on the phone in step 8 before offering more instruments.
- **Loudness between sets.** The gains in the table are by ear on this page; a set that is wrong
  elsewhere is a one-number fix, not a design one.
- **The under-line and the practice loop.** Looping a window replays whatever tiles fall in it, which
  is the same music every time round. That is intended (decision 7) and worth a line in the panel's
  title text, because "the flute restarts in the middle of its phrase" is otherwise read as a bug.
- **The flute below C4.** The set starts at C4 and stretched samples go dull; the picker says so
  (step 6) rather than refusing the choice.
