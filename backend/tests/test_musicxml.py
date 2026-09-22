"""The MusicXML door (plan 0010): unwrapping, refusing, and opening a file as a score."""
import io
import json
import zipfile

import pytest

from conftest import GROUND_TRUTH, ROOT

from partition_player.pipeline.musicxml import (
    ScoreFileError,
    ingest,
    looks_like_musicxml,
    parse,
    read_document,
    title_of,
)

CLEMENTINE = ROOT / "bench" / "songs" / "leadsheets" / "en_clementine.mxl"
ALFONSINA = ROOT / "bench" / "songs" / "leadsheets" / "es_alfonsina_y_el_mar.mxl"


def compress(xml: bytes, inner: str = "score.xml", container: bytes | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if container is None:
            container = (f'<container><rootfiles><rootfile full-path="{inner}"/></rootfiles></container>').encode()
        z.writestr("META-INF/container.xml", container)
        z.writestr(inner, xml)
    return buf.getvalue()


def test_recognizes_a_score_file_by_its_bytes():
    xml = GROUND_TRUTH.read_bytes()
    assert looks_like_musicxml("score.musicxml", xml[:64])
    assert looks_like_musicxml("SCORE.XML", xml[:64])
    assert looks_like_musicxml("score.mxl", compress(xml)[:64])
    assert not looks_like_musicxml("photo.jpg", b"\xff\xd8\xff\xe0")
    assert not looks_like_musicxml("score.musicxml", b"\xff\xd8\xff\xe0")  # a JPEG called .musicxml
    assert not looks_like_musicxml("score.xml", compress(xml)[:64])        # a zip that does not say .mxl


def test_reads_a_container(tmp_path):
    xml = GROUND_TRUTH.read_bytes()
    p = tmp_path / "score.mxl"
    p.write_bytes(compress(xml, inner="deep/inside.xml"))
    assert read_document(p).startswith(b"<?xml")
    assert title_of(parse(read_document(CLEMENTINE)).getroot()) == "Clementine"


@pytest.mark.parametrize("data, says", [
    (b"not xml at all", "well-formed"),
    (b"<html><body>no</body></html>", "not MusicXML"),
    (b"<score-timewise><measure/></score-timewise>", "timewise"),
    (b"<score-partwise><part-list/></score-partwise>", "no part"),
    (b"<score-partwise><part id='P1'><measure number='1'/></part></score-partwise>", "no notes"),
])
def test_refuses_what_cannot_be_played(data, says):
    with pytest.raises(ScoreFileError) as e:
        parse(data)
    assert says in str(e.value)


def test_refuses_entities_and_broken_containers(tmp_path):
    p = tmp_path / "bomb.musicxml"
    p.write_bytes(b'<!DOCTYPE x [<!ENTITY a "aaa">]><score-partwise/>')
    with pytest.raises(ScoreFileError, match="entities"):
        read_document(p)

    p = tmp_path / "broken.mxl"
    p.write_bytes(compress(b"<score-partwise/>", container=b"<container><rootfiles/></container>"))
    with pytest.raises(ScoreFileError, match="which file holds the music"):
        read_document(p)

    p.write_bytes(b"PK\x03\x04 and then rubbish")
    with pytest.raises(ScoreFileError, match="could not be opened"):
        read_document(p)


def test_opens_a_songbook_page_without_changing_it(tmp_path):
    """en_clementine: a pickup, three more short measures that pair with a neighbour, seven verses."""
    ingest(CLEMENTINE, tmp_path)
    info = json.loads((tmp_path / "result.json").read_text())
    stats = info["stats"]
    assert info["engine"] == "import" and info["title"] == "Clementine"
    assert stats["measures"] == 18 and stats["notes"] == 60 and stats["chords"] == 10
    assert stats["lyrics_syllables"] == 240 and stats["lyrics_verses"] == 7
    assert stats["padded_measures"] == 0 and stats["warnings"] == []
    assert stats["doubts"] == []  # nothing repaired, nothing to check: the upbeats are upbeats
    assert stats["pickup"] is True

    kept = sorted(p.name for p in tmp_path.iterdir())
    assert kept == ["lyrics.json", "original.musicxml", "result.json", "review.json", "score.musicxml"]
    assert (tmp_path / "score.musicxml").read_bytes() == (tmp_path / "original.musicxml").read_bytes()
    review = json.loads((tmp_path / "review.json").read_text())
    assert review == {"doubts": [], "checked": [], "revision": 1}

    # the lyrics panel reads the verses that were already under the notes (this page labels them "v1 …")
    lyrics = json.loads((tmp_path / "lyrics.json").read_text())
    assert lyrics["syllables"][0] == {"verse": 1, "measure": 0, "onset": 0, "text": "v1 In", "syllabic": "single",
                                      "extend": False, "confidence": 1.0, "staff": -1}
    assert lyrics["warnings"] == [] and lyrics["seen"] == []


def test_repeats_are_noted_and_odd_measures_are_only_information(tmp_path):
    ingest(ALFONSINA, tmp_path)
    doubts = json.loads((tmp_path / "result.json").read_text())["stats"]["doubts"]
    assert [d["kind"] for d in doubts] == ["repeat", "repeat"]
    assert all(d["level"] == "info" for d in doubts)

    out = tmp_path / "range"
    ingest(ROOT / "bench" / "songs" / "leadsheets" / "en_home_on_the_range.mxl", out)
    doubts = json.loads((out / "result.json").read_text())["stats"]["doubts"]
    assert [(d["measure"], d["kind"], d["level"], d["text"]) for d in doubts] == [
        (28, "overfull", "info", "six quarters in a 3/4 measure")]


def test_a_page_of_rests_is_refused_in_plain_words(tmp_path):
    p = tmp_path / "rests.musicxml"
    p.write_bytes(b"<score-partwise><part id='P1'><measure number='1'><note><rest/><duration>4</duration>"
                  b"</note></measure></part></score-partwise>")
    with pytest.raises(ScoreFileError, match="this MusicXML file cannot be played: the document has no notes"):
        ingest(p, tmp_path / "out")
