"""Synthetic lead-sheet pages with chord symbols, for the chord-recognition benchmark.

Sources (all public domain tunes): the Nottingham folk dataset (ABC with chord symbols, GPL-3 dataset
packaging) and music21's two bundled lead sheets. Each tune becomes bench/out/chords/<name>.musicxml
(ground truth, with <harmony>), <name>.png (clean verovio render) and <name>_photo.png (rotated,
blurred, shaded, noisy, like a phone photo). Deterministic (seeded), so the set is reproducible.

Usage: .venv-oemer/bin/python bench/chords/make_synthetic.py <nottingham-dataset dir> [n_tunes]
"""
import random, re, sys
from pathlib import Path

import cairosvg, cv2, numpy as np, verovio
from music21 import clef, converter, corpus, expressions, harmony, key, meter, note, stream, tempo

OUT = Path(__file__).resolve().parents[2] / "bench" / "out" / "chords"
PICK = ["jigs.abc:2", "jigs.abc:5", "reelsa-c.abc:3", "reelsd-g.abc:7", "waltzes.abc:4", "hpps.abc:6",
        "ashover.abc:9", "morris.abc:3", "playford.abc:2", "xmas.abc:3", "slip.abc:4", "reelsm-q.abc:11"]


def render(xml: Path, png: Path) -> None:
    tk = verovio.toolkit()
    # A4 at 100% is 2100x2970 verovio units (0.1 mm); rendered at 2.5x the interline is about 22 px, like a phone photo.
    tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": 100, "adjustPageHeight": True})
    tk.loadFile(str(xml))
    svg = tk.renderToSVG(1)
    # verovio sets accidentals in chord names and the metronome note in its SMuFL font, which the rasterizer
    # does not have; print them as the plain text most published sheets use ("F#", "Bb").
    glyphs = {"\ue262": "#", "\ue260": "b", "\ue261": "", "\uea64": "b", "\uea65": "", "\uea66": "#",
              "\ue1d5": "\u2669", "\ue1d7": "\u266a", "\ueca5": "\u2669", "\ueca3": "\u2669", "\ueca7": "\u266a"}
    svg = re.sub(r'<tspan font-family="Leipzig"([^>]*)>([^<]*)</tspan>',
                 lambda m: '<tspan%s>%s</tspan>' % (re.sub(r'font-size="(\d+)px"', lambda f: 'font-size="%dpx"' % (int(f.group(1)) * 0.56), m.group(1)),
                                                     "".join(glyphs.get(c, "?") for c in m.group(2))), svg)
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png), background_color="white", scale=1.2)


def photo(clean: Path, out: Path, seed: int) -> None:
    rng = random.Random(seed)
    img = cv2.imread(str(clean), cv2.IMREAD_GRAYSCALE)
    h, w = img.shape
    # small rotation and perspective
    ang = rng.uniform(-2.0, 2.0)
    M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
    img = cv2.warpAffine(img, M, (w, h), borderValue=255)
    d = int(w * 0.02)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[rng.randint(0, d), rng.randint(0, d)], [w - rng.randint(0, d), rng.randint(0, d)],
                      [w - rng.randint(0, d), h - rng.randint(0, d)], [rng.randint(0, d), h - rng.randint(0, d)]])
    img = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=255)
    # uneven lighting, paper tone, blur, sensor noise
    yy, xx = np.mgrid[0:h, 0:w]
    shade = 0.75 + 0.25 * np.cos((xx / w) * np.pi * rng.uniform(0.5, 1.5) + rng.uniform(0, 3)) * np.cos((yy / h) * np.pi * rng.uniform(0.3, 1.0))
    img = (img.astype(np.float32) * shade * rng.uniform(0.8, 0.95)).clip(0, 255)
    img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.6, 1.4))
    img = img + np.random.default_rng(seed).normal(0, rng.uniform(3, 9), img.shape)
    cv2.imwrite(str(out), img.clip(0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 85])


def jazz_page(name: str, chords: list[str], seed: int, ks: int = -2, ts: str = "4/4") -> stream.Score:
    """A synthetic tune whose chord vocabulary the folk set lacks: sevenths, dim, sus, slash, flats."""
    rng = random.Random(seed)
    sc = stream.Score(); p = stream.Part(); p.partName = "Voice"
    sc.metadata = __import__("music21").metadata.Metadata(title=name)
    beats = int(ts.split("/")[0])
    for i in range(16):
        m = stream.Measure(number=i + 1)
        if i == 0:
            m.append(clef.TrebleClef()); m.append(key.KeySignature(ks)); m.append(meter.TimeSignature(ts))
        if i == 8 and name.endswith("keychange"):
            m.append(key.KeySignature(ks + 3))
        m.insert(0, harmony.ChordSymbol(chords[i % len(chords)]))
        if beats >= 4:
            m.insert(2, harmony.ChordSymbol(chords[(i + 7) % len(chords)]))
        for b in range(beats):
            n = note.Note(rng.choice(["C4", "D4", "E4", "F4", "G4", "A4", "B-4", "C5"]), quarterLength=1)
            m.append(n)
        p.append(m)
    sc.append(p)
    return sc


def negative_page(name: str, seed: int) -> stream.Score:
    """No chord symbols, but the text that must not be mistaken for them: rehearsal letters, tempo, lyrics, Fine."""
    rng = random.Random(seed)
    sc = stream.Score(); p = stream.Part(); p.partName = "Voice"
    sc.metadata = __import__("music21").metadata.Metadata(title=name)
    for i in range(16):
        m = stream.Measure(number=i + 1)
        if i == 0:
            m.append(clef.TrebleClef()); m.append(key.KeySignature(1)); m.append(meter.TimeSignature("4/4"))
            m.insert(0, tempo.MetronomeMark(number=96, text="Allegro"))
        if i % 4 == 0:
            m.insert(0, expressions.RehearsalMark("ABCD"[i // 4]))
        if i == 7:
            m.insert(0, expressions.TextExpression("D.C. al Fine"))
        if i == 15:
            m.insert(3, expressions.TextExpression("Fine"))
        for b in range(4):
            n = note.Note(rng.choice(["D4", "E4", "F#4", "G4", "A4", "B4"]), quarterLength=1)
            n.lyric = rng.choice(["A", "la", "E", "sing", "Am", "the", "G", "day"])
            m.append(n)
        p.append(m)
    sc.append(p)
    return sc


def main() -> None:
    nott = Path(sys.argv[1]) / "ABC_cleaned"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else len(PICK)
    OUT.mkdir(parents=True, exist_ok=True)
    scores = []
    for spec in PICK[:n]:
        fname, idx = spec.split(":")
        opus = converter.parse(str(nott / fname))
        sc = opus.scores[int(idx)]
        scores.append((f"nott_{fname[:-4]}_{idx}", sc))
    for name in ("leadSheet/berlinAlexandersRagtime.mxl", "leadSheet/fosterBrownHair.mxl"):
        scores.append((Path(name).stem, corpus.parse(name)))
    scores.append(("jazz_sevenths", jazz_page("jazz_sevenths", ["Cmaj7", "Am7", "Dm7", "G7", "Em7", "A7", "Dm7", "G7", "Cmaj7", "F7", "E7", "Am7"], 101)))
    scores.append(("jazz_flats_keychange", jazz_page("jazz_flats_keychange", ["B-", "E-7", "A-maj7", "D-", "G-7", "C7", "F7", "B-7", "E-", "F", "B-", "Fsus4"], 102)))
    scores.append(("jazz_dim_slash", jazz_page("jazz_dim_slash", ["C", "C/E", "F", "F#dim", "C/G", "G7", "Am", "Am/G", "D7/F#", "G7sus4", "C6", "Bdim7"], 103, ks=0, ts="3/4")))
    scores.append(("neg_text", negative_page("neg_text", 201)))
    scores.append(("neg_letters", negative_page("neg_letters", 202)))
    for i, (name, sc) in enumerate(scores):
        chords = [c.figure for c in sc.recurse().getElementsByClass(harmony.ChordSymbol)]
        if not chords and not name.startswith("neg_"):
            continue
        # one page: keep the first 24 measures
        part = sc.parts[0]
        ms = list(part.getElementsByClass("Measure"))
        for m in ms[24:]:
            part.remove(m)
        for p in sc.parts[1:]:
            sc.remove(p)
        # lead sheets are treble; the ABC importer picks a bass clef for some tunes
        for c in part.recurse().getElementsByClass(clef.Clef):
            c.activeSite.remove(c)
        ms[0].insert(0, clef.TrebleClef())
        sc.metadata.title = sc.metadata.title or name
        xml = OUT / f"{name}.musicxml"
        sc.write("musicxml", fp=str(xml))
        render(xml, OUT / f"{name}.png")
        photo(OUT / f"{name}.png", OUT / f"{name}_photo.jpg", seed=i)
        print(name, len(ms[:24]), "measures", len(chords), "chords", sorted(set(chords))[:12])


if __name__ == "__main__":
    main()
