# Model pass benchmark (ADR 0010, plan 0016 slice 3, ticket 12)

Runs the model pass (`lyrics_pass.run`, which dispatches notes and chords spans to `notes_pass`) on the engine-flagged
spans of the song benchmark pages, per route, and counts against the ground truth. No model is the default until this
has run and the gate holds.

## What is measured

- Spans: runs of measures that did not add up in the engine's own output (as `bench/songs/doubts.py`), plus one measure
  of context each side. With `--lyrics`, each span that has ground-truth syllables is also asked as a words span, the
  ground-truth verses being the typed source. `--anton` adds the Anton photo (`bench/out/homr/anton.musicxml`), where
  homr is already right, so it mostly tests that nothing is broken.
- Counted after validation and apply (the pass as the editor would apply every change): per measure of each span, events
  are lined up by position and compared with the ground truth (pitch or rest, and length). **Notes fixed** = wrong before,
  right after. **Notes broken** = right before, wrong after. An insert or delete that shifts later notes breaks them.
  Syllables are counted the same way. Pages whose measure count differs from the ground truth are skipped and counted.
- **Validator rejections** = entries in the draft's `dropped` (operations or answers refused, calls that failed).
  **Escalated** = answers retried on the larger model. `--no-escalation` measures each model alone.
- **Cost and time per page** come from the `usage` of each answer and the time spent in calls. Built-in prices: Haiku
  $1/$5, Sonnet $3/$15 per million tokens. DeepSeek has none: pass `--price deepseek=IN,OUT` from its price list,
  or the column says n/a.
- **Gate:** broken notes and broken syllables must be 0 for a model to be offered as default (the table says PASS or FAIL,
  and the exit code is 1 on a failure).

## Run it

Needs the song benchmark outputs (`bench/songs/run_bench.py`, untracked, under `bench/out/songs/`; set `BENCH_OUT`
if they live in another checkout). Use the backend venv.

    # harness check, no keys, nothing written to RESULTS.md
    backend/.venv/bin/python bench/model/run_bench.py --offline
    backend/.venv/bin/python -m pytest bench/model

    # dry run of case loading (no key, no call; every span reports "could not be asked")
    backend/.venv/bin/python bench/model/run_bench.py --routes haiku --replay /nonexistent.json

    # real run: costs money, start small
    export PP_ANTHROPIC_API_KEY=... PP_DEEPSEEK_API_KEY=...
    backend/.venv/bin/python bench/model/run_bench.py --live --routes haiku --max-pages 3 --record bench/out/model/rec.json
    backend/.venv/bin/python bench/model/run_bench.py --live --routes haiku,sonnet,deepseek --lyrics --anton \
        --price deepseek=0.3,1.2 --audio --write --record bench/out/model/rec.json

`--record` stores every answer so `--replay` can re-run the counting without calling anything. `--write` appends the
table to `bench/RESULTS.md`. DeepSeek reads no images: only typed-source and notes spans run on it. Escalation targets
are the route's `larger_model` (Sonnet for Haiku, `deepseek-v4-pro` for DeepSeek, a guess to confirm).

## Listening

`--audio` writes, per route and page, `bench/out/model/<route>/<page>.ogg` (after the pass), `.engine.ogg` (before) and
`.truth.ogg`. It needs music21 (`bench/.venv-oemer`), timidity with FluidR3_GM, and ffmpeg; it prints why it skipped
otherwise. The maintainer listens to the Anton photo and the voice and piano set, engine against pass, and edits the
"Listening check" line in the RESULTS.md section.

## What to do with the results (not done by the harness)

1. If a model's row has any broken note or syllable, it is not offered as default. Read the cases (`--record` file,
   the per-page lines) to see which answer broke what: a validator hole is a bug in `notes_pass.vet`, not a model verdict.
2. Among models that pass, pick the default by fixed notes first, then rejection rate, then cost and time per page.
   Pick the escalation model the same way (a failed answer goes to it once).
3. Set the default: `HAIKU` / `Route.anthropic` defaults and `Settings.model_routes` in the backend (`route.py`, settings),
   and the README line of the route list.
4. After listening, change ADR 0010's status and record the chosen default and the figures in it; tick ticket 12's boxes.
5. Re-run on every model or prompt change.
