"""The other door in (plan 0010): a MusicXML file the user already has, opened as it is.

A photograph has to be read; a file has already been written. So this path runs no engine and
repairs nothing: it unwraps a `.mxl` container, checks that the document is a playable
score-partwise, counts what is in it, and reads back the lyric placements the file already carries.
The measures that do not add up become `info` notes, never doubts: on an authored page a short
measure is an upbeat, not a mistake (plan 0010, measured over 60 benchmark files).
"""
from __future__ import annotations

import json
import shutil
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from .lyrics import inject as lyrics_inject
from .postprocess import PostprocessError, postprocess

SUFFIXES = {".musicxml", ".xml", ".mxl"}
MAX_DOCUMENT = 8_000_000  # bytes of XML, unzipped: a 100-measure page is 100 KB
MAX_ENTRIES = 64          # files in a .mxl container


class ScoreFileError(ValueError):
    """The file cannot be opened as a score. The message is shown to the user as it is."""


def looks_like_musicxml(name: str, data: bytes) -> bool:
    """Decide by the bytes, not by the content type: browsers send application/octet-stream for
    both .musicxml and .mxl."""
    suffix = Path(name).suffix.lower()
    if suffix not in SUFFIXES:
        return False
    if data[:2] == b"PK":
        return suffix == ".mxl"
    return data.lstrip()[:1] == b"<"


def read_document(src: Path) -> bytes:
    """The XML bytes of a score file: the file itself, or the rootfile of a .mxl container."""
    data = src.read_bytes()
    if data[:2] == b"PK":
        data = _unzip(src)
    if len(data) > MAX_DOCUMENT:
        raise ScoreFileError(f"the document is larger than {MAX_DOCUMENT // 1_000_000} MB")
    if b"<!ENTITY" in data:
        raise ScoreFileError("the document declares XML entities, which are not read here")
    return data


def _unzip(src: Path) -> bytes:
    try:
        with zipfile.ZipFile(src) as z:
            names = z.namelist()
            if len(names) > MAX_ENTRIES:
                raise ScoreFileError("the compressed score holds too many files")
            try:
                container = ET.fromstring(z.read("META-INF/container.xml"))
            except KeyError:
                raise ScoreFileError("the compressed score has no META-INF/container.xml") from None
            rootfile = container.find(".//rootfile")
            path = rootfile.get("full-path") if rootfile is not None else None
            if not path or path not in names:
                raise ScoreFileError("the compressed score does not say which file holds the music")
            info = z.getinfo(path)
            if info.file_size > MAX_DOCUMENT:
                raise ScoreFileError(f"the document is larger than {MAX_DOCUMENT // 1_000_000} MB")
            return z.read(path)
    except zipfile.BadZipFile as e:
        raise ScoreFileError(f"the compressed score could not be opened: {e}") from e
    except ET.ParseError as e:
        raise ScoreFileError(f"the compressed score's container is not well-formed: {e}") from e


def parse(data: bytes) -> ET.ElementTree:
    """The document, checked for everything the rest of the app assumes."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ScoreFileError(f"this is not well-formed XML: {e}") from e
    if root.tag == "score-timewise":
        raise ScoreFileError("this is a timewise MusicXML file; save it as partwise (every editor can) and try again")
    if root.tag != "score-partwise":
        raise ScoreFileError(f"this is XML but not MusicXML: the document is <{root.tag}>")
    if root.find("part") is None:
        raise ScoreFileError("this MusicXML file has no part")
    if next(root.iter("note"), None) is None:
        raise ScoreFileError("this MusicXML file has no notes")
    return ET.ElementTree(root)


def title_of(root: ET.Element) -> str:
    """The name the file gives itself: the work title, the title credit, the movement title."""
    for text in (root.findtext("work/work-title"),
                 next((c.findtext("credit-words") for c in root.findall("credit")
                       if (c.findtext("credit-type") or "").strip() == "title"), None),
                 root.findtext("movement-title")):
        if text and text.strip():
            return " ".join(text.split())
    return ""


Progress = Callable[[str, str], None]


def ingest(src: Path, out_dir: Path, progress: Progress | None = None) -> Path:
    """Open `src` as a score under `out_dir`; return the final MusicXML path.

    Writes what a finished job holds, minus everything that needs a photo: no thumbnail, no review
    image, no layout, no evidence.
    """
    notify = progress or (lambda stage, msg: None)
    out_dir.mkdir(parents=True, exist_ok=True)

    notify("importing", "Reading the file")
    tree = parse(read_document(src))
    imported = out_dir / "imported.musicxml"
    tree.write(imported, encoding="UTF-8", xml_declaration=True)

    notify("postprocessing", "Checking measures")
    final = out_dir / "score.musicxml"
    try:
        stats = postprocess(imported, final, repair=False)
    except PostprocessError as e:
        raise ScoreFileError(f"this MusicXML file cannot be played: {e}") from e
    root = tree.getroot()
    stats.chords = sum(1 for _ in root.iter("harmony"))

    placed = lyrics_inject.read_placements(final)
    lyrics_inject.save(out_dir / "lyrics.json", placed, [], [])
    stats.lyrics_syllables = len(placed)
    stats.lyrics_read = len(placed)
    stats.lyrics_verses = len({p.verse for p in placed})

    info = {"engine": "import", "source": "musicxml", "title": title_of(root), "stats": asdict(stats)}
    (out_dir / "result.json").write_text(json.dumps(info, indent=2))
    shutil.copyfile(final, out_dir / "original.musicxml")
    (out_dir / "review.json").write_text(json.dumps({"doubts": stats.doubts, "checked": [], "revision": 1}, indent=1))
    imported.unlink(missing_ok=True)
    return final
