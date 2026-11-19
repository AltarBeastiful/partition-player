"""Your edits win (ticket 05): conflicts with hand edits, on every staff, through the HTTP API."""
import copy
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient

from conftest import GROUND_TRUTH, PHOTO
from test_api import wait_done
from test_model_pass import GOOD, SOURCE, FakeModel, body, start


def two_staff_app(settings, monkeypatch, tmp_path, model):
    """An app whose score has two parts (the second a copy of the first without lyrics): (client, job id)."""
    from partition_player.api import create_app
    from partition_player.config import load_settings

    root = ET.parse(GROUND_TRUTH).getroot()
    second = copy.deepcopy(root.find("part"))
    second.set("id", "P2")
    for note in second.iter("note"):
        for lyric in note.findall("lyric"):
            note.remove(lyric)
    part_list = root.find("part-list")
    score_part = copy.deepcopy(part_list.find("score-part"))
    score_part.set("id", "P2")
    part_list.append(score_part)
    root.append(second)
    two = tmp_path / "two.musicxml"
    ET.ElementTree(root).write(two, encoding="UTF-8", xml_declaration=True)
    monkeypatch.setenv("PP_FAKE_MUSICXML", str(two))
    client = TestClient(create_app(load_settings(), model_client=model))
    client.__enter__()
    job = wait_done(client, client.post("/api/jobs", files={"file": ("p.jpg", PHOTO.read_bytes(), "image/jpeg")}).json()["id"])
    return client, job["id"]


def lyric_texts(xml, part_index):
    return [t.text for t in ET.fromstring(xml).findall("part")[part_index].iter("text")]


def second_staff_span():
    return [{"staff": 1, "from": 0, "to": 1, "lyrics_source": SOURCE}]


def test_apply_writes_the_changes_to_the_staff_they_were_made_for(settings, monkeypatch, tmp_path):
    client, jid = two_staff_app(settings, monkeypatch, tmp_path, FakeModel(GOOD))
    before = lyric_texts(client.get(f"/api/jobs/{jid}/score.musicxml").text, 0)
    draft = client.post(f"/api/jobs/{jid}/model-pass", json={"spans": second_staff_span(), "api_key": "k", "confirm": True}).json()
    assert draft["changes"]
    assert client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": [c["id"] for c in draft["changes"]]}).status_code == 200
    xml = client.get(f"/api/jobs/{jid}/score.musicxml").text
    assert lyric_texts(xml, 1) == ["Lors", "que", "nous", "é", "tions"]
    assert lyric_texts(xml, 0) == before


def test_a_hand_edit_on_the_second_staff_is_a_conflict_and_survives_apply(settings, monkeypatch, tmp_path):
    client, jid = two_staff_app(settings, monkeypatch, tmp_path, FakeModel(GOOD))
    client.post(f"/api/jobs/{jid}/model-pass", json={"spans": second_staff_span(), "api_key": "k", "confirm": True})
    root = ET.fromstring(client.get(f"/api/jobs/{jid}/score.musicxml").text)
    note = next(n for n in root.findall("part")[1].find("measure").findall("note") if n.find("rest") is None and n.find("grace") is None)
    lyric = ET.SubElement(note, "lyric", number="1")
    ET.SubElement(lyric, "syllabic").text = "single"
    ET.SubElement(lyric, "text").text = "Hand"
    rev = client.get(f"/api/jobs/{jid}/review").json()["revision"]
    put = client.put(f"/api/jobs/{jid}/score", json={"musicxml": ET.tostring(root, encoding="unicode"), "checked": [], "revision": rev})
    assert put.status_code == 200, put.text
    state = client.get(f"/api/jobs/{jid}/model-draft").json()
    flags = {c["new"]["text"]: (c["conflict"], c["ticked"]) for c in state["changes"]}
    assert flags["Lors"] == (True, False) and flags["que"] == (False, True)
    client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": [c["id"] for c in state["changes"] if not c["conflict"]]})
    assert lyric_texts(client.get(f"/api/jobs/{jid}/score.musicxml").text, 1) == ["Hand", "que", "nous", "é", "tions"]


def test_an_edit_made_while_the_pass_runs_is_flagged_in_the_draft_it_returns(settings):
    state = {}

    class Editing(FakeModel):
        def post(self, url, **k):  # the user fixes a note by hand while the model is answering
            if not self.calls:
                state["client"].patch(f"/api/jobs/{state['jid']}/lyrics", json={"verses": ["Lers-que nous è-tions"]})
            return super().post(url, **k)

    client, jid = start(settings, Editing(GOOD))
    state.update(client=client, jid=jid)
    draft = client.post(f"/api/jobs/{jid}/model-pass", json=body(confirm=True)).json()
    flags = {c["new"]["text"]: (c["conflict"], c["ticked"]) for c in draft["changes"]}
    assert flags["é"] == (True, False) and flags["Lors"] == (False, True)
