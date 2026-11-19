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
`python3 ~/.claude/skills/partition-player-fix/pp.py`. A site token, if it has one, is read from `PP_API_TOKEN` or `~/.config/partition-player/token`;
a bare id needs `PP_URL` or `~/.config/partition-player/url` (the site's address); prefer the full URL.

## Steps

1. **Fetch.** `PP fetch <url or id>` writes `model-pass-<id>/` with `index.json`, `page.webp` (the photo of the
   page) and one `task-NN/` folder per question (`prompt.txt`, `task.json`, `score.musicxml`).
   - With no `--span`, the questions are the engine's doubts, the surest wrong first (at most the server's cap, 10 by default; only staff 0 is asked).
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
   them and submit again with `--replace`. Without it the site refuses (409) when a draft is already open, because the
   user may be reviewing it: do not replace a draft you did not make in this session without asking.
5. **Hand back.** Tell the user the link printed by `submit`: they open *Check with a model*, flip *as read* /
   *as corrected*, untick what they disagree with and apply once (one undo takes it all back).

## When it fails

- `401`: the site has a token. Ask the user to set the token (`PP_API_TOKEN`, or the file `~/.config/partition-player/token`); the skill never prints it.
- `404`: no such score: check the id in the URL.
- `409 a model draft is already open`: see step 4. `409 job is ...`: the score is still being read; try later.
- `422 the engine has no doubts`: nothing to fix automatically. Ask the user which measures look wrong and use `--span`.
- Cannot reach the host: say so; do not guess another address.

## Rules

- Never edit anything but `answers.json`. Never invent changes to look useful: an empty answer is a good answer.
- Put nothing in a `reply` but the answer, no commentary.
- The server's validator is the safety net, not a reason to guess.
- Clef, key and time signature cannot be changed by this pass; the notes pass works on staff 0 only.
