"""Counting notes fixed and notes broken against the ground truth (the gate of ADR 0010, plan 0016).

Per measure of the span, the events of the first part (notes, rests, chord tones, no grace notes) are lined up by
position. A slot is right when its event equals the ground truth's at the same position (pitch or rest, and length
in quarter notes). fixed = slots wrong before and right after; broken = slots right before and wrong after. An insert
or delete that shifts the notes after it therefore breaks them: that is the cost the gate should see.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from fractions import Fraction


def events(root: ET.Element) -> list[list[tuple]]:
    """Per measure of the first part: [("r"|"n", step, alter, octave, quarters)]."""
    part = root.find("part")
    divisions, out = 1, []
    for m in part.findall("measure"):
        for d in m.iter("divisions"):
            divisions = int(d.text or 1) or divisions
        row = []
        for n in m.findall("note"):
            if n.find("grace") is not None:
                continue
            q = Fraction(int(n.findtext("duration") or 0), divisions)
            p = n.find("pitch")
            if p is None:
                row.append(("r", "", 0, 0, q))
            else:
                row.append(("n", p.findtext("step", ""), int(p.findtext("alter") or 0), int(p.findtext("octave") or 0), q))
        out.append(row)
    return out


@dataclass
class Counts:
    comparable: bool = True
    fixed: int = 0
    broken: int = 0
    wrong_before: int = 0
    wrong_after: int = 0
    total: int = 0


def compare(truth: ET.Element, before: ET.Element, after: ET.Element, first: int, last: int) -> Counts:
    t, b, a = events(truth), events(before), events(after)
    if not (len(t) == len(b) == len(a)):
        return Counts(comparable=False)
    c = Counts()
    for i in range(first, min(last, len(t) - 1) + 1):
        for k, want in enumerate(t[i]):
            was = k < len(b[i]) and b[i][k] == want
            now = k < len(a[i]) and a[i][k] == want
            c.total += 1
            c.wrong_before += not was
            c.wrong_after += not now
            c.fixed += (not was) and now
            c.broken += was and not now
    return c


def lyrics(root: ET.Element) -> dict[tuple[int, int, int], str]:
    """{(verse, measure, onset): text} for the first part; onset = rank among sounding notes, as lyrics.json."""
    out = {}
    for mi, m in enumerate(root.find("part").findall("measure")):
        sounding = [n for n in m.findall("note") if n.find("rest") is None and n.find("grace") is None and n.find("chord") is None]
        for oi, n in enumerate(sounding):
            for ly in n.findall("lyric"):
                out[(int(ly.get("number") or 1), mi, oi)] = "".join(t.text or "" for t in ly.findall("text")) + "/" + (ly.findtext("syllabic") or "single")
    return out


def lyric_compare(truth: ET.Element, before: ET.Element, after: ET.Element, first: int, last: int) -> tuple[int, int]:
    """(syllables fixed, syllables broken) in the measures of the span."""
    t, b, a = lyrics(truth), lyrics(before), lyrics(after)
    fixed = broken = 0
    for key, want in t.items():
        if not first <= key[1] <= last:
            continue
        was, now = b.get(key) == want, a.get(key) == want
        fixed += (not was) and now
        broken += was and not now
    return fixed, broken
