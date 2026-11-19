"""The Claude Code route over HTTP (ADR 0010 decision 11): a session on another machine fetches the repair
bundles from the site, answers them, and posts the answers back. No model is called by the server."""
import json
from dataclasses import replace

from fastapi.testclient import TestClient
from test_model_pass import GOOD, SOURCE, FakeModel, start

from partition_player.api import create_app


def test_export_returns_the_bundles_and_writes_nothing(settings):
    api_model = FakeModel(GOOD)
    client, jid = start(settings, api_model)
    r = client.post(f"/api/jobs/{jid}/model-pass/export", json={"spans": [{"staff": 0, "from": 0, "to": 1, "lyrics_source": SOURCE}]})
    assert r.status_code == 200
    out = r.json()
    assert out["job"] == jid and len(out["tasks"]) == 1
    task = out["tasks"][0]
    assert task["span"]["lyrics_source"] == SOURCE and task["verse"] == 1
    assert "<score-partwise" in task["score_musicxml"] and task["answer_format"] and task["prompt"]
    assert out["page"] == f"/api/jobs/{jid}/review.webp"
    # the prompt is the very one the API route sends
    client.post(f"/api/jobs/{jid}/model-pass", json={"spans": [{"staff": 0, "from": 0, "to": 1, "lyrics_source": SOURCE}], "api_key": "sk-x", "confirm": True})
    assert task["prompt"] in api_model.prompts
    assert not list(settings.jobs_dir.glob(f"{jid}/task-*"))  # nothing was written on the server


def test_export_without_spans_takes_the_engines_doubts_strongest_first(settings):
    client, jid = start(settings, FakeModel(GOOD))
    review = settings.jobs_dir / jid / "review.json"
    data = json.loads(review.read_text())
    data["doubts"] = [{"measure": 6, "part": 0, "text": "check", "level": "check"},
                      {"measure": 1, "part": 0, "text": "does not add up", "level": "wrong"},
                      {"measure": 2, "part": 0, "text": "does not add up", "level": "wrong"}]
    review.write_text(json.dumps(data))
    out = client.post(f"/api/jobs/{jid}/model-pass/export", json={}).json()
    spans = [t["span"] for t in out["tasks"]]
    assert [(s["from"], s["to"]) for s in spans] == [(1, 2), (6, 6)]  # neighbours join; the stretch that does not add up comes first
    assert all("note" in s and s["note"] for s in spans)  # the engine's own words go to the model


def test_export_with_nothing_doubtful_says_so(settings):
    client, jid = start(settings, FakeModel(GOOD))
    review = settings.jobs_dir / jid / "review.json"
    data = json.loads(review.read_text())
    data["doubts"] = []
    review.write_text(json.dumps(data))
    r = client.post(f"/api/jobs/{jid}/model-pass/export", json={})
    assert r.status_code == 422 and "doubt" in r.json()["error"]


def test_answers_posted_back_become_a_draft(settings):
    client, jid = start(settings, FakeModel(GOOD))
    out = client.post(f"/api/jobs/{jid}/model-pass/export", json={"spans": [{"staff": 0, "from": 0, "to": 1, "lyrics_source": SOURCE}]}).json()
    t = out["tasks"][0]
    reply = [{"text": w, "note": i} for i, w in enumerate(["Lors-", "que", "nous", "é-", "tions"])]
    r = client.post(f"/api/jobs/{jid}/model-pass/import", json={"model": "claude-test", "answers": [{"span": t["span"], "verse": t["verse"], "reply": reply}]})
    assert r.status_code == 200 and r.json()["route"]["kind"] == "claude-code"


def test_a_token_guards_export_and_import_when_configured(settings):
    guarded = replace(settings, api_token="s3cret")
    client = TestClient(create_app(guarded, model_client=FakeModel(GOOD)))
    client.__enter__()
    # the rest of the site stays open; only the two doors of the Claude Code route ask for the token
    assert client.get("/api/model-routes").status_code == 200
    jid = "x"
    assert client.post(f"/api/jobs/{jid}/model-pass/export", json={}).status_code == 401
    assert client.post(f"/api/jobs/{jid}/model-pass/import", json={}).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert client.post(f"/api/jobs/{jid}/model-pass/export", json={}, headers=bad).status_code == 401
    ok = {"Authorization": "Bearer s3cret"}
    assert client.post(f"/api/jobs/{jid}/model-pass/export", json={}, headers=ok).status_code == 404  # past the door: no such job
