# ADR 0008: Lines — an instrument for each, and one that goes on under the others

Date: 2026-09-22
Status: Proposed (plan 0011)

## Context

The page that asked for it, photographed on 2026-09-22: *Auprès du ruisseau*, harmonisation Olivier
Bernard. Two staves from the first system to the last. Measures 1 to 8 are a flute melody over a
staff of whole rests; from measure 9 the same two staves are labelled *Vx. 1* and *Vx. 2* and sing
that same tune in canon, the second voice a measure behind the first, to the end (measure 19 is 6/4
for a bar and comes back to 4/4). Chord names sit over the voices.

Two things the app cannot do with it.

- **Everything sounds on a piano.** A flute line, a voice line and a chord accompaniment are one
  timbre, so nothing tells the ear which line is which — on a canon page, where the whole point is
  one tune against itself, that is most of the music lost.
- **The flute stops when the voices start.** It is printed once, eight measures, and never again;
  in performance it goes on underneath the singing. The app plays one order at a time and has
  nowhere to put a second.

What the player does today:

- **One sampler.** `new Tone.Sampler` with the Salamander piano, fetched from `tonejs.github.io`
  (`player.ts:364`). No sound ships in the bundle or in the image.
- **The staves are flattened.** `collect()` (`player.ts:202`) walks OSMD's cursor and puts every note
  of every staff and every part at a position into one list. The line is right there and dropped:
  `voiceEntry.ParentSourceStaffEntry.ParentStaff.idInMusicSheet`, with the printed name of the line
  in `ParentStaff.ParentInstrument.Name` for a document that has one.
- **An event knows two things about itself**: `track: "melody" | "accompaniment"` (`player.ts:24`,
  `:27`), which is exactly the two checkboxes.
- **One form, one timeline.** `Pass[]` (`form.ts:20`) laid out by `layPasses` (`player.ts:75`), and
  the cursor, the practice window (`windowOf`), click-to-seek and the written-out score
  (`expandScore`, `score/expand.ts:329`) all read their positions from that one line of time.
- **The precedent for a voice that is not on the page is already built.** The chord accompaniment
  makes its own events, they are merged into the same timeline, and they carry their own switch and
  their own velocity (`player.ts:110-118`). A line that goes on underneath is the same trick with a
  different source.

Where multi-part stands, since it decides what this can cost: `expandScore` walks **every** `<part>`
and slices them identically (`expand.ts:329-401`), so the written-out score of plan 0009 is not
part-0-only. The part-0 assumptions are in the editor (`editor/session.ts:95`, `score/edit.ts:91`,
`:393`, `:567`) and in the backend's measure count (`review.py:150`).

Measured on 2026-09-22, before deciding anything:

- **`github.com/nbrosowsky/tonejs-instruments`**: 20 sample sets (flute, clarinet, violin, cello,
  organ, harmonium, harp, guitar, trumpet, saxophone, xylophone…), served by jsDelivr from a commit
  that has not moved since 2022-05-07 (`622c2f1c32c8cfce4158ddc3eb26e518ddef37e5`). **Samples
  CC-BY 3.0, code MIT**, sources listed in the repository.
- **What a set costs**, fetched whole: flute 10 files / 1.7 MB (C4 to C7), clarinet 11 / 2.6 MB,
  violin 15 / 4.6 MB, organ 21 / 5.9 MB, harmonium 38 / 8.2 MB. The piano already in use is 21
  files of about 80 KB. So a thinned set is the same order as the piano the app downloads today.
- **There is no voice and no choir in the collection.** A sung line has no sung sound; harmonium and
  organ are the sustained stand-ins, and the piano stays the honest default.
- **A set's lowest sample matters.** The flute's is C4 and the lower voice of this very page goes
  under it; `Tone.Sampler` stretches the nearest sample down, which dulls it. The table has to carry
  each set's written range so the picker can say so.
- **`review.load()` (`review.py:37-43`) rebuilds its dict from four literal keys**, so any key it
  does not name is dropped at the next save. That is how the form's times and onsets were stripped
  once (plan 0008). Whatever this stores has to be named there in the same commit that writes it.

## Decision

1. **A line is a staff of the sheet.** Identified by `idInMusicSheet` (sheet-global, so it holds for
   a one-part two-staff page read from a photo and for a file with a part per line), named from
   `ParentInstrument.Name` when the document carries one and otherwise *Top staff*, *Bottom staff*,
   *Staff n* — or *Melody* when the page has a single staff, which keeps the word the switch has
   always used. Lines are not renamed and not reordered; nothing about the document changes.

2. **An instrument belongs to a line over a stretch of measures**, not to a line as a whole:
   `{ staff, from, to, instrument }`, one entry per line over the whole page by default. The canon
   page is the reason — the same staff is a flute for eight measures and a voice after it — and it
   costs one lookup at collect time. The picker shows one instrument per line and a *changes at
   measure…* that splits the range.

3. **Sound comes from sampled sets: pinned, thinned, lazy, with the piano as default and fallback.**
   The URL is pinned at the commit above. A set of more than 16 samples loads every second one, more
   than 32 every fourth (the collection's own `minify` rule), so no set costs much more than the
   piano does. A set is fetched when it is first chosen; until it is there the line keeps the sound
   it had, and a set that fails to load says so once and falls back to the piano. Each set carries a
   gain in the table, set by ear, because they are not level with each other.

4. **The switches become per line.** One row per line: on/off and its instrument. *Melody* and
   *Accompaniment* stay exactly as they are on a one-line page, which is every lead sheet the app
   has played so far.

5. **Parallel means: the form leads, and a line may go on underneath it.** One record:
   `{ staff, from, to, startAt, instrument }` — the measures `from..to` of that staff, laid end to
   end over and over, from the first time the timeline reaches printed measure `startAt` to the end
   of the form. For this page: *the flute goes on playing measures 1–8, from measure 9 to the end*.
   Its events are generated separately and merged into the one timeline, exactly as the chord
   accompaniment's are. The form itself is untouched: no section, no pass, no verse changes meaning.

6. **The tiling is laid on time, not on measures.** This page turns 6/4 for a bar, so a loop of whole
   measures cannot stay in step with the measures it runs under. The tiles are a slice list built by
   the arithmetic `sliceRanges` already uses, so a tile may be cut in the middle of a measure and the
   cut note is shortened there, the way the form's own cuts already shorten notes.

7. **The cursor, the practice window and click-to-seek keep the leading order.** What goes on
   underneath is heard, not followed: the cursor has one line to walk and this does not make a
   second. A practice loop over a window replays whatever the tiles put in that window, which is the
   same music every time round — that falls out of the tiles living on the timeline, and it is what
   practising a passage wants.

8. **The written-out score gains a staff for what goes on underneath, and a page with none exports
   byte for byte what it exports today.** `expandScore` already writes every part from one slice
   list; it learns to write a given part from *its own* slice list, and the under-line becomes a part
   of the output whose measures are the tiles, a cut tile written `implicit="yes"` exactly as plan
   0009 writes every cut measure. No feature of plan 0009 or plan 0010 is given up: a score without
   an under-line goes through the unchanged path, and *Duplicate as played* keeps working on it.

9. **It is saved with the form, and pinned by a round trip.** `review.json` gains `lines` (the
   instrument ranges) and `unders`; `review.py` validates their shape and bounds; `load()` names
   both keys and a round trip through `PUT /score` asserts they come back unchanged — in the same
   commit, for the reason recorded in the context.

10. **The samples are credited.** CC-BY 3.0 asks for it: one line in the page footer naming the
    collection and the licence, beside the piano's own (Salamander Grand Piano, CC-BY 3.0), which
    the app has been playing uncredited since the first day.

## Alternatives considered

- **Synthesized voices** (`Tone.Synth`, an FM flute). Nothing to download, no licence question, works
  offline — and it does not sound like a flute against a sung line, which is the whole request. Kept
  in mind as an offline fallback; the piano is the fallback that already exists and sounds right.
- **A General MIDI soundfont** (WebAudioFont, `smplr`, FluidR3). 128 instruments in one decision, and
  a much bigger surface: a new dependency, a new format, per-program loading, and sounds of uneven
  quality. Worth revisiting if more than a handful of instruments is ever wanted.
- **Self-hosting the samples** in the image. The deployment is a small ARM VPS (`deploy/README.md`)
  and the app fetches its piano from a CDN today; adding megabytes per instrument to the image buys
  only independence from jsDelivr, and can be done later without changing a decision here.
- **A form per line** — every line with its own `Pass[]`, the timeline as long as the longest. It is
  the general answer and it costs the cursor (no single line to follow), the practice window and the
  seek arithmetic (`windowOf` stops meaning one thing) and the export (parallel orders to write). The
  page that asked for this needs one line to go on underneath, not twelve independent orders.
- **Writing the flute into the document as a third part** — an edit rather than a playback setting.
  It would rewrite a page the user photographed to record something that is not printed on it, and
  the editor is part-0-only anyway. The export of decision 8 is where that document belongs: derived,
  downloadable, and never the page itself.
- **One instrument per line, no ranges.** Half the page: the flute staff would sing, or the voice
  would be a flute, because this print reuses the staff. The range costs a lookup.

## Consequences

- **No new dependency.** Tone.js is already there, the samples are URLs; the bundle does not grow and
  the image does not grow. What grows is what a browser fetches when the user picks a sound: 1.7 to
  3 MB once per set, cached by the browser after that.
- **The player gains a dimension.** An event carries its line, and there is a sampler per instrument
  in play rather than one for the page. Polyphony on a phone with three sets loaded is the thing to
  watch, and plan 0011 says where it is measured.
- **`review.json` grows two keys**, `review.py` two validators, and the round-trip test two
  assertions. The API does not change shape.
- **`ScoreView` gains a row**, which the redesign in `BACKLOG.md` will have to fold in; the other
  session working on PDF input (plan 0012) has been told.
- **The export gains a part** when an under-line is set, and is unchanged when it is not.
- **Not covered, and said so:** there is no sung sound to give a voice; a line is a staff, so
  cross-staff piano writing and two voices in one staff are one line; only one under-line is tested
  though the shape allows several; a transposing part still sounds at written pitch (plan 0010); the
  under-line is not drawn on the sheet, only heard and written into the export; and the instrument
  choice is playback, never notation — nothing in it touches the document the editor saves.
