"""Structure check of a model's lyrics answer (ADR 0010, decision 7d): same syllable count, same word breaks."""
from __future__ import annotations

from .align import Placement


def split_reply(reply: str) -> list[tuple[str, str]]:
    """(text, syllabic) per syllable of a line in the polish notation: hyphen joins syllables of a word, space separates words."""
    items = []
    for word in reply.strip().split():
        parts = [p for p in word.split("-") if p]
        for k, piece in enumerate(parts):
            syllabic = "single" if len(parts) == 1 else "begin" if k == 0 else "end" if k == len(parts) - 1 else "middle"
            items.append((piece, syllabic))
    return items


def same_structure(syls: list[Placement], reply: str) -> list[tuple[str, str]] | None:
    """The reply's syllables if they match the existing ones one for one in count and breaks, else None."""
    items = split_reply(reply)
    return items if [s for _, s in items] == [p.syllabic for p in syls] else None
