# partition-player

Photograph a page of printed sheet music, get it back as MusicXML, and play it on a piano in the
browser with the cursor following the notes. CPU only, built to run on a small ARM VPS.

Decisions are recorded in `docs/adr/`. The engine benchmark that picked homr is in `bench/`.

## Layout

- `backend/` Python package `partition_player`: FastAPI API, a one-thread job runner, and the
  pipeline (preprocess, OMR engine, postprocess). CLI entry point `partition-player`.
- `frontend/` React + Vite + TypeScript: upload or camera capture, progress, score view with
  OpenSheetMusicDisplay rendering and piano playback (Tone.js sampler, own look-ahead scheduler)
  with tempo control and a loop over a measure range.
- `bench/` benchmark samples, ground truth, scorer and audio rendering.
- `docs/adr/` architecture decision records.

## Run locally

Backend (Python 3.11 or 3.12, [uv](https://docs.astral.sh/uv/)):

```
cd backend
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m homr.main --init        # downloads the OMR models once (about 180 MB)
.venv/bin/partition-player serve            # http://localhost:8000
.venv/bin/python -m pytest
```

Frontend (Node 22):

```
cd frontend
npm install
npm run dev      # http://localhost:5173, proxies /api to :8000
npm run build    # writes dist/, which the backend serves at / when present
```

CLI, one image in, MusicXML out:

```
backend/.venv/bin/partition-player recognize photo.jpg -o out/
```

## Docker

```
docker compose up --build
```

The image builds for amd64 and arm64. Recognition data lives in the `pp-data` volume under
`/data/jobs/<id>/`. Production deployment on the main server: `deploy/README.md`.

## Configuration

All settings are environment variables with a `PP_` prefix: `PP_DATA_DIR`, `PP_ENGINE` (`homr`),
`PP_FALLBACK_ENGINE` (`none` or `audiveris`, which also needs `PP_AUDIVERIS_BIN`),
`PP_JOB_TIMEOUT_S`, `PP_JOB_TTL_DAYS` (failed jobs only, default 7), `PP_MAX_SCORES` (default 500, oldest
`PP_ANTHROPIC_API_KEY` (optional lyrics spelling pass, off when unset),
scores beyond it are deleted), `PP_MAX_UPLOAD_MB`, `PP_MAX_SIDE_PX`, `PP_FRONTEND_DIR`.

## Chord symbols and accompaniment

On a lead sheet the chord names printed above the staff (Cm, F#m7, G7/B) are read after recognition
(ADR 0003): homr's staff geometry gives the band above each system, RapidOCR's detector finds the
text, and the recognizer's character probabilities are decoded under a chord grammar, so only a legal
chord can come out and nothing is written when the reading is not sure. Chords are stored as MusicXML
`<harmony>`, drawn on the sheet, and played as a simple piano accompaniment with separate melody and
accompaniment switches. Tokens that were seen but not accepted are listed under the sheet.
The benchmark is `bench/chords/` (see `bench/RESULTS.md`).

## Score library
## Lyrics

The words printed under the staff are read and put under their notes (ADR 0004). The driver cuts a
band below every staff from the **uploaded photo at full resolution** (homr works on a downscaled
copy where the letters are too small), RapidOCR reads it with word boxes at two scales, and a small
lyric grammar turns the words into syllables: hyphens split words (attached or detached, and the
ones the OCR drops are found in the pixels), an extender line holds a syllable over the next notes,
a lone comma belongs to the syllable before it, "1." is a verse number. Each verse row is then
aligned to the score's notes by an ordered dynamic programme (a syllable may be dropped when it is
doubtful, a note may be skipped for a melisma), so a missed word never shifts the rest of the line.
The result is standard MusicXML `<lyric>`, drawn under the notes by OSMD. Rows that do not line up
with the notes (the chord line of the next system, a verse paragraph, a footer) are listed under the
sheet as "seen but not used", never written.

Text mistakes are fixed in the **Lyrics** panel under the sheet: one text field per verse in the
convention every notation program uses (`Lors-que nous é-tions`; `_` holds a syllable over the next
note, `*` skips a note). Saving rewrites only the lyric elements of the score, keeps the chords, and
re-renders the sheet. With `PP_ANTHROPIC_API_KEY` set, the recognized text of each line is also sent
with its band image to Claude Haiku for a spelling pass; the answer is used only when it keeps the
same syllables in the same places. The benchmark is `bench/lyrics/` (see `bench/RESULTS.md`).

## Note names

The score page has a **Note names** switch that writes the French name of every printed note
(do, ré, mi, fa, sol, la, si, with `b` or `#` for the alteration: `mib`, `lab`) on one row above each
system, clear of the chord symbols, so the space under the notes stays free for words. The names are
computed from the pitches of the rendered score and drawn into OSMD's SVG (`frontend/src/noteNames.ts`):
nothing is written into the MusicXML, the switch works while the piece plays, and transposing the
playback does not rename them, since they name what is printed. The choice is remembered in the
browser.


Every finished job is a saved score with its own link, `/s/{id}`, listed on the home page with a
thumbnail and an editable name. There is no login: anyone who can reach the app can add, rename
and delete. To keep the disk flat, a finished job keeps only the MusicXML, a small thumbnail and its
metadata (about 50 KB); the uploaded photo and the engine's intermediate files are deleted when the
job ends.

## API

- `POST /api/jobs` multipart `file` (JPEG, PNG, WebP): returns the job, status `queued`.
- `GET /api/jobs/{id}`: status is `queued`, `preprocessing`, `recognizing`, `postprocessing`,
  `done` or `failed`, with a `message`, and `result` or `error`.
- `GET /api/jobs/{id}/score.musicxml`: the result once `done`.
- `GET /api/jobs?limit=50`: the library, newest first. `PATCH /api/jobs/{id}` with `{"name": ...}`
  renames; `DELETE /api/jobs/{id}` removes; `GET /api/jobs/{id}/thumb.jpg` is the list thumbnail.

## License

homr and Audiveris are AGPL-3.0; this project is AGPL-3.0-or-later. See BACKLOG.md for the open
question on how source is offered to users of a hosted instance.
