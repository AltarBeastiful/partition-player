---
name: partition-player-fix
description: Improve a recognized score on a partition-player site with the user's own Claude Code session, no API key. Use when the user gives a partition-player score URL (https://host/s/<id>) or job id and asks to fix, check or improve its readings, notes, chords or lyrics.
---

# Fix the readings of a partition-player score

The site holds a score the engine read from a photo. You fetch the questions the engine is unsure about, answer them,
and post the answers back. The server validates every answer and keeps only what holds (measures that added up still
add up, the measure count is unchanged, nothing outside the span moves). What survives becomes a **model draft** the
user reviews in the browser and applies in one step. You never edit the score yourself.

The helper is `pp.py` next to this file (Python 3, standard library only). Below, `PP` is
`python3 ~/.claude/skills/partition-player-fix/pp.py`. A site token, if it has one, is read from `PP_API_TOKEN`;
a bare id needs `PP_URL` (the site's address).

## Steps

1. **Fetch.** `PP fetch <url or id>` writes `model-pass-<id>/` with `index.json`, `page.webp` (the photo of the
   page) and one `task-NN/` folder per question (`prompt.txt`, `task.json`, `score.musicxml`).
   - With no `--span`, the questions are the engine's doubts, the surest wrong first (at most 10).
   - To target something else: `--span STAFF:FROM:TO` (measures counted from 0, inclusive), repeated, with
     `--note "the second bar is a triplet"` for what the user noticed.
   - To place lyrics the user gives you: `--span STAFF:FROM:TO:WORDSFILE`. The words are authoritative; verses are
     separated by a blank line. You decide only which syllable goes under which note.
2. **Answer each task.** Read `prompt.txt` (follow its numbering exactly) and `task.json` (`answer_format`). Look at
   `page.webp` when the prompt leaves you in doubt. Answer in the format asked:
   - notes and chords: a JSON array of operations, or `[]` when the notes are right. Change only what the photo
     confirms; a doubtful note you cannot confirm stays as it is.
   - words under notes: `[{"text": "Lors-", "note": 0}, ...]`, letters exactly those of the lyrics.
3. **Write `answers.json`** next to `index.json`:

   ```json
   {"model": "your model name if you know it, else omit",
    "answers": [{"span": <span from task.json>, "verse": <verse from task.json>, "reply": [ ... ]}]}
   ```

   A task you cannot answer is left out.
4. **Submit.** `PP submit <url or id> model-pass-<id>/answers.json`. It prints how many changes were kept and why
   any answer was dropped. If answers were dropped for fixable reasons (a wrong note index, a letter off), correct
   them and submit again: a new import replaces the stored draft.
5. **Hand back.** Tell the user the link printed by `submit`: they open *Check with a model*, flip *as read* /
   *as corrected*, untick what they disagree with and apply once (one undo takes it all back).

## Rules

- Never edit anything but `answers.json`. Never invent changes to look useful: an empty answer is a good answer.
- Put nothing in a `reply` but the answer, no commentary.
- The server's validator is the safety net, not a reason to guess.
- Clef, key and time signature cannot be changed by this pass; the notes pass works on staff 0 only.
