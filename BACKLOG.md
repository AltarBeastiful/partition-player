# Backlog

Items deferred from v1 scope (decided 2026-09-18). Not ordered by priority yet.

## Correction workflow via small LLM API
- Goal: after OMR, send the recognized MusicXML (and possibly the image crop) to a cheap multimodal or text LLM to fix obvious errors: wrong durations that break measure totals, missing accidentals, clef/key inconsistencies.
- The editor (ADR 0005) now records the doubtful measures and keeps the photo strip of each; a model would get exactly those.
- Benchmark first before committing: compare candidates on a fixed set of OMR outputs with known ground truth, measure note-level accuracy gain, latency and cost per page.
- Candidates: DeepSeek (V3 / R1 via API), Gemini Flash, Claude Haiku. Pick by accuracy per euro.
- Depends on: ground-truth test set from the OMR benchmark milestone.

## Chord symbols and lyrics
- Chord symbols: done (ADR 0003, bench/chords). Follow-ups: accompaniment rhythm styles (arpeggio, waltz bass, swing), a
  count-in, an LLM or vision second opinion on tokens under the confidence floor, chord symbols under the staff (some
  editions), and lyrics under the notes: done (ADR 0004, plan 0002, bench/lyrics). Follow-ups: verse text that differs per
  repeat ending (repeats are stripped), lyrics on the lower staff of a two-voice hymn, elisions drawn as a slur.
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

## Click on the sheet to play from there
- Done: outside edit mode a click on a note leads the playback to that beat (re-anchored while playing, the resume
  point while paused, the start of the next Play while stopped); in edit mode a click selects the note. "⏮ Start" and
  Home go back to the beginning of the range. The hit test lives in `frontend/src/editor/sheet.ts`, the seek in
  `Player.seek`.

## A redesign of the score page
- The controls have grown into five rows (transport, loop range, note names, melody/accompaniment, stats and warnings)
  with the lyrics panel under them. Redesign the page around one compact transport bar and a separate practice panel for
  what is set rarely (loop, note names, tracks), so the sheet is higher on the screen.
- Make it work on a phone: the photo is taken there, so the score is read there too. The control rows wrap badly at that
  width and the sheet needs the vertical space.

## Other deferred features
- Editor follow-ups (the editor itself is done, ADR 0005): tuplet entry, a second voice, beaming, moving a note
  between staves, a doubt from a second engine's disagreement, a language-model second opinion on the flagged measures
  (the flags and the photo strips are what it would plug into).
- Multi-page pieces: several photos merged into one MusicXML
- Multi-page PDF input, split server-side
- Falling-notes / piano-roll view
- Web MIDI output to a connected digital piano, MIDI file download
- Practice tools: mute one hand (loop and tempo done)
- Form of a song, next steps (plan 0004 done to step 3): voltas are never read by the engine (8 of 30 songs) and must be entered by hand; verse rows are under-read on 6 of 25 songs (the lyrics stage); a volta editor (endings on a measure) and D.C./Fine/Coda words are not in the editor; multi-page songs
- Handwritten score support
- User accounts and saved score library
