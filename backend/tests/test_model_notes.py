"""Notes and chords from engine doubts (ADR 0010, ticket 10), through the HTTP API with a fake route.

The Anton ground truth is 2/4 with 10080 divisions. Measure 0 holds E-flat4 dotted-eighth, F4 16th, G4 eighth,
G4 eighth under a Cm chord; measure 1 holds G4, A-flat4, A-flat4, G4 eighths. An answer is a list of the editor's
operations (score/edit.ts) naming a note by `measure` and `event` (0-based, as the prompt lists them).
"""
import json
import xml.etree.ElementTree as ET

from conftest import GROUND_TRUTH
from test_model_pass import start


class Reply:
    def __init__(self, text): self._t = text
    def raise_for_status(self): pass
    def json(self): return {"content": [{"type": "text", "text": self._t}]}


class FakeOps:
    """A stubbed HTTP client answering every call with `answer`, a list of operations (or raw text)."""
    def __init__(self, answer): self.answer, self.calls, self.prompts, self.models = answer, 0, [], []
    def post(self, url, **k):
        self.calls += 1
        self.prompts.append(k["json"]["messages"][0]["content"][-1]["text"])
        self.models.append(k["json"]["model"])
        return Reply(self.answer if isinstance(self.answer, str) else json.dumps(self.answer))


def span(**extra):
    return {"staff": 0, "from": 0, "to": 1, **extra}


def ask(client, jid, spans=None, **extra):
    return client.post(f"/api/jobs/{jid}/model-pass", json={"spans": spans or [span()], "api_key": "sk", "confirm": True, **extra})


def notes_of(xml, measure):
    root = ET.fromstring(xml)
    out = []
    for n in root.find("part").findall("measure")[measure].findall("note"):
        p = n.find("pitch")
        flat = {"-1": "b", "1": "#"}.get(p.findtext("alter") or "", "") if p is not None else ""
        out.append("rest" if p is None else f"{p.findtext('step')}{flat}{p.findtext('octave')}:{n.findtext('type')}")
    return out


def harmonies(xml, measure):
    m = ET.fromstring(xml).find("part").findall("measure")[measure]
    return [(h.findtext("root/root-step"), h.findtext("kind")) for h in m.findall("harmony")]


def test_a_span_without_words_is_asked_for_notes_and_chords_and_nothing_runs_without_confirm(settings):
    model = FakeOps([])
    client, jid = start(settings, model, seed="")
    r = client.post(f"/api/jobs/{jid}/model-pass", json={"spans": [span(note="the second bar looks wrong")], "api_key": "sk"})
    assert r.status_code == 200 and r.json()["calls"] == 1 and r.json()["estimated_cost_usd"] > 0 and model.calls == 0
    assert ask(client, jid, [span(note="the second bar looks wrong")]).status_code == 200
    assert model.calls == 1
    prompt = model.prompts[0]
    assert "the second bar looks wrong" in prompt and "Eb4 eighth." in prompt and "Cm" in prompt  # what the model sees: the notes and the chord


def test_operations_become_a_draft_that_shows_old_values_and_leaves_the_score_alone(settings):
    ops = [{"op": "stepPitch", "measure": 1, "event": 0, "delta": 1},       # G4 -> A4, which the key (three flats) writes as A-flat
           {"op": "setChord", "measure": 0, "event": 0, "text": "Cm7"}]     # Cm -> Cm7
    model = FakeOps(ops)
    client, jid = start(settings, model, seed="")
    before_xml = client.get(f"/api/jobs/{jid}/score.musicxml").text
    draft = ask(client, jid).json()
    kinds = [c["kind"] for c in draft["changes"]]
    assert kinds == ["notes", "chord"] and draft["dropped"] == []
    notes, chord = draft["changes"]
    assert notes["measure"] == 1 and notes["old"]["text"].startswith("G4 eighth,") and notes["new"]["text"].startswith("Ab4 eighth,")
    assert notes["ops"] == [ops[0]] and notes["marks"] == [0]
    assert chord["old"]["text"] == "Cm" and chord["new"]["text"] == "Cm7"
    assert all(c["ticked"] and not c["conflict"] for c in draft["changes"])
    assert client.get(f"/api/jobs/{jid}/score.musicxml").text == before_xml
    corrected = client.get(f"/api/jobs/{jid}/model-draft.musicxml").text
    assert notes_of(corrected, 1)[0] == "Ab4:eighth" and harmonies(corrected, 0) == [("C", "minor-seventh")]
    assert client.get(f"/api/jobs/{jid}/model-draft").json()["changes"] == draft["changes"]

    # tick only the pitch: one revision, the chord stays a stored reading
    revision = client.get(f"/api/jobs/{jid}/review").json()["revision"]
    r = client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": [notes["id"]]})
    assert r.status_code == 200 and r.json()["revision"] == revision + 1
    after = client.get(f"/api/jobs/{jid}/score.musicxml").text
    assert notes_of(after, 1)[0] == "Ab4:eighth" and harmonies(after, 0) == [("C", "minor")]
    proposed = [x for x in r.json()["model_readings"] if x["status"] == "proposed"]
    assert [(x["kind"], x["new"]["text"]) for x in proposed] == [("chord", "Cm7")]


def reasons(draft):
    return " | ".join(d["reason"] for d in draft["dropped"])


def test_operations_that_do_not_apply_are_dropped_one_by_one_with_their_reason(settings):
    ops = [{"op": "stepPitch", "measure": 1, "event": 0, "delta": 1},          # fine
           {"op": "stepPitch", "measure": 1, "event": 99, "delta": 1},         # no such note
           {"op": "setKey", "measure": 0, "event": 0, "fifths": 2},            # not in the vocabulary: the key is out of a pass
           {"op": "stepPitch", "measure": 5, "event": 0, "delta": 1},          # outside the span
           {"op": "setAlter", "measure": 1, "event": 1, "alter": 9}]           # not an alteration
    client, jid = start(settings, FakeOps(ops), seed="")
    draft = ask(client, jid).json()
    assert [c["measure"] for c in draft["changes"]] == [1] and draft["changes"][0]["ops"] == [ops[0]]
    assert len(draft["dropped"]) == 4
    why = reasons(draft)
    assert "no note 99" in why and "unknown operation 'setKey'" in why and "outside the span" in why and "`alter` must be" in why
    assert all(d["span"] == {"staff": 0, "from": 0, "to": 1} for d in draft["dropped"])


def test_a_measure_that_added_up_must_still_add_up_but_a_balanced_group_is_kept(settings):
    lengthen = {"op": "setDuration", "measure": 1, "event": 0, "type": "quarter", "dots": 0}      # 3 + 1 eighths: overfull
    client, jid = start(settings, FakeOps([lengthen]), seed="")
    draft = ask(client, jid).json()
    assert draft["changes"] == [] and "added up" in reasons(draft) and "measure 1" in reasons(draft)
    # the same lengthening with the last note taken away adds up again: one change, both operations
    both = [lengthen, {"op": "deleteEvent", "measure": 1, "event": 3}]
    client, jid = start(settings, FakeOps(both), seed="")
    draft = ask(client, jid).json()
    assert len(draft["changes"]) == 1 and draft["changes"][0]["ops"] == both and draft["dropped"] == []
    assert draft["changes"][0]["new"]["text"] == "G4 quarter, Ab4 eighth, Ab4 eighth"
    corrected = client.get(f"/api/jobs/{jid}/model-draft.musicxml").text
    assert notes_of(corrected, 1) == ["G4:quarter", "Ab4:eighth", "Ab4:eighth"]
    assert len(ET.fromstring(corrected).find("part").findall("measure")) == 19   # the measure count is unchanged


def test_a_measure_that_was_wrong_may_get_better_but_not_worse(settings):
    model = FakeOps([])
    client, jid = start(settings, model, seed="")
    root = ET.fromstring(client.get(f"/api/jobs/{jid}/score.musicxml").text)
    m = root.find("part").findall("measure")[1]
    m.remove(m.findall("note")[3])                       # bar 2 is now short by an eighth
    revision = client.get(f"/api/jobs/{jid}/review").json()["revision"]
    r = client.put(f"/api/jobs/{jid}/score", json={"musicxml": ET.tostring(root, encoding="unicode"), "revision": revision, "checked": []})
    assert r.status_code == 200, r.text
    model.answer = [{"op": "deleteEvent", "measure": 1, "event": 2}]      # shorter still
    draft = ask(client, jid).json()
    assert draft["changes"] == [] and "worse" in reasons(draft)
    model.answer = [{"op": "setDuration", "measure": 1, "event": 0, "type": "quarter", "dots": 0}]   # now it adds up
    draft = ask(client, jid).json()
    assert len(draft["changes"]) == 1 and draft["dropped"] == []


def test_an_answer_that_is_not_operations_goes_to_the_larger_model_once_then_is_dropped(settings):
    model = FakeOps("I think bar 2 is fine.")
    client, jid = start(settings, model, seed="")
    draft = ask(client, jid).json()
    assert model.calls == 2 and model.models[0] != model.models[1]
    assert draft["changes"] == [] and "not a list of operations" in reasons(draft) and "larger model" in reasons(draft)
    model.answer = [{"op": "stepPitch", "measure": 0, "event": 1, "delta": -1}]   # the first model fails, the larger one answers
    model.calls, model.models = 0, []
    first = [json.dumps("nonsense"), json.dumps(model.answer)]
    model.post = lambda url, **k: (setattr(model, "calls", model.calls + 1), model.models.append(k["json"]["model"]), Reply(first[min(model.calls - 1, 1)]))[2]
    draft = ask(client, jid).json()
    assert len(draft["changes"]) == 1 and draft["escalated"] and draft["escalated"][0]["model"] == model.models[1]


def test_a_note_edited_by_hand_after_the_pass_makes_its_change_a_conflict(settings):
    model = FakeOps([{"op": "stepPitch", "measure": 1, "event": 0, "delta": 1}, {"op": "setChord", "measure": 0, "event": 0, "text": "Cm7"}])
    client, jid = start(settings, model, seed="")
    ask(client, jid)
    root = ET.fromstring(client.get(f"/api/jobs/{jid}/score.musicxml").text)
    note = root.find("part").findall("measure")[1].find("note")
    note.find("pitch/octave").text = "5"                  # the user moves the first note of bar 2 an octave up
    revision = client.get(f"/api/jobs/{jid}/review").json()["revision"]
    assert client.put(f"/api/jobs/{jid}/score", json={"musicxml": ET.tostring(root, encoding="unicode"), "revision": revision, "checked": []}).status_code == 200
    changes = client.get(f"/api/jobs/{jid}/model-draft").json()["changes"]
    assert [(c["kind"], c["conflict"], c["ticked"]) for c in changes] == [("notes", True, False), ("chord", False, True)]
