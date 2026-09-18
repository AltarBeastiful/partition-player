# ADR 0002: Score recognition engine

Date: 2026-09-18
Status: Accepted

## Context

The app needs an optical music recognition (OMR) engine that runs on a CPU-only ARM VPS with a few
cores and a few GB of RAM, on phone photos of printed scores, and produces MusicXML. Scoping ruled
out GPU models and a custom pipeline for v1. Three CPU engines were benchmarked on a real phone photo
of a lead sheet against a hand-encoded ground truth (`bench/RESULTS.md`):

| | homr 0.7 | Audiveris 5.11 | oemer |
|---|---|---|---|
| CPU time per page | ~80 s | ~3 min | 34 min |
| Peak RAM | 1.3 GB | 1.5 GB | 6 GB |
| Notes right (pitch and duration) | 55 of 55 | 44 of 55 | 35 of 55 |
| Rests right | 15 of 15 | 7 of 15 | 4 of 15 |
| Fully correct measures | 19 of 19 | 9 of 19 | 18 measures, key signature wrong |

## Decision

Use **homr** as the recognition engine, called in-process from the Python pipeline but executed in a
subprocess per job (`homr <image>` writes `<image>.musicxml`), with **Audiveris 5.11** kept as an
optional fallback engine behind the same interface, off by default.

Around the engine, the pipeline owns:

- **Preprocessing** in Python/OpenCV: EXIF rotation, re-encode to PNG (drops the embedded JPEG
  thumbnail that Audiveris otherwise treats as a second sheet), grayscale, downscale so the staff
  interline is roughly 20 to 30 px, contrast normalisation. homr does its own staff dewarping.
- **Post-processing** with music21: validate, pad or trim each measure to the time signature so that
  playback timing survives a missed rest, strip stray title text, write plain `.musicxml`.
- **Isolation**: per-job timeout (5 min) and memory cap; a failure marks the job failed with the
  engine log attached. If homr fails and the fallback is enabled, Audiveris runs next.

Deployment: homr is pure Python on ONNX Runtime and OpenCV, both of which publish arm64 wheels, so
the Docker image is the same on amd64 and arm64. Models (about 180 MB) are downloaded at image build
time with `homr --init`. Audiveris, when enabled, needs a JRE 21 plus the unpacked application
directory from the Ubuntu deb, which ships arm64 native jars for Tesseract and Leptonica.

## Alternatives considered

- **Audiveris as the primary engine.** It was the choice before homr was benchmarked: correct
  structure and key, but it missed 8 of 15 eighth rests and 2 dots, and takes 10x the CPU. It
  remains the fallback because it is mature on clean scans and dense piano scores, which this benchmark
  did not cover.
- **oemer.** Rejected: 34 CPU-minutes and 6 GB per page, misread the key signature for half the piece,
  read eighth rests as whole rests, and needs pinned `onnxruntime` and `opencv<5` to run at all.
- **Vision LLM as the recognizer.** Rejected: per-page cost and unverified accuracy on dense notation.
  Kept as a correction pass in the backlog.
- **Custom pipeline.** Rejected: months of work before reaching any of these engines' accuracy.

## Consequences

- Recognition should take well under a minute per page on the VPS. The async job design in ADR 0001
  stays, since phones and proxies still time out on long uploads and the fallback path is slow.
- homr and Audiveris are both AGPL-3.0. The project must be released under an AGPL-compatible license
  and, as a network service, must offer its source to users. This needs a decision before publishing.
- The benchmark covers one monophonic page. Grand-staff accuracy is unmeasured for both engines, so
  the first piano sample added to `bench/samples` re-runs this comparison before the engine choice is
  considered final.
- No chord symbols or lyrics from any engine (backlog).
- The engine boundary is one function and one subprocess, so Audiveris, a second opinion, or an LLM
  fix-up pass can be added without changing the API or the frontend.
