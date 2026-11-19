"""The model pass through the HTTP API with a fake route (ADR 0010, plan 0016 slice 1, ticket 02)."""
import json

from fastapi.testclient import TestClient

from conftest import PHOTO
from test_api import wait_done

SOURCE = "Lors-que nous é-tions"


class Reply:
    def __init__(self, text): self._t = text
    def raise_for_status(self): pass
    def json(self): return {"content": [{"type": "text", "text": self._t}]}


class FakeModel:
    """A stubbed HTTP client: answers every call with `answer` (a list of [syllable, note index] pairs)."""
    def __init__(self, answer): self.answer, self.calls, self.prompts = answer, 0, []
    def post(self, url, **k):
        self.calls += 1
        self.prompts.append(k["json"]["messages"][0]["content"][-1]["text"])
        return Reply(json.dumps([{"text": t, "note": n} for t, n in self.answer]))


GOOD = [("Lors-", 0), ("que", 1), ("nous", 2), ("é-", 3), ("tions", 4)]


def start(settings, model, seed="Lers-que nous é-tions"):
    """An app with a recognized score whose lyrics were misread: (client, job id)."""
    from partition_player.api import create_app

    client = TestClient(create_app(settings, model_client=model))
    client.__enter__()
    job = wait_done(client, client.post("/api/jobs", files={"file": ("p.jpg", PHOTO.read_bytes(), "image/jpeg")}).json()["id"])
    if seed:
        assert client.patch(f"/api/jobs/{job['id']}/lyrics", json={"verses": [seed]}).status_code == 200
    return client, job["id"]


def body(**extra):
    return {"spans": [{"staff": 0, "from": 0, "to": 1, "lyrics_source": SOURCE}], "api_key": "sk-visitor", **extra}


def test_off_without_a_key_and_nothing_runs_without_confirm(settings):
    model = FakeModel(GOOD)
    client, jid = start(settings, model)
    r = client.post(f"/api/jobs/{jid}/model-pass", json={**body(), "api_key": ""})
    assert r.status_code == 409 and "model" in r.json()["error"]
    r = client.post(f"/api/jobs/{jid}/model-pass", json=body())  # no confirm: an estimate only
    assert r.status_code == 200 and r.json()["calls"] == 1 and r.json()["estimated_cost_usd"] > 0
    assert model.calls == 0 and client.get(f"/api/jobs/{jid}/model-draft").status_code == 404


def test_typed_source_gives_a_draft_with_old_values_and_unticked_changes_become_readings(settings):
    model = FakeModel(GOOD)
    client, jid = start(settings, model)
    before = client.get(f"/api/jobs/{jid}/review").json()["revision"]
    r = client.post(f"/api/jobs/{jid}/model-pass", json=body(confirm=True))
    assert r.status_code == 200, r.text
    draft = r.json()
    assert model.calls == 1 and "Lors-que nous" in model.prompts[0]
    changes = draft["changes"]
    assert [(c["measure"], c["onset"], c["new"]["text"], c["new"]["syllabic"]) for c in changes] == [
        (0, 0, "Lors", "begin"), (0, 1, "que", "end"), (0, 2, "nous", "single"), (0, 3, "é", "begin"), (1, 0, "tions", "end")]
    assert changes[0]["old"] == {"text": "Lers", "syllabic": "begin"} and changes[2]["old"] == {"text": "nous", "syllabic": "single"}
    assert all(c["ticked"] and not c["conflict"] and c["id"] for c in changes) and draft["dropped"] == []
    assert client.get(f"/api/jobs/{jid}/model-draft").json()["changes"] == changes
    # the score itself is untouched until the draft is applied; the corrected copy is a download
    assert client.get(f"/api/jobs/{jid}/lyrics").json()["verses"] == ["Lers-que nous é-tions"]
    assert b"Lors" in client.get(f"/api/jobs/{jid}/model-draft.musicxml").content

    # tick everything but the first change
    r = client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": [c["id"] for c in changes[1:]]})
    assert r.status_code == 200 and r.json()["revision"] == before + 1  # one revision for the whole draft
    assert client.get(f"/api/jobs/{jid}/lyrics").json()["verses"] == ["Lers-que nous é-tions"]  # only the first differs, and it was unticked
    assert client.get(f"/api/jobs/{jid}/model-draft").status_code == 404
    readings = r.json()["model_readings"]
    assert [x["new"]["text"] for x in readings if x["status"] == "proposed"] == ["Lors"]
    assert readings[0]["route"] == "api" and readings[0]["model"] and readings[0]["time"]


def test_apply_changes_the_lyrics_when_ticked(settings):
    client, jid = start(settings, FakeModel(GOOD))
    draft = client.post(f"/api/jobs/{jid}/model-pass", json=body(confirm=True)).json()
    assert client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": ["nope"]}).status_code == 422
    r = client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": [c["id"] for c in draft["changes"]]})
    assert r.status_code == 200
    assert client.get(f"/api/jobs/{jid}/lyrics").json()["verses"] == ["Lors-que nous é-tions"]


def test_answer_with_other_letters_is_dropped_and_the_reason_recorded(settings):
    wrong = [("Lors-", 0), ("que", 1), ("nos", 2), ("é-", 3), ("tions", 4)]
    client, jid = start(settings, FakeModel(wrong))
    draft = client.post(f"/api/jobs/{jid}/model-pass", json=body(confirm=True)).json()
    assert draft["changes"] == [] and len(draft["dropped"]) == 1 and "letters" in draft["dropped"][0]["reason"]
    assert client.get(f"/api/jobs/{jid}/lyrics").json()["verses"] == ["Lers-que nous é-tions"]
    # whitespace and hyphens are the only slack: a different split of the same letters is accepted
    resplit = [("Lorsque", 0), ("nous", 2), ("é-", 3), ("tions", 4)]
    client, jid = start(settings, FakeModel(resplit))
    draft = client.post(f"/api/jobs/{jid}/model-pass", json=body(confirm=True)).json()
    assert draft["dropped"] == [] and draft["changes"][0]["new"]["text"] == "Lorsque"
    # notes out of order, or outside the span, are dropped too
    for bad in ([("Lors-", 1), ("que", 0), ("nous", 2), ("é-", 3), ("tions", 4)], [("Lors-", 0), ("que", 1), ("nous", 2), ("é-", 3), ("tions", 99)]):
        client, jid = start(settings, FakeModel(bad))
        draft = client.post(f"/api/jobs/{jid}/model-pass", json=body(confirm=True)).json()
        assert draft["changes"] == [] and draft["dropped"]


def test_a_hand_edit_after_the_pass_is_a_conflict_and_unticked_but_the_rest_applies(settings):
    client, jid = start(settings, FakeModel(GOOD))
    client.post(f"/api/jobs/{jid}/model-pass", json=body(confirm=True))
    client.patch(f"/api/jobs/{jid}/lyrics", json={"verses": ["Lers-que nous è-tions"]})  # the user fixes the fourth note by hand
    state = client.get(f"/api/jobs/{jid}/model-draft").json()
    flags = {c["new"]["text"]: (c["conflict"], c["ticked"]) for c in state["changes"]}
    assert flags["é"] == (True, False) and flags["Lors"] == (False, True)
    ok = [c["id"] for c in state["changes"] if not c["conflict"]]
    client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": ok})
    assert client.get(f"/api/jobs/{jid}/lyrics").json()["verses"] == ["Lors-que nous è-tions"]


def test_model_readings_survive_a_save_of_the_score(settings):
    client, jid = start(settings, FakeModel(GOOD), seed="Lers-qui nos é-tions")
    draft = client.post(f"/api/jobs/{jid}/model-pass", json=body(confirm=True)).json()
    client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": [draft["changes"][0]["id"]]})
    review = client.get(f"/api/jobs/{jid}/review").json()
    assert [r["status"] for r in review["model_readings"]] == ["accepted", "proposed", "proposed"]  # the changes that were not no-ops
    score = client.get(f"/api/jobs/{jid}/score.musicxml").text
    saved = client.put(f"/api/jobs/{jid}/score", json={"musicxml": score, "revision": review["revision"]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["model_readings"] == review["model_readings"]
    assert client.get(f"/api/jobs/{jid}/review").json()["model_readings"] == review["model_readings"]


def test_the_visitors_key_is_never_stored(settings):
    client, jid = start(settings, FakeModel(GOOD))
    client.post(f"/api/jobs/{jid}/model-pass", json=body(confirm=True))
    for p in settings.jobs_dir.rglob("*"):
        if p.is_file():
            assert b"sk-visitor" not in p.read_bytes(), p


def test_a_server_key_turns_it_on_and_a_span_outside_the_score_is_refused(settings, monkeypatch):
    monkeypatch.setenv("PP_ANTHROPIC_API_KEY", "sk-server")
    from partition_player.config import load_settings

    client, jid = start(load_settings(), FakeModel(GOOD))
    payload = body(confirm=True)
    del payload["api_key"]
    assert client.post(f"/api/jobs/{jid}/model-pass", json=payload).status_code == 200
    payload["spans"][0]["to"] = 40
    assert client.post(f"/api/jobs/{jid}/model-pass", json=payload).status_code == 422


# ---- DeepSeek preset and the vision flag (ADR 0010, decision 9, ticket 09) ----

class Recorder(FakeModel):
    def post(self, url, **k):
        self.urls = getattr(self, "urls", []) + [(url, k["headers"])]
        return super().post(url, **k)


def test_deepseek_route_places_typed_words_with_its_own_url_key_and_model(settings, monkeypatch):
    monkeypatch.setenv("PP_DEEPSEEK_API_KEY", "ds-server-key")
    monkeypatch.setenv("PP_DEEPSEEK_MODEL", "deepseek-test")
    from partition_player.config import load_settings
    model = Recorder(GOOD)
    client, jid = start(load_settings(), model)
    routes = {r["id"]: r for r in client.get("/api/model-routes").json()}
    assert routes["deepseek"]["model"] == "deepseek-test" and routes["deepseek"]["vision"] is False and routes["deepseek"]["configured"] is True
    assert routes["anthropic"]["vision"] is True and routes["anthropic"]["configured"] is False
    r = client.post(f"/api/jobs/{jid}/model-pass", json={**body(confirm=True), "api_key": "", "route": "deepseek"})
    assert r.status_code == 200, r.text
    url, headers = model.urls[0]
    assert url == "https://api.deepseek.com/anthropic/v1/messages" and headers["x-api-key"] == "ds-server-key"
    assert r.json()["route"]["model"] == "deepseek-test" and r.json()["changes"]


def test_a_span_that_needs_the_picture_is_refused_with_a_reason_on_a_route_without_vision(settings, monkeypatch):
    monkeypatch.setenv("PP_DEEPSEEK_API_KEY", "ds")
    from partition_player.config import load_settings
    model = FakeModel(GOOD)
    client, jid = start(load_settings(), model)
    b = body(confirm=True)
    b["spans"][0]["needs_image"] = True
    r = client.post(f"/api/jobs/{jid}/model-pass", json={**b, "route": "deepseek"})
    assert r.status_code == 422 and "cannot read images" in r.json()["error"] and model.calls == 0
    r = client.post(f"/api/jobs/{jid}/model-pass", json={**b, "route": "deepseek", "confirm": False})
    assert r.status_code == 422  # the estimate refuses too: no cost for a call that cannot work
    monkeypatch.setenv("PP_DEEPSEEK_VISION", "true")
    client2, jid2 = start(load_settings(), model)
    assert client2.post(f"/api/jobs/{jid2}/model-pass", json={**b, "route": "deepseek", "confirm": False}).status_code == 200


def test_unknown_route_is_refused(settings):
    client, jid = start(settings, FakeModel(GOOD))
    assert client.post(f"/api/jobs/{jid}/model-pass", json={**body(), "route": "nope"}).status_code == 422

def test_the_visitors_key_is_never_logged_even_when_the_model_fails(settings, caplog):
    import logging

    class Broken:
        def post(self, url, **k):
            raise RuntimeError(f"boom {k['headers']}")

    caplog.set_level(logging.DEBUG)
    for model in (FakeModel(GOOD), Broken()):
        client, jid = start(settings, model)
        try:
            client.post(f"/api/jobs/{jid}/model-pass", json=body())
            client.post(f"/api/jobs/{jid}/model-pass", json=body(confirm=True))
        except RuntimeError:
            pass
    assert "sk-visitor" not in caplog.text


def test_a_job_over_the_server_key_cap_is_refused_with_a_reason(settings, monkeypatch):
    monkeypatch.setenv("PP_ANTHROPIC_API_KEY", "sk-server")
    monkeypatch.setenv("PP_MODEL_MAX_SPANS", "2")
    from partition_player.config import load_settings

    model = FakeModel(GOOD)
    client, jid = start(load_settings(), model)
    payload = body(confirm=True)
    del payload["api_key"]
    payload["spans"] = payload["spans"] * 3
    for confirm in (False, True):
        r = client.post(f"/api/jobs/{jid}/model-pass", json={**payload, "confirm": confirm})
        assert r.status_code == 422 and "cap" in r.json()["error"] and "2" in r.json()["error"]
    assert model.calls == 0
    # the visitor's own key pays for itself: the cap does not apply
    assert client.post(f"/api/jobs/{jid}/model-pass", json={**payload, "api_key": "sk-visitor", "confirm": False}).status_code == 200
