"""Spans the user flagged as wrong, with a note to the model (ADR 0010, ticket 11), through the HTTP API."""
from test_model_notes import FakeOps, ask, span
from test_model_pass import GOOD, FakeModel, SOURCE, start

NOTE = "the second bar is a triplet, I can see it on the page"


def test_the_note_of_a_flagged_span_reaches_the_model_and_is_stored_with_the_draft_and_its_readings(settings):
    model = FakeOps([{"op": "stepPitch", "measure": 1, "event": 0, "delta": 1}])
    client, jid = start(settings, model, seed="")
    draft = ask(client, jid, [span(note=NOTE)]).json()
    assert NOTE in model.prompts[0]
    assert draft["spans"][0]["note"] == NOTE                                  # stored with the span in the draft
    r = client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": []})
    readings = r.json()["model_readings"]
    assert readings and all(x["span"]["note"] == NOTE for x in readings)      # and with the stored readings


def test_the_note_also_reaches_the_prompt_when_the_flagged_span_comes_with_words(settings):
    model = FakeModel(GOOD)
    client, jid = start(settings, model)
    body = {"spans": [{"staff": 0, "from": 0, "to": 1, "lyrics_source": SOURCE, "note": NOTE}], "api_key": "sk", "confirm": True}
    r = client.post(f"/api/jobs/{jid}/model-pass", json=body)
    assert r.status_code == 200 and NOTE in model.prompts[0]
    assert r.json()["spans"][0]["note"] == NOTE
