"""Benchmark pages from real songs, with their chord symbols and their printed words.

Two sets, each a manifest of thirty songs:

- `leadsheets.tsv` (default): what a songbook page is — one staff carrying the sung line, the chord
  names printed above it, the words under it, verses stacked. From PDMX
  (https://zenodo.org/records/15571083), MuseScore scores in the public domain or CC0; the .mxl
  files are vendored in `leadsheets/`, so nothing is downloaded. French, English, Spanish, German,
  Italian and Swedish, one to eight verses, 10 to 56 chord symbols a song. Chosen from the 250K by:
  one part, one staff, at least eight chord symbols, words, no chord noteheads and **one voice** —
  a staff split into two voices is not one sung line, and neither the note scorer nor the syllable
  scorer can pair its notes with what an engine reads off the page.
- `voice_piano.tsv`: art songs with a written-out piano part, three staves to a system, from the
  OpenScore Lieder corpus (CC0, downloaded on first use). Harder, and not what the product is for.

For each song: the chosen page is engraved by verovio (the music font varies from song to song), and
the ground truth is the same MusicXML cut down to exactly the measures verovio put on that page, so
the notes, the chords and the syllables are the ones a reader sees. Each page also gets a degraded
copy, like a phone photo. Deterministic: the same manifest gives the same pages.

Usage: .venv-oemer/bin/python bench/songs/make_pages.py [--set leadsheets|voice_piano] [--only NAME] [--no-photo]
"""
import copy, re, sys, urllib.parse, urllib.request, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chords"))
from make_synthetic import photo  # noqa: E402

import cairosvg, verovio  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SETS = {"leadsheets": "leadsheets.tsv", "voice_piano": "voice_piano.tsv"}
RAW = "https://raw.githubusercontent.com/OpenScore/Lieder/main/scores"


def which_set(argv: list[str]) -> str:
    return argv[argv.index("--set") + 1] if "--set" in argv else "leadsheets"


def out_dir(name: str) -> Path:
    return ROOT / "bench" / "out" / "songs" / name

# MusicXML orders the children of <attributes>; the first measure of a page has to carry the ones
# that were declared earlier in the piece.
ATTR_ORDER = ["divisions", "key", "time", "staves", "part-symbol", "instruments", "clef",
              "staff-details", "transpose", "directive", "measure-style"]


def manifest(which: str = "leadsheets") -> list[dict]:
    rows = []
    for line in (HERE / SETS[which]).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        source, ref, lang, page, font, name = line.split("\t")
        rows.append({"source": source, "ref": ref, "lang": lang, "page": int(page),
                     "font": font, "name": name.strip(), "set": which})
    return rows


def fetch(song: dict) -> Path:
    """The song's MusicXML: vendored next to the manifest, or downloaded once into <out>/src/."""
    if song["source"] == "pdmx":
        return HERE / "leadsheets" / song["ref"]
    sid, path = song["ref"].split("|", 1)
    src = out_dir(song["set"]) / "src"
    src.mkdir(parents=True, exist_ok=True)
    mxl = src / f"{sid}.mxl"
    if not mxl.exists() or mxl.stat().st_size < 2000:
        url = f"{RAW}/{urllib.parse.quote(path)}/lc{sid}.mxl"
        with urllib.request.urlopen(url, timeout=60) as r:
            mxl.write_bytes(r.read())
    return mxl


def normalize(mxl: Path) -> ET.ElementTree:
    """The score as a printed page would have it.

    Two things the transcribers leave behind: the hyphen typed into the text ("– ma") although
    <syllabic>middle</syllabic> already says it, which prints a double dash and puts a dash in the
    ground truth; and colour, which songbooks are not printed in.
    """
    with zipfile.ZipFile(mxl) as z:
        name = next(n for n in z.namelist() if n.endswith(".xml") and "META-INF" not in n)
        tree = ET.ElementTree(ET.fromstring(z.read(name)))
    for el in tree.getroot().iter():
        el.attrib.pop("color", None)
    for note in tree.getroot().iter("note"):
        for ly in list(note.findall("lyric")):
            texts = ly.findall("text")
            for t in texts:
                if t.text:
                    t.text = re.sub(r"^\s*[-–—]\s*", "", re.sub(r"\s*[-–—]\s*$", "", t.text)).strip()
            if not any((t.text or "").strip() for t in texts):
                note.remove(ly)
    return tree


def pages(xml: Path, font: str) -> tuple[verovio.toolkit, list[list[str]]]:
    """The toolkit loaded with the score, and the measure numbers verovio puts on each page."""
    tk = verovio.toolkit()
    tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": 100, "adjustPageHeight": False,
                   "font": font, "footer": "none", "svgAdditionalAttribute": ["measure@n"]})
    tk.loadFile(str(xml))
    out = []
    for p in range(1, tk.getPageCount() + 1):
        svg = tk.renderToSVG(p)
        out.append(re.findall(r'class="measure"[^>]*data-n="([^"]+)"', svg))
    return tk, out


def rasterize(tk: verovio.toolkit, page: int, png: Path) -> None:
    svg = tk.renderToSVG(page)
    # verovio draws the music as paths, but an accidental inside a text run stays a music-font glyph
    # that the rasterizer has no font for; print the plain characters instead.
    glyphs = {"": "#", "": "b", "": "", "": "b", "": "", "": "#"}
    svg = re.sub(r'<tspan font-family="(?:Leipzig|Leland|Bravura|Petaluma|Gootville)"([^>]*)>([^<]*)</tspan>',
                 lambda m: "<tspan%s>%s</tspan>" % (m.group(1), "".join(glyphs.get(c, "") for c in m.group(2))), svg)
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png), background_color="white", scale=1.0)


def absorb(state: dict, attributes: ET.Element | None) -> None:
    if attributes is None:
        return
    for child in attributes:
        state[(child.tag, child.get("number") or "1")] = copy.deepcopy(child)


def merged_attributes(state: dict, own: ET.Element | None) -> ET.Element:
    """<attributes> for the first measure of the page: everything in force, the measure's own last."""
    merged = dict(state)
    absorb(merged, own)
    out = ET.Element("attributes")
    for key in sorted(merged, key=lambda k: (ATTR_ORDER.index(k[0]) if k[0] in ATTR_ORDER else 99, k[1])):
        out.append(merged[key])
    return out


def span(per_page: list[list[str]], page: int) -> tuple[int, int]:
    """The first and last measure index of a page.

    Not by measure number: a written-out repeat numbers its measures again ("...26 27 17 18..."),
    so the numbers are not unique. verovio lays every measure out once, in order, so counting the
    measures of the earlier pages gives the index.
    """
    start = sum(len(p) for p in per_page[:page - 1])
    return start, start + len(per_page[page - 1])


def cut(tree: ET.ElementTree, first: int, last: int) -> ET.ElementTree:
    """The score reduced to the measures [first, last) of one page, attributes carried over."""
    out = copy.deepcopy(tree)
    for part in out.getroot().findall("part"):
        state, kept = {}, []
        for i, m in enumerate(part.findall("measure")):
            part.remove(m)
            if not (first <= i < last):
                absorb(state, m.find("attributes"))
                continue
            m = copy.deepcopy(m)
            for pr in m.findall("print"):
                m.remove(pr)
            if not kept:
                own = m.find("attributes")
                if own is not None:
                    m.remove(own)
                m.insert(0, merged_attributes(state, own))
            kept.append(m)
        for m in kept:
            part.append(m)
    return out


def strip_verse_numbers(tree: ET.ElementTree) -> None:
    """The verse number a transcriber typed into the first syllable ("1. Le") is a label.

    It stays on the page, because songbooks print it and the reader has to skip it, but the ground
    truth holds the syllable alone: the pipeline reads "1." as the verse number, not as a word.
    """
    for part in tree.getroot().findall("part"):
        seen = set()
        for ly in part.iter("lyric"):
            verse = ly.get("number") or "1"
            texts = ly.findall("text")
            for t in texts:
                if t.text:
                    t.text = t.text.replace(" ", " ").strip()
            if verse not in seen and texts and texts[0].text:
                seen.add(verse)
                texts[0].text = re.sub(r"^\d+\s*\.?\s+", "", texts[0].text) or texts[0].text


def syllables(tree: ET.ElementTree) -> tuple[int, int]:
    lyrics = [ly for ly in tree.getroot().iter("lyric")]
    return len(lyrics), len({int(ly.get("number") or 1) for ly in lyrics})


def main() -> None:
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    which = which_set(sys.argv)
    OUT = out_dir(which)
    (OUT / "src").mkdir(parents=True, exist_ok=True)
    print(f"{'page':48} {'lang':4} {'font':9} {'measures':>14} {'syllables':>9} {'verses':>6}")
    for i, song in enumerate(manifest(which)):
        if only and only not in song["name"]:
            continue
        tree = normalize(fetch(song))
        norm = OUT / "src" / f"{song['name']}_norm.musicxml"
        tree.write(norm, encoding="UTF-8", xml_declaration=True)
        tk, per_page = pages(norm, song["font"])
        if song["page"] > len(per_page):
            print(f"{song['name']:38} page {song['page']} of {len(per_page)}: missing")
            continue
        numbers = per_page[song["page"] - 1]
        first, last = span(per_page, song["page"])
        doc = [m.get("number") for m in tree.getroot().find("part").findall("measure")]
        assert doc[first:last] == numbers, f"{song['name']}: page {song['page']} does not line up with the score"
        gt = cut(tree, first, last)
        strip_verse_numbers(gt)
        gt.write(OUT / f"{song['name']}.musicxml", encoding="UTF-8", xml_declaration=True)
        rasterize(tk, song["page"], OUT / f"{song['name']}.png")
        if "--no-photo" not in sys.argv:
            photo(OUT / f"{song['name']}.png", OUT / f"{song['name']}_photo.jpg", seed=300 + i)
        n_syl, n_verses = syllables(gt)
        where = f"{numbers[0]}-{numbers[-1]} ({last - first})" if numbers else "-"
        print(f"{song['name']:48} {song['lang']:4} {song['font']:9} {where:>14} {n_syl:9} {n_verses:6}")


if __name__ == "__main__":
    main()
