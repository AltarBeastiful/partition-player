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
import base64
import binascii
from datetime import datetime, timezone
from pathlib import Path

from ..pipeline.lyrics import inject as lyrics_inject
from . import notes_pass
from .route import Route, image_type

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

MAX_PICTURE = 7_000_000    # characters of base64 picture per span
UNREADABLE = "UNREADABLE"

READ_PROMPT = (
    "The picture shows the lyrics of a song, printed or written. Copy the words exactly as they are written, "
    "letter for letter, keeping the hyphens that cut words into syllables and a blank line between verses. "
    f"Reply with the text only. If the picture holds no lyrics you can read, reply {UNREADABLE}."
)


class SpanError(ValueError):
    pass


def picture_bytes(encoded: str) -> bytes:
    """The picture of a span, decoded; SpanError unless it is a PNG, JPEG or WebP."""
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as e:
        raise SpanError("the lyrics picture is not valid base64") from e
    if image_type(data) is None:
        raise SpanError("the lyrics picture is not a PNG, JPEG or WebP image")
    return data


def read_pictures(spans: list[dict], route: Route, client=None) -> tuple[list[dict], list[dict]]:
    """Spans with a `lyrics_picture` get its text as `lyrics_source`, read by the route; a picture that cannot
    be read leaves an empty source and a dropped entry, never a guess. Returns (spans, dropped)."""
    out, dropped = [], []
    for span in spans:
        picture = span.get("lyrics_picture")
        if not picture:
            out.append(span)
            continue
        where = {"staff": span["staff"], "from": span["from"], "to": span["to"]}
        try:
            text = route.complete(READ_PROMPT, image_png=picture_bytes(picture), max_tokens=1500, client=client).strip()
        except Exception as e:  # noqa: BLE001
            text, why = "", f"the picture could not be read: the model could not be asked ({e.__class__.__name__})"
        else:
            why = "the picture could not be read: no lyrics found in it"
            if len(text) > MAX_SOURCE:
                text, why = "", "the picture could not be read: its text is too long"
        if not text or UNREADABLE in text:
            text = ""
            dropped.append({"span": where, "verse": 1, "reason": why})
        # an unread picture is a span with words that could not be had, never one to be checked for notes
        out.append({k: v for k, v in span.items() if k != "lyrics_picture"} | {"lyrics_source": text} | ({} if text else {"unreadable": True}))
    return out, dropped


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
        if notes_pass.is_notes_span(span):  # no words: notes and chords, one call
            c, i, o = notes_pass.estimate(root, [span]) if span["staff"] == 0 else (0, 0, 0)
            calls, tokens_in, tokens_out = calls + c, tokens_in + i, tokens_out + o
            continue
        source = span["lyrics_source"]
        if span.get("lyrics_picture"):  # one call to read it, then an average verse is placed
            calls += 1
            tokens_in += 1600
            tokens_out += 200
            source = "x " * 100
        for verse in verses_of(source):
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


def ask(route: Route, prompt: str, source: str, note_count: int, client=None) -> list[tuple[str, str, int]]:
    """One call and its validation; SpanError when the answer breaks a rule."""
    return parse_answer(route.complete(prompt, max_tokens=1500, client=client), source, note_count)


def run(score: Path, spans: list[dict], route: Route, client=None) -> dict:
    """Ask the model once per span and verse; returns {"changes": [...], "dropped": [...]}."""
    root = ET.parse(score).getroot()
    changes, dropped, escalated = [], [], []
    for span in spans:
        now = current_lyrics(root, span["staff"])
        notes = span_notes(root, span["staff"], span["from"], span["to"])
        where = {"staff": span["staff"], "from": span["from"], "to": span["to"]}
        if notes_pass.is_notes_span(span):
            got = notes_pass.run_span(root, span, route, client)
            changes += got["changes"]; dropped += got["dropped"]; escalated += got["escalated"]
            continue
        for verse_no, text in enumerate(verses_of(span["lyrics_source"]), start=1):
            prompt = prompt_for(root, span["staff"], notes, text)
            try:
                syls = ask(route, prompt, text, len(notes), client)
            except SpanError as e:
                # A failed validation goes once to the larger model (ticket 08); its answer is checked the same way.
                bigger = route.larger()
                if bigger is None:
                    dropped.append({"span": where, "verse": verse_no, "reason": str(e)})
                    continue
                try:
                    syls = ask(bigger, prompt, text, len(notes), client)
                except SpanError as e2:
                    dropped.append({"span": where, "verse": verse_no,
                                    "reason": f"{e}; the larger model ({bigger.model}) failed too: {e2}"})
                    continue
                except Exception as e2:  # noqa: BLE001
                    dropped.append({"span": where, "verse": verse_no, "reason": f"{e}; the larger model could not be asked: {e2.__class__.__name__}"})
                    continue
                escalated.append({"span": where, "verse": verse_no, "model": bigger.model})
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
    return {"changes": changes, "dropped": dropped, "escalated": escalated}


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


def apply_changes_by_staff(root: ET.Element, changes: list[dict]) -> list[str]:
    """apply_changes for changes that span several staves: each goes to the staff of its span. Returns the ids of
    the notes and chords changes that held (words are always written)."""
    lyric = [c for c in changes if c.get("kind", "lyric") == "lyric"]
    for staff in sorted({c["span"]["staff"] for c in lyric}):
        apply_changes(root, [c for c in lyric if c["span"]["staff"] == staff], staff)
    # notes and chords after the words: they name notes by place in the score as read, which the lyrics never move
    return notes_pass.apply_changes(root, [c for c in changes if c.get("kind") in ("notes", "chord")])


def flag_conflicts(root: ET.Element, changes: list[dict]) -> list[dict]:
    """Changes with `conflict` set where the score no longer holds the old value the pass saw (decision 6)."""
    seen: dict[int, dict] = {}
    out = []
    for c in changes:
        staff = c["span"]["staff"]
        if c.get("kind") in ("notes", "chord"):
            conflict = notes_pass.current_text(_parts(root)[0], c) != c["old"]["text"]
            out.append({**c, "conflict": conflict, "ticked": c["ticked"] and not conflict})
            continue
        if staff not in seen:
            seen[staff] = current_lyrics(root, staff)
        conflict = seen[staff].get((c["verse"], c["measure"], c["onset"])) != c["old"]
        out.append({**c, "conflict": conflict, "ticked": c["ticked"] and not conflict})
    return out


def save_draft(d: Path, score: Path, route: Route, spans: list[dict], result: dict, revision: int, kind: str = "api") -> dict:
    root = ET.parse(score).getroot()
    result = {**result, "changes": flag_conflicts(root, result["changes"])}  # the score may have changed while the model answered
    apply_changes_by_staff(root, result["changes"])
    ET.ElementTree(root).write(d / DRAFT_SCORE, encoding="UTF-8", xml_declaration=True)
    draft = {"id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"), "created": datetime.now(timezone.utc).isoformat(),
             "route": {"kind": kind, "model": route.model}, "base_revision": revision, "spans": spans, **result}
    (d / DRAFT).write_text(json.dumps(draft, ensure_ascii=False, indent=1))
    return draft


def load_draft(d: Path) -> dict | None:
    p = d / DRAFT
    return json.loads(p.read_text()) if p.exists() else None


def drop_draft(d: Path) -> None:
    for name in (DRAFT, DRAFT_SCORE):
        (d / name).unlink(missing_ok=True)
