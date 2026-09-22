# Plan 0006: Beams, read from the print and fixed with one key

Status 2026-09-22: on hold. The user means to sort beams out another way first, probably OSMD's
`autoBeam` (ADR 0007 decision 6 turns it off; that is the decision to revisit, not this plan's steps).

Status 2026-09-19: written, not started. Rooted in a scratch probe run the same day (numbers in
ADR 0007: 89 of 95 beam groups found on four pages, no false one, 0.3 s a page).

## The problem

The sheet does not look like the page: every eighth has its own flag, because homr reads no beams
and nothing adds them. Beams are how the beat is seen, and on a song page they follow the words.
Two things make it worse than a cosmetic gap:

1. **The readings dialog engraves flags too.** A candidate "sixteenth instead of eighth" should show a
   second beam, and a candidate "quarter" should leave the group; today every card is flags, and the
   comparison by eye the dialog is built for loses the cue a musician uses first.
2. **There is nothing to fix.** If beams were added by a rule (OSMD's `autoBeam`), a beam that the
   print draws across the beat, or a single eighth the print gives a flag, would be wrong and
   unfixable, since the document would carry no beam at all.

What the stack has: homr's segmentation gives noteheads, stems with their direction and the staff
geometry, but no beam mask (ADR 0007, context); the page pixels give the beams to a forty-line
morphological rule; the chord stage already maps noteheads to score notes measure by measure, right
on 95 % of the lead-sheet measures; OSMD renders MusicXML beams and derives the secondary beams and
the hooks from the durations; the editor is a MusicXML DOM whose operations can be made to keep the
beams consistent.

## Decision

ADR 0007, in short:

1. **Detect in the driver**, from the pixels: thick ink minus noteheads, components meeting two or
   more stems (the stem extended from its notehead in the recorded direction), the beam count per
   stem from the ink runs, stubs recorded with their side; `geometry.json` gets `beams` per staff.
2. **Place by the chord stage's mapping** and write standard `<beam>` elements (levels, hooks) and
   `<stem>`; measures whose notehead count disagrees with the score fall back to **beaming by the
   beat**, and `review.json` says per measure which it was. A print beam over a note read longer
   than an eighth splits the group and records a `beam` doubt (information until it is scored).
3. **In the browser a beam is a link to the next note.** `score/beams.ts`: `normalizeBeams` rebuilds
   a measure's beams from the links and the durations; every length-changing operation of
   `edit.ts` ends with it, so undo, autosave, the excerpts and the readings all carry consistent
   beams.
4. **Toolbar: Join next (`j`), Beam by beat** (measure, and score-wide under *Score* for old scores).
5. **Evidence**: the beam count read on a note ranks the durations in the readings dialog.
6. `autoBeam` stays off.

Upgrades: none. No new Python or npm dependency, homr stays pinned at 0.7, OSMD 1.9.9 already
renders explicit beams. What would be an upgrade and is not taken: a learned beam class (only if the
benchmark shows a family of prints the rule misses), Audiveris, music21.

## Validation of the plan

**Complexity.** Backend: `pipeline/beams/detect.py` (about 120 lines, the probe made robust: staff
zone, chord noteheads sharing a stem, the beam count and the stubs), `place.py` (about 150,
reusing `chords.place.system_runs` and `boundaries`), `rule.py` (about 60), a stage in `run.py`,
per-measure entries in `review.json`, tests (about 150). Frontend: `score/beams.ts` (about 150 with
`normalizeBeams`, `toggleJoin`, `beamByBeat`, `canBeam`), its tests (about 120), calls from about
ten operations of `edit.ts`, a toolbar section and a key (about 30 lines), the evidence ranking in
`alternatives.ts` (about 30) and the doubt words for the new kind. Benchmark: `bench/beams/score.py`
(about 120) and a section of RESULTS.md. The detection adds 0.3 s to a 30 to 60 s job.

**UI/UX.** The sheet simply looks like the page; nothing new to learn until a beam is wrong. Then the
gesture is the one the editor already has for ties ("tie to the next note", `t`): select the note,
**Join next** (`j`) joins it to the next or breaks the beam between them; the rest (a second beam on
a sixteenth, a hook on a dotted pattern, the stem direction) follows from the durations, so the user
never chooses a beam level. **Beam by beat** is the escape hatch for a measure the print path did
not get, and for scores recognized before the change. In the readings dialog every card shows its
own beams, which is the visual cue the dialog was built on. Places whose beams were not read from
the print say so ("beams not read from the print, grouped by the beat"), so a beam that looks
unlike the page is explained. Keys: `j` is free (`t` tie, `r` rest, `a`/`b` insert, `f` fill,
`c` checked, `n`/`p` places, `o` readings).

**Correctness.** The document stays valid MusicXML at every step: the normalizer is the only writer
of `<beam>` in the browser, and it runs after every operation that can break a chain (duration,
dot, rest toggle, insert, delete, split, merge, fill, tuplets left as they are). Chord tones carry
the same beam as their group's first note. Beams never cross a barline, a rest or a voice. A group
read from the print that contradicts the transformer (a quarter under a beam) is not forced: the
group splits and the disagreement becomes a doubt, so a wrong beam never rewrites a duration. The
server keeps validating saves as before (`postprocess.inspect` ignores beams). Scores without
geometry (Audiveris fallback, old jobs) are unchanged until the user asks for *Beam by beat*.

**Testing.**

- *Detector*, on the benchmark: `bench/beams/score.py` reads the run outputs of `run_bench.py`
  (the driver's `geometry.json` is kept there), aligns candidate and truth notes with
  `bench/score.py`'s alignment, and scores per measure: groups exactly right, groups missed, false
  groups, notes with the right level, and how many measures took the print path. Sets: the 30 lead
  sheets, clean and photo (the product's page), the phone photo `bench/samples/anton_yvan_boris`,
  and the voice-and-piano scans for the record (cross-staff beams and two voices, expected to be
  poor). Targets from the probe: at least 90 % of groups on the lead-sheet photos, false groups
  under 1 %, print path on at least 90 % of measures.
- *Backend unit tests*: the detector on a synthetic strip (a verovio-engraved measure in the test,
  or a hand-drawn mask: two stems and a bar, one stem and a flag, two levels, a stub, text under the
  staff), the placement on a hand-written geometry with matching and mismatching counts, the rule
  in 4/4, 3/4 and 6/8 with rests, the doubt when a quarter sits under a beam.
- *Frontend unit tests* (vitest, like `edit.test.ts`): normalize after a quarter enters a chain, a
  rest, a deleted middle note, a deleted end, an inserted note, a chord; levels and hooks for
  eighth + two sixteenths and dotted eighth + sixteenth; toggleJoin on and off; beamByBeat in 4/4
  and 6/8; the excerpt keeps beams; the readings order with evidence.
- *Browser*: a lead sheet with a photo at desktop and phone widths: the beams on the sheet, a join
  and a break with undo, a duration change under a beam, the mini sheets of the readings, Beam by
  beat on an old score, Revert.

**Impact on what exists.** `geometry.json` (additive), `review.json` (additive: `beams` per
measure; old files without it load as before), `result.json` stats (additive), `run.py` (one stage),
`homr_driver.py` (one call, the masks are already in memory). The lyrics rewrite and the chords
injection keep note children they do not own. `edit.ts` operations gain a trailing normalize; their
return keys are unchanged. The readings dialog changes nothing but what it engraves. The player,
the form, the note names and the lyrics panel are untouched. The Docker image needs no new package.
The benchmark run outputs have to be regenerated once (the pipeline changes), which also refreshes
the doubt numbers.

## Steps

1. `backend/partition_player/pipeline/beams/detect.py` from the probe, called in `homr_driver.py`
   after `add_notes_to_staffs`; `beams` in `geometry.json`. `bench/beams/score.py` and a first
   table in `bench/RESULTS.md` ("Beams") on the lead sheets and the phone photo, before any
   placement code, so the detector's misses are known and fixed first (the dropped stem, the
   degraded copies).
2. `place.py` and `rule.py`; the stage in `run.py` after chords and before lyrics; the doubt kind
   `beam` (info); `review.json` per-measure `beams`; stats; tests. Second benchmark table: groups
   placed right on the score's notes, print versus rule measures.
3. `frontend/src/score/beams.ts` and its tests; the calls from `edit.ts`; `STRIP_ON_REST` gains
   `beam`; `insertEvent` inherits the link; the excerpt test.
4. Editor: the *Beam* section, `j`, *Beam by beat* on the measure and the score, the words for the
   `beam` doubt and for a rule-beamed place, `commands.ts` and `shortcut`. ScoreView needs nothing:
   OSMD renders the document.
5. Evidence in the readings: `review.json`'s per-measure beam counts reach the session; the
   generator ranks the compatible durations first and labels them ("the print shows two beams").
   Scored on the benchmark (does the rank put the right duration first more often?); the doubt
   stays information unless its precision is at the level of the measure doubts.
6. Browser check on two scores with a photo and one old score; README ("Beams" under *Checking and
   correcting the score*, the key in the keyboard list, the API section for `review.json`),
   BACKLOG, ADR 0007 to Accepted, commit.
