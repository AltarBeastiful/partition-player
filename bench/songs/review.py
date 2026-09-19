"""The side-by-side review page: the printed page on the left, what the pipeline read on the right.

The lyric score says how many syllables landed right; it does not say what is wrong with the ones
that did not. This writes bench/out/songs/review.html, one section per benchmark page, the image
beside the verses: the ground truth line over the line the pipeline produced, syllable by syllable,
wrong ones marked, missing ones shown as a gap, and the rows the lyric stage saw but refused listed
underneath. Every syllable has an address, "<page> v2 #17", to point at a defect with.

Usage: .venv-oemer/bin/python bench/songs/review.py [--set leadsheets|voice_piano] [--open]
Open <out>/review.html in a browser (the images sit next to it).
"""
import json, sys, unicodedata, webbrowser
import xml.etree.ElementTree as ET
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "chords"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_pages import out_dir, which_set  # noqa: E402
from score_chords import chords as parse_chords  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = out_dir(which_set(sys.argv))


def verses(path: Path) -> dict[int, list[tuple[int, int, str, bool]]]:
    """{verse: [(measure, onset, text, extends)]} in note order, for the first part."""
    part = ET.parse(path).getroot().find("part")
    out: dict[int, list] = {}
    for mi, m in enumerate(part.findall("measure")):
        notes = [n for n in m.findall("note") if n.find("rest") is None and n.find("grace") is None and n.find("chord") is None]
        for oi, n in enumerate(notes):
            for ly in n.findall("lyric"):
                v = int(ly.get("number") or 1)
                text = "".join(t.text or "" for t in ly.findall("text"))
                syl = ly.findtext("syllabic") or "single"
                joined = text + ("-" if syl in ("begin", "middle") else "")
                out.setdefault(v, []).append((mi, oi, joined, ly.find("extend") is not None))
    return out


SHORT = {"major": "", "minor": "m", "dominant": "7", "dominant-seventh": "7", "major-seventh": "maj7",
         "minor-seventh": "m7", "diminished": "dim", "diminished-seventh": "dim7", "half-diminished": "m7b5",
         "augmented": "aug", "suspended-fourth": "sus4", "suspended-second": "sus2", "major-sixth": "6",
         "minor-sixth": "m6", "dominant-ninth": "9", "major-ninth": "maj9", "minor-ninth": "m9",
         "power": "5", "other": ""}


def harmonies(path: Path) -> list[tuple[int, str]]:
    """(measure index, chord name) in order, read the way the scorer reads them, so the two files
    are spelled the same: one file writes <kind text="Gm">, the other writes <kind>minor</kind>."""
    try:
        parsed, _ = parse_chords(str(path))
    except Exception:
        return []
    out = []
    for measure, _beat, root, kind, bass in parsed:
        out.append((measure, root + SHORT.get(kind, kind) + (f"/{bass}" if bass else "")))
    return out


def chord_line(gt: list, cand: list) -> str:
    """Chords paired by measure, in order: what is printed over what was read."""
    from collections import defaultdict
    by = defaultdict(list)
    for m, t in cand:
        by[m].append(t)
    cells = []
    for i, (m, text) in enumerate(gt):
        got = by[m].pop(0) if by[m] else None
        cls = "miss" if got is None else ("ok" if norm(got) == norm(text) else "bad")
        cells.append(f'<span class="s {cls}" title="#{i} m{m + 1} printed {text!r}"><b>{escape(text)}</b>'
                     f'<i>{escape(got or "·")}</i><u>{i}</u></span>')
    for m, rest in sorted(by.items()):
        for t in rest:
            cells.append(f'<span class="s extra" title="m{m + 1}: not printed"><b>·</b><i>{escape(t)}</i><u></u></span>')
    return "".join(cells)


def norm(text: str) -> str:
    t = unicodedata.normalize("NFC", text).casefold()
    return "".join(c for c in t if c.isalnum() or c in "'’")


def line(gt: list, cand: list) -> str:
    """The ground truth and the candidate on one row per note, paired by (measure, onset)."""
    by_note = {(m, o): t for m, o, t, _ in cand}
    cells = []
    for i, (m, o, text, _) in enumerate(gt):
        got = by_note.get((m, o))
        if got is None:
            cls, shown = "miss", "·"
        elif norm(got) == norm(text):
            cls, shown = "ok", got
        else:
            cls, shown = "bad", got
        title = f"#{i} m{m + 1}.{o} truth {text!r}" + ("" if got is None else f" read {got!r}")
        cells.append(f'<span class="s {cls}" title="{escape(title)}"><b>{escape(text)}</b>'
                     f'<i>{escape(shown)}</i><u>{i}</u></span>')
    extra = [(m, o, t) for m, o, t, _ in cand if (m, o) not in {(m, o) for m, o, _, _ in gt}]
    for m, o, t in extra:
        cells.append(f'<span class="s extra" title="m{m + 1}.{o}: not in the truth"><b>·</b><i>{escape(t)}</i><u></u></span>')
    return "".join(cells)


def section(row: dict, gt_dir: Path) -> str:
    name, image = row["name"], row["image"]
    gt_path = gt_dir / f"{row['base'] if 'base' in row else name}.musicxml"
    if not gt_path.exists():
        gt_path = gt_dir / f"{name.replace('_scan', '')}.musicxml"
    truth, read = verses(gt_path), verses(OUT / "run" / name / "score.musicxml")
    ly, notes = row["lyrics"], row["notes"]
    placed = "-" if ly["placed"] is None else f"{ly['placed']}/{ly['gt']}"
    ch = row.get("chords") or {}
    head = (f"{row['kind']} &middot; syllables placed {placed} &middot; text {ly['text']}/{ly['gt']} &middot; "
            f"verses {ly['verses_found']}/{ly['verses_gt']} &middot; false {ly['false']} &middot; "
            + (f"chords {ch['right']}/{ch['gt']} (false {ch['false']}) &middot; " if ch else "")
            + f"sung notes {notes['both']}/{notes['events']} &middot; measures {notes['measures'][0]}/{notes['measures'][1]}")
    body = []
    gt_ch, read_ch = harmonies(gt_path), harmonies(OUT / "run" / name / "score.musicxml")
    if gt_ch or read_ch:
        body.append(f'<div class="verse"><h4>chords</h4><div class="row">{chord_line(gt_ch, read_ch)}</div></div>')
    for v in sorted(set(truth) | set(read)):
        body.append(f'<div class="verse"><h4>v{v}</h4><div class="row">{line(truth.get(v, []), read.get(v, []))}</div></div>')
    if not body:
        body.append('<p class="none">no syllables in the ground truth</p>')
    seen = "".join(f'<li><code>{escape(s.get("text", "")[:70])}</code> <em>{escape(s.get("reason", ""))}</em></li>'
                   for s in row.get("seen", [])[:8])
    src = image_path(row)
    w, h = size(OUT / src)
    return f"""<section id="{escape(name)}" class="k-{row['kind']}">
  <h2>{escape(name)} <small>{head}</small></h2>
  <div class="split">
    <div class="pane"><a href="{escape(src)}" target="_blank"><img src="{escape(src)}" width="{w}" height="{h}" loading="lazy"></a></div>
    <div class="pane text">{''.join(body)}
      {'<h5>seen, not used</h5><ul class="seen">' + seen + '</ul>' if seen else ''}
    </div>
  </div>
</section>"""


def size(path: Path) -> tuple[int, int]:
    """The image's pixel size, written into the tag so the page keeps its height while the images
    load lazily: without it the anchors land in empty space as the layout settles."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return 2100, 2970


def image_path(row: dict) -> str:
    return ("scans/" if row["kind"] == "scan" else "") + row["image"]


CSS = """
:root { --ok:#1b7f3b; --bad:#b3261e; --miss:#9a6a00; --line:#d8d5cf; --ink:#1a1a1a; --paper:#fbfaf7; }
* { box-sizing:border-box } body { margin:0; font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; color:var(--ink); background:var(--paper) }
header { position:sticky; top:0; background:var(--paper); border-bottom:1px solid var(--line); padding:10px 16px; z-index:2 }
header h1 { font-size:16px; margin:0 0 4px } header p { margin:0; color:#666; font-size:12px }
nav { padding:8px 16px; border-bottom:1px solid var(--line); font-size:11px; max-height:38vh; overflow:auto }
nav table { border-collapse:collapse } nav th { text-align:left; color:#888; font-weight:600; padding:1px 8px 3px 0 }
nav td { padding:1px 8px 1px 0; white-space:nowrap } nav td.n { text-align:right; font-variant-numeric:tabular-nums }
nav a { color:#333 }
section { border-bottom:1px solid var(--line); padding:14px 16px; content-visibility:auto; contain-intrinsic-size:auto 1200px }
.filters { padding:6px 16px; border-bottom:1px solid var(--line) }
.filters button { font:inherit; font-size:11px; padding:2px 10px; margin-right:6px; border:1px solid var(--line); background:#fff; border-radius:10px; cursor:pointer }
.filters button[aria-pressed="true"] { background:var(--ink); color:#fff; border-color:var(--ink) }
body.only-clean section:not(.k-clean), body.only-photo section:not(.k-photo), body.only-scan section:not(.k-scan) { display:none }
body.only-clean nav tr.k-photo, body.only-clean nav tr.k-scan,
body.only-photo nav tr.k-clean, body.only-photo nav tr.k-scan,
body.only-scan nav tr.k-clean, body.only-scan nav tr.k-photo { display:none }
section h2 { font-size:14px; margin:0 0 8px; font-weight:600 } section h2 small { font-weight:400; color:#666; font-size:12px }
.split { display:flex; gap:16px; align-items:flex-start } .pane { flex:1 1 50%; min-width:0 }
.pane img { width:100%; height:auto; border:1px solid var(--line); background:#fff }
.verse { margin:0 0 12px } .verse h4 { margin:0 0 2px; font-size:11px; color:#666; font-weight:600; letter-spacing:.04em }
.row { display:flex; flex-wrap:wrap; gap:1px 4px }
.s { display:inline-flex; flex-direction:column; align-items:center; padding:1px 3px; border-radius:3px; line-height:1.25 }
.s b { font-weight:600; font-size:13px } .s i { font-style:normal; font-size:12px } .s u { text-decoration:none; font-size:8px; color:#bbb }
.s.ok i { color:var(--ok) } .s.bad { background:#fdecea } .s.bad i { color:var(--bad); font-weight:600 }
.s.miss { background:#fff6e0 } .s.miss i { color:var(--miss) }
.s.extra { background:#eef1fb } .s.extra i { color:#2b4bb3 }
h5 { margin:10px 0 3px; font-size:11px; color:#666 } ul.seen { margin:0; padding-left:16px; font-size:11px; color:#666 }
ul.seen code { background:#f0efea; padding:0 3px } .none { color:#b3261e; font-size:13px }
@media (max-width:900px) { .split { flex-direction:column } }
"""


def main() -> None:
    rows = []
    for f, gt_dir in ((OUT / "results.json", OUT), (OUT / "results_scans.json", OUT / "scans")):
        if f.exists():
            for r in json.loads(f.read_text()):
                rows.append((r, gt_dir))
    if not rows:
        print("no results.json: run bench/songs/run_bench.py first")
        return
    nav = "".join(
        f'<tr class="k-{r["kind"]}"><td><a href="#{r["name"]}">{escape(r["name"])}</a></td><td>{r["kind"]}</td>'
        f'<td class="n">{"-" if r["lyrics"]["placed"] is None else r["lyrics"]["placed"]}/{r["lyrics"]["gt"]}</td>'
        f'<td class="n">{r["lyrics"]["text"]}</td><td class="n">{r["lyrics"]["verses_found"]}/{r["lyrics"]["verses_gt"]}</td>'
        f'<td class="n">{r["lyrics"]["false"]}</td>'
        f'<td class="n">{r["notes"]["both"]}/{r["notes"]["events"]}</td>'
        f'<td class="n">{r["notes"]["measures"][0]}/{r["notes"]["measures"][1]}</td></tr>' for r, _ in rows)
    total = sum(r["lyrics"]["gt"] for r, _ in rows)
    placed = sum(r["lyrics"]["placed"] or 0 for r, _ in rows)
    html = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<title>Song benchmark review</title><style>{CSS}</style>
<header><h1>Song benchmark &mdash; printed page vs. what was read</h1>
<p>{len(rows)} pages, {total} syllables in the ground truth, {placed} placed on the right note.
Top row of each pair: the truth. Bottom: what the pipeline read (<span style="color:var(--ok)">green</span> right,
<span style="color:var(--bad)">red</span> wrong, <span style="color:var(--miss)">·</span> nothing read,
<span style="color:#2b4bb3">blue</span> read where the truth has nothing). Hover a syllable for its address.</p></header>
<div class="filters">
  <button data-k="" aria-pressed="true">all</button><button data-k="clean">engraved</button>
  <button data-k="photo">photo</button><button data-k="scan">IMSLP scan</button></div>
<nav><table><tr><th>page</th><th>kind</th><th>placed</th><th>text</th><th>verses</th><th>false</th><th>sung notes</th><th>measures</th></tr>{nav}</table></nav>
{"".join(section(r, d) for r, d in rows)}
<script>
document.querySelectorAll('.filters button').forEach(b => b.onclick = () => {{
  document.body.className = b.dataset.k ? 'only-' + b.dataset.k : '';
  document.querySelectorAll('.filters button').forEach(x => x.setAttribute('aria-pressed', x === b));
}});
</script>
</html>"""
    dst = OUT / "review.html"
    dst.write_text(html, encoding="utf-8")
    print(f"wrote {dst}")
    if "--open" in sys.argv:
        webbrowser.open(dst.as_uri())


if __name__ == "__main__":
    main()
