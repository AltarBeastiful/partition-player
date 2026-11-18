"""Pin a scanned page to the measures of its transcription, and cut the ground truth for it.

The scans in bench/out/songs/scans/ are the IMSLP prints the OpenScore transcriptions were made
from, so the notes and the words are the same; only the page breaks differ. To score a scanned page
we need to know which measures the engraver put on it. The words give it away: type the first words
printed on the page and the last ones, and this finds them in the transcription's syllable sequence
and reports the measure range, then writes bench/out/songs/scans/<name>.musicxml.

    # what the transcription holds, with the measure index of each syllable
    .venv-oemer/bin/python bench/songs/pin_scan.py <name> --dump [--verse N]
    # the measures of a page whose words run from "Ah chantez" to "toujours"
    .venv-oemer/bin/python bench/songs/pin_scan.py <name> --from "ah chan tez" --to "tou jours"
    # cut the ground truth once the range is known (scans.tsv holds it)
    .venv-oemer/bin/python bench/songs/pin_scan.py <name> --cut 12 28 [--swap]
    # cut every page listed in scans.tsv
    .venv-oemer/bin/python bench/songs/pin_scan.py --all

Getting the PDFs is not scripted: IMSLP serves them behind a JavaScript redirect, so open
https://imslp.org/wiki/Special:IMSLPDisclaimerAccept/<file id> in a browser and take the direct URL
from the `data-id` of `#sm_dl_wait` (the file server itself needs no cookie). The file id of each
song is in the corpus metadata, https://raw.githubusercontent.com/OpenScore/Lieder/main/data/scores.yaml,
under `imslp:`. Put the PDFs in bench/out/songs/scans/pdf/IMSLP<id>.pdf and extract the page with
`pdftoppm -r 200 -png -f <page> -l <page> -singlefile <pdf> bench/out/songs/scans/<name>_scan`.
"""
import sys, unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from make_pages import cut, manifest, normalize, out_dir, strip_verse_numbers  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = out_dir("voice_piano")
SCANS = OUT / "scans"


def norm(text: str) -> str:
    t = unicodedata.normalize("NFD", text).casefold()
    return "".join(c for c in t if c.isalnum())


def sequence(tree: ET.ElementTree, verse: int = 1) -> list[tuple[int, str]]:
    """(measure index, syllable) for one verse of the first part, in order."""
    out = []
    for mi, m in enumerate(tree.getroot().find("part").findall("measure")):
        for n in m.findall("note"):
            for ly in n.findall("lyric"):
                if int(ly.get("number") or 1) != verse:
                    continue
                text = "".join(t.text or "" for t in ly.findall("text"))
                if text.strip():
                    out.append((mi, text.strip()))
    return out


def find(seq: list[tuple[int, str]], words: str) -> list[int]:
    """Every place the given syllables appear in a row; each result is the index of the first."""
    want = [norm(w) for w in words.split() if norm(w)]
    hits = []
    for i in range(len(seq) - len(want) + 1):
        if [norm(s) for _, s in seq[i:i + len(want)]] == want:
            hits.append(i)
    return hits


def song(name: str) -> dict:
    return next(s for s in manifest("voice_piano") if s["name"] == name)


def tree_of(name: str) -> ET.ElementTree:
    return normalize(OUT / "src" / f"{song(name)['ref'].split('|')[0]}.mxl")


def swap_verses(tree: ET.ElementTree, a: int, b: int) -> None:
    """Some prints stack the verses the other way round from the transcription (the translation on
    top). Verse numbers count from the top of the page, so the ground truth follows the print."""
    for ly in tree.getroot().iter("lyric"):
        n = int(ly.get("number") or 1)
        if n in (a, b):
            ly.set("number", str(b if n == a else a))


def scan_rows() -> list[dict]:
    rows = []
    for line in (Path(__file__).parent / "scans.tsv").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        imslp, page, first, last, swap, name = line.split("\t")
        rows.append({"imslp": imslp, "page": int(page), "first": int(first), "last": int(last),
                     "swap": swap.strip() == "yes", "name": name.strip()})
    return rows


def write(name: str, first: int, last: int, swap: bool) -> str:
    gt = cut(tree_of(name), first, last)
    if swap:
        swap_verses(gt, 1, 2)
    strip_verse_numbers(gt)
    SCANS.mkdir(parents=True, exist_ok=True)
    gt.write(SCANS / f"{name}.musicxml", encoding="UTF-8", xml_declaration=True)
    n = len(list(gt.getroot().iter("lyric")))
    return f"{name}: measures [{first}, {last}) -> {last - first} measures, {n} syllables"


def main() -> None:
    if sys.argv[1] == "--all":
        for row in scan_rows():
            print(write(row["name"], row["first"], row["last"], row["swap"]))
        return
    name = sys.argv[1]
    verse = int(sys.argv[sys.argv.index("--verse") + 1]) if "--verse" in sys.argv else 1
    tree = tree_of(name)
    seq = sequence(tree, verse)
    if "--dump" in sys.argv:
        for i, (mi, s) in enumerate(seq):
            print(f"{i:4} m{mi:<4} {s}")
        return
    if "--cut" in sys.argv:
        k = sys.argv.index("--cut")
        print(write(name, int(sys.argv[k + 1]), int(sys.argv[k + 2]), "--swap" in sys.argv))
        return
    for flag in ("--from", "--to"):
        if flag in sys.argv:
            words = sys.argv[sys.argv.index(flag) + 1]
            hits = find(seq, words)
            for h in hits:
                span = " ".join(s for _, s in seq[h:h + len(words.split())])
                print(f"{flag} {words!r}: syllable {h}, measure index {seq[h][0]} ({span!r})")
            if not hits:
                print(f"{flag} {words!r}: not found")


if __name__ == "__main__":
    main()
