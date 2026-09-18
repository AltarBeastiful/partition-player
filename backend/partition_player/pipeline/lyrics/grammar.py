"""From OCR words to verse rows and syllables (ADR 0004, decision 3).

The grammar of engraved lyrics: rows of text under a staff, one per verse, top to bottom; a word is
split into syllables by hyphens (printed attached, "bru-", or detached, "Lors - que"); an extender
line after a syllable holds it over the following notes; a lone punctuation mark belongs to the
syllable before it; a leading "1." is a verse number; "‿" joins two syllables on one note.
Rows that do not look like lyrics (a chord line of the next system, a verse paragraph, a footer)
are rejected here by layout, and by alignment cost in `align`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..chords.grammar import parse_chord

HYPHENS = "-‐‑‒–—"
EXTENDERS = "_–—"
ELISION = "‿"
PUNCT = ",.;:!?…"
VERSE_NUMBER = re.compile(r"^\d{1,2}[.)]?$")

ROW_TOLERANCE = 0.6      # a word joins a row when its centre is within this fraction of the text height
MAX_ROW_GAP = 2.2        # rows further apart than this many text heights end the verse block
MIN_COVERAGE = 0.4       # a row must span at least this fraction of the staff's note range
CHORD_ZONE_UNITS = 5.0   # rows this close above the next staff's top line are its chord symbols
CHORD_LIKE = 0.6         # a later row whose tokens are mostly chord names is a chord line, not a verse


@dataclass
class Syllable:
    text: str
    x_left: float
    x_right: float
    confidence: float
    joins_prev: bool = False   # hyphen before it: continues a word
    joins_next: bool = False   # hyphen after it: the word goes on
    extend: bool = False       # extender line after it: held over the next note(s)
    verse: int = 1

    @property
    def syllabic(self) -> str:
        if self.joins_prev and self.joins_next:
            return "middle"
        if self.joins_next:
            return "begin"
        if self.joins_prev:
            return "end"
        return "single"


@dataclass
class Row:
    verse: int
    y_units: float
    words: list[dict]
    label: str | None = None
    syllables: list[Syllable] = field(default_factory=list)


@dataclass
class Rejected:
    text: str
    y_units: float
    reason: str


def _is_hyphen(text: str) -> bool:
    return 0 < len(text) <= 2 and all(c in HYPHENS for c in text)


def _is_extender(text: str) -> bool:
    return len(text) >= 1 and all(c in EXTENDERS for c in text) and (len(text) >= 2 or text == "_")


def chord_like(words: list[dict]) -> float:
    """Fraction of a row's words that read as chord symbols."""
    texts = [w["text"] for w in words if w["text"].strip() and not _is_hyphen(w["text"])]
    if not texts:
        return 0.0
    return sum(1 for t in texts if parse_chord(t.strip(",.;:!?")) is not None) / len(texts)


def rows(words: list[dict], note_range: tuple[float, float] | None, chord_zone_from: float | None = None) -> tuple[list[Row], list[Rejected]]:
    """Cluster words into rows by baseline; keep the rows that look like verses under this staff.
    `chord_zone_from`: y (units below the bottom line) from which rows belong to the next system's chord band."""
    if not words:
        return [], []
    words = sorted(words, key=lambda w: w["y_units"])
    height = sorted(w["height_units"] for w in words)[len(words) // 2]
    clusters: list[list[dict]] = []
    for w in words:
        if clusters and abs(w["y_units"] - _median([c["y_units"] for c in clusters[-1]])) <= ROW_TOLERANCE * height:
            clusters[-1].append(w)
        else:
            clusters.append([w])
    out: list[Row] = []
    rejected: list[Rejected] = []
    prev_y = None
    for cluster in clusters:
        cluster.sort(key=lambda w: w["x_left"])
        y = _median([w["y_units"] for w in cluster])
        text = " ".join(w["text"] for w in cluster)
        if prev_y is not None and y - prev_y > MAX_ROW_GAP * height:
            rejected.append(Rejected(text, y, "too far below the verses"))
            continue
        if chord_zone_from is not None and y >= chord_zone_from:
            rejected.append(Rejected(text, y, "in the chord band of the next system"))
            continue
        likeness = chord_like(cluster)
        if likeness >= (0.9 if not out else CHORD_LIKE) and len(cluster) >= 3:
            rejected.append(Rejected(text, y, "reads as chord symbols"))
            continue
        label = None
        if cluster and VERSE_NUMBER.match(cluster[0]["text"]):
            label = cluster[0]["text"]
            cluster = cluster[1:]
        if not cluster:
            continue
        if note_range and note_range[1] > note_range[0]:
            lo, hi = note_range
            span = min(cluster[-1]["x_right"], hi) - max(cluster[0]["x_left"], lo)
            if span / (hi - lo) < MIN_COVERAGE:
                rejected.append(Rejected(text, y, "does not span the notes"))
                continue
        prev_y = y
        out.append(Row(len(out) + 1, y, cluster, label))
    return out, rejected


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    return s[len(s) // 2]


def syllables(row: Row) -> list[Syllable]:
    """Split a row's words into syllables with their word links and extenders."""
    out: list[Syllable] = []
    pending_join = False   # a detached hyphen was seen: the next syllable continues the word
    for w in row.words:
        text = w["text"].strip()
        if not text:
            continue
        if _is_hyphen(text):
            if out:
                out[-1].joins_next = True
            pending_join = True
            continue
        if _is_extender(text):
            if out:
                out[-1].extend = True
            continue
        if text in PUNCT or all(c in PUNCT for c in text):
            if out:
                out[-1].text += text
                out[-1].x_right = w["x_right"]
            continue
        if text == ELISION:
            if out:
                out[-1].text += ELISION
            continue
        extend = bool(w.get("extend"))
        while text and text[-1] in EXTENDERS:
            text = text[:-1]
            extend = True
        parts = re.split(f"[{re.escape(HYPHENS)}]", text)
        leading = parts and parts[0] == ""
        trailing = len(parts) > 1 and parts[-1] == ""
        parts = [p for p in parts if p]
        if not parts:
            continue
        total = max(1, len(text))
        pos = w["x_left"]
        width = w["x_right"] - w["x_left"]
        for k, part in enumerate(parts):
            pw = width * len(part) / total
            syl = Syllable(part, pos, pos + pw, float(w["confidence"]), verse=row.verse)
            syl.joins_prev = (k > 0) or (k == 0 and (leading or pending_join))
            syl.joins_next = (k < len(parts) - 1) or (k == len(parts) - 1 and trailing)
            out.append(syl)
            pos += pw + width / total   # the hyphen's own width
        pending_join = False
        out[-1].extend = out[-1].extend or extend
    return out


def link_systems(rows_by_system: list[list[Row]]) -> None:
    """A word cut at the end of a system continues in the next system's same verse."""
    for prev, nxt in zip(rows_by_system, rows_by_system[1:]):
        for row in prev:
            if not row.syllables or not row.syllables[-1].joins_next:
                continue
            follow = next((r for r in nxt if r.verse == row.verse and r.syllables), None)
            if follow is not None:
                follow.syllables[0].joins_prev = True
