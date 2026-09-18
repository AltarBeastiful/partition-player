# Backlog

Items deferred from v1 scope (decided 2026-09-18). Not ordered by priority yet.

## Correction workflow via small LLM API
- Goal: after OMR, send the recognized MusicXML (and possibly the image crop) to a cheap multimodal or text LLM to fix obvious errors: wrong durations that break measure totals, missing accidentals, clef/key inconsistencies.
- Benchmark first before committing: compare candidates on a fixed set of OMR outputs with known ground truth, measure note-level accuracy gain, latency and cost per page.
- Candidates: DeepSeek (V3 / R1 via API), Gemini Flash, Claude Haiku. Pick by accuracy per euro.
- Depends on: ground-truth test set from the OMR benchmark milestone.

## Chord symbols and lyrics
- Chord symbols: done (ADR 0003, bench/chords). Follow-ups: accompaniment rhythm styles (arpeggio, waltz bass, swing), a
  count-in, an LLM or vision second opinion on tokens under the confidence floor, chord symbols under the staff (some
  editions), and lyrics under the notes (same band idea, below the staff, no grammar).
- Audiveris OCR mixes verse text into lyrics on lead sheets (see bench/RESULTS.md); not used.

## Second-opinion engine
- Audiveris is kept as fallback behind the engine interface (ADR 0002). Once a correction workflow exists, disagreements between homr and Audiveris could flag measures to review.

## Licensing decision
- homr and Audiveris are AGPL-3.0. Decide the project license and how source is offered to users of the hosted service before making the app public.

## Piano grand-staff benchmark sample
- Add a two-hand piano page (phone photo, clean PDF render, screenshot) to bench/samples with a ground truth, and re-run bench/score.py on homr and Audiveris.

## Recognition fixes
- Ties across bar lines: homr places the tied note a beat late and overfills the measure (Gymnopédie m26, m31). Detect overfull measures with a tie and shift the tied note.

## Rendering polish
- homr writes no <beam> elements, so OSMD shows separate flags instead of beams. Add beaming in post-processing (group eighths and sixteenths within a beat) or via music21's beam maker.
- homr's title OCR ends up as the score title ("Marie Lafor t"). Strip or clean it in post-processing.
- Frontend bundle is 1.6 MB minified (OSMD + Tone.js). Lazy-load the score view.

## Other deferred features
- In-app note editor (pitch / duration fixes on the rendered score)
- Multi-page pieces: several photos merged into one MusicXML
- Multi-page PDF input, split server-side
- Falling-notes / piano-roll view
- Web MIDI output to a connected digital piano, MIDI file download
- Practice tools: mute one hand (loop and tempo done)
- Repeats and endings: post-processing strips repeat signs and volta brackets so the page plays straight through; honour them in playback later
- Handwritten score support
- User accounts and saved score library
