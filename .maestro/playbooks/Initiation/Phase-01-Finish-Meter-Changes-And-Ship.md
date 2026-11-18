# Phase 01: Finish plan 0013, check OSMD 2, and ship to main

This phase closes plan 0013 (a time signature that changes mid-page) by running its last step, step 4: re-scoring the song benchmark. The false count has to hold where it was. The phase then checks that the OSMD 1.9.9 → 2.1.3 upgrade (the `osmd-2` commit, already an ancestor of `bench-song-benchmark`) broke nothing in the viewer. Once both pass, it merges `bench-song-benchmark` into `main`, pushes, and redeploys on the `main` host. At the end, https://partition-player.92.5.91.253.sslip.io runs plans 0011–0013 and OSMD 2. Three rules apply to every task. Never merge or deploy after a failed check. Commits carry **no** `Co-Authored-By` line. Licensing, the Anton files at the repo root and the rest of `BACKLOG.md` are out of scope and must not be touched. Scratch logs go in `.maestro/playbooks/Initiation/Working/`.

## Tasks

- [ ] Prepare a clean baseline for the benchmark re-score:
  - Confirm the working tree is clean and the branch is `bench-song-benchmark` (`git status`, `git branch --show-current`). Stop and record why in `Working/phase-01-log.md` if it is not.
  - Read `docs/plans/0013-meter-changes.md` (step 4 is the open item), the "Songs" sections of `bench/RESULTS.md` (tables at about lines 210–350), and the docstring of `bench/songs/run_bench.py` for how it is invoked.
  - Copy the existing `bench/out/songs/leadsheets/results.json` and `bench/out/songs/voice_piano/results.json` (dated 2026-09-19, so from before plan 0013) to `Working/baseline-leadsheets.json` and `Working/baseline-voice_piano.json`. Every comparison later in this phase uses these copies.
  - Check that the tools exist: `.venv-oemer/bin/python` and `backend/.venv/bin/partition-player`. If `.venv-oemer` is missing, look in `bench/RESULTS.md` "Reproduce" sections for how it is built and recreate it with `uv`. Use `backend/.venv/bin/python` instead only if it can import music21.

- [ ] Run the backend test suite before the long benchmark: `cd backend && .venv/bin/pytest -q`. All tests must pass, including the 17 in `tests/test_meter.py`. Fix any failure before you continue, and commit the fix with a plain message and no Co-Authored-By line. Write the pass count to `Working/phase-01-log.md`.

- [ ] Re-score the song benchmark with the plan 0013 code (long-running, about 15 + 25 + 4 min; run each command in the background with output to a log in `Working/` and wait for it, rather than hitting a tool timeout):
  - `.venv-oemer/bin/python bench/songs/run_bench.py` (leadsheets set)
  - `.venv-oemer/bin/python bench/songs/run_bench.py --set voice_piano`
  - `.venv-oemer/bin/python bench/songs/run_bench.py --set voice_piano --scans` (only if the scans' ground truth already exists in `bench/out/songs/voice_piano/scans/`; skip it otherwise and note the skip)
  - Also re-run the original single-page score: run the CLI on `bench/samples/anton_yvan_boris_photo.jpg` and score it with `bench/score.py bench/samples/anton_yvan_boris_ground_truth.musicxml <output>`. Its event error rate must stay 0.00.

- [ ] Compare the new results against the baselines and decide if plan 0013 holds <!-- MAESTRO:MODEL tier="high" effort="high" reason="Separating a real regression from a legitimate re-anchoring or meter change takes careful reading of per-page diffs against the plan's own rules. A wrong verdict either ships a regression or blocks a good merge." -->
  - Write a small script, `Working/compare_results.py`, that loads each baseline and new `results.json` and prints, per set, the same columns as the RESULTS.md tables: sung notes, pitch, pitch+duration, measure count right, syllables placed, text right, verses, false syllables, chords right, false chords. Then list every page where any number moved.
  - Pass criteria: false syllables and false chords do not rise in any set, pitch+duration does not drop, and the right-measure-count tally does not drop. For each page that moved, open its `run/<name>/` output, find the measures that changed, and say whether the change comes from plan 0013's re-anchoring (step 2) or its meter rule (step 3). Use `git stash` or a worktree at `f9b34e3` only if you need a side-by-side.
  - If a criterion fails, find the cause in `backend/` (`postprocess`, `homr_driver.parse()`), fix it, add a test in `backend/tests/test_meter.py`, re-run the affected set, and compare again. Do not loosen the criteria.
  - Write the verdict and the per-set table to `Working/phase-01-log.md`.

- [ ] Record step 4 as done in the repository docs:
  - In `docs/plans/0013-meter-changes.md`, add a new dated status line (2026-10-08 or today's date) above the existing one: **steps 1 to 4 done**. Rewrite step 4's "Not yet done" paragraph into what was measured: the per-set numbers, the false count held, and the pages that moved and why. Keep the plan's prose voice (plain sentences, measured facts, no marketing words).
  - In `bench/RESULTS.md`, add a short section, "Meter changes (plan 0013), <date>", after the Songs sections. Give it the before/after table and the exact commands used to reproduce it. Update the leadsheets/voice_piano tables only if their numbers changed, and say so.
  - Commit the docs and any code fixes, for example "Re-score the song benchmark under plan 0013 (step 4): …". Use a descriptive body in the style of the recent `git log`, with no Co-Authored-By line.

- [ ] Check that the frontend still holds under OSMD 2.1.3:
  - `cd frontend && npm ci` if `node_modules` is missing or stale. Then run `npm test` (vitest) and `npm run build` (runs `tsc --noEmit` and `vite build`). Both must pass. Fix real breakage in `frontend/src/` and look for existing patterns before adding new code. Do not downgrade OSMD.
  - Grep `frontend/src` for every OSMD API in use (`OpenSheetMusicDisplay`, `cursor`, `GraphicSheet`, `EngravingRules`, `MusicPartManagerIterator`, `drawingParameters` and the like). Check each against the 2.1.3 type definitions in `node_modules/opensheetmusicdisplay/build/dist/src/`. Note in `Working/phase-01-log.md` any API whose signature or behaviour changed.

- [ ] Smoke-test the running app end to end with OSMD 2:
  - Start the backend and the frontend the way the README or `CLAUDE.md` says (the frontend dev server on port 5174 per project convention; check `PP_FRONTEND_DIR` if you serve the built bundle from the backend).
  - Through the HTTP API: upload `bench/samples/anton_yvan_boris_photo.jpg`, poll the job until it is done, then fetch the score's MusicXML. Also import a MusicXML file (`bench/samples/anton_yvan_boris_ground_truth.musicxml`).
  - In a headless browser: load the score page and assert that OSMD drew SVG with the expected measure count and no console errors, that the cursor element exists and moves on Play/next, and that clicking a note in edit mode selects it. Use Playwright for Python or Node if it is installed or can be installed into a scratch venv under `Working/`. If no headless browser can run on this machine, write a vitest + jsdom test that renders the ground truth with OSMD 2 and checks the measure count. Record which route you took.
  - Stop every process you started. Write the results to `Working/phase-01-log.md`. If anything fails, fix it, re-run the frontend tests, and commit before you continue.

- [ ] Merge `bench-song-benchmark` into `main` and push. Do this only if every check above passed.
  - `git fetch origin`, `git checkout main`, `git pull --ff-only origin main`, then `git merge --no-ff bench-song-benchmark`. Use a message that names what lands: plans 0011–0013, the OSMD 2.1.3 upgrade, and the 0013 benchmark re-score. No Co-Authored-By line.
  - If there are conflicts, resolve them in favour of the branch unless `main` holds a fix the branch lacks. Then re-run `backend/.venv/bin/pytest -q` and `npm test` on the merged result before you push.
  - `git push origin main`. Then push `bench-song-benchmark` too, so the remote branch is current.

- [ ] Redeploy on the `main` host and verify the live site:
  - Read `deploy/README.md` and `deploy/deploy.sh`. Run `deploy/deploy.sh` from the `main` branch checkout. It rsyncs, builds on the server, restarts, installs the Caddy site and prints memory. Never add `ports:` to the production compose.
  - Verify: `curl -fsS https://partition-player.92.5.91.253.sslip.io/` returns the app. Then send one real recognition through the public API (the Anton photo), wait for it to finish, and fetch its MusicXML. Capture `ssh main docker stats --no-stream partition-player` and `ssh main free -m`, and confirm the peak stays under the 3 GB cap.
  - Record the deployed commit hash, the recognition time and the memory figures in `Working/phase-01-log.md`. Add one line to `deploy/README.md`'s Resources section only if the numbers moved meaningfully. If you did, commit and push it.
  - If the deploy or the live check fails, roll back with `git checkout <previous main commit>` and `deploy/deploy.sh`, and record the failure. Do not leave the site broken.
