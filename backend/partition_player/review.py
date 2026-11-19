"""The editor's server side (ADR 0005): the review record, saving an edited document, reverting.

review.json: {"doubts": [...], "checked": [measure indices], "revision": n, "form": null | {...},
"lines": [...], "unders": [...], "tempo": null | bpm, "model_readings": [...]}. The
form (plan 0004) is how the page is played: sections over measure ranges and passes through them,
null when the automatic form (the repeat signs and the verses) is what plays. A pass may carry
`times` and a section a `fromOnset` / `toOnset` beat inside its first and last measure (plan 0007);
all three are optional and old files simply lack them. `lines` and `unders` (plan 0011) are how the
page sounds: which instrument each staff plays over which measures, and which staff goes on playing a
stretch of measures underneath the form. Both are playback only — nothing in them touches the
document — and both are empty for every page recognized before ADR 0008. The document is edited in
the browser and saved whole; the server validates it, recomputes the statistics, re-reads the lyric
placements and bumps the revision. A save must name the revision it started from, so two browsers
cannot silently overwrite each other.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .jobs import Job, JobStore
from .pipeline.lyrics import inject as lyrics_inject
from .pipeline.postprocess import PostprocessError, ScoreStats, inspect

MAX_DOCUMENT = 4_000_000  # bytes of MusicXML a save may carry; a page is 20 to 100 KB


class InvalidDocument(ValueError):
    pass


class StaleRevision(ValueError):
    def __init__(self, current: int):
        super().__init__(f"the score was changed elsewhere (revision {current})")
        self.current = current


def load(d: Path) -> dict:
    p = d / "review.json"
    if not p.exists():  # a score recognized before the editor existed
        return {"doubts": [], "checked": [], "revision": 0, "form": None, "lines": [], "unders": [], "model_readings": [], "tempo": None}
    data = json.loads(p.read_text())
    # Every key is named here or it is dropped at the next save: that is how the form's times and
    # onsets were silently stripped once (plan 0008), and why `lines` and `unders` are listed the
    # same day they are first written.
    return {"doubts": data.get("doubts", []), "checked": data.get("checked", []), "revision": int(data.get("revision", 0)),
            "form": data.get("form"), "lines": data.get("lines", []), "unders": data.get("unders", []),
            "tempo": data.get("tempo"),
            "model_readings": data.get("model_readings", [])}  # ADR 0010: what the model proposed, kept with the job


MIN_TEMPO, MAX_TEMPO = 40, 400  # bpm. The page's slider is 40 to 180 and widens to the score's own marking; 400 is past any real one


def set_tempo(d: Path, tempo: object) -> None:
    """The tempo the player was last left at (player controls): playback only, so the revision does not
    move and the score is not edited. None forgets it, and the page falls back to the score's own marking.
    Raises InvalidDocument for anything but a whole number of bpm in range. Caller holds the store lock."""
    if tempo is not None and (type(tempo) is not int or not MIN_TEMPO <= tempo <= MAX_TEMPO):
        raise InvalidDocument(f"the tempo must be a whole number of beats per minute from {MIN_TEMPO} to {MAX_TEMPO}")
    current = load(d)
    current["tempo"] = tempo
    (d / "review.json").write_text(json.dumps(current, indent=1))


MAX_ONSET = 16.0   # whole notes from a measure start: far past any real measure, the browser clamps to its length
MAX_TIMES = 50     # how often one pass may repeat itself
MAX_LINES = 24     # staves on a page: a piano page has two, an orchestral score is not what this app is
MAX_VOICINGS = 200  # instrument ranges over those staves
MAX_UNDERS = 8     # lines going on underneath at once
MAX_UNDER_TIMES = 20  # rounds a line may be asked to play; absent means it fills the form's time

# The instruments a line may be given (plan 0011, step 2). The browser holds the same list with the
# samples; the server only has to refuse a name that is not one of them.
INSTRUMENTS = frozenset({
    "piano", "flute", "clarinet", "saxophone", "trumpet", "french-horn", "violin", "cello", "harp",
    "guitar-nylon", "organ", "harmonium", "xylophone",
})


def _section(sec: dict) -> dict:
    """One section: measures, and optionally the beat inside them where it starts and ends (plan 0007)."""
    out = {"name": str(sec.get("name", ""))[:40], "from": int(sec["from"]), "to": int(sec["to"])}
    for edge in ("fromOnset", "toOnset"):
        if sec.get(edge) is not None:
            onset = float(sec[edge])
            if not 0 <= onset <= MAX_ONSET:
                raise InvalidDocument(f"a section {edge} of {onset} is outside a measure")
            out[edge] = onset
    return out


def _pass(ps: dict) -> dict:
    out = {"section": int(ps["section"]), "verse": None if ps.get("verse") is None else int(ps["verse"])}
    if ps.get("times") is not None:
        times = int(ps["times"])
        if not 1 <= times <= MAX_TIMES:
            raise InvalidDocument(f"a pass played {times} times is outside 1 to {MAX_TIMES}")
        out["times"] = times
    return out


def validate_form(form: dict | None, measure_count: int) -> dict | None:
    """The form as the browser sends it, checked for shape and measure bounds; None is the automatic form.

    Every field is copied out by name, so a field this server does not know is dropped rather than
    stored: `times` and the two onsets (plan 0007) are listed here for that reason.
    """
    if form is None:
        return None
    try:
        sections = [_section(sec) for sec in form["sections"]]
        passes = [_pass(ps) for ps in form["passes"]]
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise InvalidDocument(f"the form is malformed: {e}") from e
    if len(sections) > 200 or len(passes) > 1000 or sum(ps.get("times", 1) for ps in passes) > 1000:
        raise InvalidDocument("the form is too long")
    for sec in sections:
        if not 0 <= sec["from"] <= sec["to"] < measure_count:
            raise InvalidDocument(f"section {sec['name']!r} covers measures {sec['from'] + 1} to {sec['to'] + 1}, outside the score")
        if sec["from"] == sec["to"] and sec.get("toOnset") is not None and sec["toOnset"] <= sec.get("fromOnset", 0.0):
            raise InvalidDocument(f"section {sec['name']!r} ends before it starts")
    for ps in passes:
        if not 0 <= ps["section"] < len(sections):
            raise InvalidDocument("a pass names a section that does not exist")
        if ps["verse"] is not None and not 1 <= ps["verse"] <= 50:
            raise InvalidDocument("a pass names a verse outside 1 to 50")
    return {"sections": sections, "passes": passes}


def _instrument(name: object) -> str:
    text = str(name)
    if text not in INSTRUMENTS:
        raise InvalidDocument(f"{text!r} is not an instrument this app plays")
    return text


def _measures(record: dict, measure_count: int, what: str) -> tuple[int, int]:
    first, last = int(record["from"]), int(record["to"])
    if not 0 <= first <= last < measure_count:
        raise InvalidDocument(f"{what} covers measures {first + 1} to {last + 1}, outside the score")
    return first, last


def validate_lines(lines: object, measure_count: int) -> list[dict]:
    """Which instrument each staff plays, over which measures (plan 0011). An empty list is a page
    played on the piano, which is every page recognized before ADR 0008."""
    if lines is None:
        return []
    if not isinstance(lines, list):
        raise InvalidDocument("the lines are malformed: not a list")
    if len(lines) > MAX_VOICINGS:
        raise InvalidDocument("too many instrument ranges")
    out = []
    try:
        for voicing in lines:
            first, last = _measures(voicing, measure_count, "an instrument range")
            line = int(voicing["line"])
            if not 0 <= line < MAX_LINES:
                raise InvalidDocument(f"line {line} is not a staff of this page")
            out.append({"line": line, "from": first, "to": last, "instrument": _instrument(voicing["instrument"])})
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        if isinstance(e, InvalidDocument):
            raise
        raise InvalidDocument(f"the lines are malformed: {e}") from e
    return out


def validate_unders(unders: object, measure_count: int, sections: int = 0) -> list[dict]:
    """The lines that go on playing underneath the form (plan 0011): a stretch of measures of one
    staff, played from a measure on.

    `times` is how many rounds it plays, absent for "fill whatever the form leaves"; `startSection`
    anchors the start to a section of the form instead of to a bare measure, and is checked against
    the form saved in the same request."""
    if unders is None:
        return []
    if not isinstance(unders, list):
        raise InvalidDocument("the unders are malformed: not a list")
    if len(unders) > MAX_UNDERS:
        raise InvalidDocument("too many lines going on underneath")
    out = []
    try:
        for under in unders:
            first, last = _measures(under, measure_count, "a line going on underneath")
            line = int(under["line"])
            start = int(under["startAt"])
            if not 0 <= line < MAX_LINES:
                raise InvalidDocument(f"line {line} is not a staff of this page")
            if not 0 <= start < measure_count:
                raise InvalidDocument(f"a line going on underneath starts at measure {start + 1}, outside the score")
            record = {"line": line, "from": first, "to": last, "startAt": start,
                      "instrument": _instrument(under["instrument"])}
            if under.get("times") is not None:
                times = int(under["times"])
                if not 1 <= times <= MAX_UNDER_TIMES:
                    raise InvalidDocument(f"a line going on underneath plays {times} times, outside 1 to {MAX_UNDER_TIMES}")
                record["times"] = times
            if under.get("startSection") is not None:
                section = int(under["startSection"])
                if not 0 <= section < sections:
                    raise InvalidDocument("a line going on underneath names a section that does not exist")
                record["startSection"] = section
            out.append(record)
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        if isinstance(e, InvalidDocument):
            raise
        raise InvalidDocument(f"the unders are malformed: {e}") from e
    return out


def bump(d: Path, model_readings: list[dict] | None = None) -> int:
    """A change to the document made outside the editor (the lyrics panel, applying a model draft): the
    revision moves on, and model readings, if given, are added to the stored ones. Caller holds the store lock."""
    current = load(d)
    current["revision"] += 1
    current["model_readings"] = current["model_readings"] + (model_readings or [])
    (d / "review.json").write_text(json.dumps(current, indent=1))
    return current["revision"]


def reject_reading(d: Path, reading_id: str) -> bool:
    """Hide a model reading: its status becomes rejected, the record stays (ADR 0010). False when there
    is no such reading. The revision does not move: the document is unchanged. Caller holds the store lock."""
    current = load(d)
    found = False
    for r in current["model_readings"]:
        if r.get("id") == reading_id:
            r["status"], found = "rejected", True
    if found:
        (d / "review.json").write_text(json.dumps(current, indent=1))
    return found


def state(store: JobStore, job_id: str) -> dict:
    d = store.dir(job_id)
    s = load(d)
    layout = d / "layout.json"
    s["layout"] = json.loads(layout.read_text()) if layout.exists() else None
    s["has_image"] = (d / "review.webp").exists()
    s["has_original"] = (d / "original.musicxml").exists()
    return s


def validate(musicxml: str) -> ET.ElementTree:
    if len(musicxml.encode("utf-8")) > MAX_DOCUMENT:
        raise InvalidDocument("document too large")
    try:
        root = ET.fromstring(musicxml)
    except ET.ParseError as e:
        raise InvalidDocument(f"not well-formed XML: {e}") from e
    tree = ET.ElementTree(root)
    try:
        inspect(tree)
    except (PostprocessError, ValueError, ZeroDivisionError) as e:
        raise InvalidDocument(str(e)) from e
    return tree


def _stats(tree: ET.ElementTree, previous: dict | None) -> dict:
    """The job's statistics after an edit: counts from the document, recognition-time fields kept."""
    fresh = inspect(tree)
    root = tree.getroot()
    out = dict(previous or asdict(ScoreStats()))
    out.update({"parts": fresh.parts, "measures": fresh.measures, "notes": fresh.notes, "rests": fresh.rests,
                "warnings": fresh.warnings, "doubts": fresh.doubts,
                "chords": sum(1 for _ in root.iter("harmony")), "lyrics_syllables": sum(1 for _ in root.iter("lyric"))})
    return out


def save(store: JobStore, job: Job, musicxml: str, checked: list[int], revision: int, doubts: list[dict] | None,
         form: dict | None = None, lines: object = None, unders: object = None) -> dict:
    """Validate, write, re-read the lyrics, update the statistics, bump the revision. Returns the new
    review state with the live check under "check" and the statistics under "stats"."""
    tree = validate(musicxml)
    measure_count = len(tree.getroot().find("part").findall("measure"))
    form = validate_form(form, measure_count)
    voicings = validate_lines(lines, measure_count)
    going_under = validate_unders(unders, measure_count, len(form["sections"]) if form else 0)
    d = store.dir(job.id)
    with store.lock:
        current = load(d)
        if revision != current["revision"]:
            raise StaleRevision(current["revision"])
        score = d / "score.musicxml"
        tmp = d / "score.musicxml.tmp"
        tree.write(tmp, encoding="UTF-8", xml_declaration=True)
        tmp.replace(score)
        record = {"doubts": doubts if doubts is not None else current["doubts"],
                  "checked": sorted(set(int(c) for c in checked)), "revision": current["revision"] + 1, "form": form,
                  "lines": voicings if lines is not None else current["lines"],
                  "unders": going_under if unders is not None else current["unders"],
                  "tempo": current["tempo"],
                  "model_readings": current["model_readings"]}
        (d / "review.json").write_text(json.dumps(record, indent=1))
        placed = lyrics_inject.read_placements(score)
        lyrics_file = d / "lyrics.json"
        old = json.loads(lyrics_file.read_text()) if lyrics_file.exists() else {}
        lyrics_inject.save(lyrics_file, placed, old.get("warnings", []), old.get("seen", []))
        stats = _stats(tree, (job.result or {}).get("stats"))
    job.result = {**(job.result or {}), "stats": stats}
    job.edited_at = datetime.now(timezone.utc).isoformat()
    store.save(job)
    out = state(store, job.id)
    out["check"] = stats["doubts"]
    out["stats"] = stats
    return out


def revert(store: JobStore, job: Job) -> dict:
    """The score as recognized, back in place; the checked list is cleared, the form is the automatic
    one again and the page is back on the piano (plan 0011: the sounds belong to the edited score)."""
    d = store.dir(job.id)
    original = d / "original.musicxml"
    if not original.exists():
        raise FileNotFoundError("no recognized version kept for this score")
    with store.lock:
        current = load(d)
        tmp = d / "score.musicxml.tmp"
        tmp.write_bytes(original.read_bytes())
        tmp.replace(d / "score.musicxml")
        (d / "review.json").write_text(json.dumps(
            {**current, "checked": [], "revision": current["revision"] + 1, "form": None, "lines": [], "unders": []}, indent=1))
        tree = ET.parse(d / "score.musicxml")
        placed = lyrics_inject.read_placements(d / "score.musicxml")
        lyrics_file = d / "lyrics.json"
        old = json.loads(lyrics_file.read_text()) if lyrics_file.exists() else {}
        lyrics_inject.save(lyrics_file, placed, old.get("warnings", []), old.get("seen", []))
        stats = _stats(tree, (job.result or {}).get("stats"))
    job.result = {**(job.result or {}), "stats": stats}
    job.edited_at = None
    store.save(job)
    out = state(store, job.id)
    out["check"] = stats["doubts"]
    out["stats"] = stats
    return out
