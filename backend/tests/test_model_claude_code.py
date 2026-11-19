"""The Claude Code route (ADR 0010 decision 11): bundles out through the CLI, answers in through the CLI,
and a draft that looks and applies like one from an API route. No model is called anywhere."""
import json
import xml.etree.ElementTree as ET

from conftest import GROUND_TRUTH  # noqa: F401  (the fixture score)
from partition_player.cli import main
from test_model_notes import FakeOps, ask as api_ask, span as notes_span
from test_model_pass import GOOD, SOURCE, FakeModel, body, start


def export(jid, out, *extra):
    assert main(["model-pass", "export", jid, "-o", str(out), *extra]) == 0
    return json.loads((out / "index.json").read_text())


def test_export_writes_one_bundle_per_span_with_the_same_prompt_the_api_sends(settings, tmp_path):
    api_model = FakeModel(GOOD)
    client, jid = start(settings, api_model)
    lyrics = tmp_path / "words.txt"
    lyrics.write_text(SOURCE)
    out = tmp_path / "bundles"
    index = export(jid, out, "--span", f"0:0:1:{lyrics}", "--span", "0:1:1")
    assert len(index["tasks"]) == 2
    first, second = (out / t["dir"] for t in index["tasks"])
    task = json.loads((first / "task.json").read_text())
    assert task["span"] == {"staff": 0, "from": 0, "to": 1, "lyrics_source": SOURCE} and task["verse"] == 1
    assert "JSON array" in task["answer_format"]
    ET.parse(first / "score.musicxml")  # a slice of the score
    assert len(ET.parse(first / "score.musicxml").getroot().find("part").findall("measure")) == 2
    # the words task carries exactly the prompt an API route would have sent
    api_model.prompts.clear()
    assert api_model.calls == 0
    client.post(f"/api/jobs/{jid}/model-pass", json=body(confirm=True))
    assert (first / "prompt.txt").read_text() == api_model.prompts[0]
    # a span without words is a notes task
    assert json.loads((second / "task.json").read_text())["span"].get("lyrics_source") is None
    assert "operations" in json.loads((second / "task.json").read_text())["answer_format"]


def test_import_gives_a_draft_like_an_api_one_and_it_applies(settings, tmp_path):
    api_model = FakeModel(GOOD)
    client, jid = start(settings, api_model)
    # the reference: what the API route makes of the same answer
    ref = client.post(f"/api/jobs/{jid}/model-pass", json=body(confirm=True)).json()
    client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": []})  # drops the draft, keeps the score as seeded

    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"answers": [{
        "span": {"staff": 0, "from": 0, "to": 1, "lyrics_source": SOURCE}, "verse": 1,
        "reply": [{"text": t, "note": n} for t, n in GOOD]}]}))
    assert main(["model-pass", "import", jid, str(answers)]) == 0
    draft = client.get(f"/api/jobs/{jid}/model-draft").json()
    strip = lambda cs: [{k: v for k, v in c.items() if k != "id"} for c in cs]
    assert strip(draft["changes"]) == strip(ref["changes"]) and draft["dropped"] == []
    assert draft["route"] == {"kind": "claude-code", "model": "unknown"}
    assert b"Lors" in client.get(f"/api/jobs/{jid}/model-draft.musicxml").content

    state = client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": [c["id"] for c in draft["changes"]]}).json()
    assert client.get(f"/api/jobs/{jid}/lyrics").json()["verses"] == ["Lors-que nous é-tions"]
    mine = [r for r in state["model_readings"] if r["route"] == "claude-code"]
    assert mine and all(r["model"] == "unknown" and r["status"] == "accepted" for r in mine)


def test_a_reported_model_is_recorded_and_invalid_answers_are_dropped_with_reasons(settings, tmp_path, capsys):
    client, jid = start(settings, FakeModel(GOOD))
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"model": "claude-opus-4-5", "answers": [
        {"span": {"staff": 0, "from": 0, "to": 1, "lyrics_source": SOURCE}, "verse": 1,
         "reply": json.dumps([{"text": "Lors-", "note": 0}, {"text": "XX", "note": 1}])}]}))  # letters differ from the source
    assert main(["model-pass", "import", jid, str(answers)]) == 0
    draft = client.get(f"/api/jobs/{jid}/model-draft").json()
    assert draft["route"] == {"kind": "claude-code", "model": "claude-opus-4-5"}
    assert draft["changes"] == [] and "letters" in draft["dropped"][0]["reason"]
    assert "letters" in capsys.readouterr().out  # the CLI says why


def test_notes_answers_and_missing_answers(settings, tmp_path):
    client, jid = start(settings, FakeOps([]), seed="")
    ref_model = FakeOps([{"op": "stepPitch", "measure": 0, "event": 0, "delta": 1}])
    ref_client, ref_jid = start(settings, ref_model, seed="")
    ref = api_ask(ref_client, ref_jid).json()
    assert ref["changes"], "the fixture operation must apply"
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"answers": [
        {"span": notes_span(), "reply": [{"op": "stepPitch", "measure": 0, "event": 0, "delta": 1}]},
        {"span": {"staff": 0, "from": 0, "to": 1, "note": "second one, never answered"}}]}))
    assert main(["model-pass", "import", jid, str(answers)]) == 0
    draft = client.get(f"/api/jobs/{jid}/model-draft").json()
    assert [(c["kind"], c["old"], c["new"]) for c in draft["changes"]] == [(c["kind"], c["old"], c["new"]) for c in ref["changes"]]
    assert any("no answer" in d["reason"] for d in draft["dropped"])


def test_import_refuses_an_unknown_job(settings, tmp_path):
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"answers": []}))
    assert main(["model-pass", "import", "nope", str(answers)]) == 1
