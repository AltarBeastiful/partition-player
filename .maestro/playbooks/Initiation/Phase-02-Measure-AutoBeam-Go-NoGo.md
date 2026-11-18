# Phase 02: Measure OSMD 2's autoBeam and write a go/no-go report

Plan 0006 (beams) has been on hold since 2026-09-22 because the user wants to try OSMD's `autoBeam` before building a pixel-based beam pipeline. ADR 0007 decision 6 turns `autoBeam` off, and the pixel rule's probe found 89 of 95 beam groups with no false group. This phase measures how well OSMD 2.1.3's `autoBeam` beams what homr actually produces, against the beams the printed pages carry. It ends with a structured go/no-go report for the user. It is measurement only. No production code changes, `autoBeam` stays off in the shipped app, plan 0006 and ADR 0007 are not rewritten, and nothing is merged or deployed. All measurement code lives under `bench/beams/` (benchmark tooling, committed) or `.maestro/playbooks/Initiation/Working/` (scratch). Commits carry no `Co-Authored-By` line. Work on a new branch, `bench-autobeam`, cut from `main` after Phase 01's merge.

## Tasks

- [ ] Set up and gather context:
  - `git checkout main && git pull --ff-only`, then `git checkout -b bench-autobeam`.
  - Read `docs/adr/0007-beams.md` (context, decision 6, the "OSMD's autoBeam alone" alternative) and `docs/plans/0006-beams.md` ("The problem", point 2: a rule cannot follow a print that beams across the beat, and leaves nothing to fix). Note the probe pages: `bench/samples/anton_yvan_boris_photo.jpg` plus three lead-sheet benchmark pages, photo and clean (17/18, 23/26, 22/23, 27/28). Identify those three pages from the ADR, the plan or git history, and if they cannot be identified, pick three leadsheets pages and say so.
  - In `frontend/node_modules/opensheetmusicdisplay/build/dist/src/`, find how 2.1.3 exposes `autoBeam` and `autoBeamOptions` (`beam_rests`, `beam_middle_rests_only`, `maintain_stem_directions`, `groups`). Find where it builds beams: look for `autoBeam` in `VexFlowMusicSheetCalculator` / `VexFlowMeasure`. Write the findings to `Working/autobeam-notes.md`, including whether the resulting groups can be read back from the graphical model after `render()`.

- [ ] Build a headless harness that renders a MusicXML file with OSMD 2 and dumps its beam groups <!-- MAESTRO:MODEL tier="high" effort="high" reason="OSMD runs in a browser and autoBeam groups live inside VexFlow objects after layout, so getting them out headlessly means digging through undocumented internals. A harness that misreports groups would invalidate every number in the go/no-go report." -->
  - Create `bench/beams/osmd_beams.ts` (or `.mjs`), run with the frontend's own toolchain (vitest's jsdom environment or Node with jsdom; reuse the setup in `frontend/vitest.bench.config.ts` and `frontend/src/form.bench.ts` if it fits). It loads a MusicXML file, renders it with `autoBeam: true` (and optionally a given `autoBeamOptions`), and writes JSON: for each measure, the beam groups as lists of note indices (onset, pitch, duration) in voice order. It also takes `--explicit` to dump the groups OSMD draws from the file's own `<beam>` elements with `autoBeam` off.
  - Check the harness on the ground truth itself: with `--explicit` on a leadsheets ground-truth `.musicxml` (which carry `<beam>` elements), the dumped groups must equal a direct parse of the file's `<beam>` begin/continue/end markers. Write that parse in Python, `bench/beams/truth.py`, reusing `bench/score.py`'s music21 loading where it helps. Do not continue until the two agree on at least three pages.

- [ ] Write the beam scorer `bench/beams/score.py`:
  - Input: the ground-truth MusicXML (its `<beam>` groups) and the harness JSON for a candidate (homr's output with `autoBeam` on).
  - Align the notes with `bench/score.py`'s `tokens`/`align`, so a missing or extra note does not shift every later group. Count per page: groups exactly right, groups missed, groups split, groups merged, and false groups (a beam where the print has a flag or no group). Report a single-eighth-with-flag that `autoBeam` beams as false.
  - Follow the existing scorers' style (`bench/chords/score_chords.py`, `bench/lyrics/score_lyrics.py`): plain functions, a `score()` that returns a dict, a `__main__` that prints a table.
  - Add unit tests in `bench/beams/test_score.py` with three or four hand-made tiny MusicXML cases (exact match, split, merge, false beam on a lone eighth), then run them with pytest.

- [ ] Run the measurement:
  - Inputs: homr's outputs from Phase 01's benchmark run (`bench/out/songs/leadsheets/run/*/` and `bench/out/songs/voice_piano/run/*/`, both clean and photo copies), plus the Anton photo's output. If a run directory lacks its output MusicXML, regenerate that page with the CLI.
  - For each page, run the harness with `autoBeam: true` and default options, then score it. Run again with the options that most plausibly fit song pages (`beam_rests: false`, `maintain_stem_directions: true`, and `groups` set by time signature: 2/4 and 4/4 by the quarter, 6/8 by the dotted quarter). Keep both result sets.
  - Also score the four probe pages separately, so the number sits beside the pixel rule's 89 of 95 on the same ground.
  - Save the raw results to `bench/out/beams/results.json` and a per-page table to `Working/autobeam-results.md`.

- [ ] Analyse where autoBeam fails <!-- MAESTRO:MODEL tier="high" effort="high" reason="The go/no-go turns on whether the misses are a fixable option setting or a structural limit of beaming by rule. That judgment needs careful reading of individual measures against the print." -->
  - Sort the errors into families: across-the-beat beams the print draws, beams broken by syllables or a rest, triplets and dotted figures, 6/8 grouping, two-voice staves, groups wrong only because homr misread a duration upstream (not autoBeam's fault), and anything else. Count each family.
  - For the three or four largest families, pick one concrete measure each: the page, the measure number, what the print shows and what `autoBeam` drew. Crop the print region from the page image into `bench/out/beams/examples/` with a small Python/PIL script.
  - Note whether each family can be cured by `autoBeamOptions`, by a few lines of MusicXML pre-processing, by the editor (plan 0006's "Join next"), or only by reading the print (the pixel rule).

- [ ] Write the go/no-go report as a structured document, `docs/research/autobeam-osmd2.md`:
  - Front matter: `type: report`, `title: OSMD 2 autoBeam against the printed beams`, `created: <today>`, `tags: [beams, osmd, benchmark, plan-0006]`, `related: ['[[0007-beams]]', '[[0006-beams]]', '[[RESULTS]]']`.
  - Sections: the question; the method (harness, scorer, pages, options); the results table (autoBeam default, autoBeam tuned, pixel rule probe) with groups right, missed, false; the failure families with counts and the example crops; what a **go** would change (ADR 0007 decision 6 reversed, which plan 0006 steps would drop — detection and placement in the driver — which would stay — the editor's links, `normalizeBeams`, the readings dialog — and whether the pixel rule survives as a fallback); what a **no-go** keeps; and a recommendation in one paragraph, with the numbers that drive it.
  - Keep the repo's prose voice: measured facts, plain sentences. Do not edit `docs/adr/0007-beams.md` or `docs/plans/0006-beams.md`.

- [ ] Commit the measurement tooling and the report on `bench-autobeam`: `bench/beams/` (harness, truth, scorer, tests), `docs/research/autobeam-osmd2.md`, and the example crops if they are small (under 500 KB in all; otherwise leave them in `bench/out/`, which is ignored). Use a plain descriptive message with no Co-Authored-By line. Push the branch to `origin`. Do **not** merge into `main` and do **not** deploy. Nothing user-facing changed.

<!-- MAESTRO:HITL reason="Go/no-go decision on OSMD autoBeam: read docs/research/autobeam-osmd2.md and decide whether plan 0006 and ADR 0007 are rewritten around autoBeam or kept as the pixel pipeline" artifact="docs/research/autobeam-osmd2.md" -->

## Manual Follow-Up (not executed by Auto Run)

- Read `docs/research/autobeam-osmd2.md` and give the go or no-go on `autoBeam`.
- On a go: ask for a follow-up playbook that rewrites plan 0006 and ADR 0007 around `autoBeam`, builds it, then merges and deploys.
- On a no-go: plan 0006 stays as written (pixel rule) until you schedule it.
