# Plan 0008: How sure we are — rating a doubt instead of raising one

Status 2026-09-21: done. Written 2026-09-20 with three levels; cut to two on the user's call —
`hint` is gone, because a level that is allowed to be wrong is a level that cries wolf, and the
worked example below is exactly a case where the one disagreeing source was wrong. A place where
only one source speaks is now silent.

Built and calibrated. Backend 83 tests, frontend 71, the whole pipeline run end to end on the page
the plan is named after: `evidence.json` written, **zero doubts**, the blot on measure 8 found and
silenced. Checked in the browser at 1280×800 with one doubt of each level injected: `info` blue and
filled, `check` a broken amber outline with no fill and a faint badge, `wrong` solid amber — and the
review bar counts the two loud ones, not the information.

Three things the benchmark changed, none of which the tests could have (step 4 is in
`bench/RESULTS.md`, "How sure"):

1. **The first rule was circular.** Demoting on "the measure adds up" made the rating speak only
   where the arithmetic flag already speaks — 48 of 48 marks on measures that were flagged anyway,
   which is the one thing the plan exists not to do. A head stacked on an existing stem adds no
   duration, so a sound measure is no evidence about it; the demotion now applies only to a note
   gained or lost in sequence.
2. **The position source does not work and is gone.** See the last bullet of the results section:
   2 wrong in 36, then 0 in 8 with the detector's own dewarped position, at three normalisations.
   Measuring it properly needed a benchmark re-run with a patched driver, which is why the driver
   now records the position and the size of every notehead.
3. **On lead sheets the feature is silent, and that is the right answer** — the raw sources are worth
   0.05 to 0.14 there, and only 3 wrong measures in 1505 are invisible to the arithmetic anyway. It
   earns its place on the voice-and-piano pages: 68 marks at 0.78 precision, 14 wrong measures the
   arithmetic cannot see, and not one mark on a page that came back right.

## The problem

A doubt today is one thing and one thing only: **a measure of the engine's output that does not add
up**. `postprocess.py` raises `underfull`, `overfull`, `padded`, `pickup`, `repeat` and `rest_chord`,
the editor paints the measure amber and puts a `?` over it, and the header counts it. It is a good
signal for what it covers (`bench/RESULTS.md`, "Doubts"):

| set | measures | flagged | of which wrong | precision | wrong | of which flagged | recall |
|---|---|---|---|---|---|---|---|
| lead sheets | 1505 | 106 | 95 | 0.90 | 98 | 95 | 0.97 |
| voice and piano | 1073 | 571 | 461 | 0.81 | 597 | 461 | 0.77 |

It is also **blind to every error that does not change a duration**: a pitch a step or two off, a
missing accidental, an octave, a notehead too many or too few inside a chord. The benchmark's own
census of what goes wrong lists exactly those on the piano pages — pitch two steps off 25 times, one
step off 20, an octave off 14, a missing accidental 12 — and none of them can move the arithmetic, so
none of them can ever raise a flag.

### The page in the app

`anton_yvan_boris`, 19 measures, 55 notes, **zero doubts**. And yet on one note, three readers
disagree:

| reader | measure 8, last eighth ("-ra-") |
|---|---|
| our transformer | one note, C4 |
| our own segmentation stage | two noteheads at the same x (1518), 0.82 interlines apart (y 977 and 991) |
| MuseScore Studio 4.6.5, importing the same photo | B3 **and** C4, a dyad |

Measured by re-running the driver on the original 3072×4096 photo. Per system, noteheads found
against notes emitted: 15/15, **18/17**, 12/12, 11/11 — and inside the one system that disagrees, the
surplus is in measure 8. One disagreement on the page, on the disputed note.

Blown up, the printed note is a **single notehead sitting on the C4 ledger line**, with an ink blot
bleeding off its lower left and a tail running down towards the lyric. **We read it right.**
MuseScore turned the blot into a second note.

That is the whole difficulty in one note. There *was* a signal — our own pixel stage disagreed with
our own transformer, on that note, and nowhere else on the page — and the output it disagreed with
was **correct**. If a disagreement were promoted to a doubt, this page would grow an amber measure
and a `?` pointing at a note that is right, on a page that is otherwise perfect.

And it would not be rare. Already measured on the lead sheets (`bench/RESULTS.md`): the segmentation
net's notehead count equals the transformer's note count on **256 of 302 systems** — so it disagrees
on **46**, about one system in seven. The detected barlines give the right measure count on 277 of
302, so that one disagrees on 25. Raised as warnings, those would bury the 106 flags that are right
90 % of the time under several hundred that are mostly wrong.

So the work is not *find another signal*. The signals are already computed and thrown away. The work
is to **rate** them, and to say no more than the rating deserves.

## What we already have, and what it costs

| # | source | where it is now | points at | new work |
|---|---|---|---|---|
| 1 | measure arithmetic | `postprocess.py`, in use | a measure | none |
| 2 | notehead count, segmentation vs transformer | `geometry.json` (`homr_driver.py:280`) vs the MusicXML | a system today; a measure with the barlines; a **note** with the x | compare two arrays |
| 3 | notehead shape | `avg_head`, the median notehead height (`homr_driver.py:70`) | a note | compare to the median |
| 4 | barline count vs measures | already a warning string under the sheet | a system | promote to evidence |
| 5 | ~~lyric alignment~~ | the ordered DP of ADR 0004 | a note | **not independent** — `lyrics.json` carries syllables already assigned to `(measure, onset)` by the DP, i.e. onto the transformer's own notes, so its count agrees with the transformer by construction. Only the raw OCR word boxes would be a second reader, and they are not kept. Dropped. |
| 6 | the transformer's own confidence | **discarded**: `decoder_inference.py` takes `argmax` over the per-head logits and keeps only the token (`homr/transformer/utils.py` even defines a `softmax` nothing calls) | a note, continuous | capture the logits inside the vendored decode loop |

1–5 are comparisons of arrays the pipeline already builds. Only 6 needs new code inside homr, which
is why it comes last.

## Decision

1. **A doubt gains a level, a place and its evidence.** `{measure, note?, kind, text, level,
   sources[]}` where `level` is `wrong` | `check`. `note` is an event key when the evidence
   localises to one note, absent when it is only about the measure. `sources` names what spoke, so
   the text can say *why* and the benchmark can score each source on its own.

2. **Two levels, and the level never comes from one source alone** — except the one source that is
   not an opinion:

   - **`wrong`** — the measure does not add up. We do not think the output may be wrong, we know it
     cannot be right. This is today's flag, unchanged, and keeps today's presentation.
   - **`check`** — the evidence against the reading, net of what supports it, reaches **2**.
   - **nothing** — anything less.

   Counted as follows, per place:

   | | |
   |---|---|
   | **+1** | each independent reader that disagrees with what was emitted |
   | **+1** | the disagreement is of a *strong* kind: a stacked notehead that **is** on the staff grid, on a page that already has chords; or the mirror of it, the score stacking notes on a stem the print does not show stacked |
   | **−1** | each demotion that applies (below) |

   There is only one independent reader today — the segmentation stage — so without the strong-kind
   bonus nothing could ever reach 2, and the feature would be vacuous. That is the honest shape of
   it: the rule is "one reader, but only when it disagrees *loudly* and nothing argues back", until
   source 6 gives a genuine second opinion.

   There is deliberately no third, quieter level. A mark that is allowed to be wrong still costs a
   look, and the page that prompted this plan is precisely a page where the single disagreeing source
   was the one in error. **Anton measure 8 will show nothing at all**, and that is the correct
   outcome: we read it right, and nothing else on the page supported the doubt.

   The cost of this choice, stated plainly: a real error that only one source can see *quietly* will
   pass in silence. Step 4 measures how many of those there are; if it is a large number, the answer
   is a better source (step 6), not a quieter level.

3. **Agreement demotes to silence.** A source that agrees is evidence *for* the reading, and a place
   where the rest of the page agrees is weaker than the same disagreement on a page that is falling
   apart. Four demotions to start with, three of which apply to Anton measure 8:

   - the measure adds up (source 1 silent) — the reading is at least arithmetically whole;
   - a **chord proposed on a page that is monophonic everywhere else**. Anton is 55 notes, 55 lyric
     syllables, not one chord read anywhere. A stacked pair of noteheads on such a page is far more
     likely to be ink than a dyad.
   - **a stacked pair that does not sit on the staff grid.** Two noteheads of a real chord are a
     whole number of scale steps apart, i.e. a multiple of half an interline. Anton's pair is 0.82
     interlines apart — 1.64 steps, neither a second nor a third. Ink does not land on the grid;
     engraving does. This is the cheapest discriminator of the three and it should be measured
     first.
   - **the measure's boundaries were estimated.** When a system's detected barlines do not match its
     measure count, `layout.measure_bounds` splits the system evenly, so which measure a notehead
     falls in is a guess and a count per measure cannot be trusted. Anton's measure 8 is in exactly
     such a system — one barline was not detected, which the pipeline already records as a chord
     warning.

   Worked out for Anton measure 8: one reader disagrees (+1), the kind is not strong — the stack is
   off-grid (+0), and three demotions apply (−3). Net −2, comfortably silent.

   Be honest about what source 5 can and cannot do: the syllable count constrains the number of note
   *positions*, not the number of noteheads. It tells a **missing or extra note in sequence** from a
   correct one; about a second head stacked on an existing stem it says nothing directly. Its use
   here is the demotion above — it establishes that the page is one note per syllable — not a
   verdict on the stack.

4. **What is shown is proportional to the level.**

   | level | on the sheet | in the header count | tooltip / dialog |
   |---|---|---|---|
   | `wrong` | amber measure box, `?` badge — as today | counted | as today |
   | `check` | amber box **on the note**, not the whole measure, no badge | counted | names the rival reading |

   `check` borrows the colour of `wrong` but not its size: the mark sits on the notehead the evidence
   points at, so a page with one doubtful note does not look like a page with one doubtful measure.

5. **A mark states what we believe, not just that something is wrong.** Our reading comes first, the
   rival second — *"we read one note (C4); the notehead detector saw two"*. The Readings dialog
   (ADR 0006) already engraves alternatives and previews them; a `check` seeds it with the rival
   ranked first rather than inventing a new surface.

6. **A note the user has edited, or a measure marked checked, never carries a mark again.**

## Calibration — the part that decides whether this ships

The rating is worthless unasserted, and the levels cannot be set by taste. Before any of it reaches
the UI, each source is scored on its own on the song benchmark, against the event alignment of
`bench/score.py`, on the pages whose measure count came back right — the same ground the existing
doubts table stands on.

Per source and per combination: how often it fires, and of those, how often the emitted note is
**actually wrong**. The bars to clear:

- `wrong` keeps **precision ≥ 0.90** on lead sheets. This is today's number; the change must not
  regress it.
- `check` must reach **precision ≥ 0.5**. Below a coin flip it has no business asking anyone to look.
  With no quieter level to fall back to, a combination that misses the bar is simply **not shown**.
- The cry-wolf test: on the benchmark pages that come back **exactly right**, `check` marks must be
  **0**. Anton must end with **nothing at all** — no amber, no dot, the count still 0.
- Report what is gained: how many of the pitch and accidental errors that today's flags cannot see
  are caught by `check`. And report what is lost: how many are seen by exactly one source and are
  therefore now silent. If the gain is near zero, the plan stops after the measurement and only the
  evidence-keeping of steps 1–2 survives, as the ground for step 6 later.

## Steps

1. **Keep the evidence.** The per-note geometry lives in `geometry.json`, which is deleted with the
   engine's intermediates when the job ends. Write what the rating needs — per note: x, y, the
   notehead's size against the page median, and the emitted event key — into a small `evidence.json`
   kept with the score. Measure it on disk and add it to the per-score budget in `deploy/README.md`
   (about 350 KB today, 500 scores under 200 MB).

2. **The comparison, in the pipeline.** Align detected noteheads to emitted notes by x within a
   measure (the barlines are already there, estimated where one was missed), and emit per-note
   disagreements: a head with no note, a note with no head, two heads on one note. Pure, with unit
   tests on a synthetic geometry — including the stacked-pair case and the missing-barline case,
   which is exactly the system Anton's measure 8 sits in.

3. **The rating function.** Pure, in the backend, taking the sources and returning
   `level` + `text` + `sources`, where the level is `wrong`, `check`, or nothing at all. Tested on
   hand-written cases, including all four demotions, the strong-kind bonus, and Anton measure 8.

4. **Calibrate.** Re-run the song benchmark with the evidence kept, add `bench/songs/rating.py`
   alongside `doubts.py`, and write a table per source and per level into `bench/RESULTS.md`. Set the
   floors from the numbers. **This step decides whether steps 5 and 6 happen.**

5. **The UI.** The note-level `check` mark in `sheet.ts` and `styles.css`, the header count, the
   Readings dialog seeded from the rival reading. Checked in the browser at 1280×800 on Anton:
   nothing anywhere, the count still 0 — and on a page the benchmark says has a corroborated error,
   the mark on the right notehead.

6. **The transformer's confidence — not done, and step 4 says it is what remains.** Capture the
   per-head softmax of the chosen token in `ScoreDecoder.generate`, carry it out through the driver
   as a per-note number, add it as a source, recalibrate. It is the only genuinely second opinion
   left: the pixel stage is one reader, and 122 wrong measures on the piano pages plus 3 on the
   lead sheets are still silent. It is last because it is the only step that reaches into vendored
   code.

## Rejected

- **Promote the notehead mismatch straight to a doubt.** 46 of 302 systems, mostly correct output.
  This is the failure this plan exists to avoid.
- **Show a confidence percentage on each note.** False precision from a number we have never
  calibrated, and it invites the user to read 82 % as meaningfully different from 79 %.
- **A third, quieter level (a "hint": one source disagreeing, shown as a faint dot).** This was the
  plan as first written and it was cut: a mark allowed to be wrong is a mark that cries wolf, and the
  case that motivated the whole plan is one where that single source was in error. The price —
  errors only one source can see now pass in silence — is accepted, measured in step 4, and answered
  by a better source rather than a louder page.
- **A second engine, or a language model on the flagged measures.** Both are in `BACKLOG.md` and both
  cost a run or a call per score; this plan is about the evidence we already compute and discard.

## Non-goals

Not about making the engine read better — nothing here changes a single note of the output. It only
changes what we say about how sure we are.
