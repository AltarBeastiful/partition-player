# ADR 0010: The model pass — chosen spans re-read by a small model, delivered as a draft, never applied unasked

Date: 2026-11-19
Status: Proposed (plan 0016)

## Context

The engine's reading is measured and its mistakes are few in kind (`bench/RESULTS.md`). Two
things already exist at the edge of what it gets wrong: the doubts (ADR 0005, plan 0008), which say
where to look and keep the photo strip of each, and `pipeline/lyrics/polish.py`, which sends one
lyric band and its OCR text to Haiku when `PP_ANTHROPIC_API_KEY` is set and accepts the answer only
if its structure is unchanged. `BACKLOG.md` ("Correction workflow via small LLM API") has asked for
the general version since v1: a cheap model as a second opinion, benchmarked before it is trusted.

What the user asked for (2026-11-19): an *optional* pass after the first recognition and the user's
review, on the parts that read badly — flagged by the engine, flagged by the user as incoherent, or
given a better source (the lyrics alone, as a picture or as text, because lyrics are what is easy to
find online) — runnable locally through Claude Code or on the hosted site, with the corrected version
reviewable in one go rather than fix by fix.

The decisions below are the answers to a design interview with the maintainer; the terms are in
`GLOSSARY.md` (span, model pass, lyrics source, repair bundle, model route, reading, doubt).

## Decision

1. **The unit is a span, never the page.** One staff over a range of measures, with its photo crop
   and the MusicXML slice. A pass touches notes, chords and lyrics inside spans. Clef, key and time
   signature are out: they change the whole score, not a span.
2. **Three ways to make a span, one panel.** The engine's doubts (selectable), "this looks wrong" on
   a measure range in edit mode (with an optional note to the model), and "add lyrics" on a staff
   with a **lyrics source**. All three land in one *Check with a model* panel that lists the spans,
   the number of calls and an estimated cost, and runs only after a confirm.
3. **A lyrics source is authoritative text; the model only places it.** Typed text or an image
   read as text, covering lyrics only. The validator checks the letters exactly (decision 7e): the
   model decides which syllable goes under which note, never what a syllable says. A better image of
   the music is deliberately not an input of this version.
4. **The answer is a patch, not a score.** Notes and chords come back as operations in the editor's
   own vocabulary (`score/edit.ts`); lyrics come back in the notation `polish.py` already uses,
   with a note index per syllable. Nothing outside the span can change because nothing outside the
   span can be named.
5. **Everything arrives as a draft.** All validated changes of one pass are applied together to a
   copy of the score, kept beside the current revision as a *model draft*. The user opens it in the
   ordinary sheet and player, toggles between *as read* and *as corrected*, sees every change marked
   with its old value, and applies the draft as one revision (one undo). The change list has a
   checkbox per change, ticked by default; unticked changes stay as stored readings.
6. **A model never overwrites what the user did.** A change that touches a place edited by hand
   since the pass started is marked as conflicting, unticked, and not applied unless ticked on
   purpose. This holds for a lyrics source too: the placement is the model's guess, so it also comes
   as a draft, and only its letters are checked as exact.
7. **A validator stands between the model and the draft.** An answer is dropped, with its reason
   logged and never shown as a "bad" reading, unless: (a) it is a well-formed patch confined to the
   span; (b) no measure that added up before stops adding up, and broken ones do not get worse;
   (c) the measure count is unchanged; (d) lyrics keep the syllable count and breaks of the existing
   rule, unless a lyrics source was given; (e) with a lyrics source, the letters match it exactly
   after normalising only whitespace and hyphens. A failed answer goes once to the larger model,
   then is dropped.
8. **Model readings are stored.** Each one (span, route, model, time, status: proposed, accepted,
   rejected) is saved with the job, shown in the other readings dialog (ADR 0006) with a "model"
   label, and never deleted; rejecting hides it. A model that offers a better reading of a span
   only produces one more reading, applied when accepted.
9. **One model route is a configuration, and a route declares whether it can see.** Base URL, key,
   model name and `vision: true|false`. Presets: Anthropic (Haiku first, Sonnet on a failed
   validation or a manual retry) and DeepSeek through its Anthropic-compatible endpoint. The panel
   disables image-based spans on a route without vision; typed lyrics placement and score-only
   checks work on any route.
10. **Who holds the key.** On the hosted site the visitor pastes their own key, kept for the session
    and never stored or logged; a server key is opt-in (`PP_ANTHROPIC_API_KEY` or the route
    configuration) with a cap on spans per job. The button carries a one-line notice that crops of
    the score leave the server for the chosen provider. The lyrics polish that runs silently on
    every job when a key is set moves behind the same setting and becomes one more kind of pass.
11. **Locally, Claude Code is a runner, not a different feature.** The core builds the repair bundles
    and validates and stores answers; there are two thin runners over it: an API runner, and a
    Claude Code runner (a CLI command and a skill) in which the user's own session reads the bundles
    and writes answers to a file. Those answers pass the same validator and are stored with
    `route = claude-code` and the model recorded as unknown unless the session reports it.
12. **The gate is "never worse than the engine".** Before a default model is committed, the pass is
    run on the song benchmark's engine-flagged spans and the voice and piano set, for Haiku, Sonnet
    and DeepSeek. Reported: notes fixed, notes broken after validation (must be 0, as `false = 0`
    for chords and lyrics), validator rejection rate, cost and time per page. Gain per euro only
    breaks a tie between models that pass. The maintainer also listens (the Anton photo and the
    voice and piano set).

## Considered options

- **A model on the whole page** (the BACKLOG's first wording): the cost grows with every page and
  the model gets the chance to damage what was right. Rejected for spans the engine or the user
  distrusts.
- **Whole-MusicXML answers**: simpler prompt, but the model can rewrite anything and the validator
  would have to diff scores. Patches in the editor's vocabulary make the validator a check on
  operations that already throw on nonsense.
- **Applying readings one by one through the other readings dialog**: what ADR 0006 does for
  engine candidates. Fine for one note, tiring for a pass that changes thirty. The dialog keeps
  showing the stored readings; the draft is how they are reviewed in bulk.
- **A better image of the music as an input**: the user's example was lyrics, and lyrics are what
  can be found online. A cleaner photo of the notes is just a better first recognition.

## Consequences

- `review.json` (or a file beside it) gains drafts and stored readings; both must be named in
  `load()` and asserted to survive `PUT /score`, which is how `lines` and `unders` were once lost.
- `polish.py` stops being called unconditionally from `pipeline/run.py`; its prompt and
  structure check become the lyrics validator.
- The hosted app now has a path where data leaves the server. This is opt-in per pass, and the
  notice is part of the feature, not an afterthought.
- AGPL is unaffected: the providers are called over HTTP.
- A Claude Code runner cannot be audited the way an API call can; recording the route is how that
  is kept honest.
