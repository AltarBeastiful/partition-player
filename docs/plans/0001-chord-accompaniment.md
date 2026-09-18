# Plan 0001: Chord symbols to accompaniment

Implements ADR 0003. Each step has its own check; nothing moves to the next step until the check
passes. Work happens on `main` in small commits.

## Step 1: Benchmark scaffolding (no pipeline change)

- `bench/chords/make_synthetic.py` (done): 12 lead sheets to `bench/out/chords/` as ground-truth
  MusicXML with `<harmony>`, a clean PNG and a photo-like JPG.
- `bench/chords/score_chords.py <gt.musicxml> <cand.musicxml>`: extracts `(measure, beat, root,
  kind, bass)` per chord from both files; reports sequence accuracy (edit distance on `(root, kind,
  bass)`), placement accuracy (same measure and beat, when both files have the same measure count),
  false chords (candidate chords with no counterpart), and a per-page line.
- `bench/chords/run_bench.py`: runs `partition-player recognize` on every page (clean, photo, and
  the real photo) and prints the table; `--only <name>` for one page.
- Check: the scorer on ground truth versus itself gives 100 percent; on the current pipeline output
  it gives 0 chords found, 0 false.

## Step 2: homr driver with geometry export

- `backend/partition_player/pipeline/engines/homr_driver.py`: `main(image, out_dir)` mirroring
  `homr.main.process_image` for the CPU path, plus `geometry.json` and `strip_<n>.png` per staff.
  Geometry per staff: `system` (index of the system it belongs to, top to bottom), `staff_in_system`,
  `x0`, `x1`, `top_y`, `unit`, `barlines` (x list), `strip` (file name), `strip_x0`, `strip_scale`.
- `HomrEngine.recognize` runs the driver instead of `homr.main`; `homr>=0.7,<0.8` in pyproject.
- Check: on the benchmark photo, `geometry.json` lists 4 staves in 4 systems with interline about 17
  px and 4, 4, 6, 6 barlines; strips show the chord names whole (visual check of one strip); the
  MusicXML is byte-identical in note content to the previous engine output (run `bench/score.py`).

## Step 3: Chord OCR

- `backend/partition_player/pipeline/chords/ocr.py`: `read_strip(strip_png, unit) ->
  list[Token(text, score, x_center, width)]` with tiling, two offsets, merge. `parse_chord(text) ->
  Chord(root, alter, kind, degrees, bass) | None` with the grammar and confusion map.
- Unit tests: grammar table (`Cm`, `F#m7`, `Bb`, `G7/B`, `Cdim`, `Dsus4`, `6`→`G`, `A` rejected
  when in the clef zone by the caller, `Marie` rejected), and `read_strip` on four strip PNGs saved
  from the benchmark photo under `backend/tests/data/` (about 100 KB) expecting the 10 names.
- Check: tests pass; `read_strip` takes under 3 s per strip on this machine.

## Step 4: Placement and MusicXML output

- `backend/partition_player/pipeline/chords/place.py`: `place(tokens, staff_geometry, measures_in_system,
  beats_per_measure) -> list[Placed(measure_index, beat, chord)]` with the barline rule and the
  equal-width fallback; warnings for mismatches and rejected tokens.
- `backend/partition_player/pipeline/chords/inject.py`: adds `<harmony>` elements to the ElementTree
  measures; kind mapping table; `<offset>` not used, position by element order.
- Wire into `run.py` after the engine and before `postprocess`: geometry present → OCR each strip →
  place per system → inject → stats gain `chords` and `chord_warnings`.
- Unit tests: placement with matching barlines, with one missing barline (fallback), beat snapping;
  injection produces valid MusicXML that OSMD-compatible tools parse (music21 in the bench venv reads
  the harmony back).
- Check: `run_bench.py` on the real photo gives 10 of 10 chords, right measures, 0 false.

## Step 5: Benchmark on the synthetic set and tune

- Run all 12 clean and 12 photo pages. Investigate every miss: detection (tile size, scale), grammar
  (slash chords `D/F#`, `B-` flats rendered as `B♭`), placement (barline mismatches).
- Record the table in `bench/RESULTS.md` (new section) with the exact command.
- Check: acceptance numbers from ADR 0003. If the degraded set stays under 95 percent after tuning,
  stop and report which failure class dominates before changing the approach.

## Step 6: Frontend accompaniment

- `frontend/src/chords.ts`: read chord symbols from the OSMD score (`SourceStaffEntry.ChordContainers`
  while walking the cursor, same walk as `Player.collect`) into `[{time, root, kind, bass}]`; voicing
  and pattern generation into note events with a `track: "accompaniment"` tag.
- `Player`: two event lists, per-track gain (melody, accompaniment), `setTrack(name, on)`; the
  scheduler treats them alike; transposition applies to both.
- `ScoreView`: "Accompaniment" and "Melody" checkboxes, shown only when the score has chords; chord
  count in the stats line; unaccepted tokens listed under the sheet as "seen but not used".
- Check in Chrome: with a spy on the sampler, the benchmark photo's score plays bass and chord notes at
  the expected times for Cm in measure 1, Fm in measure 5, G in measure 9; melody off leaves only
  accompaniment events; a chord-less score (Gymnopédie) shows no accompaniment controls.

## Step 7: Ship

- Docker image builds with the driver (no new system packages); deploy with `deploy/deploy.sh`;
  re-run the memory check during a recognition.
- README: chord symbols paragraph; BACKLOG: move "chord symbols" to done, add the follow-ups
  (rhythm styles, LLM second opinion on low-confidence tokens, lyrics).

## Risks and how they are handled

- homr internals change: pinned `<0.8`; the driver has one test that fails loudly if a function moves.
- OCR too slow on the 2-core server: measure in step 5; tiles can drop to one pass if needed.
- Photo fonts differ from the benchmark: the synthetic set uses verovio's font; the real photo uses
  another; if a third font fails later, the warnings list shows what was seen.
- Measure count from homr wrong: the chord lands in the wrong measure but the sequence stays right;
  the warning makes it visible.
