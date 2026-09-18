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
scores beyond it are deleted), `PP_MAX_UPLOAD_MB`, `PP_MAX_SIDE_PX`, `PP_FRONTEND_DIR`.

## Score library

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
