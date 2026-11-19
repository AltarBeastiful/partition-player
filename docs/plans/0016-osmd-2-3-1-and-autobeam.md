# Plan 0016: OSMD 2.3.1, then autoBeam for scores with no beam markup

Status 2026-11-19: both steps done, as two commits. Nothing deployed. Frontend only.

## Step 1: OSMD 2.1.3 to 2.3.1, pinned exactly

`package.json` now says `"opensheetmusicdisplay": "2.3.1"` (no caret), lockfile updated.

What the changelog of 2.2.0 to 2.3.1 holds that could touch us, and what we found:

- 2.3.0 renamed SVG ids and classes (`osmd-` prefix, unique measure and staffline ids) and merged
  single-child groups. No selector of ours names an OSMD id or class: the overlays select only
  their own layer classes (`verses.ts`, `noteNames.ts`, `editor/sheet.ts`), and hit-testing goes through
  `GraphicSheet`, not the DOM. Nothing to change.
- The private fields we read (`container`, `Drawer` backends, `GraphicSheet`, `Sheet`, `EngravingRules`)
  are all still there; `tsc`, the 128 tests and the build pass unchanged.
- Chord symbols keep a minimum distance of 1.5 units above the staff (was 0.6): chords sit slightly
  higher, visible in the before/after screenshots, nothing overlaps. Dynamics and part names move up a
  hair (2.3.1). Neither matters to the page.
- The removed methods (`VoiceEntry.createVoiceEntriesForOrnament`, `KeyInstruction.getAlterationForPitch`,
  the WebGL skyline) are not used by us.

Checked: the 128 tests, `tsc` and the build; the `defaultPasses` tests on the benchmark truth (voltas
and endings expanded as before); Anton's expanded score (145 measures) loaded and rendered by OSMD 2.3.1
in jsdom (145 source measures); four benchmark pages (Anton, two lead sheets, one voice and piano page)
engraved with 2.1.3 and 2.3.1 in headless Chrome, same layout and same line breaks.

`package-lock.json` shrank because OSMD 2.3.1 dropped the optional `gl`/node-gyp chain (`npm ci`
verified). Click-to-play, edit mode and the doubt markers were not exercised in a live app.

## Step 2: autoBeam, only for a score with no beam elements

homr writes no beams (plan 0006), so every eighth note on a read page prints with a flag. OSMD's
`autoBeam` groups them. `src/score/beaming.ts` is the one place that decides: `chooseBeams(osmd, xml)`
sets `autoBeam` to true only when the MusicXML contains no `<beam>` element, and the score view (first
load and reload after an edit) and the readings dialog call it before `load`. A score that carries
beams, an import fixed in MuseScore for example, is drawn as written; an import with none is treated
like a photo. The pixel beam rule of plan 0006 is neither removed nor changed (ticket 05).

What 2.2 and 2.3 changed about autoBeam: nothing in their release notes or in `CHANGELOG.md` mentions
it (the only autoBeam entry in the file is older, from 2.0: `AutoBeamNotes` no longer beams tab notes).
The 2.2 and 2.3 beam entries concern beams read from the XML (a `<beam number="2">` listed first), slurs
near beams, and, new in 2.3.1, cross-staff beams (`RenderCrossStaffBeams`, on by default), which do not
apply to autoBeam on a single staff. The option's own doc string says it beams "notes that don't have
beams set in XML", which is why the per-score decision is ours to make explicitly.

Test (`src/score/beaming.test.ts`, at the seam of a real OSMD render in jsdom, counting `.vf-beam`
in the SVG): a measure of eight eighths with no markup is drawn with beams; the same measure with two
groups marked in the XML is drawn with exactly those two. The test fails if `chooseBeams` always
turns autoBeam off or always on.

By eye (headless Chrome, 2.3.1, before and after, screenshots kept outside git): Anton, *Clementine* and
*Wiegenlied* read as on paper, eighths in groups, the dotted-eighth and sixteenth pairs beamed. Lyrics
and chords stay under and over the same notes. One side effect: beamed notes are narrower than flagged
ones, so OSMD re-breaks the systems (Anton goes from four lines to three) and a few syllables sit close
("Sous le nez des"). That is OSMD's spacing, not a shift.

## Verdict

autoBeam wins on the pages tried: it gives the beaming the pixel rule was meant to find, with no
beam errors seen on three pages. It is not yet a verdict on the pixel rule: that is ticket 05's, which
should also weigh a beamed page against the pixel rule's ~94 % of groups on a larger sample, and the
fact that autoBeam follows the meter and not the printed beaming.
