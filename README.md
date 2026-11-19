# partition-player

Photograph a page of printed sheet music, get it back as MusicXML, and play it on a piano in the
browser with the cursor following the notes. CPU only, built to run on a small ARM VPS. A MusicXML
file you already have comes in through the same door and skips the reading entirely (plan 0010).

Decisions are recorded in `docs/adr/`. The engine benchmark that picked homr is in `bench/`.

## Layout

- `backend/` Python package `partition_player`: FastAPI API, a one-thread job runner, and the
  pipeline (preprocess, OMR engine, postprocess). CLI entry point `partition-player`.
- `frontend/` React + Vite + TypeScript: upload a photo, a camera capture or a MusicXML file, progress, score view with
  OpenSheetMusicDisplay rendering and piano playback (Tone.js sampler, own look-ahead scheduler)
  with tempo control, a loop over a measure range, a switch that writes the French note names
  (do, ré, mi…) over the staff, and the score editor (`src/score/` for the document and its
  operations, `src/editor/` for the session, the sheet mapping and the commands).
- `bench/` benchmark samples, ground truth, scorer and audio rendering.
- `docs/adr/` architecture decision records.

## Run locally

Backend (Python 3.11 or 3.12, [uv](https://docs.astral.sh/uv/)):

```
cd backend
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m homr.main --init        # downloads the OMR models once (about 180 MB)
.venv/bin/partition-player serve            # http://localhost:8000
.venv/bin/python -m pytest
```

Frontend (Node 22):

```
cd frontend
npm install
npm run dev      # http://localhost:5173, proxies /api to :8000
npm run build    # writes dist/, which the backend serves at / when present
```

CLI, one page in, MusicXML out — a photo to read, or a file to open:

```
backend/.venv/bin/partition-player recognize photo.jpg -o out/
backend/.venv/bin/partition-player recognize song.mxl -o out/
```

## Docker

```
docker compose up --build
```

The image builds for amd64 and arm64. Recognition data lives in the `pp-data` volume under
`/data/jobs/<id>/`. Production deployment on the main server: `deploy/README.md`.

## Configuration

All settings are environment variables with a `PP_` prefix: `PP_DATA_DIR`, `PP_ENGINE` (`homr`),
`PP_FALLBACK_ENGINE` (`none` or `audiveris`, which also needs `PP_AUDIVERIS_BIN`),
`PP_ANTHROPIC_API_KEY` (server key for Check with a model, off when unset; nothing is sent to a model unless a pass is asked for and confirmed), `PP_ANTHROPIC_LARGER_MODEL` (Sonnet by default: where a failed answer is retried once, and "Try harder"),
`PP_MODEL_MAX_SPANS` (spans per model pass on the server key, default 10),
`PP_JOB_TIMEOUT_S`, `PP_JOB_TTL_DAYS` (failed jobs only, default 7), `PP_MAX_SCORES` (default 500, oldest
scores beyond it are deleted), `PP_MAX_UPLOAD_MB`, `PP_MAX_SIDE_PX`, `PP_FRONTEND_DIR`.

### Model routes (Check with a model)

A route is a base URL, a key, a model name and a `vision` flag (can it read images). Two presets exist, and the
panel lets you choose between them; a route with no key is off, and a visitor can bring a key per request.

| Preset | Settings | Default |
|---|---|---|
| `anthropic` | `PP_ANTHROPIC_API_KEY` | Haiku, vision on |
| `deepseek` | `PP_DEEPSEEK_API_KEY`, `PP_DEEPSEEK_BASE_URL`, `PP_DEEPSEEK_MODEL`, `PP_DEEPSEEK_VISION` | `https://api.deepseek.com/anthropic`, `deepseek-flash`, vision off |

`PP_MODEL_ROUTE` (`anthropic` or `deepseek`) picks the route used when a request names none. DeepSeek is reached
through its Anthropic-compatible endpoint, so the same client serves both. On a route without vision, spans that
need a crop or a picture are refused with a reason; typed lyrics placement works on any route. Set
`PP_DEEPSEEK_VISION=true` only if the DeepSeek model you chose reads images (the larger `deepseek-v4-pro` does not).
`GET /api/model-routes` lists the routes with their model, vision flag and whether the server holds a key.

## PDF in, and a score of several pages

A PDF comes in at the same door as a photo and a MusicXML file, decided by its bytes (ADR 0009).
Its pages are rendered at 300 dpi and read one by one, and the results are joined into one score:
measures appended and renumbered, what is in force carried across the seam so a restated key or
brace is not drawn as a change, durations scaled where two pages count a quarter differently, and
the doubts, the layout and the pixel stage's evidence shifted by the pages before them. Up to 20
pages; each page keeps its own `review-N.webp` for the editor's photo strip.

What kind of PDF it is decides how its **words** are read, and the marks decide that, not the text —
a scan with an OCR layer glued under it looks like an engraving until you count its drawings. A
**scan** or an **outlined** page is rasterized and goes down the camera path. A **born-digital** page
keeps its objects, so no OCR model is loaded at all: the syllables are the file's own text, cut where
the engraver cut them, the hyphens and extenders are its thin rectangles, and the beams are recorded
for later. They are written into the same `geometry.json` the OCR would have filled, so the lyrics
and chord stages are untouched. Measured on a LilyPond page: 66 syllables, identical to the raster
path's, in 9.3 s against 14.2 s.

## Lines: an instrument each, and one that goes on underneath

Every staff of the page is a **line** (ADR 0008), and the *Played on* panel gives each one an
instrument over a stretch of measures — the same staff can be a flute for eight measures and a voice
after it, which is how a page that introduces its tune on a flute is engraved. The sounds are sample
sets fetched when they are first chosen (flute, clarinet, saxophone, trumpet, french horn, violin,
cello, harp, nylon guitar, organ, harmonium, xylophone), pinned at one commit of
[tonejs-instruments](https://github.com/nbrosowsky/tonejs-instruments) and thinned to at most sixteen
samples each; nothing is in the bundle or the image. The piano — the Salamander set the app has
always played — stays the default, the fallback when a set will not load, and what the chord
accompaniment plays. Both collections are CC-BY 3.0 and credited in the panel.

A line can also be told to **go on playing underneath the form**: *the flute goes on playing measures
1–8, from measure 9 to the end*. Its notes are tiled across the timeline on time rather than on
measures (a page that turns 6/4 for a bar would drift otherwise) and merged into the one timeline the
cursor, the practice loop and click-to-seek already follow, exactly as the chord accompaniment is.
The written-out score (*as played*) gains a part for it, re-barred onto the form's own measures, so
the file holds what was heard. The instruments and the loop are saved in `review.json` beside the
form; they are playback only and never touch the document.

## Chord symbols and accompaniment

On a lead sheet the chord names printed above the staff (Cm, F#m7, G7/B) are read after recognition
(ADR 0003): homr's staff geometry gives the band above each system, RapidOCR's detector finds the
text, and the recognizer's character probabilities are decoded under a chord grammar, so only a legal
chord can come out and nothing is written when the reading is not sure. Chords are stored as MusicXML
`<harmony>`, drawn on the sheet, and played as a simple piano accompaniment with separate melody and
accompaniment switches. Tokens that were seen but not accepted are listed under the sheet.
The benchmark is `bench/chords/` (see `bench/RESULTS.md`).

## Lyrics

The words printed under the staff are read and put under their notes (ADR 0004). The driver cuts a
band below every staff from the **uploaded photo at full resolution** (homr works on a downscaled
copy where the letters are too small), RapidOCR reads it with word boxes at two scales, and a small
lyric grammar turns the words into syllables: hyphens split words (attached or detached, and the
ones the OCR drops are found in the pixels), an extender line holds a syllable over the next notes,
a lone comma belongs to the syllable before it, "1." is a verse number. Each verse row is then
aligned to the score's notes by an ordered dynamic programme (a syllable may be dropped when it is
doubtful, a note may be skipped for a melisma), so a missed word never shifts the rest of the line.
The result is standard MusicXML `<lyric>`, drawn under the notes by OSMD. Rows that do not line up
with the notes (the chord line of the next system, a verse paragraph, a footer) are listed under the
sheet as "seen but not used", never written.

Text mistakes are fixed in the **Lyrics** panel under the sheet: one text field per verse in the
convention every notation program uses (`Lors-que nous é-tions`; `_` holds a syllable over the next
note, `*` skips a note). Saving rewrites only the lyric elements of the score, keeps the chords, and
re-renders the sheet. No model reads lyrics on its own: a key set on the server changes nothing until a pass is
asked for and confirmed in **Check with a model**, where the engine's doubtful stretches can be picked as spans.
The benchmark is `bench/lyrics/` (see `bench/RESULTS.md`).

## Check with a model

An optional step after recognition (ADR 0010): in the **Check with a model** panel you pick a staff
and a range of measures, paste the words, and a small model places the syllables under the notes.
Nothing runs until you have seen the number of calls and the estimated cost and pressed Confirm. The
result is a draft you read in the sheet, untick, and apply as one revision (one undo).

With no words, the same panel re-reads the **notes and chords** of a span (ticket 10): the engine's
doubts are listed strongest first and each can be ticked (strong ones are ticked already), or you
give a range. The model sees the notes as text, not the photo, and answers with the editor's own
operations (change a pitch or a length, delete or insert a note, a rest, a tie, a chord symbol).
Operations that do not apply are dropped one by one; the note operations of a measure stand or fall
together, and a measure that added up must still add up, a wrong one may not get worse. Clef, key,
time and the number of measures cannot change. Each measure's change shows the notes as they were
and as they would be, marked on the sheet, and plays like the rest of the draft.
Notes and chords are checked on the first part of the score only.

Three ways to run it, and what leaves the server in each:

- **Your own Claude Code session** (local, no API key, no server key). The app writes questions to a folder,
  your Claude Code session answers them, the app checks the answers. Nothing leaves your machine except
  what your own Claude Code session sends to Anthropic under your own account, as for any file you ask it to
  read; the server makes no model call and holds no key. See below.
- **Your own key on the hosted site.** Paste an Anthropic API key in the panel. It is held in the
  page's memory for the session, sent with the request, and never written to disk or logged by the
  server. Crops of the score and the words you pasted go to the provider; your key pays.
- **A key on the server.** The operator sets `PP_ANTHROPIC_API_KEY`; visitors need no key. The same
  data goes to the provider, and `PP_MODEL_MAX_SPANS` caps the spans of one pass (a pass over the cap
  is refused with the reason). A visitor's own key is not capped.

With no key set and none pasted the feature is off and nothing is sent anywhere.

### Through Claude Code (no API key)

```bash
# once: install the skill that tells a Claude Code session how to answer
mkdir -p ~/.claude/skills && cp -r skills/partition-player-model-pass ~/.claude/skills/
# (or, to use it only in this repository: mkdir -p .claude/skills && cp -r skills/partition-player-model-pass .claude/skills/)

# 1. write one bundle per span (measures counted from 0, inclusive; a words file places the words, no file checks notes and chords)
partition-player model-pass export <job> --span 0:0:7:words.txt --span 0:8:11 -o bundles/
# 2. in Claude Code: "answer the model-pass bundles in bundles/" -> it writes bundles/answers.json
# 3. validate and store the answers as a draft
partition-player model-pass import <job> bundles/answers.json
```

Each bundle holds the very prompt an API route would send, the slice of the score and, when the job has one,
the page photo. The import runs the answers through the same validators as the API routes: what does not hold
is dropped and printed with its reason. The draft appears in **Check with a model** like any other, is read
and applied the same way, and its readings are recorded with the route `claude-code` and the model `unknown`
unless the answers file names one (`"model"`). The job ids are those of the web app (`<data dir>/jobs/<id>`);
run the commands with the same `PP_DATA_DIR` as the server.

### Through Claude Code against a running site (a deployed one, or local)

The easiest way: give your Claude Code session the address of a score and ask it to improve it.

```bash
# once: install the skill for your user (a symlink keeps it in step with the repository)
ln -sfn "$PWD/skills/partition-player-fix" ~/.claude/skills/partition-player-fix
# only when the site sets PP_API_TOKEN: export PP_API_TOKEN=<the token>
```

Then in Claude Code: *"fix the readings of https://your-site/s/<id>"*. The skill's helper (`pp.py`) asks the site
for its questions (`POST /api/jobs/<id>/model-pass/export`: with no spans, the engine's doubts, the surest wrong
first; or spans and a note you give it), the session answers them, and the answers go back
(`POST .../model-pass/import`). The site validates them and stores a draft; you open the score, flip *as read* /
*as corrected* in **Check with a model**, untick what you disagree with and apply once. The session never edits
the score. A site that sets `PP_API_TOKEN` asks for it, as a bearer token, on these two endpoints only. What leaves
the site is the score text and the page photo, to your own Claude Code session.

## MusicXML in

Beside the camera there is a second door (plan 0010): a `.musicxml`, `.xml` or `.mxl` file is
opened as it is, with no engine, no chord OCR and no lyric OCR — the chords, the words, the voltas
and the beams are already in it. Which kind of upload it is, is decided by the bytes and the suffix,
not by the content type the browser guesses; a `.mxl` container is unwrapped through its
`META-INF/container.xml`; the score's name comes from the file's own title rather than its file name.

Nothing is repaired. Padding a short measure, unmerging a rest from a chord and moving a repeat
barline all answer something an engine does to a page and an author does not, so an imported document
is stored exactly as it arrived, and a measure that does not add up is recorded as information rather
than as a doubt. A measure shorter than its time signature is usually not an error at all: over the 60
authored files of the two song benchmarks, every short measure but two is either a pickup the file
marks `implicit="yes"` or one bar written in two pieces (`en_clementine` holds 2 + 1 quarters over its
measures 9 and 10 of 3/4). The live check in the editor knows both shapes and stays quiet about them —
it never sees raw engine output, which `postprocess` has already padded.

What an imported page has that a photographed one cannot: repeat endings. `es_alfonsina_y_el_mar`
arrives with its two voltas, and the automatic form plays *intro, verse 1, verse 2* without anyone
entering a section by hand — 34 printed measures, 45 as played.

## Song benchmark

`bench/songs/` is the real-song benchmark, and it scores the three stages of one page together: the
sung line, the chord symbols above it and the words under it.

- **`leadsheets.tsv`** — thirty songbook pages, which is what the product is for: one staff, chord
  names printed above, verses stacked below. Real songs (Brassens, *La Marche des Rois*, *Bésame
  mucho*, *Camptown Races*, *Die Gedanken sind frei*…) in French, English, Spanish, German, Italian
  and Swedish, one to eight verses, 10 to 56 chord symbols each. From
  [PDMX](https://zenodo.org/records/15571083), public-domain and CC0 MuseScore scores; the `.mxl`
  files are vendored in `bench/songs/leadsheets/`, so the set needs no download.
- **`voice_piano.tsv`** — thirty art songs with a written-out piano part, three staves to a system,
  from the [OpenScore Lieder corpus](https://github.com/OpenScore/Lieder) (CC0). Harder than the
  product's target, kept because it is where the staff-grouping defect shows. It has a second tier
  of ten **real IMSLP prints** the transcriptions were made from, each pinned to its measures by its
  printed words (`pin_scan.py`).

The transcription is the ground truth for notes, chords and syllables alike: one page of each song is
engraved with verovio (`make_pages.py`, the ground truth cut to exactly the measures of that page)
and degraded into a phone photo. `review.py` writes a page that puts the image next to what the
pipeline read from it, to look over what the numbers do not say.

## Note names

The score page has a **Note names** switch that writes the French name of every printed note
(do, ré, mi, fa, sol, la, si, with `b` or `#` for the alteration: `mib`, `lab`) on one row above each
system, clear of the chord symbols, so the space under the notes stays free for words. The names are
computed from the pitches of the rendered score and drawn into OSMD's SVG (`frontend/src/noteNames.ts`):
nothing is written into the MusicXML, the switch works while the piece plays, and transposing the
playback does not rename them, since they name what is printed. The choice is remembered in the
browser.

## Checking and correcting the score

Recognition is not perfect, so the score page says where to look and lets you fix it (ADR 0005).

- **Doubts.** While it pads and checks the engine's output, the pipeline records every measure that
  did not add up: shorter than its time signature (a rest was added), longer, a rest merged into a
  chord, the pickup. On the lead-sheet benchmark these flags point at 95 of the 98 wrong measures
  with 90 % precision (`bench/RESULTS.md`, "Doubts"). They are tinted on the sheet with a "?" badge,
  counted in the review bar ("4 places to check", previous, next, mark checked), and explained in
  words ("shorter than 3/4 by an eighth: a rest was added at the end"). A measure you edit counts
  as checked; the live check keeps flagging any measure that still does not add up.
- **How sure we are.** That flag is arithmetic, so it is blind to anything that changes no duration:
  a wrong pitch, a notehead too many inside a chord. A second, independent reading of the same print
  exists and used to be thrown away — the noteheads the segmentation stage finds, kept now in
  `evidence.json` — and where the two readings disagree the measure is marked at the quieter level
  **check**: a broken amber outline, no fill, and the disagreement in words. It is deliberately hard
  to earn. One reader disagreeing is worth nothing on its own; a stacked notehead off the staff grid,
  a page that is monophonic everywhere else, or a measure whose boundaries had to be estimated all
  argue against the doubt and silence it. There is no quieter level than `check`, because a mark
  allowed to be wrong is a mark that cries wolf (plan 0008, and `bench/RESULTS.md`, "How sure").
- **The photo.** A copy of the upload is kept at 2400 px on its longest side and under 300 KB
  (`review.webp`), with the position of every measure on it (`layout.json`, from the driver's
  staff geometry and barlines). With **Photo** on, the strip of the print the selected measure was
  read from is shown with the measure framed; click it for the whole page.
- **Two modes, one click.** The page opens in playing mode: a click on a note leads the playback
  there. While it plays, the sound continues from that note; paused, it resumes there; stopped, the
  cursor moves there and Play starts from it (Stop forgets it). **⏮ Start** (or Home) goes back to
  the beginning of the range, without a break when playing. **Edit the score**, in the toast above
  the sheet (shown only when there are places to check) or at the end of the sheet, enters edit
  mode: the frame around the sheet turns amber, the review bar and the toolbar appear, and a click
  selects the note *and* leads the playback there, so Space plays the passage being corrected;
  after an edit the playback position goes back to the selected note. **Done** (or Escape with
  nothing selected) saves what is pending and goes back to playing mode.
- **Other readings.** Hearing that a note is wrong is easier than knowing what to change it to.
  Double-click a note (in either mode), or select it and press `o` or **Other readings** in the
  toolbar, and a dialog lists what the engine may have misread it as (ADR 0006): the durations a
  dot or a flag away, the pitch a step or two off, the other accidentals, an octave, a rest, no
  note, two notes instead of one; on a measure that does not add up (or was padded by the
  pipeline), the single change on any of its notes that makes it add up, ranked first. The strip of
  the photo is framed on the measure at the top; every reading is engraved on its own with the
  changed note marked, described in the toolbar's words ("dotted quarter instead of quarter",
  "measure adds up"), and has **Play** (the previous measure, then the measure read this way, with
  the accompaniment) and **Use**, which applies it as an ordinary undoable edit and keeps the dialog
  open for a second correction. It is a closed list of the benchmark's confusion kinds, computed in
  the browser with no model; an error of another kind still needs the toolbar.
- **The editor.** In edit mode, click a note or a rest on the sheet (a finger works). The toolbar under the sheet
  changes its pitch (a step, an accidental, an octave), its length (whole to thirty-second, dot,
  tie to the next note of the same pitch), turns it into a rest and back, inserts a note or a rest
  before or after it, deletes it; on its measure: fill the missing length with rests, split the
  measure at the selected note, merge it with the one after it, insert or delete a measure; on the
  score: time signature, key signature and clef from that measure on; the chord symbol on the
  selected beat (`Cm`, `F#m7/A`, empty to remove). Keyboard: ↑ ↓ pitch, Shift+↑ ↓ octave, − 0 +
  accidental, 1…6 length, `.` dot, `t` tie, `r` rest, `a` `b` insert after or before, Del, `f` fill,
  ← → move along the voice, `n` `p` next and previous place, `c` checked, Space play, Ctrl+Z / Ctrl+Y.
  Tuplets, grace notes and beams are kept as they are. Lyrics stay attached to their notes and are
  edited in the Lyrics panel as before; a deleted note loses its syllable, which the panel shows.
- **Saving.** Every change is saved by itself a second later, as the whole document, with the
  revision it was edited from; the server validates it, recomputes the statistics and refuses a
  save made from an outdated revision (another browser, or the lyrics panel, changed the score in
  between), in which case the page says to reload. **Revert** puts the recognized version back
  (`original.musicxml`). Scores recognized before the editor existed have no photo and no recorded
  doubts; the live check and the editor still work on them.

## Playing a song the way it is sung (plan 0004)

A songbook page is not played in the order it is printed: the verses are stacked under one line of
notes and the chorus is engraved once. The score page plays a **list of passes** through the printed
measures, shown above the sheet ("Played as: Verse 1 · Chorus · Verse 2 · Chorus…"), with the pass
being played highlighted.

- **Automatic form.** The pipeline keeps the repeat signs the engine read (an "i" doubt marks them),
  and the browser expands them with OSMD, each repeat played once per lyric row under it. Then the
  songbook rule: on a page without repeat signs, or when three or more verses are stacked and a
  single-lyric part follows them, the page is sung in rounds, verse *k* then the chorus. Two stacked
  rows under a repeat are played as printed (a first phrase sung twice). On the song benchmark this
  gives the right measure order on 23 of 60 pages, the rest one edit away; the causes are in
  `bench/RESULTS.md`, "Form".
- **The words of the pass.** While verse 3 plays, the other rows of words are dimmed; a note with a
  single row (the chorus) keeps it.
- **Your form.** *Change* opens the panel: presets (*As printed*, *Once per verse*, *Chorus after
  every verse*, with the verse count and a *chorus twice* box), sections over printed measure ranges,
  and the passes in order, each with the verse it sings. A preset builds on the sections already
  there rather than replacing them. It is saved with the score under the same revision as the notes,
  follows the measures when one is split, merged, inserted or deleted, and *Automatic* puts the
  derived form back. In edit mode the Measure group has two repeat-sign toggles, so a sign the engine
  missed can be put on the page.
- **A pass played several times.** The chip's `×1` counts up on a click and back to once after four:
  a chorus sung twice each time round is one chip, `Chorus ×2`, not two.
- **The form in words.** The summary line is also an input: `V1 C×2 V2 C×2 V3 C V4 C×2 V5 C×2` is a
  whole song (a section's first letters are enough, quotes for a name with a space in it). It orders
  the sections that exist; it cannot make a new one, and nothing is applied until the line parses.
- **Sections on the sheet.** While the panel is open a coloured band runs over the measures of each
  section, named at its start, so a boundary is seen rather than counted. *Starts here* and *ends
  here* put a section's edge on the note last clicked — including inside a measure, for a chorus that
  begins on an upbeat: in *Anton, Yvan, Boris et moi* the chorus starts on beat 2 of measure 11, and
  every repeat of it then begins on that "An-", not on the downbeat after it.
- **Worked example — *Anton, Yvan, Boris et moi*, as it is sung** (five verses, the chorus twice
  between them except between verses 3 and 4, and twice again at the end; the chorus starts on the
  upbeat at the end of measure 11). On the score page, seven actions:
  1. *Change* on the "Played as" bar.
  2. Set *verses* to `5` and tick *chorus twice*.
  3. *Chorus after every verse* — two sections and the ten passes at once, the measures still guessed.
  4. In *In words*, type `V1 C×2 V2 C×2 V3 C V4 C×2 V5 C×2` and press Enter — the chorus between
     verses 3 and 4 is sung once.
  5. Click the "An-" note on the sheet (measure 11, beat 2: the first note of "Anton").
  6. *starts here* on the Chorus row, then *ends here* on the Verse row — both read that one note, so
     the verse ends on "…tourterelles." and every chorus begins on its upbeat.
  7. Check it by ear: Play. The "Played as" line reads
     `Verse 1 · Chorus ×2 · Verse 2 · Chorus ×2 · Verse 3 · Chorus · Verse 4 · Chorus ×2 · Verse 5 · Chorus ×2`.
- **Undo.** Changing the form is an ordinary undo step (a run of keystrokes in one field is one
  step), and the music does not stop while the form is edited: the playback carries over when the
  new list plays the same up to it, and otherwise moves to the pass just changed.
- **Playback on the unrolled timeline.** A click on a note plays the occurrence of its measure
  that holds the current position, else the next one; the accompaniment follows the passes. The
  measure range runs to the end of the form when its last measure is the last of the page (so Play
  plays the whole song, every verse and every chorus), and stops at the first stretch of that
  measure when the range is narrowed, which is what practising a passage asks for.
- **The page as played.** Beside `Download MusicXML — as printed` there is a second link, *as played
  (N measures)*, shown once the form makes the song longer than the page: the score written out in
  the order it is sung, with each verse's words under its own notes and no repeat sign left to obey.
  Anton's 19 measures come out as 145, fifteen of them one beat long, since its verse leaves measure
  11 on beat 2 and its chorus enters it there. Each pass opens a new system under its name ("Verse
  3", "Chorus"). It is written in the browser from the score on screen, so it carries changes that
  are not saved yet; it is an export and never becomes the score being edited, which stays the page
  the photo was read from (plan 0009).
- **Duplicate as played.** The same written-out score, kept instead of downloaded: the button beside
  those links saves it as a score of its own — *"<name> (as played)"* — and opens it. It goes back in
  through the MusicXML door (plan 0010), so the copy is read by the same code that reads anyone
  else's file, and it arrives with its own link, its own name, its own lyrics panel and a form of its
  own to play with; the page it was made from is left exactly as it is. Alfonsina's 34 measures
  become a 45-measure score with no repeat sign in it. A copy of a copy is already written out, so
  the button is not offered there.

## Score library

Every finished job is a saved score with its own link, `/s/{id}`, listed on the home page with a
thumbnail and an editable name. There is no login: anyone who can reach the app can add, rename
and delete. To keep the disk flat, a finished job keeps the MusicXML, the recognized version, the
review copy of the photo (under 300 KB), the measure layout, the doubts, a small thumbnail and its
metadata (about 350 KB in all); the full-size upload and the engine's intermediate files are deleted
when the job ends. An imported score keeps the same files minus everything that needs a photo, so it
costs a few tens of kilobytes and its row in the library shows a ruled tile instead of a thumbnail.

## API

- `POST /api/jobs` multipart `file` (JPEG, PNG, WebP, or MusicXML as `.musicxml`, `.xml`, `.mxl`)
  and optional `name` (for a client that already knows what the score is called, such as the browser
  duplicating a page as played; the file's own title does not override it): returns the job, status
  `queued`. `source` says which door it came through, `image` or `musicxml`.
- `GET /api/jobs/{id}`: status is `queued`, `preprocessing`, `recognizing`, `importing`,
  `postprocessing`, `done` or `failed`, with a `message`, and `result` or `error`.
- `GET /api/jobs/{id}/score.musicxml`: the result once `done`.
- `GET /api/jobs?limit=50`: the library, newest first. `PATCH /api/jobs/{id}` with `{"name": ...}`
  renames; `DELETE /api/jobs/{id}` removes; `GET /api/jobs/{id}/thumb.jpg` is the list thumbnail.
- `GET /api/jobs/{id}/lyrics` and `PATCH /api/jobs/{id}/lyrics` with `{"verses": [...]}`: the words.
- `GET /api/jobs/{id}/review`: doubts, checked measures, revision, layout, whether a photo is kept.
  `PUT /api/jobs/{id}/score` with `{"musicxml", "checked", "revision", "doubts", "form"}` saves an edited
  document (422 when it is not a usable score, 409 when the revision is stale).
  `POST /api/jobs/{id}/revert` puts the recognized version back. `GET /api/jobs/{id}/review.webp`
  and `GET /api/jobs/{id}/original.musicxml` serve the kept files.

## License

homr and Audiveris are AGPL-3.0; this project is AGPL-3.0-or-later. See BACKLOG.md for the open
question on how source is offered to users of a hosted instance.
