"""The Claude Code runner of the model pass (ADR 0010, decision 11).

A thin runner over the same core the API route uses: `export_bundles` writes, for each span, the very prompt the
API would send (built by lyrics_pass / notes_pass) with a slice of the score; the user's own Claude Code session
answers; `import_answers` feeds those replies to `lyrics_pass.run` through a route whose "model" is the answers
file, so they pass the same validators and become the same kind of draft, stored with route kind `claude-code`.

answers.json: {"model": "optional name of the model that answered",
               "answers": [{"span": {staff, from, to, lyrics_source?, note?}, "verse": 1, "reply": [...]}]}
`verse` counts from 1 for a span with words and is left out for a span without; `reply` is the answer in the
format of the task (a list, or the text of one).
"""
from __future__ import annotations

import copy
import json
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from . import lyrics_pass, notes_pass

KIND = "claude-code"
UNKNOWN = "unknown"
SPAN_KEYS = ("staff", "from", "to", "lyrics_source", "note")

WORDS_FORMAT = ('A JSON array only, one object per syllable, in order: {"text": "Lors-", "note": 0}. A trailing hyphen means '
                "the word continues in the next syllable; `note` is the note index listed in the prompt, strictly increasing. "
                "The letters must be exactly those of the lyrics.")
NOTES_FORMAT = ("A JSON array of operations only, each {\"op\", \"measure\", \"event\", ...}: stepPitch(delta), setAlter, "
                "shiftOctave, setDuration(type, dots), toRest, deleteEvent, toggleTie, insertEvent(where, kind), "
                'setChord(text; "" removes). `event` is the index listed in the prompt. An empty array means nothing to change.')


class NoAnswer(Exception):
    pass


@dataclass(frozen=True)
class AnswerRoute:
    """Stands where a Route stands: `complete` returns the reply written for that prompt instead of asking a model."""
    replies: dict
    model: str = UNKNOWN
    vision: bool = False

    def larger(self):
        return None

    def complete(self, text: str, image_png=None, max_tokens: int = 0, client=None) -> str:
        if text not in self.replies:
            raise NoAnswer(text[:40])
        return self.replies[text]


def _where(span: dict) -> dict:
    return {"staff": span["staff"], "from": span["from"], "to": span["to"]}


def _span(raw: dict) -> dict:
    try:
        span = {"staff": int(raw.get("staff", 0)), "from": int(raw["from"]), "to": int(raw["to"])}
    except (KeyError, TypeError, ValueError) as e:
        raise lyrics_pass.SpanError("a span needs staff, from and to as numbers") from e
    for key in ("lyrics_source", "note"):
        if str(raw.get(key) or "").strip():
            span[key] = str(raw[key])
    return span


def _tasks(root: ET.Element, span: dict) -> list[tuple[int, str, str]]:
    """(verse, prompt, format) for each model call the span makes; SpanError when the span is outside the score."""
    notes = lyrics_pass.span_notes(root, span["staff"], span["from"], span["to"])
    if notes_pass.is_notes_span(span):
        return [(0, notes_pass.prompt_for(root, span), NOTES_FORMAT)]
    return [(v, lyrics_pass.prompt_for(root, span["staff"], notes, text), WORDS_FORMAT)
            for v, text in enumerate(lyrics_pass.verses_of(span["lyrics_source"]), start=1)]


def _slice(root: ET.Element, first: int, last: int) -> ET.Element:
    out = copy.deepcopy(root)
    for part in out.findall("part"):
        for i, m in enumerate(part.findall("measure")):
            if not first <= i <= last:
                part.remove(m)
    return out


def export_bundles(job_dir: Path, spans: list[dict], out: Path) -> dict:
    """One folder per model call: task.json, prompt.txt, the score slice, and the page photo when the job has one."""
    root = ET.parse(job_dir / "score.musicxml").getroot()
    out.mkdir(parents=True, exist_ok=True)
    tasks = []
    for raw in spans:
        span = _span(raw)
        for verse, prompt, fmt in _tasks(root, span):
            name = f"task-{len(tasks) + 1:02d}"
            d = out / name
            d.mkdir(exist_ok=True)
            (d / "prompt.txt").write_text(prompt)
            (d / "task.json").write_text(json.dumps({"span": span, "verse": verse, "answer_format": fmt,
                                                     "note": "Put this span (and verse) and your reply in answers.json as one answer."},
                                                    ensure_ascii=False, indent=1))
            ET.ElementTree(_slice(root, span["from"], span["to"])).write(d / "score.musicxml", encoding="UTF-8", xml_declaration=True)
            if (job_dir / "review.webp").exists():
                shutil.copyfile(job_dir / "review.webp", d / "page.webp")
            tasks.append({"dir": name, "span": span, "verse": verse})
    index = {"job": job_dir.name, "tasks": tasks,
             "answers": "answers.json: {\"model\": \"...\", \"answers\": [{\"span\": <task span>, \"verse\": <task verse>, \"reply\": [...]}]}"}
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1))
    return index


def import_answers(job_dir: Path, answers: dict, revision: int) -> dict:
    """Validate the answers like any route's and store the draft; returns it. Unanswered or invalid ones are dropped with reasons."""
    root = ET.parse(job_dir / "score.musicxml").getroot()
    replies: dict[str, str] = {}
    spans: dict[tuple, dict] = {}
    dropped: list[dict] = []
    for entry in answers.get("answers", []):
        try:
            span = _span(entry.get("span") or {})
            verse = int(entry.get("verse") or (0 if notes_pass.is_notes_span(span) else 1))
            prompt = {v: p for v, p, _ in _tasks(root, span)}.get(verse)
            if prompt is None:
                raise lyrics_pass.SpanError(f"the span has no verse {verse}")
        except (lyrics_pass.SpanError, TypeError, ValueError) as e:
            given = entry.get("span") if isinstance(entry.get("span"), dict) else {}
            dropped.append({"span": {k: given.get(k, 0) for k in ("staff", "from", "to")}, "verse": 0, "reason": str(e)})
            continue
        reply = entry.get("reply")
        if reply is None or reply == "":
            dropped.append({"span": _where(span), "verse": verse, "reason": "no answer was written for this task"})
            continue
        replies[prompt] = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        spans.setdefault(tuple(span.get(k) for k in SPAN_KEYS), span)
    route = AnswerRoute(replies, model=str(answers.get("model") or UNKNOWN))
    result = lyrics_pass.run(job_dir / "score.musicxml", list(spans.values()), route)
    result["dropped"] = dropped + result["dropped"]
    return lyrics_pass.save_draft(job_dir, job_dir / "score.musicxml", route, list(spans.values()), result, revision, kind=KIND)
