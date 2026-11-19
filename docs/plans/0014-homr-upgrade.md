# Plan 0014: Move to homr 0.7.1, then to homr `main`

Status 2026-11-19: **step 1 tried twice, NO-GO both times, pinned back to homr 0.7.0** (`homr==0.7.0` in `backend/pyproject.toml`).
Step 2 (`main`, commit `83130ba7`) was trialled the same day: NO-GO, same result (see "Step 2" below).
The driver patch for 0.7.1 works and is kept in git as commit `d1a2b61` (reverted right after, so
it can be cherry-picked when homr moves again). No ADR yet: if the trial of `main` ships, the
decision to pin an engine by commit is one and gets written then (ADR 0002 already names homr as the
engine and Audiveris as the fallback).

## Step 1 result: homr 0.7.1 (2026-11-18)

Driver patched (`d1a2b61`): `load_and_preprocess_predictions` returns three values, `detect_staff`
takes the symbols plane, `repair_systems` runs before parsing, the XML generator returns an
ElementTree element, `autocrop_with_offset` replaces our replica, the title reader must be set up
(`download_ocr_weights`), and each staff's raw stream is recorded by staff object and not by index
(hidden staffs shift the index). Dependencies: `homr[cpu]>=0.7.1`. Backend tests: 144 passed. Anton
photo: event error rate **0.00**, 55 of 55 notes, 19 of 19 measures. Run on rapidocr 3.9.2 (3.10.0
breaks the chord reader: `ocr.text_rec` is `None`; unrelated to homr, and the pin `>=3.9,<4` allows it).

Benchmark, same pages, plan 0013's results of the same day as baseline (homr 0.7.0), the three sets
re-scored with `bench/songs/run_bench.py`:

| criterion | lead sheets (60 pages) | voice and piano (60) | IMSLP scans (10) |
|---|---|---|---|
| right measure counts | 57 -> **45** (fail) | 58 -> 60 | 10 -> 10 |
| pitch + duration | 6456 -> 6457 of 6480 | 4136 -> 4450 of 4526 | 466 -> 517 of 596 |
| false syllables | 157 -> 115 | 17 -> 67 (rise) | 7 -> 2 |
| false chords | 61 -> **62** (rise) | 19 -> 33 (rise) | 1 -> 4 (rise) |
| Anton photo | error rate 0.00 | | |

Verdict **no-go** by the gate as written: the tally of right measure counts drops on the lead
sheets and false chords rise on all three sets. Why: homr 0.7.1's XML generator writes **extra
measures**, 12 lead-sheet pages end up one to three measures over (Camptown Races 17 -> 18, La
marche des rois 20 -> 23, Aupres de ma blonde 15 -> 17). `engine.musicxml` itself holds them: an
attributes-only measure before a forward repeat bar (Camptown, Votre divin maitre), and empty
measures in the middle of a system (La nave del olvido, La marche des rois, Mattinata). The lyrics
then lose their alignment (syllables placed fall from 9946 to 7996 on the lead sheets). We could
drop empty measures in `postprocess`, but the revert rule is to pin back and not patch around.

Read with care: the voice-and-piano and scan baselines are the stored plan 0013 results, whose
lyrics placement is visibly lower than today's (1138 against 4279 syllables placed); the rises in
false syllables there come with that. Pitch and duration on those two sets goes up by 314 and 51
notes, so 0.7.1 reads better there; a clean control run of `d63c27b` on 0.7.0 would be needed to
say how much. It was not made because the lead sheets already decide the gate (their baseline equals
plan 0013's table exactly: 6456, 157, 61, 57 of 60).

Meter overlap (ticket check): on 130 run pages, 16 carry a mid-page time mark, and on 12 of those
homr 0.7.1 writes its own `<time>` at a marked measure. `postprocess._set_time` removes any `<time>`
in the measure before it writes ours, and when our rule decides nothing homr's guess stands, so there
is one writer per measure and they do not double up. Not a reason for or against the step.

To retry: see the second attempt below (`a8d9df3` holds the driver patch and the empty-measure fix).

## Step 1, second attempt: homr 0.7.1 with the empty measures dropped (2026-11-19)

Cause of the extra measures, read in homr's generator (`music_xml_generator.build_measures`): the
`repeatStart` token closes the current measure and opens a new one, whether or not anything was played
since the barline before it, and a volta stop does the same. A repeat that opens a page or a system
therefore leaves a measure with attributes, a print mark or a barline and no note (Camptown: measure 1
holds only the clef, key and time; La marche des rois: three empty measures between the voltas).
`drop_empty_measures` (`postprocess.py`, test in `test_postprocess.py`) removed a measure that no part
plays in (a rest counts as played) and handed what it carried to its neighbour. Because the chord,
lyrics, layout and time-mark stages index measures through `geometry.json`, the driver called it on
homr's XML and renumbered the per-system counts and the time marks with it (driver patch plus this
wiring: commit `a8d9df3`). It is not on the integration branch: nothing calls it at the pinned homr
0.7.0. **Retry path: `git cherry-pick a8d9df3`**, with two reviewed bugs to fix first: when several
empty measures share one forward target they are inserted in reverse order, and a trailing empty
measure (no forward target) misplaces or duplicates its `<print>` and attributes. Counts came back (Camptown 17, La marche des rois
20, La nave del olvido 29) and the Anton photo is **0.00** (55 of 55, 19 of 19). Backend tests: 146 passed.
rapidocr is pinned `>=3.9,<3.10` (3.10.0 leaves `ocr.text_rec` None and breaks the chord reader);
this pin stays whatever the verdict.

Control: a fresh run of 3cc9f6e (homr 0.7.0, rapidocr 3.9.2) on all three sets, same pages. It equals
the stored plan 0013 numbers (leadsheets 6456 / 57 / 157 / 61; voice and piano 1138 syllables placed),
so those baselines were not stale: 0.7.0 really places few words on a grand staff.

| criterion | lead sheets (60) | voice and piano (60) | IMSLP scans (10) |
|---|---|---|---|
| right measure counts | 57 -> **55** (fail) | 58 -> 60 | 10 -> 10 |
| pitch + duration | 6456 -> 6457 of 6480 | 4143 -> 4450 of 4526 | 466 -> 517 of 596 |
| syllables placed | 9946 -> 9650 | 1138 -> 4278 | 10 -> 575 |
| false syllables | 157 -> 150 | 17 -> **67** (rise) | 7 -> 2 |
| false chords | 61 -> 61 | 19 -> **33** (rise) | 1 -> **4** (rise) |
| Anton photo | 0.00 | | |

Verdict **no-go** again, by the gate as written: the right-measure tally drops on the lead sheets
(57 -> 55) and false syllables and false chords rise on the voice and piano set (and false chords on
the scans). Pinned back to 0.7.0 (the 0.7.1 driver stays in `a8d9df3`).

Read with care. The measure counts of the 12 pages that broke the first attempt are all back to the
control's; the two that remain are not empty measures but homr's own reading under 0.7.1:
`en_home_on_the_range_photo` 32 -> 33 and `it_mattinata_photo` 29 -> 28. The rises in false syllables
and chords on voice and piano come with a four-fold rise in syllables placed (1138 -> 4278): 0.7.1
reads the grand staff well enough to place words that 0.7.0 never reached, and the words it places
wrongly count as false; pitch and duration there rises by 307 of 4526 and by 51 of 596 on the scans.
That is a trade the gate cannot see. If the maintainer decides the gate should weigh false against
placed (for example false per syllable placed, 1.6 % against 1.5 % on voice and piano), the step is
ready: cherry-pick `a8d9df3`, set `homr[cpu]>=0.7.1,<0.8`. One writer of time changes per measure
still holds (`_set_time` removes any `<time>` before writing ours), and the marks are renumbered with
the dropped measures.

## Step 2: homr `main` trial (2026-11-19): NO-GO, stay on 0.7.0

Installed from git at `83130ba7a190aa83c3ca32b6638199652eb0d778` ("filter 4 invalid samples from pdmx",
67 commits after v0.7.1; reports itself as `0.7.1.post67`), in a venv of its own, with
`homr[cpu] @ git+https://github.com/liebharc/homr.git@83130ba7...` and `allow-direct-references`
in pyproject. The trial is the commit `f235dbb` and is reverted right after (`77a163f`), so the
integration branch carries no git dependency; `git cherry-pick f235dbb` brings it back. Rapidocr 3.9.2,
numpy 2.5.5, onnxruntime 1.32.0. Models are downloaded on first run: a new staff-relation model
(`staff_relations_pdmx2`, `staff_pieces_h1`) joins the segnet and the transformer.

Driver changes on top of the 0.7.1 driver and `drop_empty_measures` (a8d9df3, see above): homr `main` groups staffs into
systems with a model (`homr.main.group_staffs`) and no longer has the brace/dot detection or
`Staff.y_distance_to`; the driver calls `group_staffs` and keeps a local `y_distance`. Wrapping
`parse_staff_image` and `StaffRegions` still works (`StaffRegions` moved to `homr.staff_regions`, the
name in `staff_parsing` is the one to patch). Backend tests: 146 passed. Anton photo: event error rate
**0.00** (55 of 55, 19 of 19). A page takes about the same time as on 0.7.1.

Same criteria as ticket 02, same pages, control = the fresh 0.7.0 run above:

| criterion | lead sheets (60) | voice and piano (60) | IMSLP scans (10) |
|---|---|---|---|
| right measure counts | 57 -> **56** (fail) | 58 -> 60 | 10 -> 10 |
| pitch + duration | 6456 -> 6465 of 6480 | 4143 -> 4467 of 4526 | 466 -> 512 of 596 |
| syllables placed | 9946 -> 9831 | 1138 -> 4286 | 10 -> 576 |
| false syllables | 157 -> 151 | 17 -> **64** (rise) | 7 -> 2 |
| false chords | 61 -> 61 | 19 -> **33** (rise) | 1 -> **4** (rise) |
| Anton photo | 0.00 | | |

Verdict **stay on 0.7.0**: the gate fails exactly as it did for 0.7.1, and for the same reasons (the
one lead-sheet page that drops a measure is `it_mattinata_photo`, 29 -> 28, the same page as under
0.7.1; false syllables and chords rise on voice and piano with the four-fold rise in syllables placed).
`main` brings nothing the gate can see over 0.7.1: the numbers are within a few notes of the second
0.7.1 attempt. The reading of voice and piano is clearly better (+324 notes right, 60 of 60 measure
counts, Elgar and Beethoven now right), which is the same trade as before; if the maintainer
changes the gate to weigh false against placed, step 2 and step 1 become the same decision, and
`main` is then not worth a git dependency over 0.7.1.

For ticket 05 (what `main` writes natively; our code is untouched), counted in homr's `engine.musicxml`
over the benchmark pages, with 0.7.0 as the control:

- **Beams**: `main` writes `<beam>` elements, 3933 on 56 of the 60 lead-sheet pages (0.7.0: none).
  They come from the model's beam tokens (`convert_beams`), not from a pixel rule. Not scored against
  our beam rule yet: that comparison is ticket 05's work.
- **Octave shifts**: `<octave-shift>` on 7 voice-and-piano pages (19 elements in all), none on the
  lead sheets (0.7.0: none). Pitches are written as sounding pitch (`ConversionState.sounding_pitch`).
  Whether they are right was not checked against the printed 8va marks.
- **Time changes**: on the lead sheets 2 pages carry a second `<time>` (0.7.0: none). `main` takes the
  previous page's time as an input (`inherited_times`, used by multi-page runs) and otherwise infers
  the time from measure lengths per voice. Our rule (plan 0013) is still the writer in the driver; the
  canon photo was not re-run in isolation.

## Step 3: rapidocr 3.10 (ticket 09, 2026-11-19): cap stays at `<3.10`

Cause of the 3.10.0 break: it loads its models on the first call, so `RapidOCR(...)` leaves `text_det` and
`text_rec` as `None`, and only `chords/ocr.py` (`make_ocr`, `_detect`, `read_band`) reaches into them.
Fix, kept whatever the verdict: `make_ocr()` calls `_load_det_model` and `_load_rec_model` when present
(a no-op on 3.9); `test_make_ocr_has_its_detector_and_recognizer_loaded` fails on 3.10.0 without it and
passes on both (backend tests: 151 passed on 3.9.2 and on 3.10.0, commit `a964894`). 3.10.0 is the only
3.10 on PyPI today. Also changed in 3.10: `limit_type="max"` now works in detection (#740), which the
lyrics stage uses.

Re-score on the chord and lyrics benchmarks, homr 0.7.0 both times, only rapidocr differs (3.9.2 control
against 3.10.0), same pages, run sequentially per set (no `--jobs`; those two scripts have none).

| chords (36 pages) | 3.9.2 | 3.10.0 |
|---|---|---|
| found, clean / photo / real | 365 / 374 / 10 | 365 / 374 / 10 |
| right | all found | all found |
| false chords | 0 | 0 |
| placed, clean / photo | 317 / 335 | 317 / 335 |

Chords are identical page by page.

| lyrics (39 pages) | 3.9.2 | 3.10.0 |
|---|---|---|
| syllables placed (real + clean + photo + paragraph) | 4530 | 4529 |
| text right | 5154 | 5151 |
| exact | 4404 | 4399 |
| verses found | all | all, same |
| false syllables | 3 (clean 2, photo 1) | 4 (clean 3, photo 1) |
| false verses | 0 | 0 |

Lyrics move on 28 of 39 pages, both ways (Gloria text 26 -> 28 and 27 -> 29, Au clair de la lune and
the Anton photo cer 0.005 -> 0.000; Foster 119 -> 118 and 119 -> 116, Jigs 2 259 -> 256).
Verdict: the chords pass; the lyrics pass the letter on false verses (0) but not on "no drop in aligned
syllables" (4530 -> 4529, false syllables 3 -> 4, one more on `lyr_nott_ashover_9`) and the change is
within noise of the detector rather than a gain. There is no reason to take the risk for nothing, so
the pin `>=3.9,<3.10` stays. If the maintainer judges a one-syllable move in 4530 to be noise, lifting
the cap is the single edit `rapidocr>=3.9,<4` in `backend/pyproject.toml`; the code already works on 3.10.

## Problem Statement

We are on homr 0.7.0 and the driver that wraps it copies about twenty of homr's internals and a mirror
of its `process_image` flow, so that it can keep the time-signature marks and the measure counts that
homr drops. homr has moved: 0.7.1 (released 2026-11-10) is a refactor, and `main` has unreleased work
on beams, time signatures across pages and octave shifts, which overlaps with plans 0006 and 0013.
Staying put means the engine's own fixes never reach the page; moving without a measure means we cannot
tell a better engine from a different one.

## Solution

Upgrade in two steps, each of them judged on the song benchmark and each of them revertible.

**Step 1, homr 0.7.1** (the released version, inside the existing `>=0.7,<0.8` pin). Patch the driver,
re-score every set, and keep it only if the criteria below hold; otherwise pin back to 0.7.0.

**Step 2, homr `main`**, only once step 1 is merged and stable. Installed from git and pinned to an
exact commit, never a floating branch. It may ship to production if it passes the same criteria and the
deploy is checked.

Where homr now does natively what we do ourselves (beams, a time change, the numerator of a bar), our
code stays until the benchmark shows homr's version is at least as good. Ours is then removed in a
commit of its own. The two are never active at once.

## User Stories

1. As the maintainer, I want the driver to stop copying homr's `process_image`, so that the next homr
   refactor costs a small fix and not a re-derivation.
2. As the maintainer, I want one homr internal to wrap (a staff's raw token stream, before the
   duplicate-removal), so that plan 0013's time marks survive any release.
3. As the maintainer, I want the benchmark re-scored on every engine change, so that a better engine
   and a different engine are told apart by numbers.
4. As the maintainer, I want a failing upgrade to end in a one-line pin back to 0.7.0, so that trying
   one costs nothing.
5. As a user photographing a page, I want the same or better notes, chords and words, so that an
   upgrade never makes the app worse.
6. As a user, I want a deploy that keeps working inside the host's 3 GB cap, so that the site stays up.
7. As the maintainer, I want `main` pinned by commit, so that a deploy is reproducible.
8. As the maintainer, I want our beam and meter code kept until homr's version wins, so that there is
   never a period with two writers of the same fact.
9. As the maintainer, I want each step to record its numbers in this plan, so that the next person sees
   what was measured and not what was hoped.

## Implementation Decisions

- **0.7.1 is not drop-in, and it is not a rewrite.** Measured by diffing the released wheel against the
  installed 0.7.0 (a reading of the diff, to be confirmed by running it):
  - Two helpers the driver imports for counting staffs and voices no longer exist.
  - The function that loads and preprocesses the predictions returns three values and not two.
  - The XML generator returns an ElementTree element and no longer the `musicxml` library's object, so
    how the driver writes the file changes. That library is dropped.
  - onnxruntime becomes an optional extra of homr, so our own dependencies must ask for it (the CPU
    extra) or a fresh install has no runtime.
  - Systems with differing staff counts, hidden staffs and unmarked triplets are handled by new code in
    homr's staff parsing, and positions now include a second upper and a second lower.
  - The page crop is a wrapper over a function that returns its offset, so the driver's replica of it
    can go; the paper-colour fill it adds changes pixels.
- **The time marks stay ours.** The vocabulary still has no numerators and a repeated mark is still
  dropped, so plan 0013's premise holds. What changed: homr now guesses a numerator of its own for the
  marks that survive. Our rule (the bar's own length, two voices at least agreeing, neither the meter in
  force nor twice it) is checked against that guess so the two do not double up.
- **Wrap, do not mirror.** The driver captures each staff's raw token stream by wrapping homr's own
  staff parsing, and keeps the marks and the measure counts as it does today. The copy of the
  surrounding flow is deleted.
- **Benchmark criteria, unchanged from plan 0013.** Over the leadsheets, voice_piano and scans sets and
  the Anton photo: false syllables do not rise, false chords do not rise, pitch+duration does not drop,
  the tally of right measure counts does not drop, and the Anton page keeps an event error rate of 0.00.
  The numbers become the new baseline only once the step is merged.
- **Revert rule.** A step that fails is pinned back, not patched around.
- **Step 2 pinning.** `main` is installed from git at an exact commit in the backend's dependencies. The
  deploy builds on the host, so before merging, the host's access to fetch it is checked. If it cannot,
  `main` stays a dev-laptop trial.
- **Overlap rule.** Beams (plan 0006's pixel rule), octave shifts and time changes: for each, score
  homr's reading and ours on the benchmark; remove ours in its own commit only if homr's is at least as
  good.

## Testing Decisions

- One seam: reading a page and scoring it, which is `bench/songs/run_bench.py` over the sets above. It
  is the seam the project already trusts, and it needs no new code.
- A good test here is an external number on a page, not a check that a homr function was called.
- Under it, the backend tests (in particular the meter tests of plan 0013) must stay green on each
  step; the driver patch adds none of its own for homr internals.
- Prior art: plans 0011 to 0013 each close on a re-score with a before and after table.

## Out of Scope

- Training or fine-tuning homr's models.
- Replacing homr, or the Audiveris fallback (ADR 0002).
- Using a GPU for recognition: that is plan 0015, and dev-only.
- Any change to the editor, the player or the form.

## Further Notes

- Step 1 runs the benchmark at today's speed (about 20 minutes a set) because plan 0015 comes after.
- Order of work: plan 0013 merged and deployed on 0.7.0 first; then this plan.
- Commits carry no `Co-Authored-By` line.
