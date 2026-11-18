"""MusicXML <lyric> elements and the lyrics.json record (ADR 0004, decisions 5 and 6).

A placement names a note by measure index and onset index (its rank among the measure's sounding
onsets: rests, grace notes and chord tones do not count), which survives the post-processing that
pads measures and inserts the pickup rest. `rewrite` strips every <lyric> and writes the given ones,
leaving <harmony> and everything else untouched, so a user's correction never re-runs recognition.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path

from .align import Placement

ELISION = "‿"


def sounding_notes(measure: ET.Element) -> list[ET.Element]:
    return [n for n in measure.findall("note")
            if n.find("rest") is None and n.find("grace") is None and n.find("chord") is None]


def strip_lyrics(part: ET.Element) -> int:
    removed = 0
    for note in part.iter("note"):
        for lyric in note.findall("lyric"):
            note.remove(lyric)
            removed += 1
    return removed


def lyric_element(p: Placement) -> ET.Element:
    el = ET.Element("lyric", number=str(p.verse))
    parts = p.text.split(ELISION)
    for k, piece in enumerate(parts):
        if k > 0:
            ET.SubElement(el, "elision").text = ELISION
        ET.SubElement(el, "syllabic").text = p.syllabic if k == len(parts) - 1 else "single"
        ET.SubElement(el, "text").text = piece
    if p.extend:
        ET.SubElement(el, "extend", type="start")
    return el


def _insert_lyric(note: ET.Element, lyric: ET.Element) -> None:
    """<lyric> comes after <notations> and before <play>/<listen> in a MusicXML note."""
    children = list(note)
    after = max((i for i, c in enumerate(children) if c.tag in ("notations", "lyric")), default=None)
    if after is not None:
        note.insert(after + 1, lyric)
        return
    before = next((i for i, c in enumerate(children) if c.tag in ("play", "listen")), None)
    if before is not None:
        note.insert(before, lyric)
    else:
        note.append(lyric)


def inject(part: ET.Element, placed: list[Placement]) -> int:
    measures = part.findall("measure")
    written = 0
    for p in sorted(placed, key=lambda p: (p.measure, p.onset, p.verse)):
        if p.measure >= len(measures):
            continue
        notes = sounding_notes(measures[p.measure])
        if p.onset >= len(notes):
            continue
        _insert_lyric(notes[p.onset], lyric_element(p))
        written += 1
    return written


def rewrite(score: Path, placed: list[Placement], part_index: int = 0) -> int:
    """Replace the lyrics of `score` in place; returns the number written."""
    tree = ET.parse(score)
    parts = tree.getroot().findall("part")
    if not parts:
        return 0
    part = parts[min(part_index, len(parts) - 1)]
    strip_lyrics(part)
    written = inject(part, placed)
    tree.write(score, encoding="UTF-8", xml_declaration=True)
    return written


def onset_counts(score: Path, part_index: int = 0) -> list[int]:
    """Sounding onsets per measure, for the editor's counts."""
    tree = ET.parse(score)
    parts = tree.getroot().findall("part")
    if not parts:
        return []
    return [len(sounding_notes(m)) for m in parts[min(part_index, len(parts) - 1)].findall("measure")]


def save(path: Path, placed: list[Placement], warnings: list[str], seen: list[dict]) -> None:
    path.write_text(json.dumps({"syllables": [asdict(p) for p in placed], "warnings": warnings, "seen": seen}, ensure_ascii=False, indent=1))


def load(path: Path) -> list[Placement]:
    data = json.loads(path.read_text())
    return [Placement(**s) for s in data.get("syllables", [])]


def read_placements(score: Path, part_index: int = 0) -> list[Placement]:
    """The placements a document holds, read back from its <lyric> elements: after the editor has
    changed the notes (ADR 0005) lyrics.json is rebuilt from this, so the lyrics panel keeps showing
    what the score has."""
    tree = ET.parse(score)
    parts = tree.getroot().findall("part")
    if not parts:
        return []
    placed: list[Placement] = []
    for m, measure in enumerate(parts[min(part_index, len(parts) - 1)].findall("measure")):
        for o, note in enumerate(sounding_notes(measure)):
            for lyric in note.findall("lyric"):
                try:
                    verse = int(lyric.get("number") or 1)
                except ValueError:
                    verse = 1
                texts = [t.text or "" for t in lyric.findall("text")]
                if not texts:
                    continue
                syllabics = [s.text or "single" for s in lyric.findall("syllabic")]
                placed.append(Placement(verse, m, o, ELISION.join(texts), syllabics[-1] if syllabics else "single",
                                        lyric.find("extend") is not None, 1.0))
    return placed
