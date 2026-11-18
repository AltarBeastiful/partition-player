# Plan 0014: Move to homr 0.7.1, then to homr `main`

Status 2026-11-18: **not started.** Written after plan 0013's re-score, which still runs on homr 0.7.0.
No ADR yet: if the trial of `main` ships, the decision to pin an engine by commit is one and gets
written then (ADR 0002 already names homr as the engine and Audiveris as the fallback).

## Problem Statement

We are on homr 0.7.0 and the driver that wraps it copies about twenty of homr's internals and a mirror
of its `process_image` flow, so that it can keep the time-signature marks and the measure counts that
homr drops. homr has moved: 0.7.1 (released 2026-11-10) is a refactor, and `main` has unreleased work
on beams, time signatures across pages and octave shifts, which overlaps with plans 0006 and 0013.
Staying put means the engine's own fixes never reach the page; moving without a measure means we cannot
tell a better engine from a different one.

## Solution

Upgrade in two steps, each of them judged on the song benchmark and each of them revertible.

**Step 1, homr 0.7.1** (the released version, inside the existing `>=0.7,<0.8` pin). Patch the driver,
re-score every set, and keep it only if the criteria below hold; otherwise pin back to 0.7.0.

**Step 2, homr `main`**, only once step 1 is merged and stable. Installed from git and pinned to an
exact commit, never a floating branch. It may ship to production if it passes the same criteria and the
deploy is checked.

Where homr now does natively what we do ourselves (beams, a time change, the numerator of a bar), our
code stays until the benchmark shows homr's version is at least as good. Ours is then removed in a
commit of its own. The two are never active at once.

## User Stories

1. As the maintainer, I want the driver to stop copying homr's `process_image`, so that the next homr
   refactor costs a small fix and not a re-derivation.
2. As the maintainer, I want one homr internal to wrap (a staff's raw token stream, before the
   duplicate-removal), so that plan 0013's time marks survive any release.
3. As the maintainer, I want the benchmark re-scored on every engine change, so that a better engine
   and a different engine are told apart by numbers.
4. As the maintainer, I want a failing upgrade to end in a one-line pin back to 0.7.0, so that trying
   one costs nothing.
5. As a user photographing a page, I want the same or better notes, chords and words, so that an
   upgrade never makes the app worse.
6. As a user, I want a deploy that keeps working inside the host's 3 GB cap, so that the site stays up.
7. As the maintainer, I want `main` pinned by commit, so that a deploy is reproducible.
8. As the maintainer, I want our beam and meter code kept until homr's version wins, so that there is
   never a period with two writers of the same fact.
9. As the maintainer, I want each step to record its numbers in this plan, so that the next person sees
   what was measured and not what was hoped.

## Implementation Decisions

- **0.7.1 is not drop-in, and it is not a rewrite.** Measured by diffing the released wheel against the
  installed 0.7.0 (a reading of the diff, to be confirmed by running it):
  - Two helpers the driver imports for counting staffs and voices no longer exist.
  - The function that loads and preprocesses the predictions returns three values and not two.
  - The XML generator returns an ElementTree element and no longer the `musicxml` library's object, so
    how the driver writes the file changes. That library is dropped.
  - onnxruntime becomes an optional extra of homr, so our own dependencies must ask for it (the CPU
    extra) or a fresh install has no runtime.
  - Systems with differing staff counts, hidden staffs and unmarked triplets are handled by new code in
    homr's staff parsing, and positions now include a second upper and a second lower.
  - The page crop is a wrapper over a function that returns its offset, so the driver's replica of it
    can go; the paper-colour fill it adds changes pixels.
- **The time marks stay ours.** The vocabulary still has no numerators and a repeated mark is still
  dropped, so plan 0013's premise holds. What changed: homr now guesses a numerator of its own for the
  marks that survive. Our rule (the bar's own length, two voices at least agreeing, neither the meter in
  force nor twice it) is checked against that guess so the two do not double up.
- **Wrap, do not mirror.** The driver captures each staff's raw token stream by wrapping homr's own
  staff parsing, and keeps the marks and the measure counts as it does today. The copy of the
  surrounding flow is deleted.
- **Benchmark criteria, unchanged from plan 0013.** Over the leadsheets, voice_piano and scans sets and
  the Anton photo: false syllables do not rise, false chords do not rise, pitch+duration does not drop,
  the tally of right measure counts does not drop, and the Anton page keeps an event error rate of 0.00.
  The numbers become the new baseline only once the step is merged.
- **Revert rule.** A step that fails is pinned back, not patched around.
- **Step 2 pinning.** `main` is installed from git at an exact commit in the backend's dependencies. The
  deploy builds on the host, so before merging, the host's access to fetch it is checked. If it cannot,
  `main` stays a dev-laptop trial.
- **Overlap rule.** Beams (plan 0006's pixel rule), octave shifts and time changes: for each, score
  homr's reading and ours on the benchmark; remove ours in its own commit only if homr's is at least as
  good.

## Testing Decisions

- One seam: reading a page and scoring it, which is `bench/songs/run_bench.py` over the sets above. It
  is the seam the project already trusts, and it needs no new code.
- A good test here is an external number on a page, not a check that a homr function was called.
- Under it, the backend tests (in particular the meter tests of plan 0013) must stay green on each
  step; the driver patch adds none of its own for homr internals.
- Prior art: plans 0011 to 0013 each close on a re-score with a before and after table.

## Out of Scope

- Training or fine-tuning homr's models.
- Replacing homr, or the Audiveris fallback (ADR 0002).
- Using a GPU for recognition: that is plan 0015, and dev-only.
- Any change to the editor, the player or the form.

## Further Notes

- Step 1 runs the benchmark at today's speed (about 20 minutes a set) because plan 0015 comes after.
- Order of work: plan 0013 merged and deployed on 0.7.0 first; then this plan.
- Commits carry no `Co-Authored-By` line.
