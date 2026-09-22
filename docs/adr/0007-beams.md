# ADR 0007: Beams read from the print, kept as MusicXML beams, edited as links between notes

Date: 2026-09-19
Status: Proposed (plan 0006)

## Context

The sheet shows every eighth with its own flag. homr's transformer has no beam in its vocabulary
(`homr/transformer/vocabulary.py`: a note is a kern duration, a pitch, a lift, an articulation, a
slur and a staff position), so its MusicXML carries no `<beam>` and no `<stem>`, and OSMD draws
what it is given. Beams are how a reader sees the beat, and on a song page they follow the
syllables (one beam over "ri-vière", a flag on "la"), which no rule reproduces. The editor's
readings (ADR 0006) engrave candidate measures from the same document, so they show flags too.

What was measured on 2026-09-19 (a scratch probe on `bench/samples/anton_yvan_boris_photo.jpg`, a
real phone photo, and three lead-sheet benchmark pages, photo and clean):

- homr's segmentation net labels noteheads, stems, clefs and keys, and staff lines; its "symbols"
  class is nearly empty (2,640 pixels on the whole photo). **Beams are in none of its masks.**
- On the page pixels, beams are the thickest ink besides noteheads. Binarize the working image
  (homr's 1920 px wide copy), open it with a square of 0.3 interline: staff lines (1 to 2 px), stems
  and slurs go, beams, noteheads and bold text stay. Subtract the dilated notehead mask. A remaining
  component that meets two or more stems is a beam; text meets none. homr's stem boxes are fragments
  cut by the staff lines, so the stem is taken as the column from the notehead, 0.5 to 4.5 interlines
  away in the stem's direction (which homr records).
- That rule found **17 of 18** beam groups on the phone photo, **23 of 26, 22 of 23 and 27 of 28**
  on the benchmark pages, with **no false group**, in 0.3 s a page. The misses are a stem the
  segmentation dropped (a low note under a ledger line) and one group per page on the degraded copies.
- Image notes to score notes: the chord stage's mapping (ADR 0003): a run of measures per system
  from the transformer's count, the measure boundaries from the barlines, and inside a measure the
  k-th notehead is the k-th note onset when the counts agree. On the lead-sheet photo pages the
  counts agree in **775 of 816 measures**.
- OSMD 1.9.9 renders `<beam number="1">begin / continue / end</beam>`, and draws the second and
  third beams and the partial beams (hooks) itself from the durations inside a group. Its `autoBeam`
  option beams every unbeamed eighth by rule.
- The editor is a MusicXML DOM (ADR 0005) and `NOTE_ORDER` already places `<beam>`, but no operation
  touches it: a beamed eighth made a quarter would keep its beam, a deleted note would leave a chain
  without an end.
- The benchmark's ground truth (MuseScore transcriptions) carries beams and verovio engraves them,
  so scoring beams needs no new data.

## Decision

1. **Beams come from the print, found in the driver.** `pipeline/beams/detect.py` runs inside
   `homr_driver.py`, where the masks and the staff geometry are in memory: the thick-ink opening
   above, restricted to each staff's zone (five interlines above and below), components at least
   1.2 interlines wide that meet two or more stems of that staff. Along each stem's column the ink
   runs inside the component give the beam count (one: eighth, two: sixteenth, three: thirty-second),
   and a run that does not reach the next stem is a stub with its side. Written to `geometry.json`
   per staff: `beams: [{noteheads: [[x, y], …], levels: [n, …], stubs: [side | null, …], box}]`.
2. **Beams are placed on the score's notes by the chord stage's mapping and written as standard
   MusicXML.** `pipeline/beams/place.py`: per system and measure, when the notehead count equals the
   measure's note-onset count, the groups become `<beam number="1">begin / continue / end</beam>` on
   the events (every note of a chord gets the same), `number="2"` and `"3"` from the levels,
   `forward hook` / `backward hook` from the stubs, and `<stem>` from the majority direction of the
   group's stems so it hangs like the print. A group that would cross a rest, or a note the
   transformer read longer than an eighth, splits the group there and records a doubt of kind
   `beam` ("the print beams this note with its neighbours: an eighth or shorter?"). Measures whose
   counts disagree, and scores without geometry, get **rule beaming** (`pipeline/beams/rule.py`):
   eighths and shorter grouped within the beat (a quarter in x/4, a dotted quarter in x/8), broken
   at rests; `review.json` says per measure whether its beams are `print` or `rule`, and the editor
   says so in the place's words.
3. **In the document a beam is a link between a note and the next, and every edit repairs the
   chains.** The level-1 chain is the model: `begin` and `continue` mean "joined to the next note of
   the voice", `end` means "joined to the previous only". `frontend/src/score/beams.ts` has a pure
   `normalizeBeams(measure)` that rebuilds every `<beam>` of a measure from the links and the
   durations: a note longer than an eighth, a rest or a grace note leaves the chain (which splits), a
   chain of one loses its beam, levels 2 and 3 follow the durations, hooks point to the neighbour
   that carries the lower level, unless a stub from the print is kept. Every operation of `edit.ts`
   that changes a length, turns a note into a rest or back, inserts, deletes, splits or merges ends
   by normalizing the measures it touched. An inserted note inherits the link of the note it was
   made from; a deleted middle note leaves its neighbours joined. So the readings dialog engraves
   each candidate with the beams it would have after the edit: a sixteenth reading shows its second
   beam, a quarter reading leaves the group.
4. **One editing gesture: join or break.** A *Beam* section in the toolbar: **Join next** (key `j`)
   toggles the link between the selected note and the next note of its voice, disabled when either
   cannot carry a beam; **Beam by beat** applies the rule to the measure, and under *Score* to the
   whole score, which is how scores recognized before this decision (no beams at all) catch up.
   Levels, hooks and stem directions are derived; nothing else is asked.
5. **Beams are evidence.** The beam count read on a note (per measure in `review.json`, by event
   index) ranks the readings dialog's durations: with two beams on the print, "sixteenth" comes
   before "quarter". The `beam` doubt of decision 2 is scored on the benchmark before it counts as
   more than information (it is an `info` doubt until then).
6. **OSMD's `autoBeam` stays off.** The document carries its beams; nothing is beamed on the fly.

## Alternatives considered

- **OSMD's autoBeam alone** (one option, no pipeline work). Beams by rule, never by the print: a
  single eighth printed with a flag, a beam that follows the words across the beat, would be drawn
  wrong, and there would be nothing to fix since the XML has no beams. Its logic survives as the rule
  fallback only.
- **Beams from homr's transformer.** No token; retraining is out of scope (ADR 0002).
- **Audiveris.** It writes beams, but it is the fallback engine, not deployed, and its beams come
  with its own note reading, which cannot be laid onto homr's notes.
- **A learned beam detector** (a segmentation class or a small box detector). The pixel rule finds
  89 of 95 groups on the probe with no false one; a model is for a class of print it misses (thin
  beams in old engravings), if the benchmark shows one.
- **music21's beam maker** (BACKLOG). Rule beaming only, and a heavy import on every job; the rule is
  fifty lines of the standard library.
- **Links stored outside MusicXML** (a side file of note pairs). The document would not carry its
  look; excerpts, exports and OSMD read MusicXML beams already.

## Consequences

- No new dependency and no engine change: OpenCV and numpy do the detection, homr stays at 0.7,
  OSMD at 1.9.x. The driver takes 0.3 s longer per page; `geometry.json` grows by a `beams` list per
  staff; `run.py` gains a beams stage between chords and lyrics; `review.json` gains a per-measure
  `beams` entry (source and evidence); the stats gain the group count and the share of measures
  beamed from the print.
- The frontend gains one pure module with tests, a toolbar section and one key; about ten
  operations of `edit.ts` end with a call to the normalizer. Excerpts, previews, the player, the
  note names, the form and the lyrics panel are untouched (a lyric rewrite keeps the beams, as it
  keeps every other note child).
- Vocal beaming that follows the syllables is what the print path keeps and the rule path loses;
  the benchmark table says how many measures each path gets.
- Not covered, and said so: beams over rests (the group splits at the rest), cross-staff beams on
  piano pages (a component meeting stems of two staves is dropped), tremolo bars (thick, two stems:
  guarded by the notes having to be eighths or shorter, measured on the voice-and-piano set),
  feathered beams.
