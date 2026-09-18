"""Pages with lyrics for the lyrics benchmark (ADR 0004, plan 0002 step 3).

Sources: French songs typed as verses in the editor convention on generated melodies; the chord
benchmark's Nottingham lead sheets (bench/out/chords/nott_*.musicxml) with synthetic French and
English verses (one to three verses, melismas, punctuation); music21's lead sheets and Luca's Gloria
with their own engraved lyrics; and negatives: pages whose verse paragraph sits right under the last
system (the text must not become a verse). Each page: <name>.musicxml (ground truth), <name>.png
(clean verovio render), <name>_photo.jpg (degraded like a phone photo). Deterministic.

Usage: .venv-oemer/bin/python bench/lyrics/make_pages.py
"""
import random, re, sys, xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chords"))
from make_synthetic import photo, render  # noqa: E402

from music21 import clef, converter, corpus, key, metadata, meter, note, stream  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "bench" / "out" / "lyrics"
CHORDS = ROOT / "bench" / "out" / "chords"

SONGS = {
    "au_clair": {
        "time": "4/4", "key": 0, "durations": [1, 1, 1, 1, 2, 2, 1, 1, 1, 1, 4] * 4,
        "verses": [
            "Au clair de la lu-ne, mon a-mi Pier-rot, Prê-te-moi ta plu-me pour é-crire un mot. Ma chan-delle est mor-te, je n'ai plus de feu. Ou-vre-moi ta por-te pour l'a-mour de Dieu.",
            "Au clair de la lu-ne, Pier-rot ré-pon-dit: Je n'ai pas de plu-me, je suis dans mon lit. Va chez la voi-si-ne, je crois qu'elle y est, car dans sa cui-si-ne on bat le bri-quet.",
        ]},
    "frere_jacques": {
        "time": "4/4", "key": 0, "durations": [1, 1, 1, 1] * 2 + [1, 1, 2] * 2 + [0.5, 0.5, 0.5, 0.5, 1, 1] * 2 + [1, 1, 2] * 2,
        "verses": [
            "Frè-re Jac-ques, Frè-re Jac-ques, dor-mez-vous? dor-mez-vous? Son-nez les ma-ti-nes, son-nez les ma-ti-nes, ding dang dong, ding dang dong.",
            "Are you slee-ping, are you slee-ping, Bro-ther John, Bro-ther John? Mor-ning bells are rin-ging, mor-ning bells are rin-ging, ding dang dong, ding dang dong.",
        ]},
    "claire_fontaine": {
        "time": "3/4", "key": -1, "durations": [1, 1, 1, 1, 2, 1, 1, 1, 1, 2, 1, 1, 1, 1, 2, 1, 1, 1, 3, 1, 1, 1, 1, 2, 1, 1, 1, 3],
        "verses": [
            "À la clai-re fon-tai-ne, m'en al-lant pro-me-ner, j'ai trou-vé l'eau si bel-le_ * que je m'y suis bai-gné. Il y a long-temps que je t'ai-me, ja-mais je ne t'ou-blie-rai.",
            "Sous les feuil-les d'un chê-ne, je me suis fait sé-cher, sur la plus hau-te bran-che_ * un ros-si-gnol chan-tait. Il y a long-temps que je t'ai-me, ja-mais je ne t'ou-blie-rai.",
            "Chan-te, ros-si-gnol, chan-te, toi qui as le cœur gai, tu as le cœur à ri-re,_ * moi je l'ai à pleu-rer. Il y a long-temps que je t'ai-me, ja-mais je ne t'ou-blie-rai.",
        ]},
    "pont_avignon": {
        "time": "2/4", "key": 1, "durations": [1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 2],
        "verses": [
            "Sur le pont d'A-vi-gnon, l'on y dan-se, l'on y dan-se, sur le pont d'A-vi-gnon, l'on y dan-se tous en rond. Les beaux mes-sieurs font comme ça, et puis en-core comme ça.",
            "Sur le pont d'A-vi-gnon, l'on y dan-se, l'on y dan-se, sur le pont d'A-vi-gnon, l'on y dan-se tous en rond. Les belles da-mes font comme ça, et puis en-core comme ça.",
        ]},
}

FRENCH = ("chan-ter tou-jours mer-veil-leux ma-tin so-leil la le les mon cœur a-mour jar-din oi-seau chan-son pe-tit grand belle nuit "
          "é-toi-le ri-viè-re mai-son en-fant ja-mais en-core de-main hier pour-quoi dan-ser ai-mer vi-vre rê-ver par-tir re-ve-nir "
          "bon-jour mer-ci vous l'a-mour qu'il c'est n'est où ça dé-jà fê-te hi-ver é-té prin-temps fleur ar-bre ciel mer vent pluie nei-ge "
          "lu-mière si-lence che-min vil-lage cam-pagne mon-tagne bleu rou-ge do-ré").split()
ENGLISH = ("sing-ing morn-ing riv-er gar-den lit-tle moun-tain eve-ning won-der-ful to-geth-er re-mem-ber sun-shine the and my your "
           "love heart home road long day night star sky sea wind rain snow bird tree flow-er sum-mer win-ter spring au-tumn dream "
           "smile laugh walk-ing danc-ing run-ning a-way a-gain nev-er al-ways for-ev-er gold-en si-lent qui-et").split()


def deal(verse: str) -> list:
    """Editor convention: '-' splits syllables, '_' after a syllable holds it, '*' skips a note."""
    out = []
    for word in verse.split():
        parts = word.split("-")
        for k, piece in enumerate(parts):
            if piece == "*":
                out.append(None)
                continue
            extend = piece.endswith("_")
            piece = piece.rstrip("_")
            syllabic = "single" if len(parts) == 1 else ("begin" if k == 0 else ("end" if k == len(parts) - 1 else "middle"))
            out.append((piece, syllabic, extend))
    return out


def sounding(part: stream.Part) -> list[note.Note]:
    """Notes that can carry a syllable, in order (rests, chord tones and tied continuations excluded)."""
    out = []
    for n in part.recurse().notes:
        if n.isChord or n.duration.isGrace:
            continue
        if n.tie is not None and n.tie.type in ("stop", "continue"):
            continue
        out.append(n)
    return out


def attach(part: stream.Part, verses: list[list]) -> int:
    notes = sounding(part)
    placed = 0
    for vn, verse in enumerate(verses, start=1):
        for n, syl in zip(notes, verse):
            if syl is None:
                continue
            text, syllabic, extend = syl
            n.lyrics.append(note.Lyric(text=text + ("_" if extend else ""), number=vn, syllabic=syllabic))
            placed += 1
    return placed


def synthetic_verse(rng: random.Random, n_slots: int, bank: list[str]) -> str:
    """A verse of about n_slots syllables: words from the bank, a melisma now and then, punctuation."""
    words, count, since_punct = [], 0, 0
    while count < n_slots:
        w = rng.choice(bank)
        syls = w.count("-") + 1
        if count + syls > n_slots:
            if n_slots - count == 1:
                w = rng.choice([x for x in bank if "-" not in x])
                syls = 1
            else:
                continue
        since_punct += 1
        if since_punct >= rng.randint(4, 7) and count + syls < n_slots:
            w = w + rng.choice([",", ".", ",", "!"])
            since_punct = 0
        if rng.random() < 0.06 and count + syls + 1 <= n_slots:
            w += "_ *"   # a melisma: the syllable is held over the next note
            syls += 1
        if not words or words[-1].endswith((".", "!")):
            w = w[0].upper() + w[1:]
        words.append(w)
        count += syls
    return " ".join(words)


def melody(rng: random.Random, durations: list[float], time_sig: str, ks: int, title: str) -> stream.Score:
    sc = stream.Score(); p = stream.Part(); p.partName = "Voice"
    sc.metadata = metadata.Metadata(title=title)
    scale = key.KeySignature(ks).asKey("major").pitches[:-1]
    beats = meter.TimeSignature(time_sig).barDuration.quarterLength
    m = stream.Measure(number=1); m.append(clef.TrebleClef()); m.append(key.KeySignature(ks)); m.append(meter.TimeSignature(time_sig))
    filled, degree = 0.0, 0
    for q in durations:
        degree = max(-2, min(9, degree + rng.choice([-2, -1, -1, 0, 1, 1, 2, 3])))
        pitch = scale[degree % 7].transpose(12 * (degree // 7))
        pitch = pitch.transpose(12) if pitch.octave < 4 else pitch
        m.append(note.Note(pitch, quarterLength=q))
        filled += q
        if filled >= beats:
            p.append(m); m = stream.Measure(number=len(p.getElementsByClass("Measure")) + 1); filled = 0.0
    if len(m.notes):
        p.append(m)
    sc.append(p)
    return sc


def finish(sc: stream.Score, name: str, seed: int, paragraph: list[str] | None = None) -> dict:
    xml = OUT / f"{name}.musicxml"
    sc.write("musicxml", fp=str(xml))
    tree = ET.parse(xml)   # extenders were marked with a trailing "_" (music21 has no extend flag)
    for ly in tree.getroot().iter("lyric"):
        t = ly.find("text")
        if t is not None and t.text and t.text.endswith("_"):
            t.text = t.text[:-1]
            ET.SubElement(ly, "extend", type="start")
    tree.write(xml, encoding="UTF-8", xml_declaration=True)
    render(xml, OUT / f"{name}.png")
    if paragraph:
        add_paragraph(OUT / f"{name}.png", paragraph)
    photo(OUT / f"{name}.png", OUT / f"{name}_photo.jpg", seed=seed)
    n_lyrics = sum(1 for _ in tree.getroot().iter("lyric"))
    return {"name": name, "lyrics": n_lyrics}


def add_paragraph(png: Path, lines: list[str]) -> None:
    """A verse paragraph right under the last system, as songbooks print verses 2 and up."""
    im = Image.open(png).convert("L")
    w, h = im.size
    ink_rows = [y for y in range(h) if im.crop((0, y, w, y + 1)).getextrema()[0] < 128]
    bottom = max(ink_rows) if ink_rows else h - 200
    font = None
    for cand in ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"):
        if Path(cand).exists():
            font = ImageFont.truetype(cand, 40)
            break
    canvas = Image.new("L", (w, bottom + 70 + 60 * len(lines) + 80), 255)
    canvas.paste(im.crop((0, 0, w, bottom + 20)), (0, 0))
    draw = ImageDraw.Draw(canvas)
    for i, line in enumerate(lines):
        draw.text((int(w * 0.18), bottom + 70 + 60 * i), line, fill=0, font=font)
    canvas.save(png)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    # French songs on generated melodies
    for i, (name, song) in enumerate(SONGS.items()):
        rng = random.Random(10 + i)
        verses = [deal(v) for v in song["verses"]]
        n = len(verses[0])
        for v in verses:
            assert len(v) == n, (name, [len(x) for x in verses])
        durations = (song["durations"] * (n // len(song["durations"]) + 1))[:n]
        sc = melody(rng, durations, song["time"], song["key"], name.replace("_", " ").title())
        attach(sc.parts[0], verses)
        made.append(finish(sc, name, seed=i))
    # the two French song pages again, with a verse paragraph pasted under the last system
    for i, name in enumerate(("au_clair", "pont_avignon")):
        song = SONGS[name]
        rng = random.Random(10 + list(SONGS).index(name))
        v = deal(song["verses"][0])
        durations = (song["durations"] * (len(v) // len(song["durations"]) + 1))[:len(v)]
        sc = melody(rng, durations, song["time"], song["key"], name.replace("_", " ").title())
        attach(sc.parts[0], [v])
        plain = re.sub(r"[-_*]", "", song["verses"][1]).replace("  ", " ")
        words = plain.split()
        lines = [f"2. {' '.join(words[:9])}", " ".join(words[9:18]), " ".join(words[18:])]
        made.append(finish(sc, f"para_{name}", seed=50 + i, paragraph=lines))
    # Nottingham lead sheets with synthetic verses
    for i, xml in enumerate(sorted(CHORDS.glob("nott_*.musicxml"))):
        rng = random.Random(100 + i)
        sc = converter.parse(str(xml))
        part = sc.parts[0]
        n = len(sounding(part))
        bank = FRENCH if i % 2 == 0 else ENGLISH
        n_verses = 1 + i % 3
        verses = [deal(synthetic_verse(rng, n, bank)) for _ in range(n_verses)]
        attach(part, verses)
        made.append(finish(sc, f"lyr_{xml.stem}", seed=100 + i))
    # engraved lyrics from the music21 corpus
    for name, path, measures in (("berlin", "leadSheet/berlinAlexandersRagtime.mxl", 24), ("foster", "leadSheet/fosterBrownHair.mxl", 24), ("gloria", "luca/gloria.xml", 16)):
        sc = corpus.parse(path)
        for p in sc.parts[1:]:
            sc.remove(p)
        part = sc.parts[0]
        ms = list(part.getElementsByClass("Measure"))
        for m in ms[measures:]:
            part.remove(m)
        for c in part.recurse().getElementsByClass(clef.Clef):
            c.activeSite.remove(c)
        ms[0].insert(0, clef.TrebleClef())
        made.append(finish(sc, name, seed=200 + len(made)))
    for m in made:
        print(m["name"], m["lyrics"], "syllables")


if __name__ == "__main__":
    main()
