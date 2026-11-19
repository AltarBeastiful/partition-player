"""The lyrics source as a picture, through the HTTP API with a fake route (ADR 0010, ticket 07)."""
import base64

from test_model_pass import GOOD, SOURCE, FakeModel, Reply, body, start

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
PICTURE = base64.b64encode(PNG).decode()


class PictureModel(FakeModel):
    """Answers a call that carries an image with `reading` (the transcription), any other with the syllables."""
    def __init__(self, answer, reading):
        super().__init__(answer)
        self.reading, self.pictures = reading, 0

    def post(self, url, **k):
        content = k["json"]["messages"][0]["content"]
        if any(b["type"] == "image" for b in content):
            self.pictures += 1
            return Reply(self.reading)
        return super().post(url, **k)


def picture_body(**extra):
    return {"spans": [{"staff": 0, "from": 0, "to": 1, "lyrics_picture": PICTURE}], "api_key": "sk-visitor", **extra}


def test_a_picture_gives_the_draft_the_same_text_typed_would(settings):
    typed_client, typed_id = start(settings, FakeModel(GOOD))
    typed = typed_client.post(f"/api/jobs/{typed_id}/model-pass", json=body(confirm=True)).json()
    model = PictureModel(GOOD, SOURCE)
    client, jid = start(settings, model)
    r = client.post(f"/api/jobs/{jid}/model-pass", json=picture_body(confirm=True))
    assert r.status_code == 200, r.text
    assert model.pictures == 1 and model.calls == 1
    assert r.json()["changes"] == typed["changes"] and r.json()["dropped"] == []
    assert r.json()["spans"][0]["lyrics_source"] == SOURCE  # what was read is what is kept
    assert "lyrics_picture" not in r.json()["spans"][0]


def test_the_estimate_counts_the_reading_and_reads_nothing(settings):
    model = PictureModel(GOOD, SOURCE)
    client, jid = start(settings, model)
    r = client.post(f"/api/jobs/{jid}/model-pass", json=picture_body())
    assert r.status_code == 200 and r.json()["calls"] == 2 and r.json()["vision"] is True
    assert model.pictures == 0 and model.calls == 0


def test_a_picture_that_cannot_be_read_is_reported_and_nothing_is_guessed(settings):
    model = PictureModel(GOOD, "UNREADABLE")
    client, jid = start(settings, model)
    r = client.post(f"/api/jobs/{jid}/model-pass", json=picture_body(confirm=True))
    assert r.status_code == 200
    assert r.json()["changes"] == [] and model.calls == 0
    assert len(r.json()["dropped"]) == 1 and "picture" in r.json()["dropped"][0]["reason"]


def test_the_letter_check_applies_to_the_text_read_from_the_picture(settings):
    client, jid = start(settings, PictureModel(GOOD, "Lors-que vous é-tiez"))
    r = client.post(f"/api/jobs/{jid}/model-pass", json=picture_body(confirm=True))
    assert r.json()["changes"] == [] and "letters" in r.json()["dropped"][0]["reason"]


def test_a_picture_and_a_text_together_or_a_bad_picture_are_refused(settings):
    client, jid = start(settings, PictureModel(GOOD, SOURCE))
    both = picture_body()
    both["spans"][0]["lyrics_source"] = SOURCE
    assert client.post(f"/api/jobs/{jid}/model-pass", json=both).status_code == 422
    bad = picture_body()
    bad["spans"][0]["lyrics_picture"] = base64.b64encode(b"not an image").decode()
    assert client.post(f"/api/jobs/{jid}/model-pass", json=bad).status_code == 422


def test_a_route_without_vision_refuses_a_picture_and_says_so(settings, monkeypatch):
    from partition_player.model.route import Route

    monkeypatch.setattr(Route, "anthropic", classmethod(lambda cls, key, model="m": cls("http://x", key, model, vision=False)))
    model = PictureModel(GOOD, SOURCE)
    client, jid = start(settings, model)
    r = client.post(f"/api/jobs/{jid}/model-pass", json=picture_body(confirm=True))
    assert r.status_code == 409 and "image" in r.json()["error"] and model.pictures == 0
    assert client.post(f"/api/jobs/{jid}/model-pass", json=body(confirm=True)).status_code == 200  # typed text still works
    assert client.post(f"/api/jobs/{jid}/model-pass", json=body()).json()["vision"] is False
    assert client.get("/api/model-route").json()["vision"] is False


def test_the_route_says_whether_it_is_on_and_reads_pictures(settings, monkeypatch):
    client, _ = start(settings, FakeModel(GOOD))
    assert client.get("/api/model-route").json() == {"enabled": False, "model": "claude-haiku-4-5-20251001", "vision": True}
    monkeypatch.setenv("PP_ANTHROPIC_API_KEY", "sk-server")
    from partition_player.config import load_settings

    client, _ = start(load_settings(), FakeModel(GOOD))
    assert client.get("/api/model-route").json()["enabled"] is True
