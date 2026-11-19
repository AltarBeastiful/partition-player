"""A model pass over a span with a typed lyrics source (ADR 0010, decisions 3, 5, 6, 7e).

The source is authoritative: the model only says which syllable goes under which note, and the letters
of its answer must equal the source's after normalising whitespace and hyphens. What passes becomes a
list of changes, one per placed syllable (and one clearing change per old syllable left without a
note), kept with a corrected copy of the score as a draft in the job directory.

Answer format (JSON): [{"text": "Lors-", "note": 0}, ...]; a trailing hyphen joins a syllable to the
next one, `note` is the index of the note among the span's sounding notes, in score order.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from ..pipeline.lyrics import inject as lyrics_inject
from .route import Route

DRAFT = "model-draft.json"
DRAFT_SCORE = "model-draft.musicxml"
MAX_SOURCE = 8000          # characters of lyrics source per span
MAX_NOTE = 400             # characters of note text

PROMPT = (
    "Below are the lyrics of a song and the notes of a stretch of a melody. Put the lyrics under the notes, "
    "one syllable per note, in order, cutting words into syllables where they are sung. You may leave a note "
    "without a syllable. Do not change, add, remove or reorder any letter of the lyrics: only decide the "
    "syllables and which note each one goes under.\n\n"
    "Lyrics:\n{text}\n\nNotes (index: measure, pitch):\n{notes}\n\n"
    'Reply with a JSON array only, one object per syllable, in order: {{"text": "Lors-", "note": 0}}. '
    "A trailing hyphen means the word continues in the next syllable. `note` is the note index above, "
    "strictly increasing."
)


class SpanError(ValueError):
    pass


def normalise(text: str) -> str:
    """Whitespace and hyphens are the only slack allowed between a source and an answer."""
    return re.sub(r"[\s\-]+", "", text)


def verses_of(source: str) -> list[str]:
    return [v.strip() for v in re.split(r"\n\s*\n", source.strip()) if v.strip()]


def _parts(root: ET.Element) -> list[ET.Element]:
    return root.findall("part")


def span_notes(root: ET.Element, staff: int, first: int, last: int) -> list[tuple[int, int]]:
    """(measure, onset) of every sounding note of the span, in score order."""
    parts = _parts(root)
    if not 0 <= staff < len(parts):
        raise SpanError(f"staff {staff} is not part of this score")
    measures = parts[staff].findall("measure")
    if not 0 <= first <= last < len(measures):
        raise SpanError(f"measures {first + 1} to {last + 1} are outside the score")
    return [(m, o) for m in range(first, last + 1) for o in range(len(lyrics_inject.sounding_notes(measures[m])))]


def _pitch(note: ET.Element) -> str:
    p = note.find("pitch")
    if p is None:
        return "?"
    alter = {"-1": "b", "1": "#"}.get(p.findtext("alter") or "", "")
    return f"{p.findtext('step')}{alter}{p.findtext('octave')}"


def prompt_for(root: ET.Element, staff: int, notes: list[tuple[int, int]], text: str) -> str:
    measures = _parts(root)[staff].findall("measure")
    lines = [f"{i}: bar {m + 1}, {_pitch(lyrics_inject.sounding_notes(measures[m])[o])}" for i, (m, o) in enumerate(notes)]
    return PROMPT.format(text=text, notes="\n".join(lines))


def estimate(root: ET.Element, spans: list[dict]) -> dict:
    """Calls and a rough cost (Haiku-class prices, per million tokens: $1 in, $5 out), before anything runs."""
    calls, tokens_in, tokens_out = 0, 0, 0
    for span in spans:
        notes = span_notes(root, span["staff"], span["from"], span["to"])
        for verse in verses_of(span["lyrics_source"]):
            calls += 1
            tokens_in += len(prompt_for(root, span["staff"], notes, verse)) // 3
            tokens_out += 40 + 6 * len(verse.split())
    return {"calls": calls, "estimated_tokens": tokens_in + tokens_out,
            "estimated_cost_usd": round(tokens_in * 1e-6 + tokens_out * 5e-6, 4)}


def parse_answer(reply: str, source: str, note_count: int) -> list[tuple[str, str, int]]:
    """(text, syllabic, note index) per syllable, or SpanError naming the rule the answer broke."""
    start, end = reply.find("["), reply.rfind("]")
    try:
        items = json.loads(reply[start:end + 1])
        raw = [(str(it["text"]), int(it["note"])) for it in items]
    except (ValueError, KeyError, TypeError) as e:
        raise SpanError(f"the answer is not a list of syllables with notes ({e.__class__.__name__})") from e
    if not raw:
        raise SpanError("the answer is empty")
    if normalise("".join(t for t, _ in raw)) != normalise(source):
        raise SpanError("the letters of the answer differ from the lyrics source")
    out, joined = [], False
    for k, (text, note) in enumerate(raw):
        word_goes_on = text.rstrip().endswith("-")
        clean = text.strip().strip("-")
        if not clean or "-" in clean or len(clean) > 40:
            raise SpanError(f"syllable {text!r} is malformed")
        if k and note <= raw[k - 1][1]:
            raise SpanError("the notes of the answer are not strictly increasing")
        if not 0 <= note < note_count:
            raise SpanError(f"note {note} is outside the span")
        syllabic = ("middle" if word_goes_on else "end") if joined else ("begin" if word_goes_on else "single")
        out.append((clean, syllabic, note))
        joined = word_goes_on
    if joined:
        raise SpanError("the last syllable is left open")
    return out


def current_lyrics(root: ET.Element, staff: int = 0) -> dict[tuple[int, int, int], dict]:
    """{(verse, measure, onset): {"text", "syllabic"}} of the score as it stands."""
    out = {}
    for m, measure in enumerate(_parts(root)[staff].findall("measure")):
        for o, note in enumerate(lyrics_inject.sounding_notes(measure)):
            for lyric in note.findall("lyric"):
                texts = [t.text or "" for t in lyric.findall("text")]
                if not texts:
                    continue
                syl = [s.text or "single" for s in lyric.findall("syllabic")]
                out[(int(lyric.get("number") or 1), m, o)] = {"text": lyrics_inject.ELISION.join(texts), "syllabic": syl[-1] if syl else "single"}
    return out


def run(score: Path, spans: list[dict], route: Route, client=None) -> dict:
    """Ask the model once per span and verse; returns {"changes": [...], "dropped": [...]}."""
    root = ET.parse(score).getroot()
    changes, dropped = [], []
    for span in spans:
        now = current_lyrics(root, span["staff"])
        notes = span_notes(root, span["staff"], span["from"], span["to"])
        where = {"staff": span["staff"], "from": span["from"], "to": span["to"]}
        for verse_no, text in enumerate(verses_of(span["lyrics_source"]), start=1):
            try:
                reply = route.complete(prompt_for(root, span["staff"], notes, text), max_tokens=1500, client=client)
                syls = parse_answer(reply, text, len(notes))
            except SpanError as e:
                dropped.append({"span": where, "verse": verse_no, "reason": str(e)})
                continue
            except Exception as e:  # noqa: BLE001  (a failed call is recorded, never raised past the pass)
                dropped.append({"span": where, "verse": verse_no, "reason": f"the model could not be asked: {e.__class__.__name__}"})
                continue
            placed = {notes[n]: (t, s) for t, s, n in syls}
            for (m, o), (t, s) in sorted(placed.items()):
                changes.append({"span": where, "verse": verse_no, "measure": m, "onset": o,
                                "old": now.get((verse_no, m, o)), "new": {"text": t, "syllabic": s}})
            for m, o in notes:  # an old syllable of this verse left without a note is cleared
                if (m, o) not in placed and (verse_no, m, o) in now:
                    changes.append({"span": where, "verse": verse_no, "measure": m, "onset": o, "old": now[(verse_no, m, o)], "new": None})
    for k, c in enumerate(changes, start=1):
        c.update(id=f"c{k}", ticked=True, conflict=False)
    return {"changes": changes, "dropped": dropped}


def apply_changes(root: ET.Element, changes: list[dict], staff: int = 0) -> None:
    """Write the changes into the score's lyrics in place (a clone for the draft, the score on apply)."""
    placed = {(p.verse, p.measure, p.onset): p for p in lyrics_inject.read_placements_of(root, staff)}
    for c in changes:
        key = (c["verse"], c["measure"], c["onset"])
        if c["new"] is None:
            placed.pop(key, None)
        else:
            placed[key] = lyrics_inject.Placement(c["verse"], c["measure"], c["onset"], c["new"]["text"], c["new"]["syllabic"], False, 1.0)
    part = _parts(root)[staff]
    lyrics_inject.strip_lyrics(part)
    lyrics_inject.inject(part, list(placed.values()))


def apply_changes_by_staff(root: ET.Element, changes: list[dict]) -> None:
    """apply_changes for changes that span several staves: each goes to the staff of its span."""
    for staff in sorted({c["span"]["staff"] for c in changes}):
        apply_changes(root, [c for c in changes if c["span"]["staff"] == staff], staff)


def flag_conflicts(root: ET.Element, changes: list[dict]) -> list[dict]:
    """Changes with `conflict` set where the score no longer holds the old value the pass saw (decision 6)."""
    seen: dict[int, dict] = {}
    out = []
    for c in changes:
        staff = c["span"]["staff"]
        if staff not in seen:
            seen[staff] = current_lyrics(root, staff)
        conflict = seen[staff].get((c["verse"], c["measure"], c["onset"])) != c["old"]
        out.append({**c, "conflict": conflict, "ticked": c["ticked"] and not conflict})
    return out


def save_draft(d: Path, score: Path, route: Route, spans: list[dict], result: dict, revision: int) -> dict:
    root = ET.parse(score).getroot()
    result = {**result, "changes": flag_conflicts(root, result["changes"])}  # the score may have changed while the model answered
    apply_changes_by_staff(root, result["changes"])
    ET.ElementTree(root).write(d / DRAFT_SCORE, encoding="UTF-8", xml_declaration=True)
    draft = {"id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"), "created": datetime.now(timezone.utc).isoformat(),
             "route": {"kind": "api", "model": route.model}, "base_revision": revision, "spans": spans, **result}
    (d / DRAFT).write_text(json.dumps(draft, ensure_ascii=False, indent=1))
    return draft


def load_draft(d: Path) -> dict | None:
    p = d / DRAFT
    return json.loads(p.read_text()) if p.exists() else None


def drop_draft(d: Path) -> None:
    for name in (DRAFT, DRAFT_SCORE):
        (d / name).unlink(missing_ok=True)
