# Plan 0013: A time signature that changes in the middle of the page

Status 2026-11-18: **steps 1 to 4 done.** The benchmark is re-scored against a control run of the commit
before the plan (`f9b34e3`): the false counts held, the measure counts held, and pitch and duration on
the voice and piano set fell by 19 notes of 4526. That loss was accepted by the maintainer (see
step 4). Backend 144 tests, frontend 128.

Earlier status, 2026-09-24: **steps 1 to 3 done**, step 4 done on the page that asked for it and not yet on
the benchmark. Backend 144 tests (17 new, `tests/test_meter.py`). No ADR: nothing in the architecture
moves, this is a recognition fix in the engine's own driver and in `postprocess`, the same shape as
the tie-across-a-barline item in BACKLOG.md.

The canon page now reads as it is printed: twenty measures, 87 notes, **nothing padded and no
overfull measure**, 6/4 written at measure 19 and 4/4 at measure 20, and the voices from measure 9
hold 50 quarters rather than 51 — which is the length the line that goes on underneath is tiled
against (plan 0011).

What the building changed, from the steps below:

- **A voice does not always begin at the bar line, and does not always stay on its staff.** The first
  re-anchoring put every voice at beat 0 and keyed it by (staff, voice). Measured over the
  benchmark's 61 authored scores — 1946 measures — that moved notes in 16 measures, all of them in
  the two-staff songs, and every one of them legitimate: a second voice that enters mid-bar and says
  so by the backup that positions it, and a piano voice that crosses to the other staff for a few
  notes (MusicXML numbers voices per part, not per staff). Taking each voice's entry from where its
  first note is written, and keying on the voice alone, brought that to 7.
- **The last 7 were real gaps, and no rule can tell them from a hole by looking at a voice.** A
  writer may skip a beat in an inner voice without writing the rest (six measures of Berlioz and
  Gounod do). What separates them from the engine's defect is the *bar*: a hole makes the bar longer
  than any voice needs, a written gap does not. So the repair is made **only where it shortens the
  bar**. That is 0 of the 1946 authored measures and 14 measures of homr's own output on the pages in
  this repository, 13 of them landing inside their time signature and none outside it.
- **The meter pass has to carry what it writes.** `measures()` reads the time in force as it walks,
  so a 6/4 written into measure 19 after that measure was yielded is invisible to measure 20 — which
  is where the page returns to 4/4. The pass keeps its own state and hands it forward, and `_in_force`
  is now shared with `measures()` so there is one reading of a measure's header, not two.

## The problem

*Auprès du ruisseau*, the canon photographed on 2026-09-22 (plan 0011's page), prints **6/4** at
measure 19 and **4/4** again at measure 20. The 6/4 bar is what makes the canon land: the second
voice enters a bar after the first, and those two extra beats are where it catches up, so both
voices finish together on *seaux*. We read the page as twenty measures of 4/4, and measure 19 comes
out seven quarters long with the two voices a beat out of step — the one doubt the page shows.

Two separate things are wrong, and only the first is about meter.

**The mark is read and then thrown away.** Dumping a staff's raw token stream (before homr's own
`remove_duplicated_symbols` runs) gives, for the last system:

    voice 0 system 3: 4 bars :: <clef_G2@bar1> <clef_G2@bar1> <keySignature_-1@bar1>
                                |1 |2 <timeSignature/4@bar3> |3 <timeSignature/4@bar4> |4

Both marks, in the right bars. What homr cannot do is say **how many beats**: the numerator is not
in the vocabulary. The token is `timeSignature/{beat-type}` — `transformer/vocabulary.py` builds it
from the denominators `[1, 2, 3, 4, 6, 8, 12, 16, 32, 48]` — and `build_time_signature`
(`music_xml_generator.py`) writes

    beats = median(measure lengths of the whole part) * beat_type

one number for the whole document. So 4/4 → 6/4 cannot be expressed at all, and a change that does
move the beat-type would be written with a numerator taken from the rest of the page. Both of our
marks are then dropped by `_remove_redudant_clefs_keys_and_time_signatures`, which compares the
token *string*: `timeSignature/4` equals the one at measure 1, so it is redundant.

Waiting for the engine is therefore not an option, and there is no need to: **the position is ours
already**. `homr_driver.parse()` holds each staff's `result` before `remove_duplicated_symbols`
touches it. And the numerator is on the page — measure 19 holds exactly six quarters in each voice.

**The staves drift inside the bar.** Independently of the meter, homr's generator lays chords one
after another by duration (`build_note_chord`, `build_measures`) and keeps no absolute onset. When a
long note in one staff spans a shorter note in the other, the cursor overshoots: at the beat where
only *Vx. 1*'s half note stands, the chord advances two quarters although the next thing on the page
is *Vx. 2*'s quarter one beat later. Measure 19 holds six quarters in each voice and is written
**seven** long, with a beat of silence in the middle. Setting the meter to 6/4 without repairing
this would leave the bar overfull by a quarter and the hole still there.

## The steps

**1. The driver keeps the marks.** In `homr_driver.parse()`, while each staff's `result` is still
unfiltered, count barlines and record every `timeSignature/{d}` token as
`{"measure": <index in the part>, "beat_type": d}`, using `measures_per_system` to turn a bar within
a system into a measure of the part. Write them into `geometry.json` under `times`. Nothing else
changes; a page with no change in meter gets one entry for measure 0, which later steps ignore.

**2. Re-anchor the voices of a measure.** In `postprocess`, before anything is measured or padded,
rewrite a measure's `backup` so that every voice enters where its first note is written and its own
notes follow one another from there — and keep the rewrite **only where it shortens the bar**, which
is what closing a hole does and what a gap a writer meant does not. It never runs on an authored file
(`postprocess(repair=False)`), like every other repair here, and a measure that positions a voice
with `forward` is left alone. Chord tones keep their head's onset; `harmony` and `direction` stay
immediately before the note they belong to, so a chord symbol keeps the beat it was placed on.

**3. Take the numerator from the bar.** For each mark past measure 0, compare what the bar holds
with the time in force. Write a new `<time>` only when

- every voice in the measure holds the same length `V`, and
- `V` differs from the time in force, and
- `V * beat_type / 4` is a whole number of beats between 1 and 32, and
- `V` is not exactly twice the time in force — a missed barline is far commoner than a doubled bar,
  and the upbeat rule in `postprocess` already says so.

Otherwise leave the meter alone and say what was seen in the doubt, so the page tells the user that
a time signature is printed there and the editor's `setTime` is one click away.

**4. Check it on the page that asked for it, then on the benchmark.** Done for the page: measure 19
is 6/4 with six quarters in both voices, measure 20 returns to 4/4, nothing is padded and the only
doubts left are the two that say what was read. Done for the benchmark on 2026-11-18, with the
commands in `bench/RESULTS.md` ("Meter changes (plan 0013)"):

- **Lead sheets, 60 pages: every tally is identical** to the run of 2026-09-19, to the note, the
  syllable and the chord (false syllables 157, false chords 61, both unchanged).
- **The Anton photo** keeps an event error rate of 0.00: 55 of 55 notes, 19 of 19 measures.
- **Voice and piano, 60 pages.** The run of 2026-09-19 is not a fair baseline: it was probably made before the
  scorer was committed in its final form, and its ground-truth count differs (4262 events against
  4526). So the plan was measured against a control run of `f9b34e3` with the same scorer and the same
  pages. Measure counts right: 58 of 60 in both. Placed syllables 1138 and false syllables 17 in both.
  The 19 chords read on this set (it has none in its ground truth) are **there before the plan too**:
  19 in both runs. Pitch 4265 to 4248 (-17), pitch and duration 4155 to 4136 (-19, 0.4 %).
- **Where the 19 went:** Ferrari -4 and -6 (clean and photo), Gounod's *Sérénade* -2 and -2, Puget -2,
  Wolf -1 and -1, Butterworth -1, Burleigh's photo -1, and one gained on Berlioz's photo. On Ferrari a
  note moves one position and a rest is added, on a page that already carries a dozen "padded" doubts.
  Whether those moves are the re-anchoring of step 2 doing what it should or damage was **not
  established**.
- The criterion set for this step was that pitch and duration must not drop. It dropped, by that
  margin, and the maintainer accepted it knowing the cause is not pinned down: the canon page is read
  as printed, and the loss is on pages that were already unreliable. If Ferrari or Gounod are ever
  reopened, start there.
- The scans set (10 real prints) was run once after the plan and not against a control: pitch and
  duration 78.2 % of 596 notes, 7 false syllables, 1 false chord.

## What this deliberately does not do

- **One voice is not enough evidence.** A single staff holding five quarters in a 4/4 bar is a
  misread duration far more often than it is a 5/4 bar, and step 3's first condition rules the
  single-voice page out. A lead sheet that really does change meter still needs the editor.
- **Nothing is inferred where no mark was read.** The position always comes from the page.
- **The beat-type is the engine's.** We only ever supply the numerator.
