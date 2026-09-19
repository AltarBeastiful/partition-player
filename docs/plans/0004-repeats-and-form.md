# Plan 0004: Repeats and the form of a song

Status 2026-09-19: reviewed by an independent agent (validated with changes, applied below); steps 1
to 3 done and checked (backend 69 tests, frontend 23 unit tests including OSMD headless on the
truth, the scoring run in `bench/RESULTS.md` "Form", browser checks on *Camptown Races* recognized
from its photo: passes, the words of the pass, seek across passes, presets, save and reload, the
repeat toggle). Not yet listened to; not deployed. The decision on the form panel's future is the
user's, on those numbers and their ears.

## The question

A songbook page is not played in the order it is printed. The chorus is engraved once and sung after
every verse; verses are stacked under one line of notes, so the same sixteen measures are played
four times with different words; repeat barlines, first and second endings, *D.C.*, *Fine*, *al
Coda* and a printed "4 couplets, dernière fois coda" say how. Until this plan the pipeline stripped
repeat signs and volta brackets (`postprocess._strip_repeats`), the player broke out of OSMD's
iterator the first time it jumped back (`Player.collect`), and the lyrics of every verse were shown
but the notes were played once. The user's example: a sheet whose chorus is repeated as a whole after
each of four verses.

## What is known (benchmark truth, the last song run, the OSMD source)

The 30 lead sheets of `bench/songs/leadsheets` plus the photo sample, counted by
`bench/songs/form.py` over the truth files:

| structure in the truth | songs of 31 |
|---|---|
| repeat barlines | 15 |
| first and second endings (voltas) | 8 |
| *Fine*, *al Coda*, *D.C.* | 2 |
| two or more stacked verses | 25 |
| three or more stacked verses | 19 |
| printed form words ("Refrain", "Chorus", "Strophe", "4 couplets…") | 7 |

Stacked verses are the rule, repeat barlines are on half the pages, codas and *D.C.* are rare.

What homr reads, on the 60 song pages (engraved and photo), against the truth:

| repeat barlines | precision | recall |
|---|---|---|
| exact measure and direction | 0.88 | 0.74 |
| count per page only | 1.00 | 0.84 |

The 15 exact misses are of three kinds: 4 are the implied forward repeat at the first barline
(*Camptown Races*, *Votre divin maître*), which OSMD defaults by itself; 5 land one measure early
on pages whose measure count is off by one (*Vieni sul mar*, *Mattinata*); 6 are outright misses
(*La nave del olvido* both signs on both pages, *Mattinata*'s backward repeat). Voltas are never
read (`<ending>` in 0 of 60 engine files), nor *D.C.*, *Fine*, *Coda*. The lyrics stage detects
the verse label in front of a row (`grammar.py`, `VERSE_NUMBER`) but drops it: verses are numbered
by their rank under the staff, so rows labelled "1. 3. 5." become verses 1, 2, 3 (*My grandfather's
clock*) and the text of a third ending is stored as verse 1 (*Les gens bien élevés*). Verses are
under-read on 6 of the 25 stacked-verse songs (*Camptown* 5 of 8, *Clementine* 4 of 7…). Of the 7
songs with form words, 6 already have them in `chords_seen` as text the chord OCR dropped; the same
band holds hundreds of stray digits on pages with no volta, so a "1." detector would face real
noise.

OSMD 1.9.9, read in the source: the cursor iterator follows repeat barlines, voltas, *D.C.*, *D.S.*,
*Fine* and *Coda* when the MusicXML carries them (`MusicPartManagerIterator.handleRepetitionsAtMeasureEnd`,
`Repetition.getForwardJumpTargetForIteration`, `RepetitionInstructionReader`). It exposes
`CurrentRepetitionIteration`, `backJumpOccurred`, and a monotone `CurrentEnrolledTimestamp`, while
`currentTimeStamp` is the printed position and goes backwards on a jump (hence the break in the
player). `EngravingRules.CursorIgnoreRepetitions` disables every jump; `Repetition.UserNumberOfRepetitions`
sets the count per repetition, followed by `MusicPartManager.reInit()` and a fresh cursor. OSMD
always adds a virtual repetition over the whole piece, played once; its "once per lyric verse"
multiplier is dead code (it reads the length of a method), so a page with four stacked verses plays
once. Headless, on the truth, its order equals the literal signs: *Alfonsina* `0-19, 20, 9-19,
21-33` (the volta right), *Marche des rois* three endings then *Fine*, *Camptown* `0-8, 0-16`
(verses twice, chorus once: the signs, not the song).

## The design (ADR 0006 when step 3 is listened to)

**The page is played as a list of passes.** A pass is a list of measure ranges with a verse number
or none: `{"ranges": [{"from": 9, "to": 19}, {"from": 21, "to": 33}], "verse": 2}`. Ranges are
0-based, inclusive; a pass can start on a pickup measure, since a range can start anywhere. The
player always plays a pass list: the cursor walks the printed order with repeats ignored, and jumps
back at each pass boundary (`moveCursor` already rewinds). Notes, chords and the accompaniment are
unrolled with the passes; click-to-play goes to the next occurrence of the clicked measure after
the current position, else its first; the loop range is the first occurrence of `from` to the
first occurrence of `to` after it.

**The default pass list comes from OSMD's own expansion**, with the multiplier it meant to have:
each repetition is played as many times as the largest lyric number under its span, at least its
number of endings. OSMD's virtual whole-page repetition never jumps whatever its count (found in
step 3), so the whole-page part is done as rounds of the list: the songbook rule. When the page has
no repeat sign, or when three or more verses are stacked and a single-lyric part follows them, round
k plays every pass in order, the stacked ones with verse k, the single-lyric ones every time. Two
stacked rows under a repeat are taken literally (*Kristallen den fina*: a first phrase sung twice).
The list is derived in the browser after each load and each edit, from the repeat signs in the
document and the lyrics in it, so the lyrics panel's verse count is the count that matters.

**The form is data the user can replace**: `review.json` gets `form: null | {sections, passes}`,
saved in the `PUT /score` body under the same revision as everything else, so it cannot go stale
unnoticed. Sections name measure ranges (`{"name": "Verse", "from": 0, "to": 8}`); passes name a
section and a verse. Measure indices are remapped through `session.apply` when a measure is split,
merged, inserted or deleted (as `checked` is), and snapshotted for undo; a range whose boundary
measure is deleted shrinks. **Repeat signs stay in the MusicXML**: the pipeline no longer strips
them, OSMD draws them so the user sees what was read, `original.musicxml` and Revert keep them, and
the editor gets a "repeat" toggle on a measure's barlines.

**The words of the pass.** On a pass with verse *n*, the lyric *n* of each note is shown and the
other lyrics under that note are dimmed; a note with a single lyric (the chorus) keeps it; a note
with several lyrics but no lyric *n* keeps them all.

Songs the design has to handle, from the truth files: *Marche des rois* (three endings, then
*Fine*), *Les gens bien élevés* (ending "1, 2" and a verse-3 continuation stored as verse 1),
*Alfonsina*, *Luna tucumana* and *Joyeux Noël* (a pickup before the forward repeat), *My
grandfather's clock* (rows 1/3/5 under the second phrase), *La clairière* (four couplets and a coda,
the couplets as a text block the lyrics stage rejects), and the two odd truth files (*Joyeux Noël*
has a forward repeat and no backward one; *Votre divin maître* has endings at 9 and 19 with the
backward repeat at 18).

## Step 1: The truth of the form, by hand

- `bench/songs/leadsheets/<song>.form.json`: the order the song is sung in, as passes of ranges with
  a verse or none, written by hand from the print (the signs, the verse rows, the form words), not
  from a machine expansion of the truth, which gives the literal signs (*Camptown* verses twice
  then the chorus once) and not the song. `bench/songs/form.py` prints the sign dump per song to
  start from.
- `bench/songs/form.py` also reports verses found / verses printed per song from the run's
  `lyrics.json`.
- Check: 31 files; the inventory tables above and the verses table in `bench/RESULTS.md` under
  "Form".

## Step 2: Keep the signs; the form in the review record

- `postprocess`: stop stripping `<repeat>` and `<ending>`; record an info doubt on each measure with
  a repeat sign ("a repeat sign was read here") so it is visible in the review bar.
- `review.json` gets `form`; `GET /review` returns it; `PUT /score` accepts it in the body;
  `revert` drops it (the recognized form is the automatic one).
- Check: pytest, including a save with a form and a revert without one.

## Step 3: The player plays passes (the first shippable increment)

- `frontend/src/form.ts`: the types, `defaultPasses(osmd)` (OSMD's expansion with the verse
  multiplier, read from the iterator with `CurrentEnrolledTimestamp` and `CurrentRepetitionIteration`,
  compressed into passes), `expand(form)` (sections and passes to ranges), and the remap on measure
  edits.
- `Player`: builds an unrolled timeline from the printed steps and the pass list; notes and the
  accompaniment mapped by measure; `seek`, `positionOf`, the loop window and `restart` on the
  unrolled timeline; the current pass and its verse reported to the page.
- The words of the pass dimmed on the sheet during playback (`frontend/src/verses.ts`, a layer like
  the doubts layer), with the rule above.
- A **Form** panel above the sheet: the pass list in words ("Verse 1 · Chorus · Verse 2 · Chorus"),
  the verse count, sections and passes editable, presets "as printed", "once per verse", "chorus
  after every verse"; saved with the score. A "repeat" toggle in the editor's Measure group.
- A vitest that runs OSMD headless on five truth files and asserts the default pass lists, so an
  OSMD upgrade that changes its expansion is caught.
- Check: the order the player follows for the 60 run outputs against the hand truth (fraction of
  songs in the right order, with the automatic form), in `bench/RESULTS.md`: 21 of 60 pass lists
  exact, 23 in the same measure order, 178 of 206 printed verses sung; the causes of the rest are
  listed there. Still to do: listen on *Camptown*, *Alfonsina* and *Die Gedanken sind frei*, and
  decide how far to take the form panel on that number and those ears.

## Later, not in this plan

Reading voltas from the band (8 songs, digit noise on every page), verse labels from the band,
handwritten "x4" marks, nested repeats, repeats inside a measure, multi-page songs (a chorus on the
next page). Voltas can be entered by hand once repeat signs are editable.
