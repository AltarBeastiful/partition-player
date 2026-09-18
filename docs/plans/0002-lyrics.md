# Plan 0002: Lyrics under the notes

Status 2026-09-18: in progress.

Implements ADR 0004. Each step has its own check; nothing moves to the next step until the check
passes. Work happens on `main` in small commits.

## Step 1: Driver: full-resolution lyric bands and the coordinate chain

- `HomrEngine.recognize(image, out_dir, original=None, scale=1.0)`: the pipeline passes the upload
  and the preprocess scale; the driver gets them as `--original` and `--scale`.
- `homr_driver`: computes homr's autocrop offset (same logic as `homr.autocrop`) and resize factor,
  so `to_upload(x, y)` maps working coordinates to upload pixels. For every parsed staff it writes
  `lyrics_<n>.png`: the band from 1.5 to 12 interlines below the bottom staff line (stopping one
  interline above the next staff), cut from the upload and straightened per column, with the
  factor `k` (upload pixels per working pixel). The geometry gets a `staves` list: system, voice,
  unit, x extent, bottom line, noteheads as (x, y), and the lyric tokens read from the band.
- `pipeline/lyrics/ocr.py`: `read_lyrics(ocr, band, unit_px) -> list[Word]`: RapidOCR with word
  boxes at two scales, detector long side capped at 1600 px, merged by overlap; pixel test for an
  extender line after each word.
- Check: on the photo, four bands, the word list per band matches the printed line (55 syllables,
  hyphens as separate or attached tokens), the chord benchmark stays at false = 0 (`--only anton`).

## Step 2: `pipeline/lyrics`: grammar, alignment, injection

- `grammar.py`: tokens to rows (baseline clustering, row gap rule, coverage rule, verse numbers),
  rows to syllables (hyphen split, lone hyphens, punctuation, extenders, elisions), syllabic types,
  cross-system continuation.
- `align.py`: onsets per system from the score (chord stage's measure boundaries and notehead
  matching), robust drift fit, monotone dynamic programme with match / skip / drop moves, row
  acceptance by mean cost, warnings and "seen" list.
- `inject.py`: `<lyric>` elements after `<notations>`, `lyrics.json` writer and reader, in-place
  rewrite that strips only `<lyric>`.
- `run.py`: `add_lyrics(score, geometry)` after post-processing; new `ScoreStats` fields.
- Check: unit tests on synthetic token lists and on the photo's bands; on the photo, 55 of 55
  syllables on their notes with the ground truth rewritten with syllabic types.

## Step 3: Benchmark `bench/lyrics`

- `make_pages.py`: French songs typed as melody plus verse strings in the editor convention, music21
  lead sheets with lyrics (Berlin, Foster), Luca's Gloria (Latin, choral), synthetic verses on
  Nottingham tunes; multiple verses, melismas, elisions; clean render, photo degradation; negatives
  (verse paragraphs near the last staff, Gymnopédie).
- `score_lyrics.py`: per note and verse: placed right, text exact, syllabic right, character error
  rate, false syllables; `run_bench.py` like the chord one.
- Check: acceptance numbers of the ADR; results recorded in `bench/RESULTS.md`.

## Step 4: Correction workflow

- `GET /api/jobs/{id}/lyrics` (verse strings and counts), `PATCH /api/jobs/{id}/lyrics` (verse
  strings; 409 while not done), re-injection rules of the ADR, `lyrics.json` in `KEEP_DONE`.
- Frontend: lyrics panel with one text field per verse, counts, save; score reload with a
  cache-busting version.
- Check: API tests (round trip, count mismatch dealing, 409), manual check in the browser.

## Step 5: Optional language-model polish

- `lyrics/polish.py` behind `PP_ANTHROPIC_API_KEY`: sends the band and the verse string, accepts the
  answer only if the syllable structure is unchanged; test with a fake transport.

## Step 6: Deploy and record

- Deploy, measure the page time on the server, update README, BACKLOG, `bench/RESULTS.md`, memory.
