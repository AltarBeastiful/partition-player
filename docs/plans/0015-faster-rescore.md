# Plan 0015: A re-score that fits in a coffee break

Status 2026-11-18: **not started.** Follows plan 0014, which is scored at today's speed.

## Problem Statement

Re-scoring the song benchmark takes about 20 minutes for the leadsheets set, 25 for voice_piano and 4
for the scans, so one change to the pipeline costs most of an hour to check. That is why plan 0013's
last step waited days. The cost is mostly structural, from what was measured on 2026-11-18:

- Each page is its own `recognize` call, run one after another, and each call loads homr's models and
  two OCR models again. A page takes about 20 seconds: roughly 55 % in homr's detection and parsing,
  30 % in OCR, 10 % in our own postprocessing, under 1 % in scoring.
- A page uses four to five of the sixteen cores, in bursts. The laptop is about 88 % idle during a run.
- Nothing is reused between runs.

## Solution

Two steps.

**Step 1, `--jobs N`.** Process several pages at once, each in its own process with its thread count
capped so they do not fight over the cores. Four workers is the first guess. Recognition results do not
change.

**Step 2, a one-hour trial of GPU inference on the dev laptop**, only after plan 0014 is merged and
stable. It is dev-only, an extra install that is never in the shipped dependencies. It is dropped if it
does not work or if it gains under 25 % per page on top of step 1.

## User Stories

1. As the maintainer, I want to re-score a set in a few minutes, so that I can try a change and see its
   effect the same hour.
2. As the maintainer, I want a parallel run to give the same results as a sequential one, so that speed
   never costs trust in the numbers.
3. As the maintainer, I want the worker count to be an option, so that the laptop stays usable while a
   run goes.
4. As the maintainer, I want output printed in page order, so that two runs can be compared by eye.
5. As the maintainer, I want a failed page to be reported and not to stop the others, so that one bad
   page does not cost a whole run.
6. As the maintainer, I want the production host to keep running on CPU, so that a laptop experiment
   changes nothing there.
7. As the maintainer, I want the GPU trial capped in time and judged by a number, so that it cannot
   become a project of its own.
8. As the maintainer, I want the measured speeds recorded in `bench/RESULTS.md`, so that the next
   person knows what a run costs.

## Implementation Decisions

- **Parallel pages.** The benchmark runner gains a `--jobs` option. Each worker runs one page at a
  time; results are collected and written in the order of the page list. Each worker's thread count for
  the numerical libraries is set so that workers times threads stays within the cores.
- **No cache of the engine's output.** Considered and refused: plan 0013 changed what the driver emits,
  so a saved engine output would have been stale for exactly the change being measured, and a cache
  keyed on the driver's source is one more thing to be wrong. The same goes for keeping the models warm
  in a long-lived process: it saves a few seconds a page and adds state to isolate.
- **Equality check.** A parallel and a sequential run over a sample of pages must give the same
  `results.json` in every field but the timing.
- **GPU trial facts, as found on 2026-11-18.** The laptop's GPU is a Radeon 680M integrated chip
  (gfx1035); no ROCm is installed; the onnxruntime in the backend environment offers only the CPU
  provider. homr 0.7.1 adds an AMD path (the ROCm provider) documented for ROCm 7.0 with AMD's own
  onnxruntime wheel, which would replace the one in the environment. The 680M is not an obviously
  supported target and may need an override of the reported architecture. Only the segmentation network
  (about 3.7 s of a 20 s page) is certain to benefit. Half-precision output can differ slightly from the
  CPU's, so a GPU run is a different measurement and is recorded as such, never mixed with the CPU
  baseline.
- **Where the trial lives.** In a separate environment, outside the backend's dependencies, selected by
  an environment variable the driver reads. Nothing about it is deployed.

## Testing Decisions

- One seam: the benchmark runner's results. A good test is the equality check above on real pages, not a
  unit test of a thread pool.
- The GPU trial is judged by seconds per page and by whether the scores match the CPU run.
- Prior art: the benchmark's own `results.json`, which already records seconds per page.

## Out of Scope

- Making recognition itself faster in production.
- Caching or warm models, as above.
- Skipping the OCR on pages without chords or words (it changes behaviour, so it would need its own
  benchmark pass).
- Any GPU use on the main host.

## Further Notes

- Before this plan: leadsheets 20.6 s per page, voice_piano 22.2 s, scans 17.8 s.
- Commits carry no `Co-Authored-By` line.
