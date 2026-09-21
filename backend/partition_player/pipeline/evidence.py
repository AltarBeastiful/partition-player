"""A second reading of the same staff, and how much a disagreement is worth (plan 0008).

Two stages read every page: the segmentation net finds noteheads as pixels, and the transformer
decodes the staff into symbols. Only the transformer's answer becomes the score. The pixel stage's
answer is thrown away with `geometry.json` when the job ends, although it is an independent reading
of the same ink — the one thing that can contradict a pitch, which the measure arithmetic of
`postprocess.py` never can, because a wrong pitch changes no duration.

One source was built from it, measured and taken out again: the staff position of each detected
head against the pitch the score gives. On the benchmark it landed on a wrong measure 2 times in 36
with the position read off the staff lines, and 0 times in 8 with the detector's own dewarped one —
it is noise on a photographed page, at any normalisation tried (see `bench/RESULTS.md`, "How sure").
The position is still written into `evidence.json`, where it costs nothing and is there for a reader
that can use it; nothing reads it today.

This module keeps that second reading (`evidence.json`) and rates the places where the two disagree.
It never changes a note of the output. The rating is deliberately hard to satisfy: the page that
prompted the plan is one where the pixel stage was the one in error — an ink blot over a notehead,
read as two heads where the print has one and the transformer was right — so a lone disagreement is
worth nothing, and what supports the reading is counted against it.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from bisect import bisect_right
from dataclasses import dataclass, field

from .layout import estimated_bounds, system_spans

STACK_UNITS = 0.45   # noteheads closer than this in x (in interlines) share a stem: one chord
GRID_SLACK = 0.25    # a real engraved head sits this close to a whole step of the staff grid
STEPS = "CDEFGAB"


# --- the second reading, kept ------------------------------------------------------------------

def heads_by_measure(geometry: dict, measure_count: int) -> list[list[dict]]:
    """The noteheads the pixel stage found, per measure of the final score.

    Each is `{x, y, size, position, staff, unit}`; `position` is the detector's own staff position
    in half interlines, `size` the notehead's height in pixels. The measure a head belongs to comes
    from `layout.system_spans`, the same split the review strip uses, so the two cannot drift apart.
    """
    out: list[list[dict]] = [[] for _ in range(max(measure_count, 0))]
    staves = geometry.get("staves", [])
    for i, first, n, bounds in system_spans(geometry, measure_count):
        for st in staves:
            if st.get("system") != i:
                continue
            unit = float(st.get("unit") or 0) or 1.0
            for head in st.get("noteheads", []):
                x = float(head[0])
                k = bisect_right(bounds, x) - 1
                if not (0 <= k < n) or not (0 <= first + k < measure_count):
                    continue
                y = float(head[1])
                bottom = float(st.get("bottom_y", y))
                out[first + k].append({
                    "x": x, "y": y,
                    "size": float(head[2]) if len(head) > 2 else 0.0,
                    # the detector's own staff position when it was recorded; else read off the
                    # bottom line, which lands within about half a step of it
                    "position": int(head[3]) if len(head) > 3 else round((bottom - y) / (unit / 2)),
                    "staff": int(st.get("index", 0)), "unit": unit,
                })
    for heads in out:
        heads.sort(key=lambda h: (h["x"], -h["y"]))
    return out


def collect(geometry: dict, measure_count: int) -> dict:
    """`evidence.json`: what the pixel stage read, small enough to keep beside the score."""
    systems = geometry.get("systems", [])
    return {
        "heads": [[[round(h["x"], 1), round(h["y"], 1), round(h["size"], 1), h["position"], h["staff"]] for h in m]
                  for m in heads_by_measure(geometry, measure_count)],
        "estimated": sorted({first + k for i, first, n, _ in system_spans(geometry, measure_count)
                             if i < len(systems) and estimated_bounds(systems[i]) for k in range(n)}),
        "unit": round(float(systems[0].get("unit") or 0), 2) if systems else 0.0,
    }


def heads_of(evidence: dict, measure: int) -> list[dict]:
    """Read back what `collect` wrote for one measure."""
    rows = (evidence.get("heads") or [])
    if not (0 <= measure < len(rows)):
        return []
    return [{"x": r[0], "y": r[1], "size": r[2], "position": r[3], "staff": r[4]} for r in rows[measure]]


# --- what the transformer wrote ------------------------------------------------------------------

@dataclass
class Emitted:
    """The notes of one measure as the score has them, with the staff step of each."""
    count: int = 0                      # noteheads, chord members included
    chords: int = 0                     # notes sharing a stem with the one before
    steps: list[int] = field(default_factory=list)   # where each sits on the staff, for a reader yet to come


def _diatonic(step: str, octave: int) -> int:
    return octave * 7 + STEPS.index(step)


def clef_base(part: ET.Element) -> int:
    """The diatonic index of the bottom staff line, from the first clef (G2 -> E4, F4 -> G2)."""
    clef = part.find(".//clef")
    sign = (clef.findtext("sign") if clef is not None else None) or "G"
    line = int((clef.findtext("line") if clef is not None else None) or (2 if sign == "G" else 4))
    anchor = {"G": _diatonic("G", 4), "F": _diatonic("F", 3), "C": _diatonic("C", 4)}.get(sign, _diatonic("G", 4))
    return anchor - 2 * (line - 1)


def emitted_by_measure(part: ET.Element) -> list[Emitted]:
    """Per measure: how many noteheads the score has and where each sits on the staff."""
    base = clef_base(part)
    out = []
    for measure in part.findall("measure"):
        e = Emitted()
        for note in measure.findall("note"):
            if note.find("rest") is not None or note.find("grace") is not None:
                continue
            e.count += 1
            if note.find("chord") is not None:
                e.chords += 1
            pitch = note.find("pitch")
            if pitch is not None:
                e.steps.append(_diatonic(pitch.findtext("step", "C").strip(), int(pitch.findtext("octave", "4").strip())) - base)
        out.append(e)
    return out


# --- comparing the two --------------------------------------------------------------------------

def stacks(heads: list[dict], unit: float) -> list[list[dict]]:
    """Noteheads grouped into the chords they would be: those sharing an x within `STACK_UNITS`."""
    groups: list[list[dict]] = []
    for h in heads:
        if groups and abs(h["x"] - groups[-1][-1]["x"]) <= STACK_UNITS * (unit or 1.0):
            groups[-1].append(h)
        else:
            groups.append([h])
    return groups


def off_grid(group: list[dict], unit: float) -> bool:
    """True when a stack's heads are not a whole number of staff steps apart — ink, not engraving."""
    if len(group) < 2 or not unit:
        return False
    ys = sorted(h["y"] for h in group)
    return any(abs(round(g := (ys[i + 1] - ys[i]) / (unit / 2)) - g) > GRID_SLACK or round(g) == 0
               for i in range(len(ys) - 1))


@dataclass
class Finding:
    """One place where the pixel stage does not read what the score says."""
    measure: int
    kind: str                            # heads_more | heads_fewer
    text: str
    demotions: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)     # shown to the user, saved with the doubt
    features: dict = field(default_factory=dict)   # for the benchmark only, never saved

    @property
    def score(self) -> int:
        """Readers that disagree, less what argues back. One reader is enough when nothing does.

        Measured (plan 0008, `bench/RESULTS.md`): one reader with nothing against it is right 0.76
        of the time on the piano pages and 2 times in 2 on the lead sheets, and marks no page that
        came back right. The two loosenings tried are both worse — letting a sound measure through
        buys 18 marks at 0.44 and 15 cry-wolf marks on lead sheets, and no magnitude of the count
        difference discriminates at all (precision is flat from |delta| 1 to 4)."""
        return 1 - len(self.demotions)


def compare(evidence: dict, emitted: list[Emitted], *, adds_up: list[bool]) -> list[Finding]:
    """Every disagreement between the pixel stage and the score, with what argues against each."""
    unit = float(evidence.get("unit") or 0.0)
    estimated = set(evidence.get("estimated") or [])
    monophonic = not any(e.chords for e in emitted)
    findings: list[Finding] = []
    for m, e in enumerate(emitted):
        heads = heads_of(evidence, m)
        if not heads:
            continue  # nothing was detected here: silence is not evidence
        groups = stacks(heads, unit)
        demotions = ["the measure's boundaries were estimated"] if m in estimated else []
        sound = m < len(adds_up) and adds_up[m]
        surplus = [g for g in groups if len(g) > 1]
        if len(heads) != e.count:
            more = len(heads) > e.count
            d = list(demotions)
            # "the measure adds up" is evidence only against a note gained or lost *in sequence*,
            # which would have changed the arithmetic. A head stacked on an existing stem adds no
            # duration, so a sound measure says nothing about it — and demoting on it anyway would
            # leave this rating speaking only where the arithmetic flag already speaks, which the
            # benchmark showed it doing: 48 of 48 marks on measures that were flagged already.
            if sound and not (more and surplus):
                d.append("the measure adds up")
            if more and surplus:
                if monophonic:
                    d.append("the page is monophonic everywhere else")
                if any(off_grid(g, unit) for g in surplus):
                    d.append("the extra head is not on the staff grid")
            findings.append(Finding(
                m, "heads_more" if more else "heads_fewer",
                f"{len(heads)} notehead{'' if len(heads) == 1 else 's'} {'was' if len(heads) == 1 else 'were'} "
                f"detected here, the score has {e.count}",
                demotions=d, detail={"heads": len(heads), "notes": e.count},
                features={"delta": len(heads) - e.count, "estimated": m in estimated, "sound": sound,
                          "monophonic": monophonic, "stacked": len(surplus),
                          "on_grid": bool(surplus) and not any(off_grid(g, unit) for g in surplus),
                          "notes": e.count, "chords": e.chords}))
    return findings


# --- the rating -----------------------------------------------------------------------------------

CHECK = 1  # the evidence against a reading, net of what supports it, at which we say something


def rate(findings: list[Finding]) -> list[dict]:
    """The findings worth showing, as doubts of level `check`. Everything quieter stays silent:
    a mark that is allowed to be wrong is a mark that cries wolf (plan 0008)."""
    out = []
    for f in findings:
        if f.score < CHECK:
            continue
        out.append({"measure": f.measure, "part": 0, "kind": f.kind, "text": f.text,
                    "level": "check", "sources": ["noteheads"], **f.detail})
    return out
