import time

from fastapi.testclient import TestClient

from conftest import PHOTO


def wait_done(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_upload_recognize_download(settings):
    from partition_player.api import create_app

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["engine"] == "fake"
        r = client.post("/api/jobs", files={"file": ("photo.jpg", PHOTO.read_bytes(), "image/jpeg")})
        assert r.status_code == 202, r.text
        job = wait_done(client, r.json()["id"])
        assert job["status"] == "done", job
        assert job["result"]["stats"]["measures"] == 19
        score = client.get(f"/api/jobs/{job['id']}/score.musicxml")
        assert score.status_code == 200 and b"<score-partwise" in score.content


def test_rejects_non_images(settings):
    from partition_player.api import create_app

    with TestClient(create_app(settings)) as client:
        r = client.post("/api/jobs", files={"file": ("x.txt", b"hello", "text/plain")})
        assert r.status_code == 415
        assert client.get("/api/jobs/nope").status_code == 404


def test_library_list_rename_delete(settings):
    from partition_player.api import create_app

    with TestClient(create_app(settings)) as client:
        r = client.post("/api/jobs", files={"file": ("Anton_Yvan-Boris.jpg", PHOTO.read_bytes(), "image/jpeg")})
        job = wait_done(client, r.json()["id"])
        assert job["name"] == "Anton Yvan Boris"
        assert client.get(f"/api/jobs/{job['id']}/thumb.jpg").headers["content-type"] == "image/jpeg"
        kept = sorted(p.name for p in (settings.jobs_dir / job["id"]).iterdir())
        assert kept == ["original.musicxml", "result.json", "review.json", "review.webp", "score.musicxml", "status.json", "thumb.jpg"]
        assert (settings.jobs_dir / job["id"] / "review.webp").stat().st_size <= 300_000  # ADR 0005: the photo the editor shows
        assert client.get(f"/api/jobs/{job['id']}/input").status_code == 404

        listed = client.get("/api/jobs").json()
        assert [j["id"] for j in listed] == [job["id"]]

        r = client.patch(f"/api/jobs/{job['id']}", json={"name": "  Ma   chanson  "})
        assert r.json()["name"] == "Ma chanson"
        assert client.patch(f"/api/jobs/{job['id']}", json={"name": ""}).json()["name"] == "Anton Yvan Boris"

        assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
        assert client.get(f"/api/jobs/{job['id']}").status_code == 404
        assert client.get("/api/jobs").json() == []


def test_spa_fallback(settings, tmp_path):
    from partition_player.api import create_app
    from partition_player.config import Settings

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "a.js").write_text("js")
    app = create_app(Settings(data_dir=settings.data_dir, engine="fake", frontend_dir=dist))
    with TestClient(app) as client:
        assert client.get("/").text == "<html>app</html>"
        assert client.get("/s/abc123").text == "<html>app</html>"
        assert client.get("/assets/a.js").text == "js"
        assert client.get("/api/jobs/nope").status_code == 404
        assert client.get("/api/whatever").status_code == 404


def test_failed_job_keeps_input_and_is_pruned(settings, monkeypatch):
    from partition_player.api import create_app
    from partition_player.config import Settings

    monkeypatch.setenv("PP_FAKE_MUSICXML", "/nonexistent.musicxml")
    app = create_app(Settings(data_dir=settings.data_dir, engine="fake", frontend_dir=settings.frontend_dir))
    with TestClient(app) as client:
        r = client.post("/api/jobs", files={"file": ("photo.jpg", PHOTO.read_bytes(), "image/jpeg")})
        job = wait_done(client, r.json()["id"])
        assert job["status"] == "failed" and job["error"]
        names = {p.name for p in (settings.jobs_dir / job["id"]).iterdir()}
        assert "input.jpg" in names and "preprocessed.png" not in names and "fake" not in names
        assert app.state.store.prune(0) == 1  # a failed job past its TTL goes; done ones never do
        assert client.get("/api/jobs").json() == []


def test_cap_drops_oldest_scores(settings):
    from partition_player.api import create_app
    from partition_player.config import Settings

    app = create_app(Settings(data_dir=settings.data_dir, engine="fake", frontend_dir=settings.frontend_dir, max_scores=2))
    with TestClient(app) as client:
        ids = []
        for i in range(3):
            r = client.post("/api/jobs", files={"file": (f"s{i}.jpg", PHOTO.read_bytes(), "image/jpeg")})
            ids.append(wait_done(client, r.json()["id"])["id"])
        listed = [j["id"] for j in client.get("/api/jobs").json()]
        assert listed == [ids[2], ids[1]]


def test_lyrics_editor_round_trip(settings):
    from partition_player.api import create_app

    with TestClient(create_app(settings)) as client:
        r = client.post("/api/jobs", files={"file": ("photo.jpg", PHOTO.read_bytes(), "image/jpeg")})
        job = wait_done(client, r.json()["id"])
        state = client.get(f"/api/jobs/{job['id']}/lyrics").json()
        assert state["verses"] == [] and state["notes"] > 10 and len(state["measures"]) == 19
        r = client.patch(f"/api/jobs/{job['id']}/lyrics", json={"verses": ["Lors-que nous_ é-tions", "* Deux"]})
        assert r.status_code == 200, r.text
        state = r.json()
        assert state["verses"] == ["Lors-que nous_ é-tions", "* Deux"] and state["syllables"] == [5, 1]
        score = client.get(f"/api/jobs/{job['id']}/score.musicxml")
        assert score.content.count(b"<lyric") == 6 and score.headers["cache-control"] == "no-cache"
        assert "lyrics.json" in [p.name for p in (settings.jobs_dir / job["id"]).iterdir()]
        assert client.patch(f"/api/jobs/{job['id']}/lyrics", json={"verses": []}).json()["verses"] == []


def test_editor_save_revert_and_revision(settings):
    """ADR 0005: the browser saves the whole document; the server validates, re-reads the lyrics,
    keeps the revision honest and can put the recognized version back."""
    from partition_player.api import create_app

    with TestClient(create_app(settings)) as client:
        r = client.post("/api/jobs", files={"file": ("photo.jpg", PHOTO.read_bytes(), "image/jpeg")})
        job = wait_done(client, r.json()["id"])
        jid = job["id"]
        state = client.get(f"/api/jobs/{jid}/review").json()
        assert state["revision"] == 1 and state["doubts"] == [] and state["checked"] == []
        assert state["has_image"] and state["has_original"] and state["layout"] is None  # the fake engine has no geometry
        assert client.get(f"/api/jobs/{jid}/review.webp").headers["content-type"] == "image/webp"
        assert b"<score-partwise" in client.get(f"/api/jobs/{jid}/original.musicxml").content

        client.patch(f"/api/jobs/{jid}/lyrics", json={"verses": ["Lors-que nous é-tions"]})
        xml = client.get(f"/api/jobs/{jid}/score.musicxml").text
        notes_before = job["result"]["stats"]["notes"]
        # drop the first sounding note (it carries "Lors") and shorten nothing else
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)
        measure = root.find("part").find("measure")
        first = next(n for n in measure.findall("note") if n.find("rest") is None)
        measure.remove(first)
        edited = ET.tostring(root, encoding="unicode")

        r = client.put(f"/api/jobs/{jid}/score", json={"musicxml": edited, "checked": [0, 3], "revision": 1})
        assert r.status_code == 200, r.text
        saved = r.json()
        assert saved["revision"] == 2 and saved["checked"] == [0, 3]
        assert saved["stats"]["notes"] == notes_before - 1
        assert any(d["kind"] == "underfull" and d["measure"] == 0 for d in saved["check"])
        assert client.get(f"/api/jobs/{jid}").json()["edited_at"]
        lyrics = client.get(f"/api/jobs/{jid}/lyrics").json()
        assert lyrics["verses"] == ["que nous é-tions"] and lyrics["syllables"] == [4]

        # a second browser that still holds revision 1 is refused
        r = client.put(f"/api/jobs/{jid}/score", json={"musicxml": edited, "checked": [], "revision": 1})
        assert r.status_code == 409 and "revision 2" in r.json()["error"]
        # nonsense is refused and nothing changes
        assert client.put(f"/api/jobs/{jid}/score", json={"musicxml": "<nope>", "checked": [], "revision": 2}).status_code == 422
        assert client.put(f"/api/jobs/{jid}/score", json={"musicxml": "<score-partwise><part id='P1'/></score-partwise>", "checked": [], "revision": 2}).status_code == 422
        assert client.get(f"/api/jobs/{jid}/review").json()["revision"] == 2

        r = client.post(f"/api/jobs/{jid}/revert")
        assert r.status_code == 200 and r.json()["revision"] == 3 and r.json()["checked"] == []
        assert r.json()["stats"]["notes"] == notes_before
        assert client.get(f"/api/jobs/{jid}/score.musicxml").text == client.get(f"/api/jobs/{jid}/original.musicxml").text
        # the panel shows what the document has: the fixture score's own words, re-read on revert
        assert client.get(f"/api/jobs/{jid}/lyrics").json()["verses"][0].startswith("Lors-que nous é-tions")
        assert client.get(f"/api/jobs/{jid}").json()["edited_at"] is None
