"""The editor's server side (ADR 0005): the review record, saving an edited document, reverting.

review.json: {"doubts": [...], "checked": [measure indices], "revision": n}. The document is edited in
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
        return {"doubts": [], "checked": [], "revision": 0}
    data = json.loads(p.read_text())
    return {"doubts": data.get("doubts", []), "checked": data.get("checked", []), "revision": int(data.get("revision", 0))}


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


def save(store: JobStore, job: Job, musicxml: str, checked: list[int], revision: int, doubts: list[dict] | None) -> dict:
    """Validate, write, re-read the lyrics, update the statistics, bump the revision. Returns the new
    review state with the live check under "check" and the statistics under "stats"."""
    tree = validate(musicxml)
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
                  "checked": sorted(set(int(c) for c in checked)), "revision": current["revision"] + 1}
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
    """The score as recognized, back in place; the checked list is cleared."""
    d = store.dir(job.id)
    original = d / "original.musicxml"
    if not original.exists():
        raise FileNotFoundError("no recognized version kept for this score")
    with store.lock:
        current = load(d)
        tmp = d / "score.musicxml.tmp"
        tmp.write_bytes(original.read_bytes())
        tmp.replace(d / "score.musicxml")
        (d / "review.json").write_text(json.dumps({**current, "checked": [], "revision": current["revision"] + 1}, indent=1))
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
