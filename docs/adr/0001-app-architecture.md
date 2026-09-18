# ADR 0001: Application architecture

Date: 2026-09-18
Status: Accepted

## Context

partition-player turns a photo, scan or screenshot of a printed score into MusicXML and plays it back
as a piano in the browser with a cursor synced to the rendered score. Constraints agreed during scoping:

- Target host is a small ARM VPS with no GPU. Recognition must run on CPU.
- Primary users are one person or a small group, on a phone, uploading one page at a time.
- Recognition takes tens of seconds to minutes per page on CPU depending on the engine (ADR 0002), so the UI cannot block on it.
- No accounts, no editor and no multi-page support in v1. These live in BACKLOG.md.
- MusicXML is the interchange format so results open in MuseScore and can be re-rendered cleanly.

## Decision

A single Docker image on the VPS with three parts:

1. **API and job runner, Python (FastAPI).** `POST /jobs` accepts an image, stores it on disk under a
   job id, and enqueues recognition. `GET /jobs/{id}` returns status and progress. `GET /jobs/{id}/score.musicxml`
   returns the result. The queue is in-process (a worker thread pool of size 1, since one recognition
   already saturates the small VPS). Job state is persisted as JSON next to the files so a restart
   loses nothing but the in-flight job, which is re-queued on startup.
2. **Recognition pipeline, Python, behind one interface.** `recognize(image_path) -> musicxml_path`
   wraps: preprocessing (EXIF rotation, downscale to a working resolution, grayscale, deskew, contrast
   normalisation), the OMR engine (ADR 0002), and post-processing (measure duration sanity fixes,
   MusicXML validation with music21). The engine is a subprocess so a crash or timeout kills only the job.
3. **Web frontend, React + Vite + TypeScript, served as static files by FastAPI.** Screens: capture or
   upload, job progress, score view. OpenSheetMusicDisplay renders the MusicXML and provides the
   cursor. Playback derives note events from OSMD's cursor iteration and plays them with a sampled piano
   through Tone.js. Tempo control and play/pause only.

A CLI entry point (`partition-player recognize <image> -o <dir>`) calls the same pipeline, for batch
runs and for the benchmark suite.

Storage is the filesystem: `data/jobs/<id>/{input.jpg, preprocessed.png, score.musicxml, status.json}`.
Old jobs are pruned by age.

## Alternatives considered

- **Everything in the browser (ONNX in WebAssembly).** Rejected: the OMR models are 100 MB+ and take
  minutes on a laptop CPU, far worse on a phone.
- **Synchronous recognition request.** Rejected: multi-minute requests die on mobile networks and
  reverse proxies.
- **External queue (Redis, Celery).** Rejected for v1: one worker on one box does not justify the
  operational cost. The job interface is designed so a queue can be swapped in later.
- **Java backend around Audiveris.** Rejected even with Audiveris as the fallback engine:
  the preprocessing, post-processing, rendering checks and benchmark tooling are all Python (OpenCV,
  music21, verovio). Audiveris is invoked as a subprocess.

## Consequences

- One image, one process, one worker: simple to deploy and reason about. Throughput is one page at a
  time, which fits the user base.
- The engine boundary (`recognize()` + subprocess) lets us swap or chain OMR engines and later add the
  LLM correction pass from BACKLOG.md without touching the API or frontend.
- Rendering and playback are fully client side, so the VPS does no audio or layout work.
- We depend on OSMD and Tone.js from npm and on the OMR engine's runtime (see ADR 0002 for its size
  and platform constraints).
