# partition-player

Photograph a page of printed sheet music, get it back as MusicXML, and play it on a piano in the
browser with the cursor following the notes. CPU only, built to run on a small ARM VPS.

Decisions are recorded in `docs/adr/`. The engine benchmark that picked homr is in `bench/`.

## Layout

- `backend/` Python package `partition_player`: FastAPI API, a one-thread job runner, and the
  pipeline (preprocess, OMR engine, postprocess). CLI entry point `partition-player`.
- `frontend/` React + Vite + TypeScript: upload or camera capture, progress, score view with
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

CLI, one image in, MusicXML out:

```
backend/.venv/bin/partition-player recognize photo.jpg -o out/
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
`PP_ANTHROPIC_API_KEY` (optional lyrics spelling pass, off when unset),
`PP_JOB_TIMEOUT_S`, `PP_JOB_TTL_DAYS` (failed jobs only, default 7), `PP_MAX_SCORES` (default 500, oldest
scores beyond it are deleted), `PP_MAX_UPLOAD_MB`, `PP_MAX_SIDE_PX`, `PP_FRONTEND_DIR`.

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
re-renders the sheet. With `PP_ANTHROPIC_API_KEY` set, the recognized text of each line is also sent
with its band image to Claude Haiku for a spelling pass; the answer is used only when it keeps the
same syllables in the same places. The benchmark is `bench/lyrics/` (see `bench/RESULTS.md`).

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
  every verse*, with the verse count), sections over printed measure ranges, and the passes in
  order, each with the verse it sings. It is saved with the score under the same revision as the
  notes, follows the measures when one is split, merged, inserted or deleted, and *Automatic* puts
  the derived form back. In edit mode the Measure group has two repeat-sign toggles, so a sign the
  engine missed can be put on the page.
- **Playback on the unrolled timeline.** A click on a note plays the occurrence of its measure
  that holds the current position, else the next one; the loop range runs from the first occurrence
  of its first measure to the following occurrence of its last; the accompaniment follows the passes.

## Score library

Every finished job is a saved score with its own link, `/s/{id}`, listed on the home page with a
thumbnail and an editable name. There is no login: anyone who can reach the app can add, rename
and delete. To keep the disk flat, a finished job keeps the MusicXML, the recognized version, the
review copy of the photo (under 300 KB), the measure layout, the doubts, a small thumbnail and its
metadata (about 350 KB in all); the full-size upload and the engine's intermediate files are deleted
when the job ends.

## API

- `POST /api/jobs` multipart `file` (JPEG, PNG, WebP): returns the job, status `queued`.
- `GET /api/jobs/{id}`: status is `queued`, `preprocessing`, `recognizing`, `postprocessing`,
  `done` or `failed`, with a `message`, and `result` or `error`.
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
