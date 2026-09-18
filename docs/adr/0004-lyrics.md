# ADR 0004: Lyrics recognition and correction

Date: 2026-09-18
Status: Proposed (research done, implementation not started)

Appendices: [A. research notes on OMR lyrics, OCR engines and alignment](0004-lyrics-research.md),
[B. survey of datasets, tools and papers](0004-lyrics-survey.md).

## Context

The user sings over the playback. After ADR 0003 the player gives melody and chords; the words are
still only on the paper. The goal is lyrics under the notes in the rendered score, reliable enough that
the singer can follow, with the understanding that **text mistakes are cheap to fix by hand in an
editor, wrong placement is not**: a syllable under the wrong note, a missing syllable that shifts the
rest of the line, or a verse read as prose are what make the result unusable. So the target is
"almost perfect structure, good text, easy correction", not perfect OCR.

What exists today:

- homr 0.7 has no lyrics support in its sources, README or issue tracker; the one lyrics PR (#65) was
  abandoned (Appendix B).
- Audiveris is the only open-source OMR with a lyrics pipeline (Tesseract OCR, each syllable mapped to
  the nearest note chord within 3 interlines, no left-to-right constraint). MuseScore's online
  import is Audiveris. On the benchmark photo (`bench/samples/anton_yvan_boris_photo.jpg`) MuseScore
  put a syllable on each of the 55 notes but got 18 of the 55 words wrong, including nonsense
  such as "tor-m'être" for "tourterelles" (rated in `bench/out/musescore/`). The research line on
  aligned notation-and-lyrics transcription (AMNLT, 2023–2026) is end-to-end but trained only on
  Gregorian chant; no model or dataset exists for modern lead sheets (Appendix A §1, §5).
- RapidOCR is already in the pipeline for chord symbols (ADR 0003), together with per-system staff
  geometry (interline, notehead and barline x positions) exported by our homr driver.

### Findings from the survey (Appendix B)

- No public OMR model outputs lyrics for modern notation: SMT, Zeus/OLiMPiC, Legato and LEGATO 2
  strip or replace the text, and homr's lyrics PR (#65, 2026) was closed unmerged with its model
  unpublished. The lyric stage has to be ours.
- Audiveris is the reference design to copy as an algorithm, not as code: text role guessed from
  position (below the staff, within 7 interlines, not italic, not a chord), items classified as
  syllable / hyphen / extension / elision / number, nearest-chord mapping within 3 interlines with
  conflict resolution, syllabic type from the neighbouring hyphens. Its open issues (#334, #633, #55)
  are exactly the failure modes to benchmark: wrong staff when systems are close, trailing prose taken
  as a verse, chord symbols read as words.
- Ground truth exists in symbolic form only: OpenScore Lieder (1,300 songs, CC0, lyrics in MusicXML),
  PDMX (250K MusicXML, lyrics uncommon but filterable), CPDL and Mutopia for hymns. The only scanned
  set with lyrics aligned to notes is Sheet Music Benchmark (685 public-domain pages in `**kern`,
  licence stated inconsistently as CC BY and CC BY-NC), usable for evaluation only. Every dataset on
  the OMR-Datasets list lacks lyric annotation. Verovio's SVG keeps a `syl` group under each note, so
  rendered pages give exact syllable-to-note ground truth for free.
- The AMNLT work contributes two reusable pieces: its interleaved music-and-text sequence encoding and
  its syllable-level alignment error metrics (AMLER, AlER) for the scorer.
- RapidOCR's word boxes have had regressions (issue #400): pin the version and cover word boxes in
  the tests.

### Findings from the probe (2026-09-18, benchmark photo, 4096 × 3072 px)

1. **The OCR we have reads French lyrics well.** RapidOCR's default recognizer in the installed
   version is PP-OCRv6 small, whose dictionary holds 18 708 characters including é è ê à ç œ (the
   older `en` model is ASCII-only; the PP-OCRv5 `latin` model is the documented alternative, 7.5 MB,
   and gave equivalent text). On the whole photo it returned 49 text lines in 1.8 s: title, composer,
   the chord names, the four lyric lines and the five verse paragraphs, accents right. Of the 55 lyric
   syllables 48 came back exactly; the six lost ones are one fragment ("cueil-lait la mi-ra-belle")
   that the whole-page detector missed because it works at half resolution, and "Jo" read as "To".
2. **Resolution decides everything.** The same OCR on homr's working image (1875 px wide, interline
   17 px, lyric x-height about 8 px) lost most words ("Lous", "n", "ots"). Lyrics must be read from
   the original photo, and the driver must record the scale between the photo and homr's coordinates
   (0.61 here) so boxes can be mapped onto the noteheads.
3. **Bands must be cut per system and kept squat.** A band 5 to 12 interlines below each staff's top
   line, cut from the full-resolution photo, read the lost fragment correctly ("cueil-lait", "mi - ra
   - belle.", 0.92–1.0), but a raw band 2900 × 195 px triggered RapidOCR's single-line mode (it treats
   anything wider than 8 × its height as one text line) and produced garbage; padded to a 6:1 ratio it
   read normally in 0.7 s per band. The same trap as the chord stage.
4. **Text accuracy depends on scale, so read twice.** The band pass at full resolution and the
   whole-page pass at half resolution each got 48 of 55 syllables exact but with different errors
   (one lost a fragment, the other produced one-letter spurious tokens and "Y" → "X", "ris" → "Is");
   their union is 54 of 55. Two-scale reading with confidence voting, as the chord stage does with its
   blur variant, is the cheap way to the high 90s; the last few percent are the user's editor.
5. **Word boxes and hyphens are usable.** `return_word_box=True` gives one box per word. A detached
   hyphen ("Lors - que") comes back as its own token with a box; an attached one stays in the word
   ("bru-", "Re-bec", "cueil-lait"). Nothing else in the band produced tokens: the verse paragraphs
   below the last system sit outside the 12-interline limit.
6. **Nearest-notehead placement is wrong; ordered placement is right.** A syllable's centre sits within
   one interline of its notehead at the start of a system but drifts to 2.5 interlines by the end
   (the engraver centres the first letters, not the whole word). Nearest-neighbour assignment
   mis-placed 12 of 55 syllables. A monotone dynamic-programming assignment (each syllable to a
   distinct later onset, skipping a notehead costs 1.5 interlines) put every syllable on its note in
   every system whose token count was right, including the system with 17 syllables over 19 noteheads,
   where the two skipped noteheads were exactly the two tie continuations. When OCR emitted spurious
   tokens (17 for 15 notes) the strict version had no solution, so the alignment needs a
   "drop token" move priced by OCR confidence.
7. **Erasing music ink does not help.** Painting out homr's segmentation masks (staff, symbols,
   noteheads, stems, clefs, upsampled to the photo) before OCR was tried for the ledger-line note with a
   natural sign that hangs into the band: it changed nothing there and deleted the syllable "ri"
   elsewhere. Full-resolution bands already handle the intrusion. Not used.
8. **Cost.** homr's segmentation is already run; the extra work is two OCR passes (about 1.8 s + 0.7 s
   per system on a 16-core machine, 2–3× that on the server) with models already in memory. No new
   dependency, no measurable RAM increase.

## Decision

Add a **lyrics stage** after the chord stage, built on the same principles: neural OCR for the pixels,
a small grammar and a sequence alignment for the structure, a benchmark that must not regress, and
warnings instead of guesses.

1. **Geometry from the driver.** `homr_driver` additionally records the photo-to-working-image scale
   and, for every staff (not only the top one: lyrics sit under the vocal staff, and on a grand staff
   the words between the staves belong to the upper one), a straightened band cut from the
   **original** photo along the bottom staff line, from 1.5 interlines below it down to 12 interlines
   or one interline above the next staff, whichever comes first. Noteheads get a y as well as an x so
   ledger-line notes are known. Ties are taken from homr's MusicXML: a tie continuation is not a
   sounding onset. Chords (several noteheads at one x) count as one onset.
2. **OCR** with RapidOCR word boxes on each band, padded to a 6:1 aspect ratio, at full resolution and
   at half resolution; tokens from the two passes are merged by overlap and the surer reading kept.
   The recognizer is the installed PP-OCRv6 default; the benchmark decides whether PP-OCRv5 `latin`
   replaces it (Appendix A §2). Confidence per token is RapidOCR's word score. The rapidocr version is
   pinned and a test covers word boxes, which have regressed before (Appendix B §3).
3. **Lyric grammar** (tokens to syllables): rows are formed by clustering token baselines; the row
   nearest the staff is verse 1, the next verse 2, and so on. A leading `\d+\.` is the verse number.
   A word token is split on `-` into syllables; a lone `-` token links its neighbours; `_`, dash runs
   and any thin horizontal ink run on the baseline between two boxes is an extender (melisma);
   `‿` merges two syllables into an elision; punctuation set off by a space (`, ; : ! ?`) is appended
   to the previous syllable; a trailing hyphen at the end of a system continues on the same verse row
   of the next system. The hyphen graph gives the MusicXML syllabic type: `single`, `begin`,
   `middle`, `end`. Syllable counts are never "corrected" with a dictionary: the French *e muet* is
   sung or not at the engraver's discretion, so the paper is the only authority (Appendix A §4).
4. **Alignment** per staff and per verse row: a monotone dynamic programme between the syllable
   sequence and the sequence of sounding onsets, with three moves: *match* (cost = horizontal distance
   between the syllable's anchor and the onset, in interlines, allowed up to 3), *skip onset* (cost 1.5,
   near zero when an extender or a slur covers the onset), *drop token* (cost 2 + 3 × confidence, so
   only doubtful tokens are dropped). This is the same idea as the chord stage's constrained decoding:
   the only outputs are sequences the grammar allows, and confusions are resolved by the whole line,
   not by one glyph. A row whose mean cost per syllable exceeds 2 interlines is not lyrics (a prose
   line, a footer, a translation) and is reported as "seen but not used", never written. A syllable
   that cannot be matched within 3 interlines is likewise reported with its text and measure. The
   requirement carried over from chords: never put a syllable under a note it does not belong to when
   the evidence is weak; leave the gap and warn.
5. **Output** as standard MusicXML `<lyric number="k">` with `<syllabic>`, `<text>`, `<extend>` and
   `<elision>`. OpenSheetMusicDisplay renders lyrics by default, so the score page shows them under the
   notes with no renderer change. Stats: verses, syllables read, syllables placed, warnings.
6. **Correction by the user.** The score page gets a lyrics panel with one text field per verse in the
   convention every notation program uses: `-` between the syllables of a word, `_` for a syllable
   held over the next note, one syllable per sounding note otherwise (`Lors-que nous é-tions en-core
   en-fants`). Saving re-injects the lyrics: when the syllable count equals the recognized one the
   texts replace one to one and the positions stay; when it differs, the user's hyphenation defines
   the sequence and syllables are dealt to the sounding onsets in order from the first placed note,
   `_` skipping one. The panel shows the syllable and note counts per measure so a mismatch is visible
   before saving. Lyrics are stored in the job as `lyrics.json` (kept by the cleanup) and rewritten
   into `score.musicxml` in place; the API gets `PATCH /api/jobs/{id}/lyrics`. This is where "almost
   perfect" is reached: the recognizer gets the structure right, the user fixes the odd word.
7. **Optional language-model polish, off by default.** When `PP_ANTHROPIC_API_KEY` is set, each
   verse's recognized syllable string is sent with its band image to Claude Haiku 4.5 asking for the
   corrected text with the same number of syllables and the same hyphen structure; the answer is
   accepted only if that structure is unchanged, and it never moves a syllable. About $0.001 per band
   (Appendix A §2). Off by default because the photo crop leaves the server; the operator chooses.
   Not part of the acceptance numbers below.
8. **Benchmark before merge**, `bench/lyrics/`, same shape as `bench/chords/`: pages rendered with
   verovio from MusicXML that carries lyrics, clean and photo-degraded, plus the real photo and the
   negatives (Gymnopédie, pages with prose blocks and no lyrics). Sources: French public-domain songs
   typed as ABC with `w:` lines (multiple verses, melismas, elisions, e muet cases, all under our
   control), OpenScore Lieder voice parts (CC0, MusicXML with lyrics) and a filtered slice of PDMX for
   English lead sheets (Appendix A §5, Appendix B). The ground truth is the MusicXML itself, and the
   verovio SVG gives the printed syllable boxes when box accuracy needs checking. Sheet Music Benchmark
   pages are an optional scanned evaluation set, not redistributed, because of its licence ambiguity.
   The scorer reports, per verse: syllables placed on the right note (the AMNLT alignment error),
   syllabic type right, character error rate of the text, verses found, and false lyrics (syllables
   written on a page or row that has none).
   Acceptance: **false lyrics = 0** on every page; placement ≥ 97 % on clean renders and ≥ 90 % on
   degraded ones; text character error rate ≤ 5 % on clean renders; the real photo 55 of 55 placed.

## Alternatives considered

- **Audiveris / MuseScore import for lyrics.** Tesseract text (37 of 55 words right on the photo),
  nearest-chord mapping that Audiveris's own issue tracker proposes replacing with ordered matching, a
  Java runtime and 1 GB more RAM. It sets the bar; it does not clear it.
- **End-to-end notation-and-lyrics transformers (AMNLT, SMT).** The right long-term shape, but the
  public models are trained on 4-line chant staves and there is no lead-sheet dataset with aligned
  lyrics to train on. Revisit when the benchmark corpus from step 8 is large enough to fine-tune.
- **Tesseract 5 `fra`.** Character boxes and hyphens survive better inside words, but it degrades on
  phone photos, its whitelist breaks whitespace, and the chord probe already found it worse than
  RapidOCR on the same crops. Not added.
- **A vision language model as the reader.** Near-perfect text on printed strips but approximate
  coordinates and occasional invented words, so it cannot place syllables. Kept only as the optional
  text corrector of step 7, where structure is enforced by the grammar and the count check.
- **A trained syllable detector.** Not needed: OCR word boxes already give the positions, and there
  is no dataset. The benchmark generator produces exactly the training data if the boxes prove too
  coarse on tilted photos.
- **Masking music ink before OCR.** Tried; hurt (finding 7).

## Consequences

- Recognition takes 3 to 6 s longer per page on the server; memory is unchanged; no new dependency.
- Two new job files (`lyrics.json`, and `score.musicxml` gains lyric elements); the cleanup keeps
  them. One new API route.
- The chord benchmark is unaffected: bands above and below are separate images; but the driver change
  (all staves, scale factor, notehead y) must keep `bench/chords/run_bench.py` at false = 0.
- Known risks and their planned answers: verse rows swapped when the interline spacing is tight
  (rows are clustered by baseline and validated by alignment cost); word boxes are approximate because
  RapidOCR derives them from CTC columns (anchor tolerance 3 interlines and the ordered DP absorb
  this; the benchmark's tilted photos will show whether the straightened band is enough); isolated
  hyphens and underscores are the glyphs OCR drops most (pixel fallback on the baseline); a verse
  paragraph that happens to sit within 12 interlines of the last staff (rejected by alignment cost, and
  it is the case to include in the negatives); lyrics between the staves of a piano score belong to
  the upper staff (bands stop one interline above the next staff).

## Implementation outline

1. Driver: scale factor, per-staff lower bands from the original photo, notehead y, tie flags; unit
   tests on the photo's geometry (`tests/data`).
2. `pipeline/lyrics/ocr.py`: two-scale band reading with word boxes, merge; `grammar.py`: tokens to
   rows, syllables, hyphen graph, extenders; `align.py`: the DP; `inject.py`: MusicXML lyric elements.
   Unit tests with the four band images of the photo and synthetic token lists.
3. `bench/lyrics/`: generator (ABC with `w:` lines via music21, Lieder and PDMX slices), scorer,
   runner; record results in `bench/RESULTS.md`; must meet the acceptance numbers.
4. Frontend: lyrics panel with per-verse text fields and per-measure counts; `lyrics.json` and the
   PATCH route; re-injection.
5. Optional LLM polish behind the key, with a test that the structure check rejects a changed count.
6. Deploy, measure the page timing on the server, update the README and BACKLOG.
