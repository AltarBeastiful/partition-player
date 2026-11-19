---
name: partition-player-model-pass
description: Answer the repair bundles of a partition-player model pass (placing lyrics under notes, or checking the notes and chords of a stretch of measures) and write answers.json for `partition-player model-pass import`. Use when asked to answer a model-pass export directory, or when a directory holds index.json and task-NN folders from `partition-player model-pass export`.
---

# Answering a partition-player model pass

`partition-player model-pass export <job> --span ...` wrote a directory (the user will name it) with an
`index.json` and one folder per question, `task-01`, `task-02`, ... You answer each one; you do not touch the
score. The app validates every answer itself and drops what does not hold, so answer only what you are sure of.

## Each task folder

- `prompt.txt`: the question, complete. Follow it as written, including its note or event numbering.
- `task.json`: `span` (staff, from, to, and `lyrics_source` or `note`), `verse` and `answer_format`.
- `score.musicxml`: the measures of the span, for context. Measure numbers inside `prompt.txt` are the ones to use.
- `page.webp` (when present): the photo of the page the score was read from. Look at it if the prompt leaves you in doubt.

## What to do

1. Read `index.json`, then for each task read `prompt.txt` and `task.json`.
2. Write the reply in the format of `answer_format`:
   - words under notes: a JSON array `[{"text": "Lors-", "note": 0}, ...]`. The letters of all your syllables must be
     exactly the letters of the lyrics (hyphens and spaces aside); `note` strictly increases.
   - notes and chords: a JSON array of operations, or `[]` when the notes are right. Do not invent changes: a
     doubtful note that you cannot confirm from the photo stays as it is.
3. Write one file, `answers.json`, next to `index.json`:

```json
{
  "model": "the name of the model you are, if you know it, else leave this key out",
  "answers": [
    {"span": {"staff": 0, "from": 0, "to": 1, "lyrics_source": "Lors-que nous é-tions"}, "verse": 1,
     "reply": [{"text": "Lors-", "note": 0}, {"text": "que", "note": 1}]}
  ]
}
```

   `span` and `verse` are copied from the task's `task.json`; `reply` is yours. A task you cannot answer is left out
   or given no `reply`.
4. Tell the user to run `partition-player model-pass import <job> <dir>/answers.json`, then open the score and
   apply the draft in **Check with a model**.

## Rules

- Never edit the score, the bundles or anything outside `answers.json`.
- Never put anything in a reply but the answer: no commentary inside the JSON.
- Do not run the import yourself unless the user asks.
