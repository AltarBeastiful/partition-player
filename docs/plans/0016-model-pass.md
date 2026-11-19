# Plan 0016: The model pass — spans, drafts, and a small model as a second opinion

Status 2026-11-19: **written, not started.** Decisions in ADR 0010 (read it first); terms in
`GLOSSARY.md`.

## The problem

The engine's output is good and its mistakes are few and known, but the user has to find and fix
them by hand, note by note. A small model could take the parts that read badly, and the user could
review what it did as one corrected version. The existing pass — `lyrics/polish.py`, Haiku, lyric
spelling only, silent when a key is set — shows the shape and also its limits: one kind of text, no
review, no cost line.

## Order of work

Each step ends with tests and something to try in the running app. The first slice is the cheapest
useful one, because the lyrics validator already exists in `polish.py`.

### Slice 1: lyrics, a lyrics source, API route

1. **Spans and bundles.** A `span` is `{staff, from_measure, to_measure}`. `pipeline/model/bundle.py`
   builds a repair bundle: the crop (from the review photo and measure layout the editor already
   keeps), the score slice, the task, the answer format. Test: a bundle for a doubt, a user span
   and a lyrics-source span, with no network.
2. **Routes.** `pipeline/model/route.py`: base URL, key, model name, `vision`, and the two presets
   (Anthropic, DeepSeek's Anthropic-compatible endpoint). One `ask()` replacing the one in
   `polish.py`. Test with a fake HTTP client, as `polish.py` is tested now.
3. **Lyrics validator.** Lift the structure check out of `polish.py` into `pipeline/model/validate.py`
   with rules 7a to 7e. The exact-letter check for a lyrics source is new. Tests: each rule fails
   on a crafted answer; whitespace and hyphen normalisation is the only slack.
4. **Drafts and stored readings.** The draft is a copy of the score with a change list (id, span,
   old, new, ticked, conflict). Stored in the job next to `review.json`; named in `load()` and
   asserted to round-trip through `PUT /score`. Rebase on hand edits (decision 6): a change on a
   place edited since the pass is unticked and marked.
5. **API.** `POST /api/jobs/{id}/model-pass` (spans, route, confirm), `GET` for the draft,
   `POST .../draft/apply` with the ticked ids. The cost line comes from spans times the bundle's
   token estimate, shown before the confirm. A key from the request is held for the call, not stored,
   not logged.
6. **Panel and review.** *Check with a model* panel (spans from doubts, from "this looks wrong",
   and "add lyrics" with text or image), then the draft in the ordinary sheet: *as read* /
   *as corrected* toggle, changes marked, change list with checkboxes, one Apply, one undo.
   Unticked changes appear in the other readings dialog labelled "model".
7. **Move the silent polish behind the setting.** `pipeline/run.py` stops calling it on every job;
   its job is now one kind of pass. The README line on `PP_ANTHROPIC_API_KEY` is rewritten.

Done when: the Anton photo plus a typed text of its words gives a draft whose letters match the
typed text exactly, the syllables sit under the notes the user expects by ear, and applying it is
one undo.

### Slice 2: notes and chords

8. **Patch vocabulary.** The answer format for notes and chords is a list of operations from
   `score/edit.ts`, applied to a clone and checked with `score/check.ts`, as ADR 0006 does for its
   candidates. Operations that throw are dropped.
9. **Validator rules 7a to 7c** for notes and chords, run in the backend on the MusicXML and in the
   browser on the clone so the draft shows exactly what apply will do.
10. **Spans from doubts** in the panel; the doubt level (plan 0008) sorts them.

### Slice 3: the benchmark and the choice of default

11. **`bench/model/`**: run the pass on the song benchmark's engine-flagged spans and the voice and
    piano set for Haiku, Sonnet and DeepSeek. Report notes fixed, notes broken after validation,
    validator rejections, cost and time per page, in `bench/RESULTS.md`. Gate: broken = 0. The
    maintainer listens to the Anton photo and the voice and piano set before the default is set.
12. **Default and escalation.** Haiku first, Sonnet on a failed validation or "try harder" on one
    span, unless the benchmark says otherwise. Whatever it says goes in the ADR's status line.

### Slice 4: the Claude Code route

13. **Runner.** `partition-player model-pass export <job>` writes the bundles; the skill tells a
    Claude Code session to read them and write answers; `... import <job> answers.json` validates
    and stores them with `route = claude-code`. Nothing in the core knows which runner it is.
14. **Docs.** README: the three ways to run it (Claude Code, your own key on the site, the operator's
    key), what leaves the server in each, and the DeepSeek preset.

## Not in this plan

- Clef, key and time signature changes by a model.
- A better image of the *music* as an input.
- Running a model on the whole page, or automatically on upload.
- Training or fine-tuning anything.

## Risks

- **Model patches that add up but sound wrong.** The validator checks that measures add up, not
  that the music is right; this is why everything is a draft and why the maintainer listens.
- **Cost surprises on the hosted site.** The confirm shows the estimate; the operator cap is a
  hard limit on spans per job.
- **DeepSeek without vision** cannot read crops: the panel disables those spans on that route, so
  its first use is lyrics placement and score-only checks.
- **The `review.json` trap.** New fields are silently stripped unless named in `load()`; step 4
  asserts the round trip.
