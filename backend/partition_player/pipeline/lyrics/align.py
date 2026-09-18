"""Put each syllable under its note (ADR 0004, decision 4).

Onsets are the score's notes (rests, grace notes and chord tones excluded), given an x from the
detected noteheads when a measure's notehead count matches its note count, else spread by proportion,
exactly as the chord stage does. A verse row is then aligned to the onsets of its staff by a monotone
dynamic programme: match a syllable to an onset (cost: horizontal distance in interlines, at most
MAX_DIST), skip an onset (a melisma; cheap when the previous syllable has an extender; free before
the first and after the last syllable), or drop a syllable (a spurious OCR token; expensive unless
the token is doubtful). The row's drift against the notes is fitted robustly and removed first. A row
whose alignment is poor is not lyrics and is reported instead of written.
"""
from __future__ import annotations

import statistics
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fractions import Fraction

from ..chords.place import boundaries, measure_infos, system_runs
from .grammar import Row, Syllable, link_systems, rows, syllables

MAX_DIST = 3.0
SKIP_COST = 1.5
SKIP_AFTER_EXTENDER = 0.2
DROP_BASE, DROP_PER_CONFIDENCE = 2.0, 3.0
ANCHOR_OFFSET = 0.25       # interlines to the right of the syllable's left edge
MAX_MEAN_COST = 2.0        # per syllable, else the row is not lyrics
MIN_MATCHED = 0.6          # fraction of a row's syllables that must find a note
CHORD_TONE_UNITS = 0.5     # noteheads closer than this in x are one chord


@dataclass
class Onset:
    measure: int      # 0-based index over the part's measures
    index: int        # 0-based among the sounding onsets of that measure
    x: float
    quarter: Fraction


@dataclass
class Placement:
    verse: int
    measure: int
    onset: int
    text: str
    syllabic: str
    extend: bool
    confidence: float
    staff: int = -1   # index of the staff whose band it was read from (for the polish step)


@dataclass
class LyricsResult:
    placed: list[Placement] = field(default_factory=list)
    verses: int = 0
    read: int = 0                       # syllables read in accepted rows
    warnings: list[str] = field(default_factory=list)
    seen: list[dict] = field(default_factory=list)   # rows and syllables not used, for the UI


# ---- onsets ---------------------------------------------------------------------------------------

def group_chords(xs: list[float], unit: float) -> list[float]:
    out: list[float] = []
    for x in sorted(xs):
        if out and x - out[-1] < CHORD_TONE_UNITS * unit:
            out[-1] = (out[-1] + x) / 2
        else:
            out.append(x)
    return out


def onsets_for_system(system: dict, noteheads: list[float], infos, run: tuple[int, int], warnings: list[str]) -> list[Onset]:
    start, end = run
    n = end - start
    if n <= 0:
        return []
    unit = system["unit"]
    heads = group_chords(noteheads, unit)
    geo = dict(system, notes=heads)
    edges = boundaries(geo, n, warnings, [len(infos[start + k].onsets) for k in range(n)])
    out: list[Onset] = []
    for k in range(n):
        info = infos[start + k]
        inside = [x for x in heads if edges[k] <= x < edges[k + 1]]
        if len(inside) == len(info.onsets):
            xs = inside
        else:
            first = inside[0] - 0.5 * unit if inside else edges[k]
            span = max(edges[k + 1] - first, unit)
            xs = [first + float(q / info.length) * span for q in info.onsets]
        for j, (x, q) in enumerate(zip(xs, info.onsets)):
            out.append(Onset(start + k, j, x, q))
    return out


# ---- the dynamic programme ------------------------------------------------------------------------

def _align(anchors: list[float], syls: list[Syllable], onsets: list[Onset], unit: float) -> tuple[float, list[int | None]]:
    """Returns (total cost, onset index per syllable or None when dropped)."""
    m, n = len(syls), len(onsets)
    INF = float("inf")
    D = [[INF] * (n + 1) for _ in range(m + 1)]
    B: list[list[tuple[int, int] | None]] = [[None] * (n + 1) for _ in range(m + 1)]
    for j in range(n + 1):
        D[0][j] = 0.0   # leading skips are free
        B[0][j] = (0, j - 1) if j else None
    for i in range(1, m + 1):
        s = syls[i - 1]
        drop = DROP_BASE + DROP_PER_CONFIDENCE * s.confidence
        skip = SKIP_AFTER_EXTENDER if s.extend else SKIP_COST   # skipping after syllable i-1 (= s)
        for j in range(n + 1):
            best, back = D[i - 1][j] + drop, (i - 1, j)     # drop syllable i-1
            if j >= 1:
                d = abs(anchors[i - 1] - onsets[j - 1].x) / unit
                if d <= MAX_DIST and D[i - 1][j - 1] + d < best:
                    best, back = D[i - 1][j - 1] + d, (i - 1, j - 1)
                cost = 0.0 if i == m else skip
                if D[i][j - 1] + cost < best:
                    best, back = D[i][j - 1] + cost, (i, j - 1)
            D[i][j], B[i][j] = best, back
    # trailing skips are free: end anywhere after the last syllable
    j = min(range(n + 1), key=lambda k: D[m][k])
    total = D[m][j]
    assign: list[int | None] = [None] * m
    i = m
    while i > 0 and B[i][j] is not None:
        pi, pj = B[i][j]
        if pi == i - 1 and pj == j - 1:
            assign[i - 1] = j - 1
        i, j = pi, pj
    return total, assign


def _drift(anchors: list[float], syls: list[Syllable], onsets: list[Onset], assign: list[int | None]) -> tuple[float, float]:
    """Robust linear fit of (anchor - onset x) against onset x: (intercept, slope)."""
    pts = [(onsets[j].x, anchors[i] - onsets[j].x) for i, j in enumerate(assign) if j is not None]
    if len(pts) < 4:
        return 0.0, 0.0
    slopes = [(y2 - y1) / (x2 - x1) for k, (x1, y1) in enumerate(pts) for (x2, y2) in pts[k + 1:] if x2 - x1 > 1]
    slope = statistics.median(slopes) if slopes else 0.0
    intercept = statistics.median(y - slope * x for x, y in pts)
    return intercept, slope


def align_row(syls: list[Syllable], onsets: list[Onset], unit: float) -> tuple[float, list[int | None]]:
    anchors = [s.x_left + ANCHOR_OFFSET * unit for s in syls]
    cost, assign = _align(anchors, syls, onsets, unit)
    a, b = _drift(anchors, syls, onsets, assign)
    if a or b:
        corrected = [x - (a + b * x) for x in anchors]
        cost2, assign2 = _align(corrected, syls, onsets, unit)
        if cost2 < cost:
            cost, assign = cost2, assign2
    return cost, assign


# ---- driver ---------------------------------------------------------------------------------------

def place_lyrics(tree: ET.ElementTree, geometry: dict) -> LyricsResult:
    result = LyricsResult()
    parts = tree.getroot().findall("part")
    systems = geometry.get("systems", [])
    staves = geometry.get("staves", [])
    if not parts or not staves:
        return result
    infos_by_part = [measure_infos(p) for p in parts]
    runs_by_part = []
    for p in parts:
        runs, warn = system_runs(p, [s.get("measures", 0) for s in systems])
        runs_by_part.append(runs)
    rows_by_staff: dict[int, list[Row]] = {}
    for st in staves:
        if st["voice"] >= len(parts) or st["system"] >= len(systems):
            continue
        heads_x = [x for x, _ in st["noteheads"]]
        note_range = (min(heads_x), max(heads_x)) if len(heads_x) >= 2 else None
        rws, rejected = rows(st["words"], note_range)
        for r in rejected:
            result.seen.append({"staff": st["index"] + 1, "text": r.text, "reason": r.reason})
        for r in rws:
            r.syllables = syllables(r)
        rows_by_staff[st["index"]] = rws
    # words cut at a system's end continue in the next system (same voice)
    for v in {st["voice"] for st in staves}:
        chain = [rows_by_staff.get(st["index"], []) for st in staves if st["voice"] == v]
        link_systems(chain)
    for st in staves:
        rws = rows_by_staff.get(st["index"])
        if not rws:
            continue
        part_index = st["voice"]
        infos, runs = infos_by_part[part_index], runs_by_part[part_index]
        system = systems[st["system"]]
        if st["system"] >= len(runs):
            continue
        onsets = onsets_for_system(dict(system, min_x=st["min_x"], max_x=st["max_x"]), [x for x, _ in st["noteheads"]], infos, runs[st["system"]], result.warnings)
        if not onsets:
            continue
        unit = system["unit"]
        for row in rws:
            syls = row.syllables
            if not syls:
                continue
            cost, assign = align_row(syls, onsets, unit)
            matched = sum(1 for a in assign if a is not None)
            text = " ".join(s.text for s in syls)
            if matched == 0 or cost / len(syls) > MAX_MEAN_COST or matched < MIN_MATCHED * len(syls):
                result.seen.append({"staff": st["index"] + 1, "text": text, "reason": f"does not line up with the notes (verse {row.verse})"})
                continue
            result.read += len(syls)
            result.verses = max(result.verses, row.verse)
            for s, j in zip(syls, assign):
                if j is None:
                    result.seen.append({"staff": st["index"] + 1, "text": s.text, "reason": f"no note for it (verse {row.verse})"})
                    continue
                o = onsets[j]
                result.placed.append(Placement(row.verse, o.measure, o.index, s.text, s.syllabic, s.extend, round(s.confidence, 3), st["index"]))
    result.placed.sort(key=lambda p: (p.verse, p.measure, p.onset))
    return result
