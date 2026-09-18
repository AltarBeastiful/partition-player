"""The chord-symbol grammar, as a trie, and CTC decoding constrained to it (ADR 0003).

A chord symbol is `root accidental? quality? extension? (/ bass)?`. Every string the grammar accepts
is enumerated once into a trie whose edges carry the glyphs a recognizer may emit for each character
(`G` also `6`), so decoding can only produce a legal chord and the confidence is the recognizer's own
probability for it. `parse_chord` turns the canonical string into MusicXML harmony fields.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

ROOTS = "ABCDEFG"
ACCIDENTALS = ("", "#", "b")
QUALITIES = ("", "m", "min", "Min", "maj", "Maj", "M", "dim", "aug", "sus2", "sus4", "+", "-")
EXTENSIONS = ("", "5", "6", "7", "9", "11", "13", "69", "add9", "7b5", "7#5", "b9", "#9", "7sus4", "7sus2")
# glyphs the recognizer may emit for a grammar character (the canonical one first)
GLYPHS = {"A": "Aa", "B": "B8", "C": "Cc", "D": "D0Oo", "E": "Ee", "F": "Ff", "G": "G6g",
          "b": "b♭", "#": "#♯", "0": "0O", "1": "1l|", "/": "/\\", "+": "+", "-": "-"}
END = "$"
CANON = "canon"

# (quality, extension) -> MusicXML kind, plus degree additions
KINDS: dict[tuple[str, str], tuple[str, tuple[tuple[int, int, str], ...]]] = {
    ("", ""): ("major", ()), ("maj", ""): ("major", ()), ("Maj", ""): ("major", ()), ("M", ""): ("major", ()),
    ("m", ""): ("minor", ()), ("min", ""): ("minor", ()), ("Min", ""): ("minor", ()), ("-", ""): ("minor", ()),
    ("", "7"): ("dominant", ()), ("maj", "7"): ("major-seventh", ()), ("Maj", "7"): ("major-seventh", ()), ("M", "7"): ("major-seventh", ()),
    ("m", "7"): ("minor-seventh", ()), ("min", "7"): ("minor-seventh", ()), ("Min", "7"): ("minor-seventh", ()), ("-", "7"): ("minor-seventh", ()),
    ("dim", ""): ("diminished", ()), ("dim", "7"): ("diminished-seventh", ()),
    ("aug", ""): ("augmented", ()), ("+", ""): ("augmented", ()),
    ("aug", "7"): ("augmented-seventh", ()), ("+", "7"): ("augmented-seventh", ()),
    ("", "6"): ("major-sixth", ()), ("m", "6"): ("minor-sixth", ()), ("min", "6"): ("minor-sixth", ()),
    ("", "9"): ("dominant-ninth", ()), ("maj", "9"): ("major-ninth", ()), ("Maj", "9"): ("major-ninth", ()), ("M", "9"): ("major-ninth", ()),
    ("m", "9"): ("minor-ninth", ()), ("", "11"): ("dominant-11th", ()), ("", "13"): ("dominant-13th", ()),
    ("sus4", ""): ("suspended-fourth", ()), ("sus2", ""): ("suspended-second", ()),
    ("sus4", "7"): ("suspended-fourth", ((7, -1, "add"),)), ("", "7sus4"): ("suspended-fourth", ((7, -1, "add"),)),
    ("", "7sus2"): ("suspended-second", ((7, -1, "add"),)), ("", "5"): ("power", ()),
    ("", "69"): ("major-sixth", ((9, 0, "add"),)), ("", "add9"): ("major", ((9, 0, "add"),)),
    ("m", "add9"): ("minor", ((9, 0, "add"),)),
    ("", "7b5"): ("dominant", ((5, -1, "alter"),)), ("", "7#5"): ("dominant", ((5, 1, "alter"),)),
    ("m", "7b5"): ("half-diminished", ()), ("", "b9"): ("dominant", ((9, -1, "add"),)),
    ("", "#9"): ("dominant", ((9, 1, "add"),)),
}


@dataclass(frozen=True)
class Chord:
    text: str
    root: str
    root_alter: int
    kind: str
    bass: str = ""
    bass_alter: int = 0
    degrees: tuple[tuple[int, int, str], ...] = field(default=())


def _alter(acc: str) -> int:
    return {"": 0, "#": 1, "b": -1}[acc]


def _split(text: str) -> tuple[str, str, str, str, str, str] | None:
    """canonical string -> (root, acc, quality, ext, bass root, bass acc) or None."""
    if not text or text[0] not in ROOTS:
        return None
    body, _, bass = text.partition("/")
    root, rest = body[0], body[1:]
    acc = ""
    if rest[:1] in ("#", "b"):
        acc, rest = rest[0], rest[1:]
    for q in sorted(QUALITIES, key=len, reverse=True):
        if q and rest.startswith(q):
            quality, rest = q, rest[len(q):]
            break
    else:
        quality = ""
    if rest not in EXTENSIONS:
        return None
    b_root = b_acc = ""
    if bass:
        if bass[0] not in ROOTS or bass[1:] not in ACCIDENTALS:
            return None
        b_root, b_acc = bass[0], bass[1:]
    elif "/" in text:
        return None
    return root, acc, quality, rest, b_root, b_acc


def parse_chord(text: str) -> Chord | None:
    parts = _split(text)
    if parts is None:
        return None
    root, acc, quality, ext, b_root, b_acc = parts
    kind = KINDS.get((quality, ext))
    if kind is None:
        return None
    return Chord(text, root, _alter(acc), kind[0], b_root, _alter(b_acc) if b_root else 0, kind[1])


def all_chords():
    for r, a, q, e in itertools.product(ROOTS, ACCIDENTALS, QUALITIES, EXTENSIONS):
        if (q, e) not in KINDS:
            continue
        base = r + a + q + e
        yield base
        for br, ba in itertools.product(ROOTS, ACCIDENTALS):
            yield f"{base}/{br}{ba}"


def build_trie() -> dict:
    trie: dict = {}
    for word in all_chords():
        node = trie
        for ch in word:
            child = node.get((CANON, ch))
            if child is None:
                child = {}
                node[(CANON, ch)] = child
                for g in GLYPHS.get(ch, ch):
                    node[g] = child
            node = child
        node[END] = True
    return trie


_TRIE: dict | None = None


def trie() -> dict:
    global _TRIE
    if _TRIE is None:
        _TRIE = build_trie()
    return _TRIE


def constrained_decode(probs: np.ndarray, chars: list[str], beam: int = 16) -> tuple[str, float]:
    """CTC prefix beam search over the chord trie.

    probs: (T, V) recognizer output, column 0 = blank. chars: the V labels. Returns the best legal
    chord string and its probability (0.0, "" when no legal string can be formed).
    """
    idx = {c: i for i, c in enumerate(chars)}
    root = trie()
    # key: (canonical prefix, emitted glyphs) -> (p_blank, p_nonblank, trie node)
    beams: dict[tuple[str, str], tuple[float, float, dict]] = {("", ""): (1.0, 0.0, root)}
    for t in range(probs.shape[0]):
        p = probs[t]
        nxt: dict[tuple[str, str], tuple[float, float, dict]] = {}

        def add(key, pb, pnb, node):
            b0, n0, _ = nxt.get(key, (0.0, 0.0, node))
            nxt[key] = (b0 + pb, n0 + pnb, node)

        for (prefix, emitted), (pb, pnb, node) in beams.items():
            total = pb + pnb
            add((prefix, emitted), total * p[0], 0.0, node)  # blank
            if emitted:  # repeated last glyph collapses
                add((prefix, emitted), 0.0, pnb * p[idx[emitted[-1]]], node)
            for glyph, child in node.items():
                if glyph == END or isinstance(glyph, tuple) or glyph not in idx:
                    continue
                pc = p[idx[glyph]]
                if pc < 1e-4:
                    continue
                canon = next(k[1] for k, v in node.items() if isinstance(k, tuple) and v is child)
                gain = pb * pc if (emitted and glyph == emitted[-1]) else total * pc
                add((prefix + canon, emitted + glyph), 0.0, gain, child)
        beams = dict(sorted(nxt.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))[:beam])
    finals = [(k[0], pb + pnb) for k, (pb, pnb, node) in beams.items() if END in node]
    if not finals:
        return "", 0.0
    best = max(finals, key=lambda x: x[1])
    return best[0], float(best[1])
