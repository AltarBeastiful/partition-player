"""The user's corrections (ADR 0004, decision 6): verses as text, in the convention every notation
program uses, to and from placements.

Convention: syllables separated by spaces or by "-" inside a word ("Lors-que nous é-tions"); "_"
after a syllable holds it over the next note (one "_" per held note); "*" skips a note without a
syllable. Recognized lyrics round-trip through this text exactly, so what the editor shows is what
the score has.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .align import Placement

ELISION = "‿"


@dataclass
class Item:
    text: str = ""
    syllabic: str = "single"
    extend: int = 0       # notes held after this syllable
    skip: bool = False    # a "*": the note gets nothing


def parse_verse(text: str) -> list[Item]:
    items: list[Item] = []
    for token in text.split():
        if re.fullmatch(r"\*+", token):
            items.extend(Item(skip=True) for _ in token)
            continue
        parts = token.split("-")
        parts = [p for p in parts if p != ""] if len(parts) > 1 else parts
        for k, piece in enumerate(parts):
            held = len(piece) - len(piece.rstrip("_"))
            piece = piece.rstrip("_")
            if not piece:
                continue
            syllabic = "single" if len(parts) == 1 else "begin" if k == 0 else "end" if k == len(parts) - 1 else "middle"
            items.append(Item(piece, syllabic, held))
    return items


def verse_text(placed: list[Placement], verse: int, order: list[tuple[int, int]]) -> str:
    """The verse as editor text, with "*" for notes skipped before it starts and "_" for held notes."""
    index = {key: i for i, key in enumerate(order)}
    syls = sorted((p for p in placed if p.verse == verse and (p.measure, p.onset) in index), key=lambda p: index[(p.measure, p.onset)])
    if not syls:
        return ""
    words: list[str] = []
    first = index[(syls[0].measure, syls[0].onset)]
    if first:
        words.append("*" * first)
    current = ""
    for k, p in enumerate(syls):
        gap = (index[(syls[k + 1].measure, syls[k + 1].onset)] - index[(p.measure, p.onset)] - 1) if k + 1 < len(syls) else 0
        piece = p.text + "_" * gap
        if p.syllabic == "begin" or (p.syllabic == "middle" and not current):
            if current:
                words.append(current)
            current = piece
        elif p.syllabic == "middle":
            current += "-" + piece
        elif p.syllabic == "end" and current:
            words.append(current + "-" + piece)
            current = ""
        else:
            if current:
                words.append(current)
                current = ""
            words.append(piece)
    if current:
        words.append(current)
    return " ".join(words)


def deal(verses: list[str], order: list[tuple[int, int]], recognized: list[Placement]) -> list[Placement]:
    """New placements from the verse texts. A verse whose syllable count equals the recognized one
    keeps the recognized positions (texts replaced one to one); otherwise its syllables are dealt to
    the sounding notes in order from the first, "*" skipping one and "_" holding over one."""
    out: list[Placement] = []
    for vn, text in enumerate(verses, start=1):
        items = parse_verse(text)
        syl_items = [it for it in items if not it.skip]
        old = sorted((p for p in recognized if p.verse == vn), key=lambda p: order.index((p.measure, p.onset)) if (p.measure, p.onset) in order else 10**9)
        if old and len(syl_items) == len(old) and not any(it.skip for it in items):
            for p, it in zip(old, syl_items):
                out.append(Placement(vn, p.measure, p.onset, it.text, it.syllabic, it.extend > 0, p.confidence))
            continue
        pos = 0
        for it in items:
            if pos >= len(order):
                break
            if it.skip:
                pos += 1
                continue
            m, o = order[pos]
            out.append(Placement(vn, m, o, it.text, it.syllabic, it.extend > 0, 1.0))
            pos += 1 + it.extend
    return out
