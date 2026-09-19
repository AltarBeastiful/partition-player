# Plan 0003: Doubts on the sheet and the score editor

Status 2026-09-19: steps 1 to 4 done and checked (backend 68 tests, frontend 12 unit tests, browser
checks on the benchmark photo, the Gymnopédie page and a score recognized before the editor, at
desktop and 400 px widths); step 5 done except the server deployment, which is the user's call.

Implements ADR 0005. Each step has its own check; nothing moves to the next step until the check
passes. Work happens on `main` in small commits.

## Step 1: Pipeline: doubts, review image, layout, original

- `postprocess`: `ScoreStats.doubts`, one record per measure with something to say: `{"measure": i,
  "kind": "padded" | "overfull" | "rest_chord" | "pickup", "detail": {...}, "text": "..."}`.
- `preprocess.review_image(src, dst, budget=300_000, max_side=2400)`: WebP, quality stepped down
  until the file fits, then the side reduced.
- `homr_driver`: nothing new; `pipeline/layout.py` turns `geometry.json` into `layout.json` in
  review-image pixels: per system its box, its staves' line ranges, its measures' x ranges (from the
  barlines when they give the transformer's count, else even split), and the global measure index.
- `run.py`: writes `review.webp`, `layout.json`, `original.musicxml` (the score as recognized, with
  chords and lyrics) and `review.json` (`doubts`, `checked: []`, `revision: 1`); `jobs.KEEP_DONE`
  keeps them.
- `bench/songs/doubts.py`: the precision and recall table of the ADR, from the existing run outputs.
- Check: pytest; on the photo the review image is under 300 KB and the layout's measure boxes drawn
  on it frame the measures (one visual check); the doubts table in `bench/RESULTS.md`.

## Step 2: API

- `GET /api/jobs/{id}/review`: doubts, checked, revision, `layout` (or null), `has_image`.
- `PUT /api/jobs/{id}/score` with `{musicxml, checked, revision}`: validate, check, write, re-read
  lyric placements into `lyrics.json`, update `result.stats`, return the review state and the new
  stats; 409 on a stale revision, 422 on an invalid document.
- `POST /api/jobs/{id}/revert`: `original.musicxml` back, checked cleared, revision bumped.
- `GET /api/jobs/{id}/review.webp` (cache for a day), `GET /api/jobs/{id}/original.musicxml`.
- Check: API tests for each, including a save that deletes a note carrying a syllable and the lyrics
  state after it.

## Step 3: Frontend model

- `frontend/src/score/xml.ts`: parse and serialize, `walk(part)` giving every event its key
  (measure, staff, voice, onset, pitch), divisions handling, renumbering.
- `frontend/src/score/edit.ts`: the operations of the ADR, pure functions on the DOM.
- `frontend/src/score/check.ts`: the measure check (same rules as Python).
- `frontend/src/score/chordText.ts`: chord text to and from `<harmony>`.
- vitest + jsdom; tests on the benchmark ground truth and a two-staff measure.
- Check: `npm test` green; `npm run build` clean.

## Step 4: Frontend editor

- Selection on the sheet (click and touch), highlight, key mapping to the DOM and back after a
  re-render, keyboard shortcuts.
- Doubt layer on the sheet and the review bar; the photo strip for the selected measure and the
  whole photo in a lightbox; edit toolbar (desktop: under the review bar; phone: bottom bar);
  chord field; undo/redo; autosave with state and the stale-revision case; revert; unsaved-changes
  guard; lyrics panel reloading on save.
- Check: in the browser on the benchmark photo and the Gymnopédie page, the flows of the ADR's
  validation section, at desktop and phone widths.

## Step 5: Record

- README (editor section, storage per score), BACKLOG (editor done, click-to-play noted), deploy
  README (disk), `bench/RESULTS.md`, memory. Commit.
