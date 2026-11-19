"""Optional text polish by a language model (ADR 0004, decision 7). Off unless the model route has a key (PP_ANTHROPIC_API_KEY for the default route) and can read images.

For each staff and verse, the model gets the band image and the syllables the OCR read, and returns
the corrected text in the same notation. The answer is accepted only when its structure is the same
(same number of syllables, same word breaks); a syllable never moves, only its letters change.
"""
from __future__ import annotations

import re
from pathlib import Path

from ...model.route import Route
from .align import Placement
from .validator import same_structure

PROMPT = (
    "This image is a strip of a printed song sheet: one line of lyrics under a staff. An OCR read it as the "
    "syllables below, in this notation: a hyphen joins the syllables of one word, a space separates words "
    "(or syllables placed under different notes). Return the same line with misread letters, accents, "
    "apostrophes and punctuation corrected, in exactly the same notation, with exactly the same number of "
    "syllables and the same hyphens. Do not add, remove, merge or split syllables. Reply with the corrected "
    "line only, nothing else.\n\nOCR: {text}"
)


def verse_string(syls: list[Placement]) -> str:
    out = []
    for p in syls:
        if p.syllabic in ("middle", "end") and out:
            out[-1] += "-" + p.text
        else:
            out.append(p.text)
    return " ".join(out)


def polish(placed: list[Placement], bands: dict[int, Path], route: Route, client=None) -> tuple[int, list[str]]:
    """Correct the texts in place; returns (syllables changed, warnings)."""
    changed, warnings = 0, []
    if not route.enabled or not route.vision:
        return changed, warnings
    groups: dict[tuple[int, int], list[Placement]] = {}
    for p in placed:
        groups.setdefault((p.staff, p.verse), []).append(p)
    for (staff, verse), syls in sorted(groups.items()):
        band = bands.get(staff)
        if band is None or not band.exists():
            continue
        syls.sort(key=lambda p: (p.measure, p.onset))
        text = verse_string(syls)
        try:
            reply = route.complete(PROMPT.format(text=text), image_png=band.read_bytes(), client=client)
        except Exception as e:  # noqa: BLE001  (a polish failure must not fail the job)
            warnings.append(f"lyrics polish skipped for staff {staff + 1}: {e}")
            continue
        items = same_structure(syls, reply)
        if items is None:
            warnings.append(f"lyrics polish for staff {staff + 1} verse {verse} changed the syllable structure; ignored")
            continue
        for p, (new_text, _) in zip(syls, items):
            if new_text != p.text and re.sub(r"\W", "", new_text):
                p.text = new_text
                changed += 1
    return changed, warnings
