# Plan 0007: Building the form of a song by hand

Status 2026-09-20: done. Written and reviewed by an independent agent on 2026-09-19, revised against
its findings, built on OSMD 2.1.3 (4e3857c). Frontend 57 unit tests, backend 69, `tsc` and the build
clean, `bench/out/form.txt` unchanged in its first line (the automatic form) and carrying the new
hand-work numbers. Checked in the browser on `anton_yvan_boris` at 1280×800: the preset keeps the
sections the panel has, `V1 C×2 V2 C×2 V3 C V4 C×2 V5 C×2` applies as ten chips, the bands show where
the sections fall, one click on the "An-" note plus *ends here* / *starts here* puts the boundary on
beat 2 of measure 11, and the music plays on through every edit. Three things the browser found that
the tests did not: the section layer retriggered `keepOverlay`'s observer (an endless redraw), the
edges were read from the playhead, which the first edge moves (they now come from the note last
clicked), and a section could be given an end before its start within one measure.

## The problem

The automatic form is right on 21 of the 60 benchmark pages (35 %, `bench/RESULTS.md` "Form"). The
other 39 are "one edit away in the form panel" — which makes that visit the normal case, and the
panel was built for a small correction, not for entering the form of a song.

How far away, measured on `bench/out/form.txt` (the app's pass list against the hand truth, edit
distance over passes: add, remove, change):

| pages | right as read | median edits | mean | worst | also need a section the app never proposed |
|---|---|---|---|---|---|
| the 39 that need work | — | 5 | 7.1 | 32 | 31 |
| all 60, the 21 zeros included | 21 | 2.5 | 4.6 | 32 | 31 |

The first row is the one that describes the visit; the second is there so the two are not confused.
The hand truths are long: median 4 passes over the 30 songs, 10 songs at 8 passes or more, 5 at 12 or
more, 16 at the longest (*Camptown races*: eight verses, the chorus after each); 3 of the 30 play a
pass twice in a row (*Auprès de ma blonde*, *La clairière*, *Vieni sul mar*, whose chorus is sung
twice after every verse) — the shape this plan is named after.

The worked example is the page loaded in the app today, `anton_yvan_boris` (19 measures, 2/4, one
lyric row, no repeat sign read, so the automatic form is the single pass "m. 1–19"). It is sung as
five verses with the chorus between them, doubled everywhere except between verses 3 and 4, and
doubled again at the end — 14 passes:

> Verse 1 · Chorus · Chorus · Verse 2 · Chorus · Chorus · Verse 3 · Chorus · Verse 4 · Chorus ·
> Chorus · Verse 5 · Chorus · Chorus

Entering it in the panel as it stands takes about 27 interactions (rename the one section, type its
last measure, add the second section, rename it, type the first verse number, then 13 *+ pass*
clicks alternating between the two section rows in exactly the final order — because a pass can only
be appended, and putting one back in place costs one `‹` per step). Six things make that worse than
long:

1. **Undo scrambles the form.** `snapshot()` captures `form` (`session.ts:219`) and `restore()`
   writes it back (`session.ts:225`), but `setForm()` only touches (`session.ts:132`). So a note
   edit made before the form is built, undone after it, reverts the form to `null` — `redo()` brings
   it back (`session.ts:211`), so it is a timeline the user cannot predict rather than a permanent
   loss — and a misclick in the panel (*×* on a chip, *Automatic*, a preset) has no undo at all.
2. **Every form change stops the playback.** The pass list is rebuilt whenever the form *object*
   changes (`ScoreView.tsx:185`), and `setPasses` stops unconditionally (`player.ts:148`); `stop()`
   also resets the OSMD cursor and fires `onState` (`player.ts:444`), so the sheet visibly jumps.
   Renaming a section to "Chorus" does that six times, once per keystroke, and arms six full-document
   autosaves (`session.ts:240`). Checking a form by ear while building it is the natural gesture and
   the panel fights it.
3. **The presets discard the sections you made.** Every branch of `preset()` reads the *printed*
   passes (`form.ts:182`) and the panel always passes them (`Editor.tsx:310`), so splitting the page
   into Verse and Chorus and then clicking *Chorus after every verse* loses the split; its fallback
   cuts the page in half, which for Anton gives m. 1–9 / 10–19 — one or two measures off, depending
   which whole-measure split you accept.
4. **A pass cannot say "twice".** The doubling that three of the thirty songs print, and that Anton
   needs nine times, is nine separate chips.
5. **Sections are typed blind.** The panel asks for measure numbers while the sheet on the same page
   (`ScoreView.tsx:406`, under the panel) knows where every measure is
   (`editor/sheet.ts:114 measureBox`) and the editor already has click-to-select. 31 of the 39
   differing pages need a section boundary entered by hand.
6. **A section cannot start on an upbeat.** Anton's chorus begins on the second beat of measure 11
   ("An-" of *Anton*, after "…tourterelles." on beat 1). With whole-measure edges the user must
   choose between a chorus that repeats without its upbeat (split 11/12) and one that repeats with a
   leftover syllable (split 10/11). An anacrusis chorus is ordinary in a songbook.

What the panel gets right, and what this plan keeps: the vocabulary (sections over measures, a list
of passes, a verse number per pass), the summary line in words with the pass being played lit, the
form saved per score and remapped when measures are added or removed (`remapForm`), *Automatic* as
the way back, and the panel being outside edit mode — the form is not a correction of the print.

One neighbouring friction, corrected from the first draft of this plan: the *verses* box feeds only
the presets, so nothing connects it to the lyric rows. Typing verses 2 to 5 by hand needs **no**
trailing `*` padding — `deal` stops when a verse's items run out (`pipeline/lyrics/edit.py:88`), so a
short verse simply ends before the chorus and `verses.ts:34` leaves the chorus's single lyric
undimmed, which is what is wanted. `*` is only ever *leading*, for a verse that starts later
(`edit.py:46`). Nothing to build there; one line of help text in the panel instead.

## Decision

1. **The three defects first** (they are data loss and noise, not polish). `setForm` pushes an undo
   snapshot, consecutive form-only snapshots coalesce (so a six-keystroke rename is one undo), and
   `restore` skips the re-parse and the `docVersion` bump when the XML is unchanged. `ScoreView`
   rebuilds the player's passes only when the *expanded pass list* differs, through a pure
   `samePasses(a, b)` exported from `form.ts` (a name or a verse-number change stops nothing at all).
   And `setPasses` **keeps the playback**: it rebuilds the timeline, and when the list up to the
   current position is unchanged it re-anchors at the same position and plays on, otherwise it
   re-seeks to the start of the pass the user touched and keeps the state it had. This is what makes
   "build the form by ear" true; the first draft of this plan claimed it while still stopping on
   every edit that changes the list, which is every edit that matters.
   The presets build on the sections that are there, and only invent them when the form is still the
   printed one.
2. **A repeat count on a pass.** `FormPass.times?: number` (absent = 1), expanded by `expandForm`,
   shown on the chip as `×2` with a stepper, written by `describePasses` as "Chorus ×2".
   `formFromPasses` folds a pass that repeats itself into one chip with a count, so the automatic
   form of *Vieni sul mar* reads the way a musician says it. Because `currentPass` indexes the
   *expanded* list (`player.ts:466`) while the chips index `form.passes`, the panel gets an explicit
   expanded-index → chip-index map for the "now" highlight; the same map fixes the latent case that
   already exists, a multi-range pass split into several chips (`form.ts:153`).
3. **Chips that can be built in any order**: on every chip *duplicate* (the fastest doubling),
   *insert after*, *remove*, and move; on every section *+ pass*, which now lands after the selected
   chip rather than always at the end. Verse numbers keep auto-incrementing, with a *number the
   verses* action that renumbers the verse passes 1, 2, 3 … in place.
4. **The form as one line of text.** The line the summary prints is also an input: a section name,
   an optional verse number, an optional `×n`, separated by spaces or `·`. A name is matched by its
   shortest unique prefix, and a name containing a space must be written in quotes — `nameSections`
   itself produces "Verse 2" (`form.ts:175`) and the panel allows any 20-character name, so the
   grammar has to say this rather than hope. Anton's form is then one paste:
   `V1 C×2 V2 C×2 V3 C V4 C×2 V5 C×2`. The field is only offered once a form exists (with no form the
   summary reads "m. 1–19", which is a description and not a sentence in this grammar); unknown names
   are named back in a message under it, and nothing is applied until the whole line parses.
   `parseForm` never creates a section — it only orders the ones that exist, and the panel says so.
5. **Sections on the sheet, with beat-precise edges.** A band per section over the measures it
   covers, drawn with the doubt layer's machinery, with its name at the start; in the panel a section
   row gains *starts here* / *ends here*, which take the selected note — so the boundary is chosen by
   clicking the first note of the chorus, and it can fall inside a measure. This is the expensive
   part of the plan and it is specified in full in step 5 below.
6. **The panel says where the form came from** ("from 2 repeat signs and 1 lyric row"), and, when
   several verses are played over a page with one lyric row, one line of help: the other verses can
   be typed in the lyrics panel and they need no padding.

What this is not: a volta, D.C., Fine or coda editor (backlog; the form panel is where their result
would land anyway), a redesign of the score page (backlog), a form shared between scores, or
multi-range sections — a section stays one contiguous slice and a pass one section.

## The beat-precise edges, in full

The first draft put the onsets on `Range` and said the player would "copy only the steps inside the
slice". Both are wrong in detail, and the detail is the whole cost of the item.

- **The type.** The panel edits `Section` (`form.ts:15`), not `Range` (`form.ts:13`); both carry
  `fromOnset?` / `toOnset?` (whole notes from the measure start, the player's unit), and
  `expandForm` copies them across. The section key `` `${r.from}-${r.to}` `` in `formFromPasses`
  (`form.ts:150`) and in `nameSections` (`form.ts:172`) must include the onsets, or two different
  slices of the same measures collapse into one section.
- **The timeline.** `setPasses` (`player.ts:148`) copies the steps of the slice and advances by the
  slice's length. A melody note or an accompaniment pulse that *covers* the slice start is clamped to
  it, not dropped: `accompByMeasure` holds pulses relative to the measure start (`player.ts:136`), so
  a chorus beginning on beat 2 would otherwise lose the chord struck on beat 1 — Anton exactly. A
  note ringing past `toOnset` is cut there, and `totalWholeNotes` (`player.ts:163`) follows.
- **Where the slice is remembered.** `occurrences` reconstructs a measure's origin by subtracting the
  first step's in-measure offset (`player.ts:186`); on a sliced measure that origin lands before the
  pass and `positionOf` (`player.ts:202`) and `window` (`player.ts:213`) both go wrong — `window`
  also adds a whole `measureDuration[to]` past a sliced end. So the slice is recorded, not
  recomputed: `Step` (`player.ts:27`) gains the pass's start time, and `occurrences`, `positionOf`
  and `window` read it.
- **A note that belongs to two passes.** Once a printed measure is split between two sections,
  `positionOf` must choose by onset, not by measure (`player.ts:206` uses the full measure duration
  today), or click-to-play (`ScoreView.tsx:266`) and the re-seek after an edit (`ScoreView.tsx:162`)
  land in the wrong pass. Rule: the occurrence whose slice contains the note's onset, then the one
  that holds the current position, then the next, then the first.
- **The loop range stays whole measures** (`LoopRange`, `player.ts:20`, the inputs at
  `ScoreView.tsx:361`). Rule: a loop from measure *a* to *b* starts at the first occurrence of *a*
  whatever its slice and ends at the end of the last slice of *b* in that pass run.
- **`remapForm` cannot clamp the onsets**: its callback is `(m: number) => number | null`
  (`form.ts:203`) and knows nothing of the new measure's length, so the clamp happens where the
  durations are known — in `expandForm` against the measure count, and in the player against
  `measureDuration`.
- **`drawSections` is not 40 lines.** `measureBox` returns whole-measure boxes (`sheet.ts:114`), so a
  beat-precise edge needs the staff-entry x (`sheet.ts:42`), and a section crossing a system break
  needs one band per system row. Call it 90.
- **The cheaper path, weighed and not taken.** `splitMeasure` already exists as an editor command
  with the right remap (`editor/commands.ts:21`, `score/edit.ts:428`, and it requires the first note
  of the new measure, which is the upbeat), and `remapForm` already follows it (`session.ts:184`): it
  makes whole-measure sections exact at zero player cost. It is not the default because it prints a
  barline the page does not have and leaves two measures the check layer flags as underfull, which
  pollutes the review workflow the editor is built on. It stays the escape hatch if step 5 overruns,
  and the panel's help names it.

## Validation of the plan

**Complexity.** Not frontend-only: `validate_form` rebuilds every dict key by key
(`backend/partition_player/review.py:49`), so `times`, `fromOnset` and `toOnset` would be silently
stripped on save and the form would revert on reload — about 15 lines there (accept and bound the
three fields) and an update to the shape assertions in `backend/tests/test_api.py:158`. Frontend:
`form.ts` gains `times`, the onsets, `samePasses`, `parseForm` and the section-key change — about 140
lines and about 140 of tests; `player.ts` the slice, the recorded pass start and the clamping — about
110, the delicate part; `session.ts` the coalesced snapshot and the cheap restore — about 20;
`ScoreView.tsx` the `samePasses` guard and the bands — about 50; `Editor.tsx` the chip actions, the
stepper, the text line, *starts here*, the highlight map — about 170; `editor/sheet.ts`
`drawSections` — about 90; `form.bench.ts` the edit-distance columns — about 40. No new dependency.

**UI/UX.** The panel keeps its three rows and gains one: *Presets*, *Sections*, *Order*, and under
them the text line, which is the summary made editable — one thing to learn, not two, and the path
for anyone who knows the song, while the chips stay the path for anyone who does not. Doubling gets
the shortest gesture (the chip's stepper, or *duplicate*). The sheet is the reference for section
edges: the bands make a wrong boundary visible instead of arithmetic. Anton's 14 passes, counted
honestly and in the order that works (`parseForm` cannot create a section, and neither can *Chorus
starts here* before a Chorus exists): set the verses to 5, click *Chorus after every verse* with
*chorus twice* — that creates both sections and ten passes — then click the first chorus note and
*Chorus starts here* to move the boundary onto the upbeat, then one click on the third chorus to take
it back to one. Six interactions, undoable, with the music playing throughout. A phone keeps the same
rows; the order row scrolls sideways at that width rather than wrapping into a wall (the page
redesign in the backlog is the broader fix and is not pulled in here).

**Correctness.** `times` and the onsets are additive and optional, so every saved form and every
`bench/songs/leadsheets/*.form.json` still loads and still means the same thing; a form written by
the new panel and read by an old build loses only the doubling. The player is the risk, and the
slice is applied in one place (the measure loop of `setPasses`) with the pass start recorded on the
step, so `occurrences`, `positionOf`, `window` and the cursor path all read one number instead of
recomputing it. A section whose edges fall in the same measure with no note between them, or whose
onset lands past the last note, collapses and is dropped at expansion rather than producing a
zero-length pass. The undo timeline stays consistent because the form now travels in the snapshots it
was already part of.

**Testing.**

- *Unit* (vitest, `src/**/*.test.ts` only — the config includes no `.tsx` and the project has no
  testing-library, so anything to be tested must be pure and live in `form.ts` or `player.ts`, not in
  a component): `times` through expansion and description; `samePasses` on the rename, verse-number
  and reorder cases; `parseForm` on the Anton line, prefixes, a quoted two-word name, `x2` and `×2`,
  an unknown name, an empty line, and round-tripping `describePasses`; `formFromPasses` folding,
  which also rewrites the expectations at `form.test.ts:86`; the section key with onsets; presets
  built on existing sections; a pre-change form (no `times`, no onsets) still expanding as before.
- *Player*: `occurrences`, `window` and `stepIndex` are private and `window` is only reachable
  through `play()`, which starts Tone and fetches the Salamander samples (`player.ts:240`); the slice
  arithmetic is extracted into a pure exported function taking the printed steps and the pass list,
  and that is what the tests drive (step times, total length, a clamped covering chord, a note cut at
  `toOnset`, `positionOf` for a note in the second of two slices of one measure, the loop window over
  a sliced end).
- *Backend*: `validate_form` keeps the new fields, bounds them (`0 ≤ onset < measure length` is not
  knowable there, so bound against a sane ceiling and let the browser clamp), and refuses a malformed
  one; the existing assertions at `test_api.py:158` updated.
- *Session*: "edit a note, set a form, undo" and "undo a rename in one step", with fake timers or
  `dispose()` so `touch()`'s 1200 ms autosave never reaches `fetch` (`session.ts:240`).
- *Regression*: `npm run bench:form` — the numbers must not move **because of this plan**; the
  baseline `bench/out/form.txt` is captured before the first commit and re-baselined after the OSMD
  upgrade lands, since `defaultPasses` drives OSMD internals that the upgrade can move.
- *Browser*: Anton built both ways (chips and the pasted line), played through to hear the doubled
  choruses and the chorus starting on its upbeat; a form edit while the music plays, which must not
  stop it; undo of a form edit and of a note edit made before it; a score whose form was saved before
  this change; at desktop width and at 400 px.

**Impact on what exists.** `review.json` gains two optional fields inside the form (old files load
unchanged); the API contract gains them too. The editor, the readings dialog, the lyrics panel, the
chords and the pipeline are untouched. The 21 pages the automatic form already gets right keep their
form. The benchmark truth files need no rewrite (`*.form.json` are expanded pass lists and
`form.bench.ts` only runs `defaultPasses`).

**Exposure to the OSMD 1.9.9 → 2.1.3 upgrade** (in flight in another session, branch `osmd-2`, which
touches only `package.json` and the lock file). Not exposed, and landable either way: step 1
(`session.ts`, `samePasses`), steps 2, 3 and 4 (`times`, folding, presets, `parseForm`, the chips,
the text line) and the backend. Exposed: step 5's `drawSections` and *starts here*, which read
`GraphicSheet.MeasureList`, `PositionAndShape` (`sheet.ts:43`, `sheet.ts:115`, `verses.ts:29`) and
the note onset from `ParentVoiceEntry.Timestamp.RealValue` (`sheet.ts:21`); the player's slice
consumes `measureStart` / `measureDuration` from `SourceMeasure` (`chords.ts:35`) and the printed
walk from the cursor (`player.ts:110`) — both verified identical under 2.1.3 by the other session (494
steps, five scores, byte-identical dumps) and re-confirmed here after the merge (4e3857c: `tsc`
clean, 31 tests green, `bench/out/form.txt` byte-identical, `exact 21 (35 %)`), so the arithmetic is
safe; only the drawing is new surface. Three 2.x changes to build around, none of which moves the
current corpus: staff lines snap to half pixels (`SnapStafflinesToCrispPixels`, default true), which
shifts y by about half a pixel and some systems up to 3.5 units on 11 of the 60 pages, so
`drawSections` must read its coordinates at draw time and cache no y between renders; 2.1.0 treats
text as a repeat instruction only when the whole text is the instruction, which feeds
`Sheet.Repetitions` and so the `FromWords` check in `defaultPasses` (`form.ts:58`); and 2.1.3 groups
a grace note after its main note into the main note's staff entry and cursor step, which changes the
printed step indexing on any score that has one — self-consistent, since the walk is rebuilt on every
load, but it is the step list the onset slicing indexes into.

## Steps

1. `session.ts`: the coalesced undo snapshot on `setForm`, the cheap `restore`; `form.ts`:
   `samePasses`; `ScoreView`: the guard on it. Session tests with fake timers.
2. `player.ts`: `setPasses` keeps the playback (re-anchor when the prefix is unchanged, else re-seek
   and keep the state), and the slice arithmetic is extracted as a pure exported function with no
   behaviour change yet, so it can be tested; its tests.
3. `backend/partition_player/review.py`: `validate_form` accepts and bounds `times`, `fromOnset`,
   `toOnset`; `backend/tests/test_api.py` updated. Lands before anything can save the new fields.
4. `form.ts`: `times` everywhere, `formFromPasses` folding, presets on the current sections with a
   `chorusTwice` option, `parseForm`; `Editor.tsx`: the stepper, duplicate, insert after, remove,
   move, *number the verses*, the text line, the expanded→chip highlight map; tests, including
   `form.test.ts:86` rewritten for the folding.
5. The beat-precise edges, in two parts. **5a**: the onsets on `Section` and `Range`, the section key,
   `expandForm` and the clamps, the slice and the recorded pass start in the player, `positionOf`,
   `window` and the loop rule; tests, no UI. **5b**: `drawSections` with the staff-entry x and one
   band per system row, *starts here* / *ends here* from the selected note, the bands toggled with
   the panel. If 5a overruns, stop there and let the anacrusis be solved with the editor's
   *Split measure*, which is named in the panel's help either way.
6. The provenance line and the help text (the other verses need no padding); `form.bench.ts`'s
   edit-distance columns; `bench/RESULTS.md` "Form" updated with them; browser check as above; README
   (*The form of a song*: the text line, the counts, the section bands), BACKLOG (the form follow-ups
   that stay: voltas, D.C./coda, looping a single pass); commit.
