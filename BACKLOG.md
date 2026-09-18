# Backlog

Items deferred from v1 scope (decided 2026-09-18). Not ordered by priority yet.

## Correction workflow via small LLM API
- Goal: after OMR, send the recognized MusicXML (and possibly the image crop) to a cheap multimodal or text LLM to fix obvious errors: wrong durations that break measure totals, missing accidentals, clef/key inconsistencies.
- Benchmark first before committing: compare candidates on a fixed set of OMR outputs with known ground truth, measure note-level accuracy gain, latency and cost per page.
- Candidates: DeepSeek (V3 / R1 via API), Gemini Flash, Claude Haiku. Pick by accuracy per euro.
- Depends on: ground-truth test set from the OMR benchmark milestone.

## Chord symbols and lyrics
- Audiveris OCR mixes verse text into lyrics on lead sheets (see bench/RESULTS.md). Options: mask non-staff text regions before OCR, or run Tesseract ourselves on the chord-symbol band above each staff.

## Second-opinion engine
- Audiveris is kept as fallback behind the engine interface (ADR 0002). Once a correction workflow exists, disagreements between homr and Audiveris could flag measures to review.

## Licensing decision
- homr and Audiveris are AGPL-3.0. Decide the project license and how source is offered to users of the hosted service before making the app public.

## Piano grand-staff benchmark sample
- Add a two-hand piano page (phone photo, clean PDF render, screenshot) to bench/samples with a ground truth, and re-run bench/score.py on homr and Audiveris.

## Other deferred features
- In-app note editor (pitch / duration fixes on the rendered score)
- Multi-page pieces: several photos merged into one MusicXML
- Multi-page PDF input, split server-side
- Falling-notes / piano-roll view
- Web MIDI output to a connected digital piano, MIDI file download
- Practice tools: section loop, tempo scaling, mute one hand
- Handwritten score support
- User accounts and saved score library
