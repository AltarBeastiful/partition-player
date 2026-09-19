# Plan 0004: Assess repeats and the form of a song

Status 2026-09-19: written, not started. An assessment plan: it ends with a decision and an ADR, not
with a feature. Nothing here changes what the app does today (the page plays straight through).

## The question

A songbook page is not played in the order it is printed. The chorus is engraved once and sung after
every verse; verses are stacked under one line of notes, so the same sixteen measures are played
four times with different words; repeat barlines, first and second endings, *D.C.*, *Fine*, *al
Coda* and a printed "4 couplets, dernière fois coda" say how. Today the pipeline strips repeat signs
and volta brackets (`postprocess._strip_repeats`), the player breaks out of OSMD's iterator the first
time it jumps back (`Player.collect`), and the lyrics of every verse are shown but only the notes are
played, once. The user's example: a sheet whose chorus is repeated as a whole after each of four
verses. The assessment has to say how often this matters, what the engine already gives us, what the
renderer can do, and what the smallest design is that plays a song the way it is sung.

## What is already known (from the benchmark truth and the last song run)

The 31 benchmark songs (`bench/songs/leadsheets`, the photo sample), counted by `bench/songs/form.py`
over the truth files (`repeat`, `ending`, `segno`, `coda`, `sound` jumps, lyric verse numbers, `words`):

| structure in the truth | songs |
|---|---|
| repeat barlines | 15 of 31 |
| first and second endings (voltas) | 8 of 31 |
| *Fine*, *al Coda*, *D.C.* (as `sound` or words) | 2 of 31 |
| two or more stacked verses | 25 of 31 |
| three or more stacked verses | 19 of 31 |
| printed form words ("Refrain", "Chorus", "Strophe", "4 couplets…") | 7 of 31 |

So stacked verses are the rule (four of five songs) and repeat barlines are on half the pages; codas
and *D.C.* are rare on this kind of page.

What homr reads today, on the 60 song pages (engraved and photo), against the truth, by measure
index and direction:

| repeat barlines | precision | recall |
|---|---|---|
| exact position and direction | 0.88 | 0.74 |
| count per page only | 1.00 | 0.84 |

The misses are of two kinds: the forward repeat at the very first barline (*Camptown Races*, *Votre
divin maître*), which is implied and can be defaulted; and pages whose measure count is off by one
(*Vieni sul mar*, *Mattinata*), where the sign is read but lands one measure early. Voltas are never
read (0 of 8 songs, the `ending` element never appears in an engine file), and neither are *D.C.*,
*Fine*, *Coda*, nor the verse numbers in front of the lyric rows (the lyrics stage reads rows and
places syllables; it does not know verse 2 from verse 1 beyond their order).

## Step 1: Measure how the printed form is read and rendered

- `bench/songs/form.py` (the inventory and the repeat-barline table exist): add voltas (span,
  number), `sound` jumps, verse count per song, and for each song the **unrolled measure sequence**
  that music21's `expandRepeats` gives from the truth (the order the song is actually played, verse
  by verse), so a later player can be scored against it.
- What the lyrics stage sees: for each song with stacked verses, does `lyrics.json` hold every verse
  with its number (the OCR band reads the rows top to bottom; check the verse index against the
  truth's `lyric number`). Report the verses found / verses printed.
- What OSMD does with repeats it is given: feed the truth MusicXML of the 15 songs with repeats to
  OSMD's cursor iterator (a vitest with jsdom, or a small page) and record the order of measures it
  visits, against music21's unrolled order. This decides whether the player can keep its cursor
  walk and simply stop breaking out at a backward jump, or must drive the order itself.
- Check: the tables are in `bench/RESULTS.md` under "Form", with the unrolled sequences saved
  next to the run outputs.

## Step 2: Try to read what is missing, cheaply

- Voltas: the bracket is a thin horizontal line with a "1." or "2." at its left end above the
  staff, in the band the chord stage already OCRs. Try a detector on that band (line + small digit
  followed by a dot), scored on the 8 songs with endings, engraved and photo. Keep it only if it
  reaches the chord stage's standard: no false bracket on a page without one.
- Words: *Fine*, *D.C. al Fine*, *D.S.*, *Coda*, *Refrain*, *Chorus*, *Couplet*, "x4", "bis" are
  in the same band, or under the last staff; the chord OCR sees them and drops them as "not a chord"
  (`chords_seen`). Count how many of the 7 songs' form words are already in `chords_seen`, and
  whether the lyrics band catches the rest.
- Verse numbers: the digit and dot at the left of a lyric row. Check whether the lyrics stage keeps
  it or strips it, and whether row order alone is enough (it is when every verse starts on the same
  note).
- Check: a precision/recall line per sign kind; a decision per kind: read it, default it, or leave
  it to the editor.

## Step 3: Design the form as data, not as playback code

- One file per score, `form.json`, that says how the page is played: a list of sections over
  measure ranges (`{"name": "verse", "from": 1, "to": 16}`, `{"name": "chorus", "from": 17, "to":
  24}`) and an order of passes (`[{"section": "verse", "verse": 1}, {"section": "chorus"},
  {"section": "verse", "verse": 2}, …]`), with the ending taken on each pass when there are voltas.
  Stacked verses become passes of the same section with a different verse number, which is what the
  singer wants: the words of verse 3 highlighted the third time round.
- Where it comes from, in this order: repeat signs and voltas read by the engine (defaulted at the
  first barline), the verse count from the lyrics, form words when read; else the trivial form (one
  pass, straight through). The editor gets a **Form** panel: sections by measure range, the order
  as a list of passes, "repeat the chorus after every verse" as a one-click preset, since that is
  the shape of most songbook pages.
- The player takes the form and plays passes: the measure sequence unrolled from `form.json`, the
  cursor jumping back at a pass boundary, the syllables of the pass's verse highlighted (or the
  other verses dimmed) while the note names and chords stay. Loop and range apply to the unrolled
  sequence ("play the chorus twice"). The score stays as printed; nothing is duplicated in the
  MusicXML, so the editor and the lyrics panel are untouched.
- Check: the design fits the 31 songs' unrolled sequences from step 1 (every one expressible as
  sections and passes), written up as ADR 0006 with the numbers from steps 1 and 2.

## Step 4: A prototype on the unrolled order

- The player plays an unrolled measure sequence instead of the straight cursor walk (`Player`
  gets a list of `[from, to]` passes; the cursor is repositioned at each pass start, which
  `moveCursor` can already do backwards). No form UI yet: the passes come from the repeat signs the
  engine read, plus one pass per stacked verse when the page has no repeat sign at all.
- Score it: for the 31 songs, the sequence the player would follow against music21's unrolled
  truth, as the fraction of songs played in the right order. Listen to two (the user's ear is the
  benchmark: [[feedback-listen-to-results]]).
- Check: the fraction is in `bench/RESULTS.md`; the decision to build the full form panel, or to
  ship only "repeat signs honoured, verses as passes", is taken on that number.

## Not in this plan

Reading handwritten "x4" marks, nested repeats, repeats inside a measure, and multi-page songs
(a chorus on the next page) are noted for later; the benchmark set has none of them.
