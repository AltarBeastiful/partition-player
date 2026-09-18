"""Optional text polish by a language model (ADR 0004, decision 7). Off unless PP_ANTHROPIC_API_KEY is set.

For each staff and verse, the model gets the band image and the syllables the OCR read, and returns
the corrected text in the same notation. The answer is accepted only when its structure is the same
(same number of syllables, same word breaks); a syllable never moves, only its letters change.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

from .align import Placement

MODEL = "claude-haiku-4-5-20251001"
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


def split_reply(reply: str) -> list[tuple[str, str]]:
    """(text, syllabic) per syllable of a line in the notation above."""
    items = []
    for word in reply.strip().split():
        parts = [p for p in word.split("-") if p]
        for k, piece in enumerate(parts):
            syllabic = "single" if len(parts) == 1 else "begin" if k == 0 else "end" if k == len(parts) - 1 else "middle"
            items.append((piece, syllabic))
    return items


def ask(client, api_key: str, image_png: bytes, text: str) -> str:
    r = client.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 400, "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(image_png).decode()}},
            {"type": "text", "text": PROMPT.format(text=text)}]}]},
        timeout=60.0,
    )
    r.raise_for_status()
    return "".join(block.get("text", "") for block in r.json().get("content", []))


def polish(placed: list[Placement], bands: dict[int, Path], api_key: str, client=None) -> tuple[int, list[str]]:
    """Correct the texts in place; returns (syllables changed, warnings)."""
    import httpx

    client = client or httpx.Client()
    changed, warnings = 0, []
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
            reply = ask(client, api_key, band.read_bytes(), text)
        except Exception as e:  # noqa: BLE001  (a polish failure must not fail the job)
            warnings.append(f"lyrics polish skipped for staff {staff + 1}: {e}")
            continue
        items = split_reply(reply)
        if [s for _, s in items] != [p.syllabic for p in syls]:
            warnings.append(f"lyrics polish for staff {staff + 1} verse {verse} changed the syllable structure; ignored")
            continue
        for p, (new_text, _) in zip(syls, items):
            if new_text != p.text and re.sub(r"\W", "", new_text):
                p.text = new_text
                changed += 1
    return changed, warnings
